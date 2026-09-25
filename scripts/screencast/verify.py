"""`python -m screencast verify DIR/` -- automated take verification,
replacing the manual "Verifying a take" steps duplicated across each
docs/*-scenario.md.

Checks:

- **ffprobe**: exactly one 1920x1080, 25fps video stream on the composed
  output, and its duration matches what the timeline predicts (the
  observer's own measured length plus every chapter/hold duration, which
  is exactly what the composer (screencast.compose) inserts), within
  DURATION_TOLERANCE.
- **Contact sheet**: a `rows x cols` tile built at a sampling rate derived
  from the *real* measured duration (`fps >= rows*cols / duration`), so a
  longer take than the last one still gets full coverage instead of a
  stale, undersized rate.
- **Dead air** (`severity: "warning"`, does not fail `ok`): `freezedetect`
  finds frozen runs; their total is compared against the "expected freeze
  budget" (the sum of chapter and hold durations -- title cards and holds
  are the only segments the composer ever freezes on purpose, plus a
  "recorded" hold's own real elapsed wait, e.g. the return-to-observer
  pause after a turn -- see library.py's end_actor_turn and
  predicted_duration()'s docstring). More frozen time than that budget
  plus DEAD_AIR_TOLERANCE is reported as a finding, but only a warning:
  on a real recording, `freezedetect`'s whole-frame pixel comparison
  can't see cursor-only motion at 1920x1080, so ordinary human-paced
  turns routinely false-positive as "frozen". Judging this from the
  timeline instead of pixels is tracked in
  datakurre/collective.bpmproxy#15; until then this check is advisory.
- **Blank frames**: `blackdetect` on the composed output, tuned to
  near-pure black (`pix_th=0.02`) rather than the default's
  dark-theme-triggering 10% luma threshold, since this project's own
  title cards are a dark navy that would otherwise false-positive on
  every take -- plus a uniform-color sample (the same technique as
  "Empty insets", below, applied to each actor clip's own opening moment
  instead of the observer's) since a blank turn-opening frame is just as
  often a plain white Plone loading page (or any other flat color a
  missing font renders as) as it is black, and blackdetect alone would
  never see it.
- **Empty insets**: for each actor turn, one raw grayscale sample from the
  observer's own footage at the turn's real-time midpoint (the frame that
  becomes that turn's inset). A near-zero luma range means a blank/dead
  inset -- also what missing fonts look like, per the browser skill.

Returns a JSON-serializable report (`{"ok": bool, "findings": [...],
...}`); `main()`/the CLI also write it to `report.json` and the contact
sheet to `contact-sheet.png` in the take directory.
"""

from pathlib import Path
from screencast.compose import ffprobe_duration
from screencast.timeline import Timeline
import json
import re
import subprocess


DURATION_TOLERANCE = 1.5  # seconds; see screencast.timeline.OVERLAP_TOLERANCE
DEAD_AIR_TOLERANCE = 2.0  # seconds of unaccounted freeze before it's a finding
BLANK_LUMA_RANGE = 4  # max:min luma spread below this counts as "uniform"
# Sampling exactly at a turn's start boundary risks a compressed keyframe
# seek landing just before the composer's hard cut there and reading the
# previous segment's content instead -- a small offset into the turn avoids
# that while still sampling what the turn visibly opens on.
TURN_OPEN_SAMPLE_OFFSET = 0.15
EXPECTED_SIZE = (1920, 1080)
EXPECTED_FPS = 25.0


class VerifyError(ValueError):
    pass


def ffprobe_streams(video):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-of",
            "json",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)["streams"]


def frame_luma_range(video, at, width=64, height=36):
    """The luma (max - min) of one downscaled frame sampled at `at`
    seconds -- near zero means the frame is a uniform color."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{max(0.0, at):.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:{height}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    data = result.stdout
    if not data:
        raise VerifyError(f"Could not sample a frame at {at:.2f}s from {video}")
    return max(data) - min(data)


_FREEZE_START_RE = re.compile(r"freeze_start:\s*([\d.]+)")
_FREEZE_DURATION_RE = re.compile(r"freeze_duration:\s*([\d.]+)")
_BLACK_RE = re.compile(
    r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)\s+black_duration:\s*([\d.]+)"
)


def detect_freezes(video, noise_db=-30, min_duration=1.0):
    """Durations of every frozen run `freezedetect` finds. A freeze that is
    still ongoing when the stream ends never gets a matching
    freeze_duration/freeze_end line from ffmpeg -- only freeze_start -- so
    that trailing case is computed from the clip's own measured duration
    instead of silently dropped."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            str(video),
            "-vf",
            f"freezedetect=n={noise_db}dB:d={min_duration}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    starts = [float(m.group(1)) for m in _FREEZE_START_RE.finditer(result.stderr)]
    durations = [float(m.group(1)) for m in _FREEZE_DURATION_RE.finditer(result.stderr)]
    if len(starts) > len(durations):
        durations.append(ffprobe_duration(video) - starts[-1])
    return durations


def detect_black_intervals(video, min_duration=0.5, pic_th=0.98, pix_th=0.02):
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            str(video),
            "-vf",
            f"blackdetect=d={min_duration}:pic_th={pic_th}:pix_th={pix_th}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    return [
        {
            "start": float(m.group(1)),
            "end": float(m.group(2)),
            "duration": float(m.group(3)),
        }
        for m in _BLACK_RE.finditer(result.stderr)
    ]


def make_contact_sheet(video, output, rows=6, cols=5, duration=None):
    duration = duration or ffprobe_duration(video)
    fps = max((rows * cols) / max(duration, 0.1), 0.5)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            f"fps={fps},scale=320:-1,tile={cols}x{rows}",
            "-frames:v",
            "1",
            str(output),
        ],
        check=True,
    )
    return Path(output)


def predicted_duration(timeline, observer_duration):
    """What the composer's output duration should be: the observer's own
    measured length, plus every chapter/hold duration it inserts (see
    screencast.compose's module docstring -- inserted segments never
    consume recorded footage, they only add to the output). A "recorded"
    hold (e.g. the return-to-observer wait, see library.py's
    end_actor_turn) is excluded: the composer never inserts a synthetic
    freeze for it, since that time is already real, un-trimmed observer
    footage -- counting it here would overshoot the actual output length."""
    inserted = sum(e["duration"] for e in timeline.events_of("chapter"))
    inserted += sum(
        e["duration"] for e in timeline.events_of("hold") if not e.get("recorded")
    )
    return observer_duration + inserted


def verify(take_dir, output_video=None, contact_sheet=None, rows=6, cols=5):
    take_dir = Path(take_dir)
    timeline = Timeline.load(take_dir / "timeline.json")
    observer_duration = ffprobe_duration(take_dir / timeline.observer["video"])
    expected_duration = predicted_duration(timeline, observer_duration)

    output_video = Path(output_video) if output_video else take_dir / "output.webm"
    if not output_video.exists():
        raise VerifyError(f"No composed output at {output_video}")

    findings = []

    streams = ffprobe_streams(output_video)
    if len(streams) != 1:
        findings.append(
            {
                "check": "stream",
                "severity": "error",
                "message": f"Expected exactly one video stream, found {len(streams)}",
            }
        )
    else:
        stream = streams[0]
        size = (stream.get("width"), stream.get("height"))
        fps = _parse_rate(stream.get("r_frame_rate"))
        if size != EXPECTED_SIZE:
            findings.append(
                {
                    "check": "stream",
                    "severity": "error",
                    "message": f"Expected {EXPECTED_SIZE[0]}x{EXPECTED_SIZE[1]}, got {size[0]}x{size[1]}",
                }
            )
        if fps is None or abs(fps - EXPECTED_FPS) > 0.1:
            findings.append(
                {
                    "check": "stream",
                    "severity": "error",
                    "message": f"Expected {EXPECTED_FPS}fps, got {fps}",
                }
            )

    actual_duration = ffprobe_duration(output_video)
    if abs(actual_duration - expected_duration) > DURATION_TOLERANCE:
        findings.append(
            {
                "check": "duration",
                "severity": "error",
                "message": (
                    f"Expected ~{expected_duration:.2f}s (observer "
                    f"{observer_duration:.2f}s + inserted segments), got "
                    f"{actual_duration:.2f}s"
                ),
            }
        )

    freeze_budget = sum(e["duration"] for e in timeline.events_of("chapter"))
    freeze_budget += sum(e["duration"] for e in timeline.events_of("hold"))
    total_freeze = sum(detect_freezes(output_video))
    if total_freeze - freeze_budget > DEAD_AIR_TOLERANCE:
        findings.append(
            {
                "check": "dead_air",
                # Not "error": on a real recording, freezedetect compares
                # mean pixel difference across the whole composited frame,
                # and a cursor move/click ring is far below any usable
                # threshold at 1920x1080 -- ordinary human-paced turns
                # (hover, read, click) false-positive as "frozen" even
                # though nothing is wrong. Downgraded to a warning (still
                # reported, but does not fail ok/the exit code) until this
                # is judged from the timeline instead of pixels -- see
                # datakurre/collective.bpmproxy#15.
                "severity": "warning",
                "message": (
                    f"{total_freeze:.2f}s of frozen video, but only "
                    f"{freeze_budget:.2f}s is accounted for by chapter/hold "
                    "events -- something outside a declared hold produced "
                    "dead air (or this is cursor-only motion freezedetect "
                    "can't see -- see datakurre/collective.bpmproxy#15)"
                ),
            }
        )

    black_intervals = detect_black_intervals(output_video)
    for interval in black_intervals:
        findings.append(
            {
                "check": "blank_frame",
                "severity": "error",
                "message": (
                    f"Near-black video from {interval['start']:.2f}s to "
                    f"{interval['end']:.2f}s ({interval['duration']:.2f}s) -- "
                    "also what missing fonts look like"
                ),
            }
        )

    # blackdetect only catches near-pure-black -- a turn's own opening frame
    # can just as easily be a plain white Plone loading page, or any other
    # flat color a missing font renders as. Sample each actor clip's own
    # opening moment directly, the same uniform-color technique empty_inset
    # below already uses on the observer's footage: the composed output
    # itself is a poor sampling target here, since every turn's segment
    # overlays the observer as a bordered inset, and that border alone
    # keeps the composited frame's luma range well above BLANK_LUMA_RANGE
    # regardless of whether the actor's own content is blank.
    for clip in timeline.actors:
        clip_path = take_dir / clip["video"]
        clip_duration = ffprobe_duration(clip_path)
        at = min(TURN_OPEN_SAMPLE_OFFSET, max(0.0, clip_duration - 0.05))
        luma_range = frame_luma_range(clip_path, at)
        if luma_range < BLANK_LUMA_RANGE:
            findings.append(
                {
                    "check": "blank_frame",
                    "severity": "error",
                    "message": (
                        f"{clip['actor']!r}'s turn ({clip['video']}) opens "
                        f"at {at:.2f}s on a near-uniform color frame (luma "
                        f"range {luma_range}) -- also what missing fonts "
                        "look like"
                    ),
                }
            )

    for start_event in timeline.events_of("turn_start"):
        end_event = next(
            (
                e
                for e in timeline.events_of("turn_end")
                if e["actor"] == start_event["actor"]
            ),
            None,
        )
        if end_event is None:
            continue
        midpoint = min(
            (start_event["time"] + end_event["time"]) / 2, observer_duration - 0.05
        )
        if midpoint < 0:
            continue
        luma_range = frame_luma_range(take_dir / timeline.observer["video"], midpoint)
        if luma_range < BLANK_LUMA_RANGE:
            findings.append(
                {
                    "check": "empty_inset",
                    "severity": "error",
                    "message": (
                        f"Observer frame at {midpoint:.2f}s (the inset during "
                        f"{start_event['actor']!r}'s turn) is a near-uniform "
                        f"color (luma range {luma_range})"
                    ),
                }
            )

    sheet_path = (
        Path(contact_sheet) if contact_sheet else take_dir / "contact-sheet.png"
    )
    make_contact_sheet(
        output_video, sheet_path, rows=rows, cols=cols, duration=actual_duration
    )

    return {
        "ok": not any(f["severity"] == "error" for f in findings),
        "observer_duration": observer_duration,
        "expected_duration": expected_duration,
        "actual_duration": actual_duration,
        "freeze_budget": freeze_budget,
        "total_freeze": total_freeze,
        "contact_sheet": str(sheet_path),
        "findings": findings,
    }


def _parse_rate(value):
    if not value:
        return None
    if "/" in value:
        num, _, den = value.partition("/")
        den = float(den) or 1.0
        return float(num) / den
    return float(value)
