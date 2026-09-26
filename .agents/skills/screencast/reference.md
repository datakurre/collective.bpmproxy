# screencast reference

Deeper detail for `SKILL.md`'s summaries. Read that first.

## Timeline schema v2, field by field

`src/screencast/schema/timeline.schema.json` is the source of truth;
`src/screencast/timeline.py`'s `Timeline` class validates against it on
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
    {"type": "hold", "time": 58.0, "duration": 12.0, "view": "observer"},
    {"type": "caption", "time": 30.0, "text": "Alice submits the form", "duration": 4.0},
    {"type": "wait", "time": 40.0, "duration": 2.5, "keyword": "Wait For Order"}
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
  it; no browser time is spent waiting for it.
- **`focus`** — which recording (`"actor"` or `"observer"`) is main from
  this point on. `scale`/`margin`/`border` (defaults 0.4/24/3) describe the
  *other* one's inset.
- **`hold`** — freeze the current frame(s) for `duration` extra seconds.
  `view` (default `"observer"`) is which side is "current" for freezing
  purposes when a hold coincides with a turn boundary. A hold with
  `"recorded": true` is real elapsed recording time the library itself
  noted (the wait after a turn ends, while the observer is brought back to
  the front): the composer inserts no synthetic freeze for it.
- **`caption`** — a subtitle cue. The composer maps `time` (observer clock) to
  the composed output's clock, adding every title card and hold inserted at
  or before it, and writes `output.vtt` next to `output.webm`.
- **`wait`** — recorded by the library's listener around the outermost
  waiting keyword (`Sleep`, `Wait Until Keyword Succeeds`, the engine's own
  waits, or a keyword tagged `screencast:wait`), for waits of 0.25 s or more.
  The composer ignores it; `verify`'s `dead_air` check judges it.

`screencast.timeline.OVERLAP_TOLERANCE` (1.5s) is not a schema field — it's
the composer's tolerance for encoder-startup jitter between a
`time.monotonic()` offset and ffprobe's measured duration, so two
back-to-back turns with near-zero real gap don't spuriously fail the
overlap check. An overlap *larger* than that is a real bug: two actor
contexts were open at once, which `Start Actor Turn`/`End Actor Turn`
should never allow.

## The composer's segment algorithm

`src/screencast/compose.py`'s module docstring has the policy; this is
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

`src/screencast/verify.py`'s `verify()` returns
`{"ok": bool, "findings": [...], ...}`; each finding is
`{"check": str, "severity": "error", "message": str}`. To add one:

1. Write the detection as its own function, real ffmpeg/ffprobe underneath
   (see `detect_black_intervals()`/`frame_luma_range()`
   for the existing patterns — a filter run with `-f null -`, parsed from
   stderr, or a raw-pixel pipe for a single-frame sample).
2. Call it from `verify()`, append a finding dict on a problem.
3. Test it in `tests/test_verify.py` against a real synthetic clip
   (`make_clip`/`make_animated_clip`) that should and shouldn't trigger it —
   see `test_detect_black_intervals_ignores_a_dark_but_not_black_theme` for
   why a "should not trigger" case matters as much as a "should".

Calibrate new checks against real footage, not generic defaults —
`blackdetect`'s default `pix_th` (10% luma) flags the dark-navy title cards
(`#0f172a`) as black, which is exactly why `verify.py` tightens it to `0.02`.
A check is only worth having if it can tell a healthy take from a broken one
on real recordings: a whole-frame freeze check could not (a healthy take's
longest frozen stretch was longer than that of a take with a deliberate 12 s
sleep), and was removed in favour of judging dead air from the timeline.

## What CI covers

The engine's own tests (schema, the library against a fake Playwright, the
driver, the composer and verifier against real ffmpeg on synthetic clips) run
on Python 3.10 and 3.13 with the oldest supported and the latest Robot
Framework. They never run a real story's content: that needs the application
it records. After any change that could affect a story's selectors or flow,
run the story (`screencast run`, or with `--no-record` while iterating) against
your application by hand, then `compose` and `verify` it.
