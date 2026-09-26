# Renovation case-management scenario

This is the reproducible case-management example for the
`collective.bpmproxy:renovation_demo` profile. A folderish Renovation Project
is a Plone case. Creating the case starts one Operaton process with a signal;
the case UUID correlates all later messages and task queries.

The example demonstrates both directions of synchronization:

- Plone workflow transitions notify the running case process with correlated
  BPMN messages.
- The manager's workflow transition closes the case and the case process
  receives the correlated close message.
- A BPMN `++add++Document` task opens the native Plone creation form and is
  completed by the existing add-task subscriber.
- Direct Document creation during work emits a case-correlated message and
  starts a non-interrupting document-review subprocess.
- The case Message portlet starts a repeatable extra-work approval subprocess.

## Assets

The case coordinator process is:

```text
examples/renovation-project/renovation-case.bpmn
```

The called page-review process is:

```text
examples/renovation-project/renovation-page-review.bpmn
```

Forms are:

```text
renovation-owner-approval.form
renovation-inspector-approval.form
```

## Prerequisites

Run from the repository root:

```sh
devenv up -d
until curl -sf http://127.0.0.1:8081/engine-rest/engine >/dev/null; do sleep 5; done
make bootstrap-site
make start &   # it blocks: use a second terminal instead of the &
until curl -sf http://127.0.0.1:8080/Plone >/dev/null; do sleep 3; done
```

On a clean checkout `make reset-site` and `make bootstrap-site` create the
Zope instance first (`make instance`), so this sequence works as written.
The first, cold `devenv up -d` also downloads Operaton's Maven
dependencies, which takes several minutes; if that stalls, see
[devenv-browser-smoke.md](devenv-browser-smoke.md).

Or do all of it in one command: `make demo-stack STORY=renovation_project` brings up the
services, the Zope instance, the site and this scenario's demo profile, then
starts Plone in the background (logs in `var/demo-stack/`);
`make demo-stack-down` stops them again. It refuses to run when something
else already answers on port 8080.

Deploy the case process:

```sh
cd examples/renovation-project
cp secrets.example.env secrets.env
make deploy
cd ../..
```

Stop the Plone process, install the demo profile so its creation signal starts the
deployed process, and start Plone again:

```sh
make bootstrap-renovation-demo
make start &   # it blocks: use a second terminal instead of the &
until curl -sf http://127.0.0.1:8080/Plone >/dev/null; do sleep 3; done
```

The bootstrap script creates the groups and demo users. The profile's
content-type portlet assignments provide aggregate case tasks on the case and
page-review tasks on Documents. The browser scenario deletes and recreates the
demo case during the recorded manager turn so the opening empty-site state and
the case-creation process instance are visible.

## Personas

| User | Role |
| --- | --- |
| `owner` | Renovation Owners |
| `contractor` | Renovation Contractors |
| `inspector` | Renovation Inspectors |
| `admin` | Operaton Cockpit observer |

## Scenario

1. The manager creates the Demo renovation project from Plone's Add new menu.
2. The contractor adds a Document directly inside the case.
3. The child-created message starts a child page-review process with parallel owner and inspector tasks.
4. Owner and inspector complete the document review independently.
5. The page-review subprocess completes and the main case process resumes.
6. A case manager closes the Plone case through its `close-case` workflow transition.
7. The close message reaches the main case process and ends it.

Run the story with the screencast driver. `make screencast STORY=<story>` does
this and then `compose` and `verify`; `playwright-python` is the wrapper (from
`devenv.nix`) that puts the engine and Playwright on the path:

```sh
playwright-python -m screencast run scripts/screencasts/renovation_project.robot
```

The recording follows the same conventions as the contact-form and
review-process scenarios (see `scripts/screencast/` and
`scripts/screencasts/resources/bpmproxy.resource`, collective/collective.bpmproxy#8-#10):

- Cockpit is authenticated in an unrecorded context (`Log In To Cockpit`),
  then recorded first and kept open as the observer for the whole run.
  Auto-refresh and sequence-flow visualization are enabled before the empty
  Plone site is recorded.
- Each persona turn gets its own 1920x1080 recorded context (`Start Actor
  Turn`/`End Actor Turn`), cursor/click overlay, human-paced interactions,
  and a chapter event the composer turns into a title card -- no waiting in
  the browser for it, unlike the old script's 8s `show_actor_slide()`.
- Two points reload Cockpit rather than navigate in-app -- the documented
  exception in docs/AGENTS.md, forcing a refresh past auto-refresh's own
  polling interval right after a review that can otherwise complete between
  polls (`Observe    reload=${True}`).
- `playwright-python -m screencast compose` writes the composite as `output.webm` in
  the take directory; the old hard-coded `final_focus_switch_at = 117.0` is
  gone -- the composer's default (observer main between turns, unless a
  `focus` event says otherwise) already does what that constant was for.

The runner does not activate Cockpit's time heat-map. It captures the final
case in History with the left information-panel sash dragged left so the
panel remains visible at roughly two thirds of its original width.

## Artifacts

Written to `var/screencasts/renovation_project/<take>/` (gitignored):

| Artifact | Description |
| --- | --- |
| `page@*.webm` | The observer (Cockpit) recording and each actor turn's own clip |
| `timeline.json` | Schema v2 timeline: observer/actor clips, chapter/focus/hold events |
| `output.webm` | The composite, actor turns as picture-in-picture over the Cockpit observer |
| `report.json` / `contact-sheet.png` | `playwright-python -m screencast verify`'s findings and contact sheet |

The doc-illustration screenshots below are written under the take too
(`var/screencasts/renovation_project/<take>/screenshots/`). They differ slightly on
every run, so a run never overwrites the tracked copies in `docs/` by
accident; after a take you are happy with,
`make promote-screenshots STORY=renovation_project` copies the latest ones into `docs/`
(review the diff, then commit).

| Screenshot | Description |
| --- | --- |
| `renovation-project-document-added.png` | Contractor's document in the case |
| `renovation-project-cockpit-parallel-review.png` | Cockpit showing the two review tasks |
| `renovation-project-closed.png` | Case after the manager closes it |
| `renovation-project-cockpit-completed.png` | Completed case in Cockpit History |

## Verifying a take

The story's exit status alone does not verify the video -- `verify` does:

```sh
playwright-python -m screencast compose var/screencasts/renovation_project/<take>/
playwright-python -m screencast verify var/screencasts/renovation_project/<take>/
```

`verify` derives its contact-sheet sampling rate from the take's own measured
duration, so there is no `tile=RxC` rate to hand-tune here -- see
`scripts/screencast/verify.py`, and `report.json` for what a failing check
found.

## Resetting

Delete the Operton deployment, stop Plone, redeploy the BPMN, and rerun
`make bootstrap-renovation-demo` to delete and recreate the demo case, groups,
roles, and portlets. Since this is a disposable example, no migration or
upgrade path is provided.
