"""Unit tests for screencast.library, against the fake Playwright in
fakes.py -- no real browser involved, per the library's acceptance
criterion in collective/collective.bpmproxy#4."""

from pathlib import Path
from robot.api import FatalError
from screencast import library as library_module
from screencast.tests.fakes import fake_sync_playwright
from screencast.tests.fakes import FakePlaywright
import pytest
import sys
import types


@pytest.fixture(autouse=True)
def fake_playwright(monkeypatch):
    FakePlaywright.instances.clear()
    fake_module = types.ModuleType("playwright.sync_api")
    fake_module.sync_playwright = fake_sync_playwright
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_module)
    library_module._SESSION.reset()
    yield
    library_module._SESSION.reset()


def test_start_observer_starts_the_clock_and_a_timeline(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    assert library_module._SESSION.started is not None
    assert library_module._SESSION.timeline.observer["name"] == "cockpit"
    assert library_module._SESSION.current_page.url == "http://example.test/cockpit"


def test_actor_turn_records_matching_start_and_end_events(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.start_actor_turn(
        "author", eyebrow="Story", title="Author", subtitle="Doing"
    )
    screencast.human_click("text=Add new")
    screencast.end_actor_turn()

    timeline = library_module._SESSION.timeline
    starts = timeline.events_of("turn_start")
    ends = timeline.events_of("turn_end")
    chapters = timeline.events_of("chapter")
    assert [event["actor"] for event in starts] == ["author"]
    assert [event["actor"] for event in ends] == ["author"]
    assert chapters[0]["title"] == "Author"
    assert timeline.actor_clip("author")["offset"] >= 0
    # human_click actually clicked, through the fake page.
    clicked_pages = [
        page
        for context in library_module._SESSION.browser.contexts
        for page in context.pages
        if page.clicked
    ]
    assert len(clicked_pages) == 1
    assert clicked_pages[0].clicked == ["text=Add new"]


def test_end_actor_turn_without_start_raises(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    with pytest.raises(FatalError):
        screencast.end_actor_turn()


def test_starting_a_second_turn_before_closing_the_first_raises(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.start_actor_turn("author")
    with pytest.raises(FatalError):
        screencast.start_actor_turn("author")


def test_chapter_focus_hold_add_timeline_events_without_waiting(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.chapter("Story", "Title", "Subtitle", duration=5.0)
    screencast.focus("actor", scale=0.3)
    screencast.hold(10.0)

    timeline = library_module._SESSION.timeline
    assert timeline.events_of("chapter")[0]["duration"] == 5.0
    assert timeline.events_of("focus")[0]["view"] == "actor"
    assert timeline.events_of("hold")[0]["duration"] == 10.0


def test_focus_rejects_unknown_view(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    with pytest.raises(FatalError):
        screencast.focus("sideways")


def test_browser_is_reused_across_repeated_instantiation(tmp_path):
    """This is the property the agent debug loop (screencast.driver) relies
    on: repeated `TestSuite(...).run()` calls construct a fresh Screencast()
    instance each time, but must not launch a second browser."""
    first = library_module.Screencast(take_dir=tmp_path)
    first.start_browser()
    browser_after_first = library_module._SESSION.browser

    second = library_module.Screencast(take_dir=tmp_path)
    second.start_browser()
    assert library_module._SESSION.browser is browser_after_first
    assert len(FakePlaywright.instances) == 1


def test_end_observer_closes_the_context_and_clears_current_page(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    context = library_module._SESSION.observer_context
    screencast.end_observer()

    assert context.closed
    assert library_module._SESSION.observer_context is None
    assert library_module._SESSION.current_page is None


def test_end_observer_without_start_raises(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    with pytest.raises(FatalError):
        screencast.end_observer()


def test_timeline_written_to_disk_by_the_listener_on_close(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.start_actor_turn("author", title="Author")
    screencast.end_actor_turn()
    library_module.Screencast.ROBOT_LIBRARY_LISTENER.close()

    timeline_path = Path(tmp_path) / "timeline.json"
    assert timeline_path.exists()
    from screencast.timeline import Timeline

    loaded = Timeline.load(timeline_path)
    assert loaded.actor_clip("author")


def test_no_record_mode_skips_video_but_still_builds_timeline(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path, record=False)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.start_actor_turn("author", title="Author")
    screencast.end_actor_turn()

    timeline = library_module._SESSION.timeline
    assert timeline.actors == []  # no video path was produced to register
    assert timeline.events_of("turn_start")
    assert timeline.events_of("turn_end")


def test_paste_text_fills_without_per_keystroke_typing(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.paste_text("#body", "a long paragraph")
    page = library_module._SESSION.current_page
    assert page.filled["#body"] == "a long paragraph"


def test_human_click_with_index_minus_one_clicks_the_last_match(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.human_click("a.row", index=-1)
    locator = library_module._SESSION.current_page.locator("a.row")
    assert locator.last.index == -1


def test_a_label_selector_resolves_via_get_by_label(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.human_click("label=Approve")
    page = library_module._SESSION.current_page
    assert page.clicked == ["label=Approve"]


def test_a_frame_piercing_selector_resolves_via_frame_locator(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.paste_text("iframe >>> body", "rich text")
    page = library_module._SESSION.current_page
    assert page.filled["iframe >>> body"] == "rich text"


def test_select_option_sets_the_value(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.select_option("#kind", "example-process")
    page = library_module._SESSION.current_page
    assert page.filled["#kind"] == "example-process"


def test_observe_reload_reloads_instead_of_navigating(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.observe(url="http://example.test/should-not-navigate", reload=True)
    page = library_module._SESSION.observer_page
    assert page.reloaded == 1
    assert page.url == "http://example.test/cockpit"


def test_check_and_uncheck(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    screencast.check("#diagram-enabled")
    page = library_module._SESSION.current_page
    assert page.checked["#diagram-enabled"] is True
    screencast.uncheck("#diagram-enabled")
    assert page.checked["#diagram-enabled"] is False


def test_scratch_context_does_not_touch_the_timeline(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_scratch_context("http://example.test/login")
    state = screencast.get_storage_state()
    screencast.end_scratch_context()

    assert state == {}
    assert library_module._SESSION.timeline is None
    assert library_module._SESSION.current_page is None


def test_scratch_context_restores_the_previous_current_page(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_observer("cockpit", "http://example.test/cockpit")
    observer_page = library_module._SESSION.current_page

    screencast.start_scratch_context("http://example.test/login")
    assert library_module._SESSION.current_page is not observer_page
    screencast.end_scratch_context()

    assert library_module._SESSION.current_page is observer_page


def test_end_scratch_context_without_start_raises(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    with pytest.raises(FatalError):
        screencast.end_scratch_context()


def test_starting_a_second_scratch_context_before_closing_raises(tmp_path):
    screencast = library_module.Screencast(take_dir=tmp_path)
    screencast.start_scratch_context("http://example.test/login")
    with pytest.raises(FatalError):
        screencast.start_scratch_context("http://example.test/login")
