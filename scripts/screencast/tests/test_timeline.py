from screencast.timeline import Timeline
from screencast.timeline import TimelineError
from screencast.timeline import VERSION
import pytest


def make_timeline():
    timeline = Timeline.new("observer.webm")
    timeline.add_actor_clip("author", "turn-01-author.webm", offset=1.2, duration=10.0)
    timeline.add_event({"type": "turn_start", "time": 1.2, "actor": "author"})
    timeline.add_event(
        {
            "type": "chapter",
            "time": 1.2,
            "eyebrow": "Story · 1/1",
            "title": "Author",
            "subtitle": "Doing a thing",
            "duration": 8.0,
        }
    )
    timeline.add_event({"type": "focus", "time": 9.2, "view": "actor"})
    timeline.add_event({"type": "turn_end", "time": 11.2, "actor": "author"})
    timeline.add_event({"type": "hold", "time": 11.2, "duration": 5.0})
    return timeline


def test_valid_timeline_round_trips_through_disk(tmp_path):
    timeline = make_timeline()
    path = timeline.save(tmp_path / "timeline.json")
    loaded = Timeline.load(path)
    assert loaded.data == timeline.data


def test_events_of_filters_by_type():
    timeline = make_timeline()
    assert [event["type"] for event in timeline.events_of("focus")] == ["focus"]


def test_actor_clip_looks_up_by_name():
    timeline = make_timeline()
    assert timeline.actor_clip("author")["video"] == "turn-01-author.webm"
    with pytest.raises(TimelineError):
        timeline.actor_clip("nobody")


def test_wrong_version_is_rejected():
    data = make_timeline().data
    data["version"] = 1
    with pytest.raises(TimelineError):
        Timeline(data)


def test_unknown_top_level_field_is_rejected():
    data = make_timeline().data
    data["bogus"] = True
    with pytest.raises(TimelineError):
        Timeline(data)


def test_unknown_event_type_is_rejected():
    data = make_timeline().data
    data["events"].append({"type": "wipe", "time": 0})
    with pytest.raises(TimelineError):
        Timeline(data)


def test_negative_offset_is_rejected():
    data = make_timeline().data
    data["actors"][0]["offset"] = -1
    with pytest.raises(TimelineError):
        Timeline(data)


def test_current_version_constant_matches_schema():
    assert VERSION == 2
