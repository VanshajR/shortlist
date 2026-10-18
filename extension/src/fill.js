// Fills the Workday page in front of you from your saved profile, then points at what's left.
// It never presses Save and Continue or Submit: you look over each page and press them.
(function () {
  const M = self.WDMatch;
  const D = self.WDDom;

  const SECTIONS = {
    experience: /work experience|employment|work history|professional experience/i,
    education: /^education/i,
    websites: /^websites?$|web address/i,
    languages: /^languages?$/i,
  };

  const monthYear = (ym) => {
    const [y, m] = String(ym || "").split("-");
    return y ? { year: y, month: m ? Number(m) : undefined } : null;
  };
  const today = () => {
    const d = new Date();
    return { month: d.getMonth() + 1, day: d.getDate(), year: d.getFullYear() };
  };
  const fullName = (p) => [p.personal.firstName, p.personal.middleName, p.personal.lastName].filter(Boolean).join(" ");
  const websites = (p) => [p.links.github, p.links.portfolio].filter(Boolean);

  // Per-entry fields: [pattern on the field's key, value from the entry]. A string fills a text
  // box; an array is candidates for a dropdown or picker; an object is a date; true/false a checkbox.
  const ENTRY = {
    experience: [
      [/currentlyworkhere|currently work/, (e) => !!e.current],
      [/jobtitle|job title|position title|\btitle\b/, (e) => e.title],
      [/companyname|company|employer|organi[sz]ation/, (e) => e.company],
      [/--location|\blocation\b|\bcity\b/, (e) => e.location],
      [/startdate|\bfrom\b|start date/, (e) => monthYear(e.start)],
      [/enddate|\bto\b|end date/, (e) => (e.current ? null : monthYear(e.end))],
      [/roledescription|description|responsibilit/, (e) => e.description],
    ],
    education: [
      [/schoolname|school|university|institution|college/, (e) => [e.school]],
      [/degree/, (e) => M.degreeCandidates(e.degree)],
      [/fieldofstudy|field of study|major|discipline|specialization/, (e) => [e.field, "Computer Science", "Computer Science and Engineering", "Computer Engineering"]],
      [/gradeaverage|gpa|grade|cgpa|overall result/, (e) => e.gpa],
      [/firstyearattended|\bfrom\b|start/, (e) => (e.start ? { year: e.start } : null)],
      [/lastyearattended|\bto\b|graduat|\bend\b|expected/, (e) => (e.end ? { year: e.end } : null)],
    ],
    websites: [[/url|website|web address/, (u) => u]],
    languages: [
      [/native|fluent in/, (l) => /native/i.test(l.proficiency)],
      [/proficien|reading|writing|speaking|comprehension|overall/, (l) => (/native/i.test(l.proficiency)
        ? ["Native", "Native or Bilingual", "Native or bilingual proficiency", "Fluent", "Expert", "Advanced"]
        : [l.proficiency, "Fluent", "Advanced", "Professional working proficiency", "Full professional proficiency", "Expert"])],
      [/\blanguage\b/, (l) => [l.language]],
    ],
  };

  // One-off fields, matched on the field's key (ids + label). Order matters: narrow first.
  const SINGLE = [
    [/extension|preferred name|local name|phonetic/, () => null],
    [/legalname--firstname|legalnamesection_firstname|first name|given name/, (p) => p.personal.firstName],
    [/legalname--middlename|legalnamesection_middlename|middle name/, (p) => p.personal.middleName || null],
    [/legalname--lastname|legalnamesection_lastname|last name|family name|surname/, (p) => p.personal.lastName],
    [/countryphonecode|country phone code|phone code|dialing code/, (p) => [`${p.personal.phoneCountry} (${p.personal.phoneCode})`, p.personal.phoneCode, p.personal.phoneCountry]],
    [/phonetype|phone-device-type|device type|phone type/, (p) => M.candidatesFor(p.personal.phoneType)],
    [/phonenumber|phone-number|phone number|mobile|\bphone\b|contact number/, (p) => p.personal.phone.replace(/^\+?91[\s-]?/, "")],
    [/\bemail\b|e-mail/, (p) => p.personal.email],
    [/addressline1|address line 1|street/, (p) => p.personal.address1],
    [/addressline2|address line 2/, (p) => p.personal.address2 || null],
    [/address--city|addresssection_city|\bcity\b|town/, (p) => p.personal.city],
    [/countryregion|\bstate\b|province/, (p) => [p.personal.state]],
    [/postalcode|postal|zip|pin ?code|pincode/, (p) => p.personal.postalCode],
    [/country--country|countrydropdown|\bcountry\b/, (p) => [p.personal.country]],
    [/linkedin/, (p) => p.links.linkedin],
    [/github/, (p) => p.links.github],
    [/portfolio|personal website|website url|\bblog\b/, (p) => p.links.portfolio],
    [/source--source|sourcedropdown|how did you hear|\bsource\b/, (p) => M.candidatesFor(p.answers.source)],
    [/candidateispreviousworker|previousworker/, (p) => [p.answers.previouslyWorked]],
    [/datesignedon|date signed|today.?s date/, () => today()],
    [/selfidentifieddisabilitydata--name|\bfull name\b|your name|signature/, (p) => fullName(p)],
    [/acceptterms|termsandconditions|agreementcheckbox|terms and conditions|i (have read|agree|acknowledge|consent|certify)|privacy (policy|notice)/,
      (p) => (p.settings.acceptTerms ? true : null)],
    [/skills--skills|\bskills?\b/, (p) => ({ many: p.skills.slice(0, p.settings.maxSkills) })],
  ];

  const sectionOf = (f) => Object.keys(SECTIONS).find((s) => SECTIONS[s].test(f.section)) || "single";

  function itemsFor(section, p) {
    return section === "websites" ? websites(p) : p[section] || [];
  }

  // What this field should get: { value, how } or null when it isn't ours to fill.
  function valueFor(f, p) {
    const section = sectionOf(f);
    if (section !== "single") {
      const item = itemsFor(section, p)[f.entry];
      if (item === undefined) return null;
      for (const [re, get] of ENTRY[section]) if (re.test(f.key)) return { value: get(item), how: section };
      return null;
    }
    // A long label is a question in a sentence ("please state your notice period"): match the
    // one-off fields on its ids alone, and leave the wording to the question rules.
    const key = f.label.length > 40 ? f.key.slice(0, f.key.length - f.label.length) : f.key;
    for (const [re, get] of SINGLE) if (re.test(key)) return { value: get(p), how: "profile" };
    const a = M.answerFor(f.label, p);
    if (a) return { value: a.value ? M.candidatesFor(a.value) : null, how: a.why, question: true };
    if (f.label.length > 12) return { value: null, how: "unknown", question: true };
    return null;
  }

  async function apply(f, value, p) {
    if (value == null || value === "") return false;
    if (value.many && f.kind !== "prompt") return false;
    const has = D.valueOf(f);
    if (has && !p.settings.overwrite && f.kind !== "checkbox") return true;
    switch (f.kind) {
      case "text": {
        if (typeof value === "object" && !Array.isArray(value)) {
          return D.setText(f.el, value.month ? `${String(value.month).padStart(2, "0")}/${value.year}` : value.year);
        }
        return D.setText(f.el, Array.isArray(value) ? value[0] : value);
      }
      case "dropdown": return D.chooseDropdown(f.el, [].concat(value));
      case "select": return D.chooseSelect(f.el, [].concat(value));
      case "radio": return D.chooseRadio(f, [].concat(value));
      case "checkbox": return typeof value === "boolean" ? D.setCheckbox(f.el, value) : D.setCheckbox(f.el, /^(yes|true)$/i.test([].concat(value)[0]));
      case "date": return typeof value === "object" && !Array.isArray(value) ? D.setDate(f, value) : false;
      case "prompt": {
        if (value.many) {
          let any = false;
          const have = D.valueOf(f).toLowerCase();
          for (const s of value.many) if (!have.includes(s.toLowerCase())) any = (await D.choosePrompt(f.el, [s], { many: true })) || any;
          return any || !!have;
        }
        return D.choosePrompt(f.el, [].concat(value));
      }
    }
    return false;
  }

  // Give each section as many entries as the profile has, pressing its Add button.
  async function addEntries(p) {
    for (const [section, re] of Object.entries(SECTIONS)) {
      const want = itemsFor(section, p).length;
      for (let n = D.entryCount(re); n < want; n++) {
        const add = D.addButton(re);
        if (!add) break;
        D.click(add);
        if (!(await D.waitFor(() => D.entryCount(re) > n, 3000))) break;
      }
    }
  }

  async function uploadResume(resume, report) {
    if (!resume) return;
    const input = document.querySelector('input[type="file"][data-automation-id="file-upload-input-ref"], input[type="file"]');
    if (!input) return;
    const done = document.querySelector('[data-automation-id="file-upload-successful"], [data-automation-id="fileName"]');
    if (done || (input.files && input.files.length)) return;
    D.upload(input, resume);
    report.filled.push("Resume: " + resume.name);
    await D.sleep(800);
  }

  let watching = [];

  async function fillPage(profile, resume) {
    const p = M.withDefaults(profile);
    const report = { filled: [], missed: [], unknown: [] };
    await addEntries(p);
    await uploadResume(resume, report);

    // "I currently work here" first: ticking it removes the end date.
    const all = D.fields().sort((a, b) => (b.key.includes("currently") ? 1 : 0) - (a.key.includes("currently") ? 1 : 0));
    const questions = [];
    for (const f of all) {
      if (f.kind !== "date" && !f.el.isConnected) continue;
      if (f.kind === "date" && !Object.values(f.parts).some((el) => el.isConnected && D.visible(el))) continue;
      const v = valueFor(f, p);
      if (!v) continue;
      if (v.question) questions.push(f);
      let ok = false;
      try { ok = await apply(f, v.value, p); } catch (e) { console.warn("[shortlist-fill]", f.label, e); }
      if (ok) report.filled.push(f.label || f.key);
      else if (v.value == null && v.question) report.unknown.push(f);
    }

    // What still needs you: required and empty, whatever the reason.
    const after = D.fields();
    for (const f of after) {
      if (D.isRequired(f) && !D.valueOf(f)) report.missed.push(f);
    }
    watching = questions;
    return report;
  }

  // Answers you give yourself to questions it didn't know are kept when you press Save and
  // Continue, so the next company's form gets them filled.
  // Called from the button's click, before Workday swaps the page out: the answers are read
  // right away, and only saving waits.
  function learn() {
    const given = watching.map((f) => ({ q: f.label, a: D.valueOf(f) }))
      .filter((g) => g.a && g.q && g.q.length <= 400);
    watching = [];
    return given.length ? remember(given) : Promise.resolve(0);
  }

  async function remember(given) {
    const p = M.withDefaults((await chrome.storage.local.get("profile")).profile);
    if (!p.settings.learn) return 0;
    let n = 0;
    for (const g of given) {
      if (M.answerFor(g.q, p)?.value) continue;
      p.custom.push({ ...g, learned: location.hostname.split(".")[0] });
      n++;
    }
    if (n) await chrome.storage.local.set({ profile: p });
    return n;
  }

  self.WDFill = { fillPage, learn, valueFor, sectionOf };
})();
