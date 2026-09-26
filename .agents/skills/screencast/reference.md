# screencast reference

Deeper detail for `SKILL.md`'s summaries. Read that first.

## Timeline schema v2, field by field

`scripts/screencast/schema/timeline.schema.json` is the source of truth;
`scripts/screencast/timeline.py`'s `Timeline` class validates against it on
every load/construction. A document:

```json
{
  "version": 2,
  "observer": {"name": "cockpit", "video": "page@abc123.webm"},
  "actors": [
    {"actor": "author", "video": "page@def456.webm", "offset": 12.34, "duration": 45.6}
  ],
  "events": [
    {"type": "turn_start", "time": 12.34, "actor": "author"},
    {"type": "chapter", "time": 12.34, "eyebrow": "Story · 1/5", "title": "Author",
     "subtitle": "Drafting", "duration": 8.0},
    {"type": "focus", "time": 20.0, "view": "observer", "scale": 0.4, "margin": 24, "border": 3},
    {"type": "turn_end", "time": 58.0, "actor": "author"},
    {"type": "hold", "time": 58.0, "duration": 12.0, "view": "observer"}
  ]
}
```

- **`version`** — the composer/verifier refuse anything but `2`, loudly.
- **`observer.video`** — the one recording spanning the whole take. All
  other times (`actors[].offset`, every event's `time`) are seconds on
  *this* clip's own clock.
- **`actors[]`** — one entry per recorded turn. `offset` is when the actor's
  context was *created* (`time.monotonic() - started`, captured by `Start
  Actor Turn`), not when the turn's first click happened. `duration` is
  written by `End Actor Turn` from the real elapsed time; the composer
  re-measures it with `ffprobe` anyway and does not trust a stale value.
- **`events[].time`** — always on the observer's clock, same units as
  `actors[].offset`.
- **`chapter`** — a title card. `duration` is how long the composer holds
  it; no browser time is spent waiting for it (unlike the old system's 8s
  `show_actor_slide()`).
- **`focus`** — which recording (`"actor"` or `"observer"`) is main from
  this point on. `scale`/`margin`/`border` (defaults 0.4/24/3) describe the
  *other* one's inset.
- **`hold`** — freeze the current frame(s) for `duration` extra seconds.
  `view` (default `"observer"`) is which side is "current" for freezing
  purposes when a hold coincides with a turn boundary.

`screencast.timeline.OVERLAP_TOLERANCE` (1.5s) is not a schema field — it's
the composer's tolerance for encoder-startup jitter between a
`time.monotonic()` offset and ffprobe's measured duration, so two
back-to-back turns with near-zero real gap don't spuriously fail the
overlap check. An overlap *larger* than that is a real bug: two actor
contexts were open at once, which `Start Actor Turn`/`End Actor Turn`
should never allow.

## The composer's segment algorithm

`scripts/screencast/compose.py`'s module docstring has the policy; this is
the mechanism.

1. Collect every turn's `(actor, start, end)` window from `turn_start`/
   `turn_end` events, and every `focus`/`chapter`/`hold` event's time.
2. Build a sorted list of **boundaries**: `0`, the observer's total
   duration, every turn start/end, every event time (all clamped to
   `[0, observer_duration]` — a `time.monotonic()` timestamp can land a few
   milliseconds past ffprobe's measured length from encoder flush latency;
   clamping instead of dropping is what stops a trailing hold from silently
   never rendering).
3. Walk consecutive boundary pairs `(start, end)`. For each: emit any
   chapter/hold whose event time equals `start` (a title card or freeze
   inserted *before* this segment — pure insertion, consumes no recorded
   time from either source), then resolve `(view, inset_actor, scale,
   margin, border)` at the segment's midpoint via `_view_at()` (the default
   policy from `SKILL.md`), and build the segment: a `trim`+`scale` of the
   main source, an inset built from the other source (live footage if that
   actor's turn is still technically open, otherwise their last frame
   frozen with `tpad=stop_mode=clone`), composited with `overlay`.
4. A **trailing** chapter/hold whose time equals the very last boundary
   never becomes any segment's `start` (nothing follows it) — emitted once
   more, explicitly, after the loop.
5. Every source slice is normalized to `scale=1920:1080` before concat:
   nothing guarantees a source clip was recorded at exactly that size (a
   differently configured viewport, or in `tests/test_compose.py`, a
   synthetic stand-in clip), and `concat` requires uniform frame size.
6. All segments concatenate, in order, into `[out]`.

Title cards are rendered once per distinct `(eyebrow, title, subtitle,
duration)` and cached in `<take_dir>/titles/`; composing the same timeline
twice does not re-render them.

## Writing a new `verify` check

`scripts/screencast/verify.py`'s `verify()` returns
`{"ok": bool, "findings": [...], ...}`; each finding is
`{"check": str, "severity": "error", "message": str}`. To add one:

1. Write the detection as its own function, real ffmpeg/ffprobe underneath
   (see `detect_freezes()`/`detect_black_intervals()`/`frame_luma_range()`
   for the existing patterns — a filter run with `-f null -`, parsed from
   stderr, or a raw-pixel pipe for a single-frame sample).
2. Call it from `verify()`, append a finding dict on a problem.
3. Test it in `tests/test_verify.py` against a real synthetic clip
   (`make_clip`/`make_animated_clip`) that should and shouldn't trigger it —
   see `test_detect_black_intervals_ignores_a_dark_but_not_black_theme` for
   why a "should not trigger" case matters as much as a "should".

Keep new checks calibrated against this project's own dark-navy title cards
and Cockpit's own UI, not generic defaults — `blackdetect`'s default
`pix_th` (10% luma) flags navy `#0f172a` as black, which is exactly why
`verify.py` tightens it to `0.02`.

## Makefile targets

```sh
make screencast [STORY=review_process]   # run, compose, verify; fixed take dir
make story-test [STORY=...]              # --no-record, fast, for the fix loop
make promote-screenshots STORY=...       # copy a take's screenshots into docs/
make demo-stack STORY=...                # services + site + demo profile + Plone + worker
make demo-stack-down                     # stop Plone and the worker again
```

`screencast` and `story-test` need the stack up: `make demo-stack STORY=...` does that in one go (or `make services` + `make start`, see the scenario docs). Never run a story against a stack you did not start: its first task clears the engine's deployments. `STORY` defaults to
`review_process`; the take directory is `var/screencasts/<story>/latest`
(or `latest-test`) rather than timestamped, so re-running overwrites in
place instead of accumulating takes — use `playwright-python -m screencast run
--take DIR` directly when you want to keep more than one.

## What's still manual

Full-content verification against a live Plone/Operaton/Keycloak stack
(`make services`, `make start`) — CI only covers the engine itself (schema,
library against a fake Playwright, driver, composer/verifier against real
ffmpeg on synthetic clips), never a real story's content, since CI has no
devenv stack. Run `make screencast` (or `story-test` while iterating) by
hand after any change that could affect a story's actual selectors or flow.
