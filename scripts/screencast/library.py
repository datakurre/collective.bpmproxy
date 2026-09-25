"""Screencast: a Robot Framework keyword library over sync Playwright.

Session state (Playwright, browser, contexts, pages, the in-progress
Timeline) lives in **module-level globals** (`_SESSION`), not on `self`.
Robot Framework constructs a fresh library instance for every
`TestSuite(...).run()` call, but the module stays imported in one Python
process -- so module-level state is what lets the agent driver (see
screencast.driver) run one keyword after another against a live browser,
REPL-style, across repeated `run()` calls. This is verified by
tests/test_library.py, which calls `.run()` twice against a fake Playwright
and asserts the second run reuses the first run's browser.

The `Browser` Robot Framework library (Node + `rfbrowser init`) is
deliberately not used here: it needs a browser download the `browser` agent
skill's rules forbid re-fetching, and it does not expose the raw
per-context video handling recording depends on.
"""

from datetime import datetime
from pathlib import Path
from robot.api import FatalError
from robot.api import logger
from screencast.cursor import CLICK_SETTLE_MS
from screencast.cursor import CURSOR_SCRIPT
from screencast.cursor import FILL_SETTLE_MS
from screencast.cursor import MOVE_SETTLE_MS
from screencast.cursor import MOVE_STEPS
from screencast.cursor import TYPE_DELAY_MS
from screencast.timeline import Timeline
import os
import time


DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}
DEFAULT_OBSERVE_WAIT = 1.5
DEFAULT_RETURN_TO_OBSERVER_WAIT = 6.0


class _Session:
    """Module-level Playwright/timeline state. See the module docstring."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.playwright = None
        self.browser = None
        self.headless = True
        self.record = True
        self.take_dir = None
        self.viewport = dict(DEFAULT_VIEWPORT)
        self.started = None
        self.observer_name = None
        self.observer_context = None
        self.observer_page = None
        self.current_page = None
        self.current_actor = None
        self._turn_context = None
        self._scratch_context = None
        self._page_before_scratch = None
        self._turn_started_at = None
        self.timeline = None
        self.console_logs = {}
        self.open_pages = []

    def elapsed(self):
        if self.started is None:
            raise FatalError("No observer started yet -- call Start Observer first")
        return time.monotonic() - self.started


_SESSION = _Session()


class _Listener:
    """Writes the in-progress Timeline to disk, and captures failure
    artifacts. Registered automatically via ROBOT_LIBRARY_LISTENER -- story
    authors never import or configure it directly."""

    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self):
        self._pending_dump_paths = None

    def start_test(self, data, result):
        self._pending_dump_paths = None

    def end_keyword(self, data, result):
        # Dump immediately, on the *first* failure in this test, while the
        # failing keyword's own page is still open -- a task's teardown
        # (e.g. End Actor Turn) can close it before end_test below fires,
        # which would leave nothing left to screenshot. A keyword retried
        # inside Wait Until Keyword Succeeds reports FAIL on every failed
        # attempt even when a later attempt succeeds and the task passes
        # overall, so only the first attempt's dump is kept as "pending" --
        # end_test discards it if the task did not, in the end, fail.
        if result.status == "FAIL" and self._pending_dump_paths is None:
            self._pending_dump_paths = _dump_failure_artifacts(result.name)

    def end_test(self, data, result):
        if result.status != "FAIL" and self._pending_dump_paths:
            for path in self._pending_dump_paths:
                path.unlink(missing_ok=True)
        self._pending_dump_paths = None

    def close(self):
        _save_timeline()


def _save_timeline():
    """Write the in-progress timeline to disk now, rather than only once at
    the very end of the run (_Listener.close()) -- a crash mid-take (an
    ffmpeg/browser death, a killed process) would otherwise lose every
    event recorded so far along with whatever video did make it to disk.
    Called after every keyword that mutates the timeline, not just once."""
    if _SESSION.timeline is not None and _SESSION.take_dir is not None:
        path = _SESSION.timeline.save(Path(_SESSION.take_dir) / "timeline.json")
        logger.info(f"Wrote timeline: {path}")


def _dump_failure_artifacts(keyword_name):
    if _SESSION.take_dir is None:
        return []
    take_dir = Path(_SESSION.take_dir)
    take_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S-%f")
    written = []
    for index, page in enumerate(list(_SESSION.open_pages)):
        if page.is_closed():
            continue
        prefix = take_dir / f"failure-{stamp}-{index}"
        try:
            page.screenshot(path=str(prefix.with_suffix(".png")), full_page=True)
            written.append(prefix.with_suffix(".png"))
        except Exception as error:  # noqa: BLE001 -- best-effort diagnostics
            logger.warn(f"Could not screenshot {page.url}: {error}")
        try:
            snapshot = page.locator("body").aria_snapshot()
        except Exception as error:  # noqa: BLE001
            snapshot = f"<aria_snapshot failed: {error}>"
        console = "\n".join(_SESSION.console_logs.get(page, []))
        prefix.with_suffix(".txt").write_text(
            f"keyword: {keyword_name}\n"
            f"url: {page.url}\n\n"
            f"console:\n{console}\n\n"
            f"aria snapshot:\n{snapshot}\n"
        )
        written.append(prefix.with_suffix(".txt"))
        logger.info(f"Failure artifacts: {prefix}.png, {prefix}.txt")
    return written


def _track_console(page):
    _SESSION.console_logs[page] = []
    log = _SESSION.console_logs[page]
    page.on("console", lambda msg: log.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda exc: log.append(f"pageerror: {exc}"))
    page.on(
        "requestfailed",
        lambda req: log.append(f"requestfailed: {req.url} {req.failure}"),
    )


class Screencast:
    """Robot Framework keyword library for recorded, human-paced browser
    scenarios. See scripts/screencasts/resources/*.resource for how a
    project builds its own keywords on top of these."""

    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    ROBOT_LIBRARY_LISTENER = _Listener()

    def __init__(self, take_dir=".", record=True, headless=True, viewport=None):
        _SESSION.take_dir = Path(take_dir)
        _SESSION.record = _as_bool(record)
        _SESSION.headless = _as_bool(headless)
        if viewport:
            _SESSION.viewport = viewport
        if _SESSION.timeline is None:
            _SESSION.take_dir.mkdir(parents=True, exist_ok=True)

    # -- session/browser lifecycle -----------------------------------------

    def start_browser(self):
        """Start Playwright and launch Chromium, unless a previous call (in
        this same process) already did -- the browser instance is reused
        across `TestSuite.run()` calls, which is what makes `probe`/REPL
        debugging possible. Never launches a second browser."""
        if _SESSION.browser is not None:
            return
        try:
            from playwright.sync_api import sync_playwright

            _SESSION.playwright = sync_playwright().start()
            launch_kwargs = {
                "headless": _SESSION.headless,
                "args": ["--no-sandbox", "--disable-dev-shm-usage"],
            }
            # devenv's playwright-driver.browsers (or `playwright install`)
            # already pairs the driver with a matching browser build, so
            # this is normally unset. It exists for environments -- like a
            # plain pip install against a pre-fetched, differently
            # versioned browser cache -- where the two disagree.
            executable_path = os.environ.get("SCREENCAST_CHROMIUM_PATH")
            if executable_path:
                launch_kwargs["executable_path"] = executable_path
            _SESSION.browser = _SESSION.playwright.chromium.launch(**launch_kwargs)
        except Exception as error:
            raise FatalError(f"Could not start the browser: {error}") from error

    def stop_browser(self):
        """Close every open context/page and shut Playwright down. Only the
        top-level driver command calls this at the very end of a process --
        never between `run()` calls, or the session would not survive."""
        for page in list(_SESSION.open_pages):
            if not page.is_closed():
                page.close()
        if _SESSION.browser is not None:
            _SESSION.browser.close()
        if _SESSION.playwright is not None:
            _SESSION.playwright.stop()
        _SESSION.reset()

    # -- observer -------------------------------------------------------------

    def start_observer(self, name, url, storage_state=None):
        """Open the observer recording: the one context that spans the
        whole take, opened first and closed last. Starts the take's clock,
        which every actor clip's `offset` is measured against."""
        self.start_browser()
        if _SESSION.observer_context is not None:
            raise FatalError("Start Observer was already called for this take")
        context_kwargs = {"viewport": _SESSION.viewport}
        if _SESSION.record:
            context_kwargs["record_video_dir"] = str(_SESSION.take_dir)
            context_kwargs["record_video_size"] = _SESSION.viewport
        if storage_state:
            context_kwargs["storage_state"] = storage_state
        try:
            context = _SESSION.browser.new_context(**context_kwargs)
            context.add_init_script(CURSOR_SCRIPT)
            page = context.new_page()
            # Recording begins here, at page creation -- not at the first
            # goto below. Starting the clock any later would make every
            # timeline timestamp (turn offsets, turn_start/end, chapter,
            # focus, hold) land earlier than its true position in the
            # observer video by however long that first navigation took.
            _SESSION.started = time.monotonic()
            _track_console(page)
            _SESSION.open_pages.append(page)
            page.goto(url, wait_until="load")
        except Exception as error:
            raise FatalError(
                f"Could not start the observer at {url}: {error}"
            ) from error
        _SESSION.observer_name = name
        _SESSION.observer_context = context
        _SESSION.observer_page = page
        _SESSION.current_page = page
        video_path = page.video.path() if _SESSION.record else None
        _SESSION.timeline = Timeline.new(
            observer_video=Path(video_path).name if video_path else "",
            observer_name=name,
        )
        _save_timeline()

    def end_observer(self):
        """Close the observer context, flushing its video -- Cockpit (or
        whatever the observer is) "closes last": call this as the story's
        very last keyword. Without it the observer's .webm never finishes
        writing and ffprobe sees a near-empty file, since Playwright only
        flushes a context's video on `close()`. Does not stop the browser
        itself -- that stays alive for a following `probe` call."""
        context = _SESSION.observer_context
        if context is None:
            raise FatalError("No observer -- call Start Observer first")
        context.close()
        _SESSION.observer_context = None
        _SESSION.observer_page = None
        _SESSION.current_page = None

    def observe(self, url=None, wait=DEFAULT_OBSERVE_WAIT, reload=False):
        """Bring the observer to the front, and refresh it. With `url`, this
        is an in-app route change (`page.goto()`), never `page.reload()`:
        a reload re-bootstraps a client-side app and puts a flash in the
        middle of the view, where an in-app route change does not. Only
        pass `reload=True` for the documented exception (see
        docs/AGENTS.md): forcing a refresh past auto-refresh's own polling
        interval right after a transition that can otherwise complete
        between intervals -- an in-app route change is still the default."""
        page = _SESSION.observer_page
        if page is None:
            raise FatalError("No observer -- call Start Observer first")
        page.bring_to_front()
        if reload:
            page.reload(wait_until="load")
        elif url:
            page.goto(url, wait_until="load")
        _SESSION.current_page = page
        page.wait_for_timeout(int(float(wait) * 1000))

    def start_scratch_context(
        self, url=None, storage_state=None, http_credentials=None
    ):
        """Open an unrecorded, throwaway context/page -- e.g. to complete
        an OIDC login flow that would otherwise put a login redirect in a
        recording (see docs/AGENTS.md), or to do privileged setup (deploy
        fixtures, clear old content) via HTTP Basic Auth rather than a
        Manager's own form login. Never touches the timeline: no
        turn_start/turn_end event, and it does not count as an actor turn.
        Pair with `End Scratch Context`."""
        self.start_browser()
        if _SESSION._scratch_context is not None:
            raise FatalError(
                "A scratch context is already open -- call End Scratch Context first"
            )
        context_kwargs = {"viewport": _SESSION.viewport}
        if storage_state:
            context_kwargs["storage_state"] = storage_state
        if http_credentials:
            context_kwargs["http_credentials"] = http_credentials
        context = _SESSION.browser.new_context(**context_kwargs)
        page = context.new_page()
        _track_console(page)
        _SESSION.open_pages.append(page)
        if url:
            page.goto(url, wait_until="load")
        _SESSION._scratch_context = context
        _SESSION._page_before_scratch = _SESSION.current_page
        _SESSION.current_page = page

    def end_scratch_context(self):
        """Close the scratch context and restore whatever page was current
        before `Start Scratch Context` (typically none yet, if this ran
        ahead of `Start Observer` as intended)."""
        context = _SESSION._scratch_context
        if context is None:
            raise FatalError("No scratch context -- call Start Scratch Context first")
        context.close()
        _SESSION._scratch_context = None
        _SESSION.current_page = _SESSION._page_before_scratch
        _SESSION._page_before_scratch = None

    def get_storage_state(self):
        """The current page's context storage_state() (cookies, local
        storage) -- typically assigned to a variable right before `End
        Scratch Context` and passed on to `Start Observer`'s
        `storage_state` argument, to carry an OIDC session into a recorded
        context without recording the login redirect."""
        return self._page().context.storage_state()

    # -- actor turns ------------------------------------------------------

    def start_actor_turn(
        self,
        actor,
        eyebrow=None,
        title=None,
        subtitle=None,
        password=None,
        anonymous=False,
    ):
        """Open a short recorded context for one persona turn. Use as
        `[Setup]` on the Task that plays the turn, with `End Actor Turn` as
        its `[Teardown]` -- the context is created immediately before the
        turn and closed immediately after, so no wall time it is open goes
        undriven and becomes dead air in its clip.

        Authenticates the context via HTTP Basic Auth as `actor`/`password`
        (defaulting `password` to `actor`, this project's convention for its
        demo users) unless `anonymous=True` -- the same
        `extra_http_headers={"Authorization": ...}` the old e2e_*.py scripts
        used, done here via Playwright's own `http_credentials` context
        option instead. Without this, every turn ran as an anonymous
        visitor regardless of `actor`, which most stories cannot get past
        their first permission-gated click.

        With `title`, also records a `chapter` event: a title card the
        composer inserts ahead of this turn's clip. No time is spent
        waiting on it in the browser -- unlike the title overlay the old
        e2e_*.py scripts drew and waited 8s for on every turn.
        """
        if _SESSION.observer_context is None:
            raise FatalError("No observer -- call Start Observer first")
        if _SESSION._turn_context is not None:
            raise FatalError(
                f"Actor turn for {_SESSION.current_actor!r} was not closed "
                "with End Actor Turn before starting a new one"
            )
        offset = _SESSION.elapsed()
        context_kwargs = {"viewport": _SESSION.viewport}
        if _SESSION.record:
            context_kwargs["record_video_dir"] = str(_SESSION.take_dir)
            context_kwargs["record_video_size"] = _SESSION.viewport
        if not _as_bool(anonymous):
            context_kwargs["http_credentials"] = {
                "username": actor,
                "password": password or actor,
            }
        try:
            context = _SESSION.browser.new_context(**context_kwargs)
            context.add_init_script(CURSOR_SCRIPT)
            page = context.new_page()
            _track_console(page)
            _SESSION.open_pages.append(page)
        except Exception as error:
            raise FatalError(f"Could not open a turn for {actor}: {error}") from error
        _SESSION._turn_context = context
        _SESSION._turn_started_at = offset
        _SESSION.current_actor = actor
        _SESSION.current_page = page
        if _SESSION.timeline is not None:
            _SESSION.timeline.add_event(
                {"type": "turn_start", "time": offset, "actor": actor}
            )
            if title:
                _SESSION.timeline.add_event(
                    {
                        "type": "chapter",
                        "time": offset,
                        "eyebrow": eyebrow or "",
                        "title": title,
                        "subtitle": subtitle or "",
                        "duration": 8.0,
                    }
                )
            _save_timeline()

    def end_actor_turn(self, return_to_observer=True):
        """Close the current actor turn's context, flush its video, and
        register it on the timeline. Use as `[Teardown]`."""
        context = _SESSION._turn_context
        if context is None:
            raise FatalError("No actor turn is open -- call Start Actor Turn first")
        page = _SESSION.current_page
        video_path = page.video.path() if _SESSION.record and page.video else None
        context.close()
        end_offset = _SESSION.elapsed()
        actor = _SESSION.current_actor
        if _SESSION.timeline is not None:
            _SESSION.timeline.add_event(
                {"type": "turn_end", "time": end_offset, "actor": actor}
            )
            if video_path:
                _SESSION.timeline.add_actor_clip(
                    actor,
                    Path(video_path).name,
                    offset=_SESSION._turn_started_at,
                    duration=round(end_offset - _SESSION._turn_started_at, 3),
                )
            _save_timeline()
        _SESSION._turn_context = None
        _SESSION._turn_started_at = None
        _SESSION.current_actor = None
        if return_to_observer and _SESSION.observer_page is not None:
            # Longer than observe()'s own default: this is the cut back to
            # the wide/observer shot after a turn ends, not a brief in-app
            # navigation settle -- give the viewer time to register it.
            self.observe(wait=DEFAULT_RETURN_TO_OBSERVER_WAIT)

    # -- timeline-only events, no browser wait -----------------------------

    def chapter(self, eyebrow, title, subtitle, duration=8.0):
        """Record a title-card event at the current moment, without opening
        an actor turn. `duration` is how long the composer holds the card,
        not time spent waiting here."""
        if _SESSION.timeline is None:
            raise FatalError("No timeline -- call Start Observer first")
        _SESSION.timeline.add_event(
            {
                "type": "chapter",
                "time": _SESSION.elapsed(),
                "eyebrow": eyebrow,
                "title": title,
                "subtitle": subtitle,
                "duration": float(duration),
            }
        )
        _save_timeline()

    def focus(self, view, scale=0.4, margin=24, border=3):
        """Record which recording ('actor' or 'observer') is the composer's
        main view from this point on; the other becomes the inset."""
        if view not in ("actor", "observer"):
            raise FatalError(f"Focus view must be 'actor' or 'observer', got {view!r}")
        if _SESSION.timeline is None:
            raise FatalError("No timeline -- call Start Observer first")
        _SESSION.timeline.add_event(
            {
                "type": "focus",
                "time": _SESSION.elapsed(),
                "view": view,
                "scale": float(scale),
                "margin": int(margin),
                "border": int(border),
            }
        )
        _save_timeline()

    def hold(self, duration, view="observer"):
        """Record extra observer (or actor) time to hold at the current
        moment, e.g. after a submit, or over the final History view."""
        if _SESSION.timeline is None:
            raise FatalError("No timeline -- call Start Observer first")
        _SESSION.timeline.add_event(
            {
                "type": "hold",
                "time": _SESSION.elapsed(),
                "duration": float(duration),
                "view": view,
            }
        )
        _save_timeline()

    # -- human-paced input, against the current page -----------------------

    def _locator(self, selector, index=0):
        """Resolve `selector` against the current page, at `index` (0 is
        the first match, -1 the last) -- e.g. the most recently created row
        in a table that only ever grows, which project keywords need and
        Playwright's own `.first`/`.last` express.

        A `label=<text>` selector resolves via `page.get_by_label()`
        instead of `page.locator()`: form-js (and most form libraries)
        associate an input with its visible label rather than an
        accessible role+name, and `get_by_label` has no plain-string
        equivalent in Playwright's own locator engine syntax (unlike
        `role=`, which `.locator()` already understands natively).

        A `<frame selector> >>> <inner selector>` selector resolves via
        `page.frame_locator()` -- `>>>` looks like Playwright's own
        shadow-DOM-piercing combinator but does *not* cross an `<iframe>`
        boundary (verified: it parses as a plain child combinator against
        the iframe *element*, which times out), so real `<iframe>` content
        -- a rich-text editor's body, for instance -- needs this instead."""
        if selector.startswith("label="):
            locator = self._page().get_by_label(selector[len("label=") :])
        elif " >>> " in selector:
            frame_selector, _, inner_selector = selector.partition(" >>> ")
            locator = self._page().frame_locator(frame_selector).locator(inner_selector)
        else:
            locator = self._page().locator(selector)
        index = int(index)
        if index == 0:
            return locator.first
        if index == -1:
            return locator.last
        return locator.nth(index)

    def human_move(self, selector, index=0):
        page = self._page()
        locator = self._locator(selector, index)
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        if box is None:
            raise AssertionError(f"{selector!r} has no bounding box to move to")
        page.mouse.move(
            box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=MOVE_STEPS
        )
        page.wait_for_timeout(MOVE_SETTLE_MS)

    def human_click(self, selector, index=0):
        self.human_move(selector, index)
        self._locator(selector, index).click()
        self._page().wait_for_timeout(CLICK_SETTLE_MS)

    def human_type(self, selector, text, delay=TYPE_DELAY_MS, index=0):
        self.human_click(selector, index)
        locator = self._locator(selector, index)
        locator.fill("")
        locator.press_sequentially(text, delay=int(delay))
        self._page().wait_for_timeout(FILL_SETTLE_MS)

    def paste_text(self, selector, text, index=0):
        """Fill a long body of text in one shot instead of Human Type's
        per-keystroke pacing -- typing hundreds of characters at 75ms each
        would stretch a turn's recording by tens of seconds for no benefit."""
        self.human_click(selector, index)
        self._locator(selector, index).fill(text)
        self._page().wait_for_timeout(FILL_SETTLE_MS)

    def wait_until_visible(self, selector, timeout=10000, index=0):
        self._locator(selector, index).wait_for(state="visible", timeout=int(timeout))

    def count_matches(self, selector):
        """The number of elements matching `selector` right now -- for a
        project keyword branching on whether something is present (an IF,
        not a wait), e.g. Cockpit rendering one of two possible layouts."""
        return self._page().locator(selector).count()

    def get_attribute(self, selector, name, index=0):
        return self._locator(selector, index).get_attribute(name)

    def select_option(self, selector, value, index=0):
        """Select `value` on a `<select>` -- there is no human-paced
        equivalent for a native select dropdown the way there is for a
        click or a typed field, so this does not move the mouse first."""
        self._locator(selector, index).select_option(value)
        self._page().wait_for_timeout(FILL_SETTLE_MS)

    def check(self, selector, index=0):
        self.human_move(selector, index)
        self._locator(selector, index).check()
        self._page().wait_for_timeout(CLICK_SETTLE_MS)

    def uncheck(self, selector, index=0):
        self.human_move(selector, index)
        self._locator(selector, index).uncheck()
        self._page().wait_for_timeout(CLICK_SETTLE_MS)

    def go_to(self, url):
        """Navigate the current page. A thin wrapper over `page.goto()` --
        project keywords needing anything more specific (auth, polling
        redirects) build on `Get Current Page` instead."""
        self._page().goto(url, wait_until="load")

    def get_current_page(self):
        """Return the live Playwright Page for the current context, for
        project keywords that need the raw Playwright API (e.g. `.request`
        for a JSON fetch, or `.keyboard`)."""
        return self._page()

    def take_screenshot(self, path, full_page=True):
        self._page().screenshot(path=str(path), full_page=_as_bool(full_page))

    def _page(self):
        if _SESSION.current_page is None:
            raise FatalError("No open page -- call Start Observer first")
        return _SESSION.current_page


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("false", "no", "0", "")
