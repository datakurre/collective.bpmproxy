*** Settings ***
Documentation     Project keywords for collective.bpmproxy screencasts, built
...               on the generic screencast.Screencast library (see
...               scripts/screencast/) plus bpmproxy_keywords.py for the few
...               things that need the raw Playwright page (HTTP calls,
...               reading a DOM attribute, dragging by a bounding box).
...
...               Story authors only need this file and screencast.Screencast
...               -- see docs/AGENTS.md for the recording architecture these
...               keywords implement (unrecorded setup, one recorded context
...               per turn, in-app navigation over page.reload(), the human
...               cursor).
Library           screencast.Screencast
Library           bpmproxy_keywords.py


*** Variables ***
${BASE_URL}       http://localhost:8080/Plone
${COCKPIT_URL}    http://localhost:8081/operaton/app/cockpit/default
${KEYCLOAK_USER}      admin
${KEYCLOAK_PASSWORD}    admin


*** Keywords ***
Prepare Fixtures
    [Documentation]    Unrecorded setup: log in as Manager, clear old
    ...    deployments, deploy this story's process/form/dmn assets, and
    ...    remove any leftover demo content -- all before Start Observer, so
    ...    none of it becomes blank/white seconds in a recording.
    [Arguments]    ${assets_dir}    @{demo_content_paths}    ${username}=manager    ${password}=manager
    Start Scratch Context    ${BASE_URL}    http_credentials=${{ {'username': $username, 'password': $password} }}
    Clear Deployments    base_url=${BASE_URL}
    Deploy Process Assets    ${assets_dir}    base_url=${BASE_URL}
    IF    ${{ len($demo_content_paths) > 0 }}
        Delete Demo Content    ${demo_content_paths}    base_url=${BASE_URL}
    END
    End Scratch Context

Set Sharing As Manager
    [Documentation]    Grant local roles on `url` (a Robot list of
    ...    {"id", "type", "roles"} dicts) via an unrecorded, privileged
    ...    context -- for content created mid-take whose URL is only known
    ...    at record time (e.g. the renovation-project story's case
    ...    document, shared with the Owner/Inspector after the Contractor
    ...    creates it).
    [Arguments]    ${url}    ${entries}    ${username}=manager    ${password}=manager
    Start Scratch Context    http_credentials=${{ {'username': $username, 'password': $password} }}
    Set Sharing    ${url}    ${entries}
    End Scratch Context

Log In To Cockpit
    [Documentation]    Complete the Keycloak OIDC login for Cockpit in an
    ...    unrecorded context, and return its storage_state() for
    ...    `Start Observer` -- this keeps the login redirect out of the
    ...    recording while carrying the session into the recorded context.
    ...    A no-op (still returns a usable, empty state) when the `oauth2`
    ...    Spring profile is off and Cockpit's own permit-all chain applies.
    [Arguments]    ${cockpit_url}=${COCKPIT_URL}    ${username}=${KEYCLOAK_USER}    ${password}=${KEYCLOAK_PASSWORD}
    Start Scratch Context    ${cockpit_url}/
    ${page}=    Get Current Page
    ${on_keycloak}=    Evaluate    "realms" in $page.url
    IF    ${on_keycloak}
        Human Type    \#username    ${username}
        Human Type    \#password    ${password}
        Human Click    \#kc-login
    END
    ${state}=    Get Storage State
    End Scratch Context
    RETURN    ${state}

Open Process In Cockpit
    [Documentation]    Enter a process definition's instance list from the
    ...    Cockpit landing page, by in-app navigation.
    [Arguments]    ${process_definition_key}
    Observe    url=${COCKPIT_URL}/#/processes
    Human Click    role=link[name="${process_definition_key}"]

Enter Latest Process Instance
    [Documentation]    Click the most recently created instance link on the
    ...    current Cockpit definition/instance-list view, and enable the
    ...    auto-refresh and sequence-flow toggles on it.
    Wait Until Visible    a[href*="/process-instance/"]    index=-1
    Human Click    a[href*="/process-instance/"]    index=-1
    Enable Cockpit Toggles

Enable Cockpit Toggles
    [Documentation]    Turn on Cockpit's auto-refresh and sequence-flow
    ...    display for the currently open process instance view.
    Enable Cockpit Toggle    .toggle-auto-refresh-button    auto-refresh
    Enable Cockpit Toggle    .toggle-sequence-flow-button    sequence-flow

Show Completed Instance In History
    [Documentation]    Open a completed process instance's History view --
    ...    either via the toggle on an instance still on screen, or by
    ...    re-entering the definition's History tab -- and drag the info
    ...    panel's sash to two-thirds width instead of leaving it collapsed
    ...    or full width.
    [Arguments]    ${process_definition_key}
    ${toggles}=    Count Matches    button.toggle-history-view-button
    IF    ${toggles} > 0
        ${label}=    Get Attribute    button.toggle-history-view-button    aria-label
        IF    "${label}" == "Show history view"
            Human Click    button.toggle-history-view-button
        END
    ELSE
        Observe    url=${COCKPIT_URL}/#/processes
        Human Click    role=link[name="${process_definition_key}"]
        Human Click    text=History    index=-1
        Wait Until Visible    a[href*="/process-instance/"]    index=-1
        Human Click    a[href*="/process-instance/"]    index=-1
    END
    Wait Until Keyword Succeeds    10x    1s    Location Should Contain    /history/process-instance/
    Drag Sash To Fraction

Location Should Contain
    [Documentation]    Fail unless the current page's URL contains `text` --
    ...    a small polling primitive for Wait Until Keyword Succeeds, since
    ...    Cockpit's history route only appears after an in-app navigation
    ...    finishes.
    [Arguments]    ${text}
    ${page}=    Get Current Page
    Should Contain    ${page.url}    ${text}

Add Content
    [Documentation]    Add a new content item of `type_name` from the
    ...    current folder view, filling only its title.
    [Arguments]    ${type_name}    ${title}
    Human Click    role=link[name="Add new…"]
    Human Click    role=link[name="${type_name}"]
    Human Type    \#form-widgets-IDublinCore-title    ${title}
    Human Click    role=button[name="Save"]

Workflow Transition
    [Documentation]    Fire a Plone workflow transition by its visible
    ...    link text (e.g. "Submit for publication", "Publish").
    [Arguments]    ${transition_label}
    Human Click    \#plone-contentmenu-workflow a
    Human Click    role=link[name="${transition_label}"]

Wait For Task
    [Documentation]    Poll `base_url` (by in-app navigation, i.e.
    ...    Go To -- there is nothing to refresh in place, the whole point is
    ...    to see a task portlet that did not exist before) until a task
    ...    named `task_name` is visible, then return its locator's page.
    [Arguments]    ${task_name}    ${base_url}=${BASE_URL}    ${retries}=20x    ${interval}=3s
    Wait Until Keyword Succeeds    ${retries}    ${interval}    Task Is Visible    ${task_name}    ${base_url}

Task Is Visible
    [Documentation]    One polling attempt for `Wait For Task`. A Bpm Proxy
    ...    page lists its tasks under a "Task list" tab that is hidden
    ...    until clicked; a Tasks portlet (other pages) has no such tab.
    ...    Match an *anchor*, not bare text: with the diagram enabled,
    ...    `text=<task name>` first resolves to the BPMN diagram's own
    ...    (hidden) SVG label and never reaches the task link.
    [Arguments]    ${task_name}    ${base_url}
    Go To    ${base_url}
    ${tabs}=    Count Matches    role=link[name="Task list"s]
    IF    ${tabs} > 0
        Human Click    role=link[name="Task list"s]
    END
    Wait Until Visible    a:has-text("${task_name}")    timeout=1000

Open Task
    [Documentation]    Wait for, then open, a task named `task_name`. When
    ...    several tasks share the name (one per process instance), `index`
    ...    picks one: 0 is the first row, -1 the last.
    [Arguments]    ${task_name}    ${base_url}=${BASE_URL}    ${index}=0
    Wait For Task    ${task_name}    base_url=${base_url}
    Human Click    a:has-text("${task_name}")    index=${index}

Submit Task Form
    [Documentation]    Click a task form's submit button by its visible
    ...    label (forms in this project use varied labels: "Submit Review",
    ...    "Complete Review", "Assign Reviewers", ...).
    [Arguments]    ${button_label}=Submit
    Human Click    role=button[name="${button_label}"]

Wait For Workflow State
    [Documentation]    Poll a document's URL until its workflow state label
    ...    reads `state_text` -- driven by an external worker reacting to a
    ...    BPMN task, not by anything this story does directly. Polls
    ...    through an unrecorded, authenticated scratch context (like
    ...    Prepare Fixtures) rather than the current page: a story's
    ...    wrap-up commonly calls this right after re-entering Cockpit,
    ...    whose page has no Plone login session and so can never see a
    ...    still-private document's state label -- the poll would just
    ...    exhaust its retries and fail.
    [Arguments]    ${doc_url}    ${state_text}    ${retries}=20x    ${interval}=3s
    ...    ${username}=manager    ${password}=manager
    Start Scratch Context    http_credentials=${{ {'username': $username, 'password': $password} }}
    Wait Until Keyword Succeeds    ${retries}    ${interval}    Workflow State Is    ${doc_url}    ${state_text}
    [Teardown]    End Scratch Context

Workflow State Is
    [Arguments]    ${doc_url}    ${state_text}
    Go To    ${doc_url}
    Wait Until Visible    text=State: ${state_text}    timeout=1000
