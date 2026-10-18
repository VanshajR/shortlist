# Shortlist Fill

A Chrome extension that fills Workday job applications from details you save once. Workday runs the
careers sites of NVIDIA, Adobe, Mastercard, Intel, Cisco, Salesforce and thousands more, and each
one asks for the same things page after page.

On any Workday application, press **Fill this page** (bottom right), the toolbar button, or
<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>F</kbd>. It fills:

- **My Information**: name, email, phone (type, country code, number), address, how you heard about the role, whether you've worked there before
- **My Experience**: adds and fills an entry for each role (title, company, location, dates, "I currently work here", description) and each degree (school, degree, field of study, GPA, years), plus websites, LinkedIn and skills, and uploads your resume
- **Application Questions** and **Voluntary Disclosures**: work authorisation, sponsorship, relocation, notice period, CTC, relatives at the company, non-competes, gender, disability and veteran status, the terms box, and anything you've answered before

Then it outlines in amber whatever still needs you and lists it, so you can jump straight there.
It never presses Save and Continue or Submit.

**It learns.** Answer a question it didn't know, press Save and Continue, and the answer is kept
for the next application, matched by the question's wording. You can edit or remove these answers
under *Your answers* on the details page, or add your own: a short phrase like `convicted` answers
any question containing it.

## Install

1. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick this `extension` folder.
2. The details page opens. Import your portfolio's `profile.json` (or fill the sections in), then add
   your phone, address, standard answers and resume PDF. Everything is saved as you type.

Your details stay in this browser (`chrome.storage.local`); nothing is sent anywhere. The only
network request the extension makes is the import you ask for.

## How it recognises fields

Every company's Workday is the same React app, so fields are found by Workday's own
`data-automation-id` and id naming (`legalNameSection_firstName` in older sites,
`name--legalName--firstName` in newer ones) and by their visible labels, then filled the way
typing would fill them. Entries are found by Workday's section headings ("Work Experience 2"),
and the Add button for each section is pressed until there's one per role. Questions are matched
by wording (`src/match.js`), and dropdown answers by whole words, so "No" never picks "Not applicable".

## Tests

```bash
node --test "extension/tests/*.test.js"   # matching and import
pytest extension/tests                    # loads the extension in Chromium against a stand-in Workday form
```

The end-to-end test serves `tests/fixture/apply.html`, a React imitation of a Workday application
(controlled inputs, dropdown lists in portals, search pickers, keystroke-only date boxes, entry
sections), at a `myworkdayjobs.com` address, so the real content scripts inject. It checks what
React received. It needs Playwright with its Chromium installed.
