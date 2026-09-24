"""screencast.driver tests, against the fake Playwright in fakes.py -- real
Robot Framework execution, no real browser. Manually verified separately
against a real headless Chromium and a toy two-actor story (see the #4/#5
commit messages); that is not repeated here since it would need a browser
in CI."""

from screencast import driver
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


PASSING_STORY = """\
*** Settings ***
Library    screencast.Screencast    take_dir=${TAKE_DIR}    record=${RECORD}

*** Test Cases ***
Watches
    Start Observer    observer    http://example.test

Turn
    [Setup]    Start Actor Turn    author    title=Author
    No Operation
    [Teardown]    End Actor Turn
"""

FAILING_STORY = """\
*** Settings ***
Library    screencast.Screencast    take_dir=${TAKE_DIR}    record=${RECORD}

*** Test Cases ***
Broken
    [Setup]    Start Actor Turn    author
    No Operation
    [Teardown]    End Actor Turn
"""


def write_story(tmp_path, text, name="story.robot"):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_run_passes_and_writes_a_timeline(tmp_path):
    story = write_story(tmp_path, PASSING_STORY)
    code, output = driver.run(story, take_dir=tmp_path / "take", quiet=True)
    assert code == 0
    assert output.exists()
    timeline_path = tmp_path / "take" / "timeline.json"
    assert timeline_path.exists()


def test_run_with_task_runs_only_that_task(tmp_path):
    story = write_story(tmp_path, PASSING_STORY)
    code, output = driver.run(
        story, task="Watches", take_dir=tmp_path / "take", quiet=True
    )
    assert code == 0
    from robot.api import ExecutionResult

    result = ExecutionResult(str(output))
    ran = [test.name for test in result.suite.all_tests if test.status != "SKIP"]
    assert ran == ["Watches"]


def test_run_failure_is_summarized_with_keyword_path(tmp_path):
    story = write_story(tmp_path, FAILING_STORY)
    code, output = driver.run(story, take_dir=tmp_path / "take", quiet=True)
    assert code != 0
    summary = driver.summarize_failures(output)
    assert "Broken" in summary
    assert "Start Actor Turn" in summary
    assert "FatalError" in summary


def test_summarize_failures_reports_all_tasks_passed(tmp_path):
    story = write_story(tmp_path, PASSING_STORY)
    _, output = driver.run(story, take_dir=tmp_path / "take", quiet=True)
    assert driver.summarize_failures(output) == "All tasks passed."


def test_check_passes_a_valid_story(tmp_path):
    story = write_story(tmp_path, PASSING_STORY)
    errors = driver.check(story, take_dir=tmp_path / "check")
    assert errors == []


def test_check_catches_a_keyword_typo_without_a_browser(tmp_path):
    story = write_story(
        tmp_path,
        PASSING_STORY.replace("Start Observer", "Start Observerrr"),
    )
    errors = driver.check(story, take_dir=tmp_path / "check")
    assert errors
    assert "Start Observerrr" in errors[0]
    # No browser was launched -- dryrun never executes keyword bodies.
    assert FakePlaywright.instances == []


def test_probe_runs_one_keyword_against_the_live_session(tmp_path):
    code = driver.probe(
        None,
        "Start Observer",
        ["observer", "http://example.test"],
        take_dir=tmp_path,
        record=False,
    )
    assert code == 0
    assert library_module._SESSION.observer_page is not None


def test_probe_reuses_the_browser_across_calls(tmp_path):
    driver.probe(
        None, "Start Observer", ["observer", "http://example.test"], take_dir=tmp_path
    )
    browser_after_first = library_module._SESSION.browser
    driver.probe(None, "Chapter", ["Story", "Title", "Subtitle"], take_dir=tmp_path)
    assert library_module._SESSION.browser is browser_after_first
    assert len(FakePlaywright.instances) == 1


def test_keywords_lists_resource_keywords_with_docs(tmp_path):
    resource = tmp_path / "project.resource"
    resource.write_text(
        "*** Keywords ***\n"
        "Do The Thing\n"
        "    [Documentation]    Does the thing.\n"
        "    [Arguments]    ${x}\n"
        "    No Operation\n"
    )
    listing = driver.keywords(resource)
    assert "Do The Thing(x)" in listing
    assert "Does the thing." in listing


def test_render_log_writes_log_html(tmp_path):
    story = write_story(tmp_path, PASSING_STORY)
    _, _ = driver.run(story, take_dir=tmp_path / "take", quiet=True)
    log_path = driver.render_log(tmp_path / "take")
    assert log_path.exists()
