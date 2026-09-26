---
name: screencast
description: Record, compose, and verify a multi-actor screencast of a Robot Framework-driven browser scenario in this repository — a Cockpit/Plone demo with several personas, an observer, title cards, and a picture-in-picture composite. Trigger when asked to record a scenario/demo video, add a new persona turn to an existing recording, re-cut a take without re-recording, debug a broken take, or fix dead air/a blank frame/a truncated composite in one. Extends the `browser` skill (recording, human-paced input, PIP composition fundamentals) with the reusable engine this repo built on top of it — read `browser` first if you haven't.
compatibility: opencode
metadata:
  workflow: screencast-recording
  audience: developers-and-agents
---

## Before you start

- Load the `browser` skill first if you haven't — this skill assumes you
  already know why a recorded context must open immediately before its flow
  and close immediately after (dead air), why the cursor is injected per
  context, and the PIP composition fundamentals (`tpad=stop_mode=clone`,
  never `overlay=...:shortest=1`). Nothing here repeats that.
- **Never run `playwright install`** — same rule as `browser`. `make shell`
  (`devenv shell`) provides a paired Playwright + Chromium via
  `pkgs.playwright-driver.browsers`.
- Everything here assumes a running stack: `make services` (Operaton,
  Keycloak, Postgres, Mailpit) and `make start` (Plone) in two terminals
  inside `make shell`.

# Three layers, one engine

```
scripts/screencast/            generic engine — no bpmproxy import anywhere
  library.py                     Screencast: the Robot Framework keyword library
  timeline.py                    Timeline (EDL) schema v2: load/validate/save
  schema/timeline.schema.json    the JSON Schema timeline.py validates against
  compose.py                     timeline.json -> one ffmpeg filter_complex
  verify.py                      ffprobe/freezedetect/blackdetect + contact sheet
  driver.py, __main__.py         `playwright-python -m screencast` (see below)

scripts/screencasts/           this project's own layer, built on the engine
  resources/bpmproxy.resource    project keywords (Prepare Fixtures, Open Task, ...)
  resources/bpmproxy_keywords.py  the few keywords needing the raw Playwright page
  review_process.robot           one story per scenario, *** Tasks *** suites
  contact_form.robot
  renovation_project.robot

var/screencasts/<story>/<take>/   everything a take writes (gitignored)
  page@*.webm                      observer + each actor turn's own clip
  timeline.json                    schema v2 — see *The timeline*, below
  output.webm                      playwright-python -m screencast compose's output
  report.json, contact-sheet.png   playwright-python -m screencast verify's output
```

Who writes what:

- **The engine** (`scripts/screencast/`) is generic — no BPMN/Plone/Cockpit
  knowledge anywhere in it. Extend it only for something a *different*
  project's screencast would also need (a new selector convention, a new
  verify check) — see *Extending the engine*, below. It's a candidate for
  extraction into its own repository once two or three stories built on it
  are stable (datakurre/collective.bpmproxy#13); keep it that way.
- **The project resource** (`bpmproxy.resource` + `bpmproxy_keywords.py`) is
  this project's own vocabulary: `Prepare Fixtures`, `Open Task`,
  `Workflow Transition`, `Log In To Cockpit`, and so on, all built from the
  engine's primitives. Add a keyword here when two or more stories would
  otherwise repeat the same sequence of engine primitives.
  `scripts/screencast keywords resources/bpmproxy.resource` lists what
  already exists before you write a new one.
- **A story** (`scripts/screencasts/<name>.robot`) reads like a screenplay:
  one `*** Tasks ***` suite, one task per actor turn (plus a few unrecorded
  setup/observation tasks), built from the resource file's keywords and, for
  anything genuinely one-off, the engine's own primitives directly
  (`Human Click role=button[name="..."]`, `Paste Text`, ...).

# Scaffolding a new story

```
scripts/screencasts/my_scenario.robot
```

```robotframework
*** Settings ***
Documentation     One or two sentences: who does what, and why it's worth recording.
Library           screencast.Screencast    take_dir=${TAKE_DIR}    record=${RECORD}
Resource          resources/bpmproxy.resource

*** Variables ***
${SHOTS_DIR}      ${TAKE_DIR}/screenshots    # promote to docs/ with `make promote-screenshots`
${ASSETS_DIR}     examples/my-scenario

*** Tasks ***
Prepare The Take
    Prepare Fixtures    ${ASSETS_DIR}    any-leftover-demo-content-path

Start Observing In Cockpit
    ${state}=    Log In To Cockpit
    Start Observer    cockpit    ${COCKPIT_URL}/    storage_state=${state}
    Open Process In Cockpit    my-process-key

Persona Does A Thing
    [Setup]    Start Actor Turn    username    eyebrow=My scenario · 1 / N
    ...    title=Persona    subtitle=What they're doing
    Go To    ${BASE_URL}
    Human Click    role=link[name="Add new…"]
    ...
    [Teardown]    End Actor Turn

Wrap Up
    Show Completed Instance In History    my-process-key
    End Observer
```

`${TAKE_DIR}` and `${RECORD}` are supplied by the driver (`python -m
screencast run`), never hard-coded in the story. `${BASE_URL}`/`${COCKPIT_URL}`
come from `bpmproxy.resource`.

Two rules that are easy to get backwards:

- **`Start Observer` first, `End Observer` last, always as the very last
  keyword of the very last task.** Playwright only flushes a context's video
  on `close()` — skip `End Observer` and `ffprobe` sees a near-empty file no
  matter how long the take actually ran.
- **Every `Start Actor Turn` needs a matching `End Actor Turn`**, as
  `[Setup]`/`[Teardown]` on the same Task. This is what makes "one recorded
  context per turn, opened immediately before, closed immediately after"
  automatic — see the `browser` skill for why that matters.

## Selector conventions `Human Click`/`Human Type`/`Wait Until Visible`/etc. understand

Beyond a plain CSS selector or Playwright's own `role=`/`text=` engines:

| Prefix | Resolves via | For |
|---|---|---|
| `label=<text>` | `page.get_by_label()` | A form-js field's own label (most task-form fields) |
| `<frame> >>> <inner>` | `page.frame_locator(frame).locator(inner)` | Content inside a real `<iframe>` (a rich-text body) — **`>>>` alone in `.locator()` does not cross an iframe boundary**, verified: it parses as a plain child combinator and times out |
| `role=X[name="Y"s]` | Playwright's own role engine | Exact-match a name — the attribute is **not** `[exact=true]`, which errors; `s` is a suffix on the value |

`index=` on the same keywords: `0` (default) is `.first`, `-1` is `.last` —
e.g. the most recently created row in a table that only grows.

# The timeline

`timeline.json` (schema v2, `scripts/screencast/schema/timeline.schema.json`)
is the *only* input the composer and verifier need: the observer clip, each
actor clip with its measured offset on the observer's own clock, and a
chronological event list (`turn_start`/`turn_end`, `chapter`, `focus`,
`hold`). The library writes it automatically from real keyword start/end
times — a story never constructs it by hand.

**Re-cutting a take needs no re-recording.** Edit `focus`/`hold` events
directly in `var/screencasts/<story>/<take>/timeline.json`, then:

```sh
playwright-python -m screencast compose var/screencasts/<story>/<take>/
```

Composer defaults, if you're wondering why a take looks a certain way with no
`Focus` calls in the story at all: before any turn, the observer is the only
view (nothing to inset yet); during a turn its actor is main and the
observer is the inset; between turns the main view follows the most recent
`focus` event, default observer. A story only calls `Focus` to override one
of these defaults for a specific stretch.

# The agent debug loop

`playwright-python -m screencast` (the wrapper in devenv.nix sets
`PYTHONPATH=scripts` and provides Playwright; a bare `python` has neither) is a thin CLI over
`scripts/screencast/driver.py`, whose functions are also plain Python if you
want to call them directly:

1. **`check story.robot`** — Robot Framework's own `--dryrun`: every keyword
   call resolves and validates its arguments against what's actually
   imported, with no browser opened. Cheapest first move on anything that
   might be a typo or a missing argument.
2. **`run story.robot [--task NAME] [--no-record] [--take DIR] [--repl-on-failure]`**
   — executes in-process. On a failure, prints a compact summary instead of
   Robot Framework's normal per-keyword trace:
   ```
   FAIL: Story.Broken Turn
     Broken Turn > Human Click[label=Approve]
       TimeoutError: Locator.get_by_label: Timeout 30000ms exceeded.
       Traceback (most recent call last):
         File ".../library.py", line 487, in human_click
       ...
       Failure artifacts: var/screencasts/.../failure-143022-0.png, .txt
   ```
   The path is the keyword call chain (`Task > Setup[args] > Keyword[args]`,
   collapsed to the innermost failure), then the message, then the DEBUG-level
   Python traceback, then any failure-artifact paths the library's own
   listener wrote — a screenshot, `aria_snapshot()`, console log, and URL for
   every page still open when it failed. Read those before touching the
   story again; the answer is usually right there.

   **`--repl-on-failure` is the primary way to debug a broken story.** On
   the first keyword that fails outside any recovery boundary (a `Wait
   Until Keyword Succeeds`/`Run Keyword And ...`/`TRY` block whose retries
   or `EXCEPT` might still swallow it), the run pauses *before* the task's
   own `[Teardown]` runs — so `End Actor Turn` has not yet closed the page
   that failed — prints the same failure summary, and drops into a
   keyword-per-line REPL against that exact live session:
   ```
   FAIL: Story.Broken Turn > Human Click[label=Approve]
     TimeoutError: Locator.get_by_label: Timeout 30000ms exceeded.
   repl-on-failure: one keyword per line against the live session
   (Keyword Name<tab or 4 spaces>arg1<tab or 4 spaces>arg2), Ctrl-D/EOF to
   stop and let teardown run.
   Get Current Page
   OK
   ```
   Try the fix directly against the failing page, Ctrl-D/EOF when done, and
   teardown (and the process) proceeds normally. This is a single `run`
   invocation, one Python process throughout — no separate `probe` call and
   no risk of a dead browser.
3. **`probe KEYWORD args... [--resource FILE]`** — runs one keyword against
   the *live* session a previous `run`/`probe` call left open, **as long as
   it happened in this same Python process**: the session is module-level
   state in `screencast.library`, not per-instance, and it does **not**
   survive a process exit. Two separate `playwright-python -m screencast run` /
   `playwright-python -m screencast probe` shell commands do *not* share a browser --
   each is its own process, so `probe` there always starts a fresh one.
   `--repl` reads one keyword call per line from stdin against the same
   session for as long as the process stays up, which is the practical way
   to get several `probe` calls (or a `run` followed by `probe` calls) to
   share one browser without `--repl-on-failure`: call `driver.run(...)`
   then `driver.probe(...)`/`driver.repl(...)` directly from one Python
   script or interpreter, rather than chaining separate `python -m
   screencast ...` invocations. Useful once a story already passes and you
   want to poke at the resulting session, or from a script that wants
   `run`/`probe` as separate, composable calls rather than one paused `run`.
4. **`keywords resources/bpmproxy.resource`** — lists a resource's keywords
   with their arguments and doc, so you know what already exists before
   writing a new one or guessing an argument name.

Loop: `run --repl-on-failure` → read the summary → try the fix at the paused
REPL against the still-open page → Ctrl-D/EOF → `run --no-record` again once
it's clean → record for real. `--repl-on-failure` runs `Get Current Page`- or
`Go To`-style probes via `BuiltIn().run_keyword()` in the same process and
execution context as the run itself — deliberately not a nested
`TestSuite.run()` (as `probe` uses): Robot Framework's `TestSuite.run()`
wraps its execution in `with LOGGER:`, and `LOGGER` is a process-wide
singleton whose `__exit__` unconditionally resets it, discarding every
listener the *outer*, still-running suite registered — a nested run from
inside a listener callback returns normally with no exception, but every
listener notification for the rest of the outer run silently stops
arriving (verified directly against Robot Framework 7.5 for
collective/collective.bpmproxy#16, which also flagged the `run`→`probe`
gap this closes).

# Take verification

`run` exiting 0 does not mean the *recording* is good — dead air, a blank
frame, and a truncated composite all still exit 0. Always:

```sh
playwright-python -m screencast compose var/screencasts/<story>/<take>/
playwright-python -m screencast verify var/screencasts/<story>/<take>/
```

`verify` writes `report.json` (`{"ok": bool, "findings": [...]}`) and
`contact-sheet.png`, sampled at a rate derived from the take's own measured
duration — never a stale hand-tuned value. Findings, by `check`:

| `check` | Means |
|---|---|
| `stream` | Not exactly one 1920x1080 25fps video stream |
| `duration` | Composed duration doesn't match the timeline's own prediction (observer length + every chapter/hold duration) |
| `dead_air` | More frozen time (`freezedetect`) than the chapter+hold "freeze budget" accounts for — something outside a declared hold produced dead air |
| `blank_frame` | A near-pure-black interval (`blackdetect`, tuned past this project's own dark-navy title cards) — also what missing fonts look like |
| `empty_inset` | A sampled observer frame at some turn's midpoint is a near-uniform color — that turn's inset would be blank |

# Extending the engine

Add to `scripts/screencast/library.py` only when the need is generic — not
"this project's form has a field named X" but "Robot keywords can't express
`get_by_label()`/`frame_locator()`/`.last` in plain selector syntax", the
kind of gap that produced the `label=`/`>>>`/`index=` conventions above.
Mirror an addition with:

- a unit test in `scripts/screencast/tests/test_library.py` against the fake
  Playwright in `tests/fakes.py` (extend the fake if the new keyword touches
  a Playwright API it doesn't cover yet) — no real browser needed;
- if it changes what the composer/verifier read or produce, a
  `scripts/screencast/tests/test_compose.py`/`test_verify.py` case, which
  runs against real ffmpeg on tiny synthetic clips.

See `reference.md` for the timeline schema's full field reference, the
composer's segment-boundary algorithm in more depth, writing a new `verify`
check, and the `Makefile` targets (`make screencast`/`make story-test`).
