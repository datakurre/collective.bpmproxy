# robotframework-screencast

Record, compose and verify **multi-actor browser screencasts** from Robot
Framework stories. A story is a `*** Tasks ***` suite that reads like a
screenplay: several personas take turns in their own browser, an observer
watches the whole time, and the result is one composed video, with title
cards and picture-in-picture, that is checked automatically for dead air,
blank frames and a wrong duration.

```robotframework
*** Settings ***
Library    screencast.Screencast    take_dir=${TAKE_DIR}    record=${RECORD}

*** Tasks ***
Watch The Dashboard
    Start Observer    dashboard    https://example.org/dashboard

Alice Adds A Page
    [Setup]    Start Actor Turn    alice    eyebrow=Demo · 1 / 1
    ...    title=Alice    subtitle=Adding a page
    Go To    https://example.org/
    Human Click    role=link[name="Add new…"]
    [Teardown]    End Actor Turn

Wrap Up
    End Observer
```

```sh
screencast run story.robot          # record: one clip per turn, one for the observer
screencast compose <take dir>       # compose them into output.webm
screencast verify <take dir>        # ffprobe, blank frames, dead air, contact sheet
```

## What is in it

Three layers, and only the first is in this repository:

| Layer | What | Where |
|---|---|---|
| **Engine** | A Robot Framework keyword library over sync Playwright (human-paced input, a visible cursor, one recorded context per turn), a versioned timeline (edit-decision list) schema, a declarative composer, a take verifier, and an agent-facing driver | `src/screencast/` |
| **Project keywords** | A `.resource` file that turns your app's UI into keywords: `Log In`, `Add Content`, `Wait For Task` | Your project |
| **Stories** | The `*** Tasks ***` suites | Your project |

`screencast --version` prints the resolved versions of Robot Framework,
Playwright, jsonschema and ffmpeg; paste it into bug reports.

### Commands

| Command | |
|---|---|
| `run story.robot [--task NAME] [--no-record] [--take DIR]` | Run a story in-process and write `timeline.json` and the clips. On failure it prints the keyword path, the message, the traceback and the failure screenshots. `--repl-on-failure` pauses before the failing turn's teardown and drops into a REPL against the still-open page |
| `probe KEYWORD args... [--resource FILE]` | Run one keyword against the live browser session |
| `keywords FILE` | List a resource file's keywords with arguments and docs |
| `check story.robot` | Dry-run a story (no browser) |
| `compose DIR` | Compose a take into `output.webm` (and `output.vtt` when the story has captions) |
| `verify DIR` | Check a composed take and write `report.json` and a contact sheet |
| `log DIR` | Render Robot Framework's `log.html` for a take |

### Dead air

The library records a `wait` event around every waiting keyword (`Sleep`,
`Wait Until Keyword Succeeds`, its own waits, and any keyword you tag
`screencast:wait`). `verify` fails a take with a single wait over 10 seconds
and warns when all waits together pass 30. Tag your own polling keywords:

```robotframework
Wait For Task
    [Tags]    screencast:wait
    Wait Until Keyword Succeeds    20x    3s    Task Is Visible
```

## Requirements

- Python 3.10 or newer, and `ffmpeg`/`ffprobe` on the `PATH`.
- **Robot Framework 7.4 or newer.** 7.4.2 is the oldest release the tests
  cover, next to the latest; anything newer that the engine can use only when
  present (`robot.api.console`, from 7.5) is imported behind a guard.
- Playwright with a Chromium it can launch. It never runs `playwright install`
  itself; provide the browser the way your environment does (a Nix
  `playwright-driver.browsers`, or `playwright install chromium` yourself). The
  `SCREENCAST_CHROMIUM_PATH` environment variable points it at a specific
  Chromium build.

Not on PyPI yet. Until it is, install from this branch:

```sh
pip install "git+https://github.com/datakurre/collective.bpmproxy@screencast-engine"
```

## An example use case

The engine was built for, and is still used by,
[collective.bpmproxy](https://github.com/datakurre/collective.bpmproxy), whose
`scripts/screencasts/` holds three complete stories (a review process, a
contact form and a renovation project, each with several personas and Cockpit
as the observer) and the project keyword layer (`resources/bpmproxy.resource`)
that they share. That repository is the reference example of the two upper
layers, and its `docs/*-scenario.md` walk through each story.

## Development

```sh
pip install -e ".[test]"
pytest
```

No live browser or application stack is needed: `tests/fakes.py` stands in for
Playwright, and the composer and verifier tests run against real ffmpeg on tiny
synthetic clips. CI runs them on Robot Framework 7.4.2 and the latest release.

## Provenance

This branch's history is the engine's own: it was extracted from
collective.bpmproxy with `git filter-repo`, keeping only the commits that
touched the engine (`scripts/screencast/`, moved to `src/screencast/`) and its
agent skill (`.agents/skills/screencast/`). Commit messages and code comments
that refer to `#N` issues mean issues of that repository, and some comments
use its Plone and Operaton scenario as illustration; the code itself imports
and assumes nothing from it. See datakurre/collective.bpmproxy#13.

### Before a first release

- Decide the repository and package names (`robotframework-screencast` is a
  working name) and update `$id` in `src/screencast/schema/timeline.schema.json`,
  which still points into the collective.bpmproxy repository, and the URLs in
  `pyproject.toml`.
- Publish to PyPI; then collective.bpmproxy can depend on the released package
  instead of carrying its own copy.
- The `screencast` agent skill (`.agents/skills/screencast/`) still describes
  the collective.bpmproxy setup (`make screencast`, its stack) and needs
  splitting into a generic part and a project part.

## License

GPL version 2, as the repository the engine was written in. See `LICENSE`.
