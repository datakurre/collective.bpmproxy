"""Python keywords for the bpmproxy screencast project resource
(bpmproxy.resource): the pieces that need the raw Playwright page --
`.request`/`.evaluate()` HTTP calls, reading a DOM attribute, or dragging by
a measured bounding box -- rather than a sequence of Screencast's own
keywords. Plain HTTP with no page at all (Wait For Mail) lives here too, per
collective/collective.bpmproxy#8's own framing.

Reaches into screencast.library's module-level session (`_SESSION`) directly
for the current page, the same state screencast.library.Screencast's own
keywords use -- this is a project resource cooperating with the engine in
one process, not a public API boundary.
"""

from pathlib import Path
from robot.api.deco import keyword
from screencast.library import _SESSION
from screencast.library import WAIT_TAG
import json
import time
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "http://localhost:8080/Plone"
DEFAULT_MAILPIT_URL = "http://localhost:8025"


def _page():
    page = _SESSION.current_page
    if page is None:
        raise AssertionError(
            "No open page -- call Start Observer or Start Actor Turn first"
        )
    return page


def deploy_process_assets(directory, base_url=DEFAULT_BASE_URL):
    """Deploy every .bpmn/.dmn/.form file in `directory` via
    @bpmproxy-deploy, through the current page's session (its Plone
    Manager/admin cookies, not a separate HTTP client)."""
    directory = Path(directory)
    for path in sorted(directory.iterdir()):
        if path.suffix not in (".bpmn", ".dmn", ".form"):
            continue
        result = _page().evaluate(
            """async ({base, name, xml}) => {
              const response = await fetch(base + '/@bpmproxy-deploy', {
                method: 'POST',
                headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
                body: JSON.stringify({name, xml})
              });
              return {status: response.status, body: await response.text()};
            }""",
            {"base": base_url, "name": path.name, "xml": path.read_text()},
        )
        if result["status"] != 200:
            raise AssertionError(f"Could not deploy {path.name}: {result}")


def clear_deployments(base_url=DEFAULT_BASE_URL):
    """Delete every existing engine deployment, so a take starts from a
    clean process list and instance history -- same as each e2e_*.py
    script's own setup."""
    deployments = _page().evaluate(
        """async base => (await (await fetch(base + '/@bpmproxy-deployments', {
          headers: {'Accept': 'application/json'}
        })).json())""",
        base_url,
    )
    for deployment in deployments:
        response = _page().request.delete(
            f"{base_url}/@bpmproxy-deployments",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            data=json.dumps({"id": deployment["id"]}),
        )
        if response.status not in (200, 204):
            raise AssertionError(
                f"Could not delete deployment {deployment['id']}: {response.status}"
            )


def delete_demo_content(paths, base_url=DEFAULT_BASE_URL):
    """Remove scenario-owned top-level content before a take. `paths` is a
    Robot list of site-relative paths; 404 is fine -- there is nothing to
    clean up on a first run."""
    for path in paths:
        response = _page().request.delete(
            f"{base_url}/{str(path).lstrip('/')}",
            headers={"Accept": "application/json"},
        )
        if response.status not in (200, 204, 404):
            raise AssertionError(
                f"Could not remove demo content {path!r}: "
                f"{response.status} {response.text()}"
            )


def set_sharing(url, entries):
    """POST a @sharing update -- entries is a list of
    {"id", "type" ("user"/"group"), "roles": {role: True}} dicts. Used by
    the renovation-project story to grant the contractor/owner/inspector
    groups and users access to a case document created at record time
    (whose URL is not known until the manager's own turn runs)."""
    response = _page().request.post(
        f"{url}/@sharing",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        data=json.dumps({"entries": entries}),
    )
    if response.status not in (200, 204):
        raise AssertionError(f"Could not update sharing on {url}: {response.status}")


@keyword(tags=[WAIT_TAG])  # a wait: verify's dead_air check counts it
def wait_for_mail(subject, timeout=60, mailpit_url=DEFAULT_MAILPIT_URL):
    """Poll Mailpit's own HTTP API for a message with this Subject -- no
    browser page needed, unlike this module's other keywords."""
    deadline = time.monotonic() + float(timeout)
    url = f"{mailpit_url}/api/v1/messages"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                messages = json.load(response).get("messages", [])
        except (OSError, urllib.error.URLError):
            messages = []
        if any(message.get("Subject") == subject for message in messages):
            return
        time.sleep(1.5)
    raise AssertionError(f"Mailpit did not receive {subject!r} in time")


def enable_cockpit_toggle(selector, label):
    """Click a Cockpit toggle button (auto-refresh, sequence-flow) into its
    "on" state, and fail loudly instead of silently leaving it off --
    Cockpit exposes state through `aria-pressed` in newer builds and
    through a describing `aria-label` ("Disable X" while on, "Enable X"
    while off) in older ones, so both are checked."""
    page = _page()
    button = page.locator(selector).first
    button.wait_for(state="visible", timeout=10000)

    def enabled():
        pressed = button.get_attribute("aria-pressed")
        aria_label = (button.get_attribute("aria-label") or "").lower()
        if pressed is not None:
            return pressed == "true"
        if label == "auto-refresh":
            return "off" in aria_label
        return "hide" in aria_label or "disable" in aria_label

    if not enabled():
        button.click()
    for _ in range(10):
        if enabled():
            return
        page.wait_for_timeout(300)
    raise AssertionError(f"Cockpit {label} did not become enabled")


def drag_sash_to_fraction(selector='[data-testid="sash"]', fraction=2 / 3):
    """Drag Cockpit's History info-panel sash left to `fraction` of its
    original x position, instead of collapsing the panel entirely -- the
    two-thirds position is part of the recording composition, not
    incidental."""
    page = _page()
    sash = page.locator(selector).first
    sash.wait_for(state="visible", timeout=10000)
    box = sash.bounding_box()
    if box is None:
        raise AssertionError(f"{selector!r} has no bounding box to drag")
    target_x = box["x"] * fraction
    target_y = box["y"] + box["height"] / 2
    page.mouse.move(box["x"] + box["width"] / 2, target_y)
    page.mouse.down()
    page.mouse.move(target_x, target_y, steps=18)
    page.mouse.up()
