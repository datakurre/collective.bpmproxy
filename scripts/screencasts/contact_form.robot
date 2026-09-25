*** Settings ***
Documentation     The contact-form scenario: Reception publishes a Bpm Proxy
...               page, two anonymous Visitors submit independent inquiries
...               (concurrent process instances against one page), Reception
...               replies to one and delegates the other to a Specialist.
...
...               Equivalent to scripts/scenarios/e2e_contact_form.py (see
...               collective/collective.bpmproxy#10), built on the generic
...               engine (#1-#7) and bpmproxy.resource (#8).
Library           screencast.Screencast    take_dir=${TAKE_DIR}    record=${RECORD}
Resource          resources/bpmproxy.resource


*** Variables ***
${DOCS_DIR}         ${CURDIR}/../../docs
${ASSETS_DIR}       examples/contact-form
${PROCESS_KEY}      example-contact-form
${PROXY_PATH}       contact-us
${PROXY_URL}        ${BASE_URL}/${PROXY_PATH}
${MAILPIT_URL}      http://localhost:8025


*** Tasks ***
Prepare The Take
    [Documentation]    Unrecorded: deploy this scenario's process/form
    ...    assets and remove any leftover demo content from a previous run.
    Prepare Fixtures    ${ASSETS_DIR}    contact-us    plone-conference-2027-unveiled

Start Observing In Cockpit
    [Documentation]    Cockpit starts observing before Reception creates the
    ...    proxy, so the first instance appearing needs no re-entry.
    ${state}=    Log In To Cockpit
    Start Observer    cockpit    ${COCKPIT_URL}/    storage_state=${state}
    Open Process In Cockpit    ${PROCESS_KEY}

Reception Creates And Publishes The Proxy
    [Documentation]    Contact form · 1 / 6.
    [Setup]    Start Actor Turn    reception    eyebrow=Contact form · 1 / 6
    ...    title=Reception    subtitle=Creating and publishing the public Contact Us page
    Go To    ${BASE_URL}
    Human Click    role=link[name="Add new…"]
    Human Click    role=link[name="Bpm Proxy"s]
    Human Type    \#form-widgets-IBasic-title    Contact us
    Select Option    \#form-widgets-process_definition_key    ${PROCESS_KEY}
    Check    \#form-widgets-diagram_enabled-0
    Human Click    \#form-buttons-save
    Go To    ${PROXY_URL}
    Wait Until Visible    role=link[name="Process diagram"s]
    Human Click    role=link[name="Process diagram"s]
    Human Click    role=link[name="State: Private"]
    Human Click    a[href*="workflow_action=publish"]    index=-1
    Take Screenshot    ${DOCS_DIR}/contact-form-proxy-created.png
    [Teardown]    End Actor Turn

First Visitor Submits
    [Documentation]    Contact form · 2 / 6. Anonymous: no login.
    [Setup]    Start Actor Turn    visitor-1    eyebrow=Contact form · 2 / 6
    ...    title=Visitor    subtitle=Submitting the venue availability inquiry
    ...    anonymous=${True}
    Go To    ${PROXY_URL}
    Wait Until Visible    \#collective-bpmproxy-form .fjs-container
    Take Screenshot    ${DOCS_DIR}/contact-form-start-form.png
    Human Type    label=Your Name    Conference visitor
    Human Type    label=Your Email    venue@example.com
    Human Type    label=Subject    Venue availability for a conference
    Paste Text    label=Message    Could you tell me whether the venue is available for a conference?
    Human Click    role=button[name="Send message"]
    [Teardown]    End Actor Turn

Cockpit Shows The First Instance
    Open Process In Cockpit    ${PROCESS_KEY}

Second Visitor Submits
    [Documentation]    Contact form · 3 / 6. A second, independent
    ...    process instance against the same proxy page.
    [Setup]    Start Actor Turn    visitor-2    eyebrow=Contact form · 3 / 6
    ...    title=Visitor    subtitle=Submitting the sponsorship inquiry
    ...    anonymous=${True}
    Go To    ${PROXY_URL}
    Wait Until Visible    \#collective-bpmproxy-form .fjs-container
    Human Type    label=Your Name    Sponsorship visitor
    Human Type    label=Your Email    sponsor@example.com
    Human Type    label=Subject    Sponsorship options
    Paste Text    label=Message    Please send information about sponsorship options and packages.
    Human Click    role=button[name="Send message"]
    [Teardown]    End Actor Turn

Cockpit Shows Both Instances
    Open Process In Cockpit    ${PROCESS_KEY}
    Enter Latest Process Instance
    Take Screenshot    ${DOCS_DIR}/contact-form-cockpit-concurrent-instances.png

Reception Replies To The First Inquiry
    [Documentation]    Contact form · 4 / 6.
    [Setup]    Start Actor Turn    reception    eyebrow=Contact form · 4 / 6
    ...    title=Reception    subtitle=Replying to the venue inquiry
    Open Task    Review contact    base_url=${PROXY_URL}
    Take Screenshot    ${DOCS_DIR}/contact-form-review-tasks.png
    Human Click    label=Reply to sender by email
    Paste Text    label=Reply message
    ...    Thank you for your inquiry. The venue is available, and we would be happy to discuss dates and room arrangements.
    Human Click    role=button[name="Submit decision"]
    [Teardown]    End Actor Turn

Reply Mail Is Delivered
    Wait For Mail    Re: Venue availability for a conference    mailpit_url=${MAILPIT_URL}
    Open Process In Cockpit    ${PROCESS_KEY}
    Enter Latest Process Instance

Reception Delegates The Second Inquiry
    [Documentation]    Contact form · 5 / 6.
    [Setup]    Start Actor Turn    reception    eyebrow=Contact form · 5 / 6
    ...    title=Reception    subtitle=Delegating the sponsorship inquiry to a specialist
    Open Task    Review contact    base_url=${PROXY_URL}
    Human Click    label=Delegate to specific user
    Human Type    label=Delegate to user (Plone username)    specialist
    Human Click    role=button[name="Submit decision"]
    [Teardown]    End Actor Turn

Specialist Replies To The Delegated Inquiry
    [Documentation]    Contact form · 6 / 6.
    [Setup]    Start Actor Turn    specialist    eyebrow=Contact form · 6 / 6
    ...    title=Specialist    subtitle=Replying to the delegated sponsorship inquiry
    Open Task    Handle delegated contact    base_url=${PROXY_URL}
    Take Screenshot    ${DOCS_DIR}/contact-form-delegated-task.png
    Human Click    label=Reply to sender by email
    Paste Text    label=Reply message
    ...    Thank you for asking about sponsorship. I have attached our current sponsorship options and would be glad to answer any questions.
    Human Click    role=button[name="Submit decision"]
    [Teardown]    End Actor Turn

Wrap Up In Cockpit History
    [Documentation]    Both instances are now complete: show the latest in
    ...    Cockpit's History view, then screenshot Mailpit's own inbox.
    Wait For Mail    Re: Sponsorship options    mailpit_url=${MAILPIT_URL}
    Show Completed Instance In History    ${PROCESS_KEY}
    Take Screenshot    ${DOCS_DIR}/contact-form-cockpit-completed.png
    End Observer
    Start Scratch Context    ${MAILPIT_URL}
    Take Screenshot    ${DOCS_DIR}/contact-form-mailpit.png
    End Scratch Context
