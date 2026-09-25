*** Settings ***
Documentation     The renovation-project scenario: a case manager starts a
...               renovation case, a contractor adds a document, an owner
...               and an inspector independently review it (a correlated
...               event subprocess per reviewer), and the manager closes
...               the completed case -- driven entirely from Plone, with no
...               external worker.
...
...               Equivalent to scripts/scenarios/e2e_renovation_project.py
...               (see collective/collective.bpmproxy#10), built on the
...               generic engine (#1-#7) and bpmproxy.resource (#8).
Library           screencast.Screencast    take_dir=${TAKE_DIR}    record=${RECORD}
Resource          resources/bpmproxy.resource


*** Variables ***
${DOCS_DIR}           ${CURDIR}/../../docs
${ASSETS_DIR}         examples/renovation-project
${CASE_PROCESS_KEY}      renovation-case
${REVIEW_PROCESS_KEY}    renovation-page-review
${SEED_CASE_PATH}     renovation-project-demo
${CASE_URL}           ${EMPTY}
${DOCUMENT_URL}       ${EMPTY}


*** Tasks ***
Prepare The Take
    [Documentation]    Unrecorded: deploy this scenario's process assets and
    ...    remove any leftover seed case from a previous run.
    Prepare Fixtures    ${ASSETS_DIR}    ${SEED_CASE_PATH}

Start Observing In Cockpit
    ${state}=    Log In To Cockpit
    Start Observer    cockpit    ${COCKPIT_URL}/    storage_state=${state}
    Open Process In Cockpit    ${CASE_PROCESS_KEY}

Manager Creates The Case
    [Documentation]    Renovation case · 1 / 5.
    [Setup]    Start Actor Turn    manager    eyebrow=Renovation case · 1 / 5
    ...    title=Case manager    subtitle=Creating the demo renovation project
    Go To    ${BASE_URL}
    Human Click    role=link[name="Add new…"]
    Human Click    role=link[name="Renovation Project"s]
    Human Type    \#form-widgets-IBasic-title    Demo renovation project
    Human Click    role=button[name="Save"]
    ${page}=    Get Current Page
    ${case_url}=    Evaluate    $page.url.removesuffix("/view")
    Set Suite Variable    ${CASE_URL}    ${case_url}
    [Teardown]    End Actor Turn

Manager Shares The Case
    [Documentation]    Unrecorded: grant the Contractor/Owner/Inspector
    ...    groups their roles on the new case.
    ${entries}=    Evaluate    [{'id': 'Renovation Contractors', 'type': 'group', 'roles': {'Contributor': True, 'Editor': True}}, {'id': 'Renovation Owners', 'type': 'group', 'roles': {'Reviewer': True}}, {'id': 'Renovation Inspectors', 'type': 'group', 'roles': {'Reviewer': True}}]
    Set Sharing As Manager    ${CASE_URL}    ${entries}

Cockpit Enters The Case Instance
    [Documentation]    Enter the case's live instance before the Contractor
    ...    turn so auto-refresh and sequence-flow are active for every
    ...    subsequent engine update.
    Open Process In Cockpit    ${CASE_PROCESS_KEY}
    Enter Latest Process Instance

Contractor Adds A Document
    [Documentation]    Renovation case · 2 / 5.
    [Setup]    Start Actor Turn    contractor    eyebrow=Renovation case · 2 / 5
    ...    title=Contractor    subtitle=Adding a document to the renovation case
    Go To    ${CASE_URL}
    Human Click    role=link[name="Add new…"]
    Human Click    role=link[name="Page"s]
    Human Type    \#form-widgets-IDublinCore-title    Initial renovation document
    Paste Text    iframe >>> body    The case document requires independent owner and inspector review.
    Human Click    role=button[name="Save"]
    ${page}=    Get Current Page
    ${document_url}=    Evaluate    $page.url.removesuffix("/view")
    Set Suite Variable    ${DOCUMENT_URL}    ${document_url}
    Take Screenshot    ${DOCS_DIR}/renovation-project-document-added.png
    [Teardown]    End Actor Turn

Manager Shares The Document
    [Documentation]    Unrecorded: grant the Owner and Inspector users
    ...    Reader access to the new document.
    ${entries}=    Evaluate    [{'id': 'owner', 'type': 'user', 'roles': {'Reader': True}}, {'id': 'inspector', 'type': 'user', 'roles': {'Reader': True}}]
    Set Sharing As Manager    ${DOCUMENT_URL}    ${entries}

Cockpit Shows Parallel Review
    Open Process In Cockpit    ${REVIEW_PROCESS_KEY}
    Enter Latest Process Instance
    Take Screenshot    ${DOCS_DIR}/renovation-project-cockpit-parallel-review.png

Owner Approves The Document
    [Documentation]    Renovation case · 3 / 5.
    [Setup]    Start Actor Turn    owner    eyebrow=Renovation case · 3 / 5
    ...    title=Owner    subtitle=Reviewing the added page
    Open Task    Owner reviews page    base_url=${CASE_URL}
    Human Click    label=Approved
    Human Click    role=button[name="Submit review"]
    [Teardown]    End Actor Turn

Cockpit Refreshes After Owner Review
    [Documentation]    The documented reload exception (see docs/AGENTS.md):
    ...    force a refresh past auto-refresh's own interval right after a
    ...    review that can otherwise complete between polls.
    Observe    reload=${True}
    Enable Cockpit Toggles

Inspector Approves The Document
    [Documentation]    Renovation case · 4 / 5.
    [Setup]    Start Actor Turn    inspector    eyebrow=Renovation case · 4 / 5
    ...    title=Inspector    subtitle=Reviewing the added page for compliance
    Open Task    Inspector reviews page    base_url=${CASE_URL}
    Human Click    label=Approved
    Human Click    role=button[name="Submit review"]
    [Teardown]    End Actor Turn

Cockpit Returns To The Case Instance
    Open Process In Cockpit    ${CASE_PROCESS_KEY}
    Enter Latest Process Instance
    Hold    1.8

Manager Closes The Case
    [Documentation]    Renovation case · 5 / 5.
    [Setup]    Start Actor Turn    manager    eyebrow=Renovation case · 5 / 5
    ...    title=Case manager    subtitle=Closing the completed renovation case
    Go To    ${CASE_URL}
    Human Click    role=link[name="State: Open"]
    Wait Until Visible    a[href*="workflow_action=close-case"]    index=-1
    Human Click    a[href*="workflow_action=close-case"]    index=-1
    Take Screenshot    ${DOCS_DIR}/renovation-project-closed.png
    [Teardown]    End Actor Turn

Wrap Up In Cockpit History
    [Documentation]    The close transition can finish the engine instance
    ...    while Cockpit's auto-refresh request is between intervals: force
    ...    one refresh before opening History (the same documented
    ...    exception as above) so the completion is visible.
    Observe    reload=${True}
    Show Completed Instance In History    ${CASE_PROCESS_KEY}
    Take Screenshot    ${DOCS_DIR}/renovation-project-cockpit-completed.png
    End Observer
