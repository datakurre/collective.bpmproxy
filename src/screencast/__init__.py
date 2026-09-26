"""Generic screencast recording engine: a Robot Framework keyword library
over sync Playwright, a timeline (edit-decision list) schema, a composer and
a take verifier.

This package is deliberately free of anything specific to the project it was
written for (collective.bpmproxy). That project's playground lives on as this
repository's `legacy-playground` branch: see its
scripts/screencasts/resources/bpmproxy.resource for an example project layer.
"""

__version__ = "0.1.0"

from screencast.library import Screencast  # noqa: E402
from screencast.timeline import Timeline  # noqa: E402


__all__ = ["Screencast", "Timeline"]
