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

ORDINARY_FAILURE_STORY = """\
*** Settings ***
Library    screencast.Screencast    take_dir=${TAKE_DIR}    record=${RECORD}

*** Test Cases ***
Broken
    Fail    something in the page did not look right

After
    No Operation
"""

EVENTUAL_SUCCESS_STORY = """\
*** Settings ***
Library    screencast.Screencast    take_dir=${TAKE_DIR}    record=${RECORD}

*** Test Cases ***
Eventually Succeeds
    Start Observer    observer    http://example.test
    Wait Until Keyword Succeeds    5x    0.01s    Fail Twice Then Pass
    [Teardown]    End Observer

*** Keywords ***
Fail Twice Then Pass
    ${count}=    Get Variable Value    ${ATTEMPT_COUNT}    ${0}
    ${count}=    Evaluate    ${count} + 1
    Set Suite Variable    ${ATTEMPT_COUNT}    ${count}
    IF    ${count} < 3
        Fail    not yet
    END
"""

GENUINE_FAILURE_WITH_RETRIES_STORY = """\
*** Settings ***
Library    screencast.Screencast    take_dir=${TAKE_DIR}    record=${RECORD}

*** Test Cases ***
Genuinely Fails
    Start Observer    observer    http://example.test
    Wait Until Keyword Succeeds    3x    0.01s    Fail    still broken
    [Teardown]    End Observer
"""

RECOVERS_THEN_REALLY_FAILS_STORY = """\
*** Settings ***
Library    screencast.Screencast    take_dir=${TAKE_DIR}    record=${RECORD}

*** Test Cases ***
Recovers Then Really Fails
    Start Observer    observer    http://example.test
    Wait Until Keyword Succeeds    5x    0.01s    Fail Twice Then Pass
    Should Be Equal    a    b
    [Teardown]    End Observer

*** Keywords ***
Fail Twice Then Pass
    ${count}=    Get Variable Value    ${ATTEMPT_COUNT}    ${0}
    ${count}=    Evaluate    ${count} + 1
    Set Suite Variable    ${ATTEMPT_COUNT}    ${count}
    IF    ${count} < 3
        Fail    not yet
    END
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


def test_run_stops_after_the_first_failed_task(tmp_path):
    """(regression, PR #14 review finding #8) run() used to run every task
    regardless of an earlier failure -- each carries its own Wait Until
    Keyword Succeeds retries, so a broken early task meant burning through
    every later one's retry loops for nothing. Uses an ordinary keyword
    failure (Fail), not one of screencast.library's own FatalErrors --
    robot.api.FatalError already aborts the whole run by itself, which
    would make this test pass regardless of whether run() asks for
    exitonfailure."""
    story = write_story(tmp_path, ORDINARY_FAILURE_STORY)
    code, output = driver.run(story, take_dir=tmp_path / "take", quiet=True)
    assert code != 0
    from robot.api import ExecutionResult

    result = ExecutionResult(str(output))
    statuses = {test.name: test.status for test in result.suite.all_tests}
    assert statuses["Broken"] == "FAIL"
    assert statuses["After"] != "PASS"


def test_failure_artifacts_dumped_once_per_task_not_per_retry_attempt(tmp_path):
    """(regression, PR #14 review finding #9) The listener used to dump a
    screenshot/aria-snapshot/console-log bundle on every failed keyword
    (end_keyword), including every failed attempt inside a Wait Until
    Keyword Succeeds retry loop -- noisy, and outright wrong when a later
    attempt succeeds and the task passes overall. FakePage.screenshot() is
    a no-op, so a dump's real, countable side effect is its .txt file."""
    take_dir = tmp_path / "take"

    # Two failed attempts, then a third that succeeds -- the task PASSES
    # overall, so nothing should be dumped.
    story = write_story(tmp_path, EVENTUAL_SUCCESS_STORY, name="eventual.robot")
    code, _ = driver.run(story, take_dir=take_dir, quiet=True)
    assert code == 0
    assert list(take_dir.glob("failure-*.txt")) == []

    # Every attempt fails -- the task FAILS overall, so exactly one bundle
    # should be dumped, not one per retry attempt.
    story = write_story(
        tmp_path, GENUINE_FAILURE_WITH_RETRIES_STORY, name="broken.robot"
    )
    code, _ = driver.run(story, take_dir=take_dir, quiet=True)
    assert code != 0
    assert len(list(take_dir.glob("failure-*.txt"))) == 1


def test_a_later_genuine_failure_gets_its_own_dump_not_a_recovered_ones(tmp_path):
    """(regression, PR #14 follow-up review, reproduced) The one dump slot
    per task used to be claimed by whichever failure happened first, even
    a *recovered* one -- a Wait Until Keyword Succeeds attempt that later
    succeeds. That left a genuine failure later in the same task with no
    dump of its own (the slot was taken), and the stale recovered
    attempt's artifacts sitting there instead. This is the shape it
    happens in for real: Open Task -> Wait For Task polls and fails a few
    times, then succeeds, and only then does e.g. a click actually fail."""
    take_dir = tmp_path / "take"
    story = write_story(tmp_path, RECOVERS_THEN_REALLY_FAILS_STORY)
    code, _ = driver.run(story, take_dir=take_dir, quiet=True)
    assert code != 0

    dumps = list(take_dir.glob("failure-*.txt"))
    assert len(dumps) == 1
    assert "keyword: Should Be Equal" in dumps[0].read_text()


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


def test_probe_passes_take_dir_and_record_as_named_library_args(tmp_path):
    """(regression, PR #14 review finding #5) probe() used to build the
    library import's args with `:` instead of `=` -- Robot Framework only
    recognizes `name=value` as named-argument syntax for a library import,
    so the whole string ("take_dir:/x") was passed as one positional
    argument instead: take_dir ended up holding that literal string, and
    record -- run through _as_bool() -- was always truthy (any non-empty
    string) regardless of the value actually asked for."""
    take_dir = tmp_path / "take"
    driver.probe(
        None,
        "Start Observer",
        ["observer", "http://example.test"],
        take_dir=take_dir,
        record=False,
    )
    assert library_module._SESSION.take_dir == take_dir
    assert library_module._SESSION.record is False


def test_probe_resolves_a_relative_resource_path_against_cwd(tmp_path, monkeypatch):
    """(regression, PR #14 review finding #6) probe()'s suite is built in
    memory, not via TestSuite.from_file_system, so it has no source file
    for Robot to resolve a relative --resource path against -- passing one
    straight through used to fail (or resolve against the wrong base)."""
    resource_dir = tmp_path / "resources"
    resource_dir.mkdir()
    (resource_dir / "project.resource").write_text(
        "*** Keywords ***\nDo The Thing\n    No Operation\n"
    )
    monkeypatch.chdir(tmp_path)

    code = driver.probe(
        "resources/project.resource",
        "Do The Thing",
        take_dir=tmp_path / "take",
        record=False,
    )
    assert code == 0


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
