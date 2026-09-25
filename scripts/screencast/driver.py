"""The Python driver API behind `python -m screencast`: run/probe/keywords/
check/log, all runnable as plain functions too (see __main__.py).

The commands exist for one reason: an agent debugging a broken story should
never have to replay the whole thing blind. `run` gives a compact
keyword-path failure summary with the real Python traceback and the
listener's failure artifacts; `probe` re-runs one keyword against the same
live session `run` just left open; `keywords` and `check` answer "what
exists" and "does this parse" without spending a turn on the browser at all.
"""

from pathlib import Path
from robot.api import ExecutionResult
from robot.result import Keyword as ResultKeyword
from robot.result import Message as ResultMessage
from robot.running import TestSuite
from robot.running.builder import ResourceFileBuilder
from screencast.console import TaskConsole
import datetime
import sys


def default_take_dir(story, base=None):
    stem = Path(story).stem
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = Path(base) if base else Path.cwd() / "var" / "screencasts" / stem
    return base / stamp


def run(story, task=None, record=True, take_dir=None, headless=True, quiet=False):
    """Run `story` in-process, in this same interpreter, so a later `probe`
    call can reuse the live browser. Returns (return_code, output_path)."""
    take_dir = Path(take_dir) if take_dir else default_take_dir(story)
    take_dir.mkdir(parents=True, exist_ok=True)
    output = take_dir / "output.json"

    suite = TestSuite.from_file_system(story)
    if task:
        suite.filter(included_tests=[task])
    run_kwargs = {
        "output": str(output),
        "log": None,
        "report": None,
        "loglevel": "DEBUG",
        "console": "none",
        "variable": [f"TAKE_DIR:{take_dir}", f"RECORD:{record}"],
    }
    if not quiet:
        run_kwargs["listener"] = [TaskConsole()]

    result = suite.run(**run_kwargs)
    if not quiet:
        if result.return_code:
            print(summarize_failures(output))
        print(f"Take directory: {take_dir}")
    return result.return_code, output


def summarize_failures(output_path):
    """A compact keyword-path failure summary from `output`: the keyword
    path (Task > Setup[args] > Human Click[args]), its message, the
    DEBUG-level Python traceback, and any failure-artifact paths the
    library's listener logged -- everything screencast.library writes for
    exactly this purpose."""
    result = ExecutionResult(str(output_path))
    lines = []
    for test in result.suite.all_tests:
        if test.status != "FAIL":
            continue
        lines.append(f"FAIL: {test.full_name}")
        for part in (test.setup, *test.body, test.teardown):
            if part is not None:
                _summarize_keyword(part, [test.name], lines)
    return "\n".join(lines) if lines else "All tasks passed."


def _summarize_keyword(item, path, lines):
    if not isinstance(item, ResultKeyword) or item.status != "FAIL":
        return
    if item.name is None:
        return  # a synthetic body wrapper (e.g. an invalid-test placeholder)
    args = ", ".join(str(arg) for arg in item.args)
    label = f"{item.name}[{args}]" if args else item.name
    path = [*path, label]
    failed_children = [
        child
        for child in item.body
        if isinstance(child, ResultKeyword) and child.status == "FAIL"
    ]
    if failed_children:
        for child in failed_children:
            _summarize_keyword(child, path, lines)
        return
    # This is the leaf: the keyword that actually failed.
    lines.append("  " + " > ".join(path))
    if item.message:
        lines.append(f"    {item.message}")
    for message in item.body:
        if not isinstance(message, ResultMessage):
            continue
        if message.level == "DEBUG" or "Failure artifacts" in (message.message or ""):
            lines.append(f"    {message.message}")


def probe(resource, keyword, args=(), take_dir=".", record=False, headless=True):
    """Run one keyword against the live session -- the browser started by a
    previous `run`/`probe` call in this process survives, per
    screencast.library's module-level session state. Builds a throwaway
    TestSuite instead of parsing a story file, per the driver's own
    research: BuiltIn().run_keyword() outside a run raises
    RobotNotRunningError, so even one keyword needs a (tiny) suite run."""
    take_dir = Path(take_dir)
    take_dir.mkdir(parents=True, exist_ok=True)
    suite = TestSuite(name="Probe")
    suite.resource.imports.library(
        "screencast.Screencast",
        args=(f"take_dir={take_dir}", f"record={record}", f"headless={headless}"),
    )
    if resource:
        suite.resource.imports.resource(str(resource))
    task = suite.tests.create(name="Probe")
    task.body.create_keyword(name=keyword, args=tuple(args))
    output = take_dir / "probe-output.json"
    result = suite.run(
        output=str(output), log=None, report=None, loglevel="DEBUG", console="none"
    )
    print(summarize_failures(output))
    return result.return_code


def repl(resource, take_dir=".", record=False, headless=True):
    """Interactive mode: read one keyword call per line from stdin (space
    separated: `Keyword Name    arg1    arg2`), run it against the live
    session, print its status, and keep going -- Ctrl-D / an empty line to
    stop. The browser survives between lines, same as `probe`."""
    print("screencast repl -- one keyword per line, Ctrl-D to stop")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t") if "\t" in line else line.split("    ")
        parts = [part.strip() for part in parts if part.strip()]
        name, args = parts[0], parts[1:]
        code = probe(
            resource, name, args, take_dir=take_dir, record=record, headless=headless
        )
        print("OK" if code == 0 else "FAIL")


def keywords(resource):
    """List a resource file's own keywords with their arguments and source
    line, via ResourceFileBuilder -- what an agent checks before writing or
    fixing a story, instead of guessing what a project resource exposes."""
    built = ResourceFileBuilder().build(Path(resource))
    lines = []
    for keyword in built.keywords:
        args = ", ".join(str(arg) for arg in keyword.args)
        lines.append(f"{keyword.name}({args})  -- {resource}:{keyword.lineno}")
        if keyword.doc:
            lines.append(f"    {keyword.doc.splitlines()[0]}")
    return "\n".join(lines)


def check(story, take_dir=None):
    """Check `story` with Robot Framework's own `--dryrun`: it parses,
    resolves every keyword against the libraries/resources actually
    imported, and validates arguments -- without opening a browser, since
    dry-run skips real keyword bodies. Cheaper than a real run when the
    browser was never the problem. Returns a list of "task: message"
    strings; empty means it checked out clean."""
    take_dir = Path(take_dir) if take_dir else default_take_dir(story, base=Path.cwd())
    take_dir.mkdir(parents=True, exist_ok=True)
    output = take_dir / "check-output.json"
    suite = TestSuite.from_file_system(str(story))
    suite.run(
        dryrun=True,
        output=str(output),
        log=None,
        report=None,
        console="none",
        variable=["TAKE_DIR:.", "RECORD:False"],
    )
    result = ExecutionResult(str(output))
    return [
        f"{test.full_name}: {test.message}"
        for test in result.suite.all_tests
        if test.status == "FAIL"
    ]


def render_log(take_dir):
    """Render log.html from a take directory's output.json on demand, for
    humans -- `run` itself never writes log.html, to keep the fast loop
    fast."""
    from robot.api import ResultWriter

    take_dir = Path(take_dir)
    output = take_dir / "output.json"
    log = take_dir / "log.html"
    ResultWriter(str(output)).write_results(report=None, log=str(log))
    return log
