"""A compact console for `screencast run`: one line per task/turn instead
of Robot Framework's default per-keyword verbose trace, which buries a
story's own progress under every Human Click and wait_for_timeout call.
"""

from robot.api import console


class TaskConsole(console.BaseConsole):
    """Attached as a listener (not via `console=`), since BaseConsole's
    hook methods are the listener API, per its own docstring."""

    def start_suite(self, data, result):
        if data.parent is None:
            self.write(f"{result.name}\n")

    def end_test(self, data, result):
        status = result.status
        elapsed = result.elapsed_time.total_seconds()
        line = f"{status:6} {result.name} ({elapsed:.1f}s)"
        self.highlight(status, line + "\n")

    def end_suite(self, data, result):
        if data.parent is None:
            stats = result.statistics
            self.write(f"{stats.total} run, {stats.failed} failed\n")
