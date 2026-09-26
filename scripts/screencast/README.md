# screencast

A Robot Framework keyword library, timeline (EDL) schema, composer, and take
verifier for recording multi-actor browser screencasts: a Cockpit/Plone-style
demo with several personas, an observer, title cards, and a picture-in-picture
composite. Built for and currently used by
[collective.bpmproxy](https://github.com/datakurre/collective.bpmproxy)'s own
scenario recordings (`scripts/screencasts/`), but deliberately free of
anything specific to that project — see the package docstring
(`__init__.py`) and the audit below.

See the `screencast` agent skill
(`.agents/skills/screencast/{SKILL.md,reference.md}` in the parent
repository) for how to use this from an agent's own workflow: scaffolding a
story, the timeline schema, the debug loop (`run`/`probe`/`keywords`/
`check`), and take verification. This README is about the package itself.

## Extraction plan (datakurre/collective.bpmproxy#13)

This package is the last step of that issue's epic, deliberately deferred:
"once two or three stories are stable here." Three stories now exist
(`review_process.robot`, `contact_form.robot`, `renovation_project.robot`,
landed in #9/#10) but none has yet been run against a live
Plone/Operaton/Keycloak stack — dry-run syntax checking and toy-page
integration tests (see each port's commit message) are as far as this
package has actually been exercised so far. Extracting now, before that,
would mean discovering real API gaps in a separate repository instead of
here, where fixing them is a one-line change instead of a cross-repo release.

**Coupling audit** (what extraction needs to be true, and currently is):
grepping `*.py`/`schema/*.json` for `bpmproxy`/`Plone`/`Cockpit`/`Operaton`/
`Camunda` outside of `tests/` turns up only prose in docstrings using
Cockpit as an illustrative example (e.g. "Cockpit (or whatever the observer
is) closes last") and this file's own cross-references — no import, no
hard-coded selector, no assumption about what the browser is driving. The
project-specific layer (`bpmproxy.resource`, `bpmproxy_keywords.py`,
`*.robot`) lives entirely in the parent repository's `scripts/screencasts/`,
one level up, and reaches into this package only through its public
keywords (`Library screencast.Screencast`) and `python -m screencast`.

**What extraction will actually need to change**, when it happens:

- A real Python package layout (`src/screencast/` or similar) with its own
  `pyproject.toml`, replacing the current `PYTHONPATH=scripts` convention.
  This directory is *not* laid out that way yet — `pyproject.toml` cannot
  simply be dropped in next to `__init__.py` here without also moving the
  package into a subdirectory, so that restructuring is left for the actual
  extraction rather than done partially now.
- `scripts/screencast/schema/timeline.schema.json`'s `$id` currently points
  at this path inside `collective.bpmproxy`; update it to the new repo.
- A PyPI release, and `scripts/screencasts/resources/bpmproxy.resource`'s
  `Library screencast.Screencast` import switching from a path-relative
  `PYTHONPATH` dependency to an installed one.
- The `screencast` agent skill pinning a released version instead of the
  parent repo carrying this source directly (named explicitly as the epic's
  own last sub-issue, once this one lands).

## Supported versions

**Robot Framework 7.4 or newer.** 7.4.2 is what the nixpkgs pinned by this
repository's devenv ships, so it is what users actually run; CI tests it and
the latest release. Anything newer than 7.4 that the engine can use only when
present (`robot.api.console`, from 7.5) is imported behind a guard. Use
`python -m screencast --version` to print the resolved versions of Robot
Framework, Playwright, jsonschema and ffmpeg, and paste them into bug reports.

## Running its own tests

```sh
pip install pytest robotframework jsonschema
PYTHONPATH=.. python -m pytest tests/   # from scripts/screencast/, or:
PYTHONPATH=scripts python -m pytest scripts/screencast/tests/   # from the repo root
```

No live browser or Plone/Operaton/Keycloak stack needed: `tests/fakes.py`
stands in for Playwright, and the composer/verifier tests run against real
ffmpeg on tiny synthetic clips. This is also what the parent repository's
`screencast-engine` CI job runs.
