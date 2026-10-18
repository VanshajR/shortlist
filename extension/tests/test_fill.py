"""The extension, loaded into Chromium for real, filling a stand-in Workday application served at
a myworkdayjobs.com address (so the content scripts inject as they would on a company's site).

    pytest extension/tests            # needs playwright and its Chromium; reaches unpkg for React
"""
import base64
import json
import os
import pathlib
import tempfile

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

HERE = pathlib.Path(__file__).parent
EXT = HERE.parent
FIXTURE = HERE / "fixture"
SITE = "https://acme.wd3.myworkdayjobs.com/en-US/External/job/Bengaluru/Software-Engineer_R123"

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PROFILE = {
    "personal": {"firstName": "Vanshaj", "middleName": "", "lastName": "Raghuvanshi", "email": "v@example.com",
                 "phone": "+91 98765 43210", "phoneCountry": "India", "phoneCode": "+91", "phoneType": "Mobile",
                 "address1": "12 Rajpur Road", "address2": "", "city": "Dehradun", "state": "Uttarakhand",
                 "postalCode": "248001", "country": "India"},
    "links": {"linkedin": "https://www.linkedin.com/in/someone/", "github": "https://github.com/someone",
              "portfolio": "https://someone.dev"},
    "experience": [
        {"title": "Software Engineer Intern", "company": "DXFactor", "location": "Ahmedabad", "start": "2026-02",
         "end": "2026-06", "current": False, "description": "• Built a routing layer"},
        {"title": "AI Intern", "company": "DRDO", "location": "Dehradun", "start": "2025-06", "end": "",
         "current": True, "description": "• Image completion"},
    ],
    "education": [{"school": "Thapar Institute of Engineering and Technology", "degree": "B.E.",
                   "field": "Computer Science", "gpa": "9.00", "start": "2022", "end": "2026"}],
    "skills": ["Python", "FastAPI", "Kubernetes", "PostgreSQL"],
    "answers": {"source": "LinkedIn", "previouslyWorked": "No", "authorized": "Yes", "sponsorship": "No",
                "relocate": "Yes", "noticePeriod": "Immediately"},
    "custom": [],
    "settings": {"overwrite": True, "acceptTerms": True, "learn": True, "maxSkills": 15},
}


def chrome():
    root = pathlib.Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or pathlib.Path.home() / "AppData/Local/ms-playwright")
    found = sorted(root.glob("chromium-*/chrome-*/chrome*"))
    found = [p for p in found if p.name in ("chrome.exe", "chrome")]
    return str(found[-1]) if found else None


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p, tempfile.TemporaryDirectory() as profile_dir:
        ctx = p.chromium.launch_persistent_context(
            profile_dir, executable_path=chrome(), headless=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        ctx.route("https://*.myworkdayjobs.com/**", lambda route: route.fulfill(
            path=FIXTURE / ("legacy.html" if "legacy" in route.request.url else "apply.html"), content_type="text/html"))
        worker = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
        for page in ctx.pages:  # the details page opens itself on install
            if page.url.startswith("chrome-extension://"):
                page.close()
        worker.evaluate("p => chrome.storage.local.set(p)", {"profile": PROFILE, "resume": {
            "name": "resume.pdf", "type": "application/pdf", "size": len(PDF), "data": base64.b64encode(PDF).decode()}})
        yield ctx, worker
        ctx.close()


def fill(page):
    page.locator("#shortlist-fill button.fill").click()
    page.wait_for_function("() => { const b = document.querySelector('#shortlist-fill').shadowRoot.querySelector('button.fill');"
                           " return !b.disabled && b.textContent.includes('Fill this page') }", timeout=60000)
    return page.locator("#shortlist-fill .panel").inner_text()


def state(page):
    return page.evaluate("() => window.__state")


def test_fills_a_whole_application(browser):
    ctx, worker = browser
    page = ctx.new_page()
    page.goto(SITE + "/apply/applyManually")
    page.wait_for_selector("#shortlist-fill button.fill")
    panel = fill(page)
    s = state(page)

    assert s["name--legalName--firstName"] == "Vanshaj"
    assert s["name--legalName--lastName"] == "Raghuvanshi"
    assert s["name--legalName--middleName"] == ""
    assert s["email"] == "v@example.com"
    assert s["address--addressLine1"] == "12 Rajpur Road"
    assert s["address--city"] == "Dehradun"
    assert s["address--countryRegion"] == "Uttarakhand"
    assert s["address--postalCode"] == "248001"
    assert s["country--country"] == "India"  # not British Indian Ocean Territory
    assert s["phoneNumber--phoneType"] == "Mobile"
    assert s["phoneNumber--countryPhoneCode"] == "India (+91)"
    assert s["phoneNumber--phoneNumber"] == "98765 43210"
    assert s["phoneNumber--extension"] == ""
    assert s["source--source"] == "LinkedIn"
    assert s["candidateIsPreviousWorker"] == "No"

    assert s["Work Experience#count"] == 2
    jobs = sorted({k.split("--")[0] for k in s if k.startswith("workExperience-")})
    first, second = (f"{j}--" for j in jobs)
    assert s[first + "jobTitle"] == "Software Engineer Intern"
    assert s[first + "companyName"] == "DXFactor"
    assert s[first + "location"] == "Ahmedabad"
    assert (s[first + "startDate-month"], s[first + "startDate-year"]) == ("02", "2026")
    assert (s[first + "endDate-month"], s[first + "endDate-year"]) == ("06", "2026")
    assert s[first + "roleDescription"] == "• Built a routing layer"
    assert s[second + "currentlyWorkHere"] is True
    assert second + "endDate-year" not in s or s[second + "endDate-year"] == ""
    assert s[second + "startDate-year"] == "2025"

    assert s["Education#count"] == 1
    edu = next(k.split("--")[0] for k in s if k.startswith("education-")) + "--"
    assert s[edu + "schoolName"] == "Thapar Institute of Engineering and Technology"
    assert s[edu + "degree"] == "Bachelor of Engineering"
    assert s[edu + "fieldOfStudy"] == "Computer Science"
    assert s[edu + "gradeAverage"] == "9.00"
    assert (s[edu + "firstYearAttended-year"], s[edu + "lastYearAttended-year"]) == ("2022", "2026")

    assert s["Websites#count"] == 2
    assert sorted(v for k, v in s.items() if k.startswith("webAddress-")) == ["https://github.com/someone", "https://someone.dev"]
    assert s["socialNetworkAccounts--linkedInAccount"] == "https://www.linkedin.com/in/someone/"
    assert s["skills--skills"] == ["Python", "FastAPI", "PostgreSQL"]  # Kubernetes isn't offered: skipped
    assert s["resume"] == f"resume.pdf:{len(PDF)}"

    assert s["primaryQuestionnaire--q1"] == "Yes"
    assert s["primaryQuestionnaire--q2"] == "No"
    assert s["primaryQuestionnaire--q3"] == "Immediately"
    assert s["primaryQuestionnaire--q4"] == ""  # it doesn't know: left for me
    assert s["primaryQuestionnaire--q5"] == "Yes"
    assert s["termsAndConditions--acceptTermsAndAgreements"] is True

    assert "convicted" in panel and "Why do you want" in panel
    assert "First Name" not in panel

    fill(page)  # pressing it again changes nothing and adds no entries
    again = state(page)
    assert again["Work Experience#count"] == 2 and again["Websites#count"] == 2
    assert again == s


def test_remembers_an_answer_i_gave(browser):
    ctx, worker = browser
    page = ctx.new_page()
    page.goto(SITE + "/apply/applyManually")
    page.wait_for_selector("#shortlist-fill button.fill")
    fill(page)
    page.click("#primaryQuestionnaire--q4")
    page.click("[role=listbox] [role=option]:text-is('No')")
    page.click("[data-automation-id=pageFooterNextButton]")
    page.wait_for_function("() => document.querySelector('#shortlist-fill').shadowRoot.textContent.includes('Remembered 1 answer')")
    custom = worker.evaluate("() => chrome.storage.local.get('profile').then(s => s.profile.custom)")
    assert custom == [{"q": "Have you ever been convicted of a criminal offence?", "a": "No", "learned": "acme"}]

    page.reload()
    page.wait_for_selector("#shortlist-fill button.fill")
    panel = fill(page)
    assert state(page)["primaryQuestionnaire--q4"] == "No"
    assert "convicted" not in panel


def test_older_workday_markup(browser):
    ctx, _ = browser
    page = ctx.new_page()
    page.goto("https://acme.wd1.myworkdayjobs.com/legacy/apply")
    page.wait_for_selector("#shortlist-fill button.fill")
    fill(page)
    values = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('[data-automation-id]')]
        .filter(e => 'value' in e && e.type !== 'radio').map(e => [e.dataset.automationId, e.value]))""")
    assert values["legalNameSection_firstName"] == "Vanshaj"
    assert values["legalNameSection_lastName"] == "Raghuvanshi"
    assert values["addressSection_city"] == "Dehradun"
    assert values["phone-number"] == "98765 43210"
    assert page.eval_on_selector("[data-automation-id=phone-device-type]", "s => s.value") == "Mobile"
    assert page.is_checked("#pw-no")


def test_details_page_saves_what_i_type(browser):
    ctx, worker = browser
    ext_id = worker.url.split("/")[2]
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"chrome-extension://{ext_id}/options.html")
    assert page.input_value("[data-path='personal.firstName']") == "Vanshaj"
    assert page.locator("#experience .item").count() == 2
    page.fill("[data-path='personal.city']", "Bengaluru")
    page.wait_for_function("() => document.querySelector('#status').textContent === 'Saved'")
    saved = worker.evaluate("() => chrome.storage.local.get('profile').then(s => s.profile.personal.city)")
    assert saved == "Bengaluru"
    assert "resume.pdf" in page.inner_text("#resume-name")
    assert not errors
    worker.evaluate("p => chrome.storage.local.set({profile: p})", PROFILE)
