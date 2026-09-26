"""screencast.verify tests against real ffmpeg output on tiny synthetic
clips -- skipped when ffmpeg/ffprobe aren't on PATH. Also manually verified
end-to-end against the real toy take composed for #4/#5/#6 (see the #7
commit message)."""

from screencast.compose import compose
from screencast.timeline import Timeline
from screencast.verify import detect_black_intervals
from screencast.verify import detect_freezes
from screencast.verify import frame_luma_range
from screencast.verify import parse_vtt_cue_times
from screencast.verify import predicted_duration
from screencast.verify import verify
import pytest
import shutil
import subprocess


requires_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="ffmpeg/ffprobe not on PATH",
)


def make_clip(path, duration, color="blue", size="320x180"):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={size}:d={duration}:r=25",
            "-c:v",
            "libvpx",
            "-deadline",
            "realtime",
            "-cpu-used",
            "16",
            str(path),
        ],
        check=True,
    )


@requires_ffmpeg
def test_frame_luma_range_is_near_zero_for_a_solid_color(tmp_path):
    clip = tmp_path / "solid.webm"
    make_clip(clip, 1.0, color="black")
    assert frame_luma_range(clip, 0.5) < 4


@requires_ffmpeg
def test_frame_luma_range_is_large_for_content(tmp_path):
    clip = tmp_path / "checkers.webm"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:duration=1:rate=25",
            str(clip),
        ],
        check=True,
    )
    assert frame_luma_range(clip, 0.5) > 20


@requires_ffmpeg
def test_detect_freezes_finds_a_frozen_run(tmp_path):
    clip = tmp_path / "frozen.webm"
    make_clip(clip, 3.0, color="red")
    freezes = detect_freezes(clip, min_duration=1.0)
    assert freezes and freezes[0] > 1.0


@requires_ffmpeg
def test_detect_black_intervals_finds_near_pure_black(tmp_path):
    clip = tmp_path / "black.webm"
    make_clip(clip, 2.0, color="black")
    intervals = detect_black_intervals(clip, min_duration=0.5)
    assert intervals
    assert intervals[0]["duration"] > 0.5


@requires_ffmpeg
def test_detect_black_intervals_ignores_a_dark_but_not_black_theme(tmp_path):
    """The project's own title cards are a dark navy (#0f172a) -- the
    default blackdetect threshold would false-positive on every take."""
    clip = tmp_path / "navy.webm"
    make_clip(clip, 2.0, color="0x0f172a")
    intervals = detect_black_intervals(clip, min_duration=0.5)
    assert intervals == []


def make_animated_clip(path, duration, color="blue"):
    """Per-frame random noise over a solid color, standing in for real
    recorded footage (which always has at least cursor movement) -- unlike
    make_clip()'s flat color (or, it turns out, ffmpeg's own `testsrc`,
    whose motion is too gradual to clear freezedetect's noise floor over a
    1s window), this reliably does not itself look like dead air or a
    blank frame to freezedetect/frame_luma_range. `-crf 20 -b:v 4M` keeps
    enough bitrate that the noise survives frame to frame -- a more
    aggressively compressed encode converges consecutive frames to the
    same predicted content despite the spatial noise, which reads as
    frozen. `-cpu-used 5` keeps this fast regardless (~0.4s/clip here vs.
    ~30s at the encoder's default effort)."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=320x180:d={duration}:r=25",
            "-vf",
            "noise=alls=40:allf=t+u",
            "-c:v",
            "libvpx",
            "-deadline",
            "good",
            "-cpu-used",
            "5",
            "-crf",
            "20",
            "-b:v",
            "4M",
            str(path),
        ],
        check=True,
    )


def make_freeze_then_move_clip(path, freeze_at, freeze_duration, total_duration):
    """Animated, then genuinely static for `freeze_duration`, then animated
    again -- simulates an observer that really does hold still for a real
    elapsed wait (e.g. the return-to-observer pause after a turn), as
    opposed to make_animated_clip()'s constant motion throughout."""
    tail = max(total_duration - freeze_at - freeze_duration, 0.1)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s=320x180:d={freeze_at}:r=25",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s=320x180:d={freeze_duration}:r=25",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s=320x180:d={tail}:r=25",
            "-filter_complex",
            "[0:v]noise=alls=40:allf=t+u[a];[2:v]noise=alls=40:allf=t+u[c];"
            "[a][1:v][c]concat=n=3:v=1:a=0[out]",
            "-map",
            "[out]",
            "-c:v",
            "libvpx",
            "-deadline",
            "good",
            "-cpu-used",
            "5",
            "-crf",
            "20",
            "-b:v",
            "4M",
            str(path),
        ],
        check=True,
    )


def make_take(take_dir, observer_duration=4.0, with_turn=True):
    take_dir.mkdir(parents=True, exist_ok=True)
    make_animated_clip(take_dir / "observer.webm", observer_duration)
    timeline = Timeline.new("observer.webm")
    if with_turn:
        make_animated_clip(take_dir / "author.webm", 1.5)
        timeline.add_actor_clip("author", "author.webm", offset=1.0, duration=1.5)
        timeline.add_event({"type": "turn_start", "time": 1.0, "actor": "author"})
        timeline.add_event({"type": "turn_end", "time": 2.5, "actor": "author"})
    timeline.save(take_dir / "timeline.json")
    return timeline


@requires_ffmpeg
def test_predicted_duration_adds_chapter_and_hold_durations(tmp_path):
    timeline = Timeline.new("observer.webm")
    timeline.add_event(
        {
            "type": "chapter",
            "time": 0.0,
            "eyebrow": "e",
            "title": "t",
            "subtitle": "s",
            "duration": 3.0,
        }
    )
    timeline.add_event({"type": "hold", "time": 1.0, "duration": 2.0})
    assert predicted_duration(timeline, observer_duration=5.0) == 10.0


@requires_ffmpeg
def test_predicted_duration_excludes_a_recorded_hold(tmp_path):
    """(regression, PR #14 follow-up review) A "recorded" hold (the
    return-to-observer wait) is real elapsed time already inside the
    observer's own footage -- the composer never inserts a synthetic
    freeze for it, so predicted_duration must not add it either, or
    verify's duration check would fail a perfectly healthy take."""
    timeline = Timeline.new("observer.webm")
    timeline.add_event({"type": "hold", "time": 1.0, "duration": 2.0})
    timeline.add_event({"type": "hold", "time": 4.0, "duration": 6.0, "recorded": True})
    assert predicted_duration(timeline, observer_duration=5.0) == 7.0


@requires_ffmpeg
def test_verify_budgets_the_recorded_return_to_observer_wait(tmp_path):
    """(regression, PR #14 follow-up review, reproduced) A real
    return-to-observer wait freezes the observer for real: 6s of genuinely
    static footage right after a turn ends (the reviewer's own real-Chromium
    repro). Confirms both that this exact shape fails without the
    "recorded" hold (pre-fix simulation) and passes with it."""
    take_dir = tmp_path / "take"
    take_dir.mkdir(parents=True, exist_ok=True)
    make_freeze_then_move_clip(
        take_dir / "observer.webm",
        freeze_at=3.0,
        freeze_duration=6.0,
        total_duration=10.0,
    )
    make_animated_clip(take_dir / "author.webm", 2.0)

    timeline = Timeline.new("observer.webm")
    timeline.add_actor_clip("author", "author.webm", offset=1.0, duration=2.0)
    timeline.add_event({"type": "turn_start", "time": 1.0, "actor": "author"})
    timeline.add_event({"type": "turn_end", "time": 3.0, "actor": "author"})
    timeline.save(take_dir / "timeline.json")  # no hold yet: pre-fix shape

    compose(take_dir)
    pre_fix_report = verify(take_dir)
    assert any(f["check"] == "dead_air" for f in pre_fix_report["findings"])
    # dead_air is a warning (PR #14 follow-up review, datakurre/
    # collective.bpmproxy#15): freezedetect can't see cursor-only motion at
    # 1080p, so it false-positives on ordinary real turns -- reported, but
    # must not fail ok/the exit code on its own.
    dead_air = next(f for f in pre_fix_report["findings"] if f["check"] == "dead_air")
    assert dead_air["severity"] == "warning"
    assert pre_fix_report["ok"] is True

    timeline.add_event(
        {
            "type": "hold",
            "time": 3.0,
            "duration": 6.0,
            "view": "observer",
            "recorded": True,
        }
    )
    timeline.save(take_dir / "timeline.json")

    report = verify(take_dir)
    assert not any(f["check"] == "dead_air" for f in report["findings"]), report[
        "findings"
    ]


@requires_ffmpeg
def test_verify_passes_a_clean_composed_take(tmp_path):
    take_dir = tmp_path / "take"
    make_take(take_dir)
    compose(take_dir)

    report = verify(take_dir)
    assert report["ok"], report["findings"]
    assert (take_dir / "contact-sheet.png").exists()


@requires_ffmpeg
def test_verify_flags_a_blank_composed_output(tmp_path):
    take_dir = tmp_path / "take"
    make_take(take_dir, with_turn=False)
    # Compose normally to get a correctly *sized* and *timed* file, then
    # replace its content with a near-black clip of the same duration --
    # this is what a font/rendering failure looks like: right shape, wrong
    # content.
    output = compose(take_dir)
    from screencast.compose import ffprobe_duration

    duration = ffprobe_duration(output)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=1920x1080:d={duration}:r=25",
            "-c:v",
            "libvpx-vp9",
            str(output),
        ],
        check=True,
    )

    report = verify(take_dir)
    assert not report["ok"]
    assert any(f["check"] == "blank_frame" for f in report["findings"])


@requires_ffmpeg
def test_verify_flags_a_white_turn_opening_frame_blackdetect_misses(tmp_path):
    """(regression, PR #14 review finding #10) blackdetect only catches
    near-black frames -- a turn's own opening frame is just as likely to be
    a plain white Plone loading page (or any other flat color a missing
    font renders as), which blackdetect cannot see at all. The "author"
    clip is a flat white color throughout; the observer stays animated,
    proving this check samples the actor's own clip directly rather than
    the composed output (whose every turn segment overlays a bordered
    observer inset that would otherwise mask a blank main view)."""
    take_dir = tmp_path / "take"
    take_dir.mkdir(parents=True, exist_ok=True)
    make_animated_clip(take_dir / "observer.webm", 4.0)
    make_clip(take_dir / "author.webm", 1.5, color="white")
    timeline = Timeline.new("observer.webm")
    timeline.add_actor_clip("author", "author.webm", offset=1.0, duration=1.5)
    timeline.add_event({"type": "turn_start", "time": 1.0, "actor": "author"})
    timeline.add_event({"type": "turn_end", "time": 2.5, "actor": "author"})
    timeline.save(take_dir / "timeline.json")
    output = compose(take_dir)

    # blackdetect itself genuinely finds nothing here -- confirms this is
    # the new uniform-color check catching it, not a coincidental overlap.
    assert detect_black_intervals(output) == []

    report = verify(take_dir)
    assert not report["ok"]
    assert any(
        f["check"] == "blank_frame" and "author" in f["message"]
        for f in report["findings"]
    )


@requires_ffmpeg
def test_verify_flags_wrong_frame_size(tmp_path):
    take_dir = tmp_path / "take"
    make_take(take_dir, with_turn=False)
    make_clip(take_dir / "output.webm", 4.0, size="640x360")

    report = verify(take_dir)
    assert not report["ok"]
    assert any(f["check"] == "stream" for f in report["findings"])


@requires_ffmpeg
def test_verify_flags_duration_mismatch(tmp_path):
    take_dir = tmp_path / "take"
    make_take(take_dir, with_turn=False)
    make_clip(take_dir / "output.webm", 10.0, size="1920x1080")

    report = verify(take_dir)
    assert not report["ok"]
    assert any(f["check"] == "duration" for f in report["findings"])


def test_parse_vtt_cue_times_reads_start_and_end_seconds(tmp_path):
    vtt_path = tmp_path / "output.vtt"
    vtt_path.write_text(
        "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.500\nFirst\n\n"
        "2\n00:01:02.250 --> 00:01:04.000\nSecond\n"
    )
    assert parse_vtt_cue_times(vtt_path) == [(1.0, 3.5), (62.25, 64.0)]


@requires_ffmpeg
def test_verify_flags_a_caption_event_with_no_composed_vtt(tmp_path):
    """A caption on the timeline, but compose() either never ran again
    after it was added, or (hypothetically) failed to write the sidecar --
    either way this must not pass silently."""
    take_dir = tmp_path / "take"
    make_take(take_dir, with_turn=False)
    timeline = Timeline.load(take_dir / "timeline.json")
    timeline.add_event({"type": "caption", "time": 0.5, "text": "Hi", "duration": 1.0})
    timeline.save(take_dir / "timeline.json")
    output = compose(take_dir)
    output.with_suffix(".vtt").unlink(missing_ok=True)

    report = verify(take_dir)
    assert not report["ok"]
    assert any(f["check"] == "captions" for f in report["findings"])


@requires_ffmpeg
def test_verify_flags_a_caption_cue_past_the_outputs_own_duration(tmp_path):
    """(regression) A cue that was never correctly mapped past an inserted
    title card/hold would run past where the composed output actually
    ends -- this is what that looks like on disk, independent of whether
    compose() itself has a mapping bug."""
    take_dir = tmp_path / "take"
    make_take(take_dir, with_turn=False)
    output = compose(take_dir)

    from screencast.compose import ffprobe_duration

    duration = ffprobe_duration(output)
    output.with_suffix(".vtt").write_text(
        "WEBVTT\n\n1\n00:00:00.000 --> " + f"00:00:{duration + 5.0:06.3f}\nToo long\n"
    )
    timeline = Timeline.load(take_dir / "timeline.json")
    timeline.add_event(
        {"type": "caption", "time": 0.0, "text": "Too long", "duration": 5.0}
    )
    timeline.save(take_dir / "timeline.json")

    report = verify(take_dir)
    assert not report["ok"]
    assert any(f["check"] == "captions" for f in report["findings"])


@requires_ffmpeg
def test_verify_passes_a_take_with_a_correctly_mapped_caption(tmp_path):
    take_dir = tmp_path / "take"
    make_take(take_dir, with_turn=False)
    timeline = Timeline.load(take_dir / "timeline.json")
    timeline.add_event({"type": "caption", "time": 0.5, "text": "Hi", "duration": 1.0})
    timeline.save(take_dir / "timeline.json")
    compose(take_dir)

    report = verify(take_dir)
    assert report["ok"], report["findings"]
    assert not any(f["check"] == "captions" for f in report["findings"])


def test_contact_sheet_fps_spans_the_whole_clip_however_long():
    """(found reviewing a real 170 s take) A `max(..., 0.5)` floor made the
    sheet cover only the first 60 s of any longer take."""
    from screencast.verify import contact_sheet_fps

    for duration in (10, 60, 170, 900):
        fps = contact_sheet_fps(duration, rows=6, cols=5)
        assert 30 / fps == pytest.approx(duration)  # 30 frames span it all
