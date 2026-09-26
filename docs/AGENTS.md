# Recording-specific guidance

This directory contains browser scenario recording documentation. Each
scenario has its own Robot Framework story in `scripts/screencasts/` (built
on the generic engine in `scripts/screencast/`) and its own `*-scenario.md`
here. Run a story from the repository root with `playwright-python` (the wrapper in
`devenv.nix`: it puts `scripts/` on the path and provides Playwright), or
`make screencast STORY=...` for run, compose and verify in one go:

```sh
playwright-python -m screencast run scripts/screencasts/renovation_project.robot
playwright-python -m screencast run scripts/screencasts/review_process.robot
playwright-python -m screencast run scripts/screencasts/contact_form.robot
```

See [renovation-project-scenario.md](renovation-project-scenario.md) and
[review-process-scenario.md](review-process-scenario.md) and
[contact-form-scenario.md](contact-form-scenario.md) for each one's
prerequisites, personas, and artifacts.

Everything about the *engine* -- the three-layer structure, the timeline
schema and how to re-cut a take by editing it, the agent debug loop
(`run`/`probe`/`keywords`/`check`) and how to read its failure summary, take
verification and what each finding means -- lives in the `screencast` agent
skill (`.agents/skills/screencast/`, a sibling of `.agents/skills/browser/`),
not here. This file only covers what is specific to *this project's*
recordings: Cockpit's own quirks, and the BPMN diagram viewer's tab-flash
fix.

## Cockpit quirks

- Cockpit's definition page loads its instance table once and does not
  poll, so a new instance never appears without navigation. Prefer
  navigating -- `Open Process In Cockpit`/`Observe url=...`, an in-app route
  change -- over a reload: reloading re-bootstraps the Angular SPA and puts
  a flash in the middle of the view, where an in-app route change does not.
- `renovation_project.robot` reloads Cockpit at two points instead
  (`Observe reload=${True}`), to force a refresh past auto-refresh's own
  polling interval right after a review that can otherwise complete between
  polls. Treat that as the deliberate, documented exception -- an in-app
  route change is still the default everywhere else.
- When a story ends on a completed process in Cockpit's History view, keep
  the information panel visible and drag its `[data-testid="sash"]` left to
  two-thirds of its original width (`Drag Sash To Fraction`,
  `bpmproxy_keywords.py`) rather than collapsing it -- the two-thirds
  position is part of the recording composition, not incidental.
- `bpmproxy.resource`'s `Enable Cockpit Toggle` checks both `aria-pressed`
  and a describing `aria-label` ("Disable X" while on, "Enable X" while
  off), because Cockpit exposes toggle state through `aria-pressed` in
  newer builds and only through the label in older ones.

## BPMN diagram flashes

The Plone template always emits `#collective-bpmproxy-diagram` when diagrams
are enabled, even if the Process diagram tab is hidden. The old `diagram.js`
initialized `bpmn-js` immediately on page load, so the hidden container could
briefly paint during autotoc/tab setup and navigation.

`frontend-classic/src/diagram.ts` now checks `offsetParent` and uses a
`MutationObserver` on the tab container. BPMN XML is imported only after the
diagram container becomes visible. After changing this source, rebuild the
committed bundle:

```sh
npm --prefix frontend-classic run build
```

This keeps the diagram available when its tab is selected while preventing
unselected-tab flashes in the recordings.
