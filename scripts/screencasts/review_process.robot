*** Settings ***
Documentation     The review-process scenario: an Author drafts and submits
...               a conference announcement, a Lead reviewer delegates to
...               two parallel Reviewers, and the Lead reviewer consolidates
...               their feedback into a publish/reject decision -- one BPMN
...               process instance throughout, with Cockpit observing from
...               before the instance exists to its completed History view.
...
...               Equivalent to scripts/scenarios/e2e_review_process.py (see
...               collective/collective.bpmproxy#9), but as a Robot
...               Framework story built on scripts/screencast/ (the generic
...               engine, #1-#7) and
...               scripts/screencasts/resources/bpmproxy.resource (the
...               project keywords, #8).
Library           screencast.Screencast    take_dir=${TAKE_DIR}    record=${RECORD}
Resource          resources/bpmproxy.resource


*** Variables ***
${DOCS_DIR}       ${CURDIR}/../../docs
${ASSETS_DIR}     examples/review-process
${PROCESS_KEY}    example-plone-review-process
${DOC_TITLE}      Plone Conference 2027 unveiled!
${DOC_PATH}       plone-conference-2027-unveiled
${DOC_URL}        ${BASE_URL}/${DOC_PATH}
${DOC_BODY}       The upcoming conference brings together practical ideas, ambitious teams, and a fresh programme of useful conversations.\n\nAttendees can expect thoughtful sessions, productive connections, and plenty of opportunities to exchange lessons learned from recent projects.\n\nThe programme will highlight:\n• responsible growth and customer understanding\n• small operational improvements that help good work scale\n• practical demonstrations and measurable outcomes\n\nOur organisers are shaping a welcoming experience with clear communication, carefully timed activities, and a steady focus on value for every participant.


*** Tasks ***
Prepare The Take
    [Documentation]    Unrecorded: deploy this scenario's process/form
    ...    assets and remove any leftover demo document from a previous run.
    Prepare Fixtures    ${ASSETS_DIR}    contact-us    ${DOC_PATH}

Start Observing In Cockpit
    [Documentation]    Cockpit is the observer: open it first, before the
    ...    process instance exists, so its recording spans every actor turn
    ...    (see docs/AGENTS.md). Watches the still-empty process definition
    ...    -- the instance appears the moment the Author submits, without
    ...    this story reaching back into Cockpit for it.
    ${state}=    Log In To Cockpit
    Start Observer    cockpit    ${COCKPIT_URL}/    storage_state=${state}
    Open Process In Cockpit    ${PROCESS_KEY}

Author Drafts And Submits
    [Documentation]    Review process · 1 / 5. The Author creates the
    ...    announcement and submits it for review -- the site-wide "submit"
    ...    content rule then starts the BPMN process instance.
    [Setup]    Start Actor Turn    author    eyebrow=Review process · 1 / 5
    ...    title=Author    subtitle=Drafting and submitting the conference announcement
    Go To    ${BASE_URL}
    Human Click    role=link[name="Add new…"]
    Human Click    role=link[name="Page"s]
    Human Type    \#form-widgets-IDublinCore-title    ${DOC_TITLE}
    Paste Text    iframe >>> body    ${DOC_BODY}
    Human Click    role=button[name="Save"]
    Workflow Transition    Submit for publication
    Take Screenshot    ${DOCS_DIR}/review-process-submitted.png
    [Teardown]    End Actor Turn

Cockpit Shows Choose Reviewers
    [Documentation]    The instance now exists: enter it and show the
    ...    "Choose reviewers" task before the Lead reviewer acts.
    Enter Latest Process Instance
    Take Screenshot    ${DOCS_DIR}/review-process-cockpit-choose-reviewers.png

Lead Reviewer Assigns Reviewers
    [Documentation]    Review process · 2 / 5. The Lead reviewer
    ...    delegates to two parallel Reviewers.
    [Setup]    Start Actor Turn    reviewer3    eyebrow=Review process · 2 / 5
    ...    title=Lead reviewer    subtitle=Choosing reviewers for a parallel assessment
    Open Task    Choose reviewers
    Human Type    .fjs-taglist-input    reviewer1
    Human Type    .fjs-taglist-input    reviewer2
    Human Type    label=Instructions for reviewers
    ...    Please recommend or critique the location, without naming it.
    Submit Task Form    Assign Reviewers
    [Teardown]    End Actor Turn

Cockpit Shows Parallel Review
    [Documentation]    The multi-instance sub-process now has two parallel
    ...    active tasks -- the visual point of this whole example.
    Take Screenshot    ${DOCS_DIR}/review-process-cockpit-parallel-review.png

Reviewer One Approves
    [Documentation]    Review process · 3 / 5.
    [Setup]    Start Actor Turn    reviewer1    eyebrow=Review process · 3 / 5
    ...    title=Reviewer 1    subtitle=Recommending the location
    Open Task    Submit review
    Human Click    label=Approve
    Human Type    label=Review Comments
    ...    I recommend the location; it supports a welcoming conference experience.
    Submit Task Form    Submit Review
    [Teardown]    End Actor Turn

Reviewer Two Requests Changes
    [Documentation]    Review process · 4 / 5.
    [Setup]    Start Actor Turn    reviewer2    eyebrow=Review process · 4 / 5
    ...    title=Reviewer 2    subtitle=Critiquing the location
    Open Task    Submit review
    Human Click    label=Request Changes
    Human Type    label=Review Comments
    ...    I critique the location because access and flow may need improvement.
    Submit Task Form    Submit Review
    [Teardown]    End Actor Turn

Lead Reviewer Consolidates
    [Documentation]    Review process · 5 / 5. The Lead reviewer
    ...    consolidates both reviews into a final publish decision.
    [Setup]    Start Actor Turn    reviewer3    eyebrow=Review process · 5 / 5
    ...    title=Lead reviewer    subtitle=Consolidating feedback and making the final decision
    Open Task    Consolidate review
    Human Click    label=publish
    Human Type    label=Coordinator Comments
    ...    Thanks both -- the location feedback supports publishing as is.
    Submit Task Form    Complete Review
    [Teardown]    End Actor Turn

Wrap Up In Cockpit History
    [Documentation]    Wait for the document to actually publish (driven by
    ...    the BPMN process, not this story), then show the completed
    ...    instance in Cockpit's History view.
    Wait For Workflow State    ${DOC_URL}    Published
    Show Completed Instance In History    ${PROCESS_KEY}
    Take Screenshot    ${DOCS_DIR}/review-process-cockpit-completed.png
    Go To    ${DOC_URL}
    Take Screenshot    ${DOCS_DIR}/review-process-published.png
    End Observer
