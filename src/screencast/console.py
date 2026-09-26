"""A compact console for `screencast run`: one line per task/turn instead
of Robot Framework's default per-keyword verbose trace, which buries a
story's own progress under every Human Click and wait_for_timeout call.

`robot.api.console.BaseConsole` only exists from Robot Framework 7.5, but
nixpkgs (which devenv's `playwright-python` wrapper uses) can lag behind, so
older versions get a plain listener that prints the same lines.
"""

import sys


class _TaskLines:
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


try:
    from robot.api.console import BaseConsole
except ImportError:  # Robot Framework < 7.5

    class TaskConsole(_TaskLines):
        ROBOT_LISTENER_API_VERSION = 3

        def write(self, text):
            sys.stdout.write(text)
            sys.stdout.flush()

        def highlight(self, status, text):
            self.write(text)

else:

    class TaskConsole(_TaskLines, BaseConsole):
        """Attached as a listener (not via `console=`), since BaseConsole's
        hook methods are the listener API, per its own docstring."""
