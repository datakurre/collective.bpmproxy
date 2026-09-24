"""Generic screencast recording engine: a Robot Framework keyword library
over sync Playwright, a timeline (edit-decision list) schema, a composer and
a take verifier.

This package is deliberately free of anything specific to collective.bpmproxy
-- see scripts/screencasts/resources/bpmproxy.resource for the project layer,
and https://github.com/datakurre/collective.bpmproxy/issues/13 for the plan
to extract it into its own repository once two or three stories built on it
are stable.
"""

__version__ = "0.1.0"

from screencast.library import Screencast  # noqa: E402
from screencast.timeline import Timeline  # noqa: E402


__all__ = ["Screencast", "Timeline"]
