// Shared by the page filler and the details page: the saved profile's shape, importing it
// from a portfolio profile.json, and matching your answers to a form's options and questions.
// No DOM in here, so node can test it.
(function (root) {
  const DEFAULT_PROFILE = {
    personal: {
      firstName: "", middleName: "", lastName: "", email: "",
      phone: "", phoneCountry: "India", phoneCode: "+91", phoneType: "Mobile",
      address1: "", address2: "", city: "", state: "", postalCode: "", country: "India",
    },
    links: { linkedin: "", github: "", portfolio: "" },
    experience: [],  // {title, company, location, start: "2026-02", end: "" , current, description}
    education: [],   // {school, degree, field, gpa, start: "2022", end: "2026"}
    skills: [],
    languages: [{ language: "English", proficiency: "Fluent" }, { language: "Hindi", proficiency: "Native" }],
    answers: {
      source: "LinkedIn", previouslyWorked: "No", authorized: "Yes", sponsorship: "No",
      relocate: "Yes", noticePeriod: "Immediately", age18: "Yes", relatives: "No",
      nonCompete: "No", government: "No", currentCtc: "", expectedCtc: "",
      gender: "", veteran: "", disability: "", ethnicity: "",
    },
    custom: [],      // {q, a}: answers you've given (or that were learned from your own entries)
    settings: { overwrite: true, acceptTerms: true, learn: true, maxSkills: 15 },
  };

  const norm = (s) => String(s ?? "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "")
    .replace(/[’']/g, "").replace(/[^a-z0-9+]+/g, " ").trim();
  const tokens = (s) => norm(s).split(" ").filter(Boolean);

  function runAt(hay, needle) {
    outer: for (let i = 0; i + needle.length <= hay.length; i++) {
      for (let j = 0; j < needle.length; j++) if (hay[i + j] !== needle[j]) continue outer;
      return i;
    }
    return -1;
  }

  // The option that best fits the first candidate that fits any: exact, then the option starting
  // with it ("Yes, I am authorised"), then containing it ("India (+91)"). Whole words only, so
  // "No" never picks "Not applicable".
  function pick(options, candidates) {
    const opts = options.map((o) => ({ o, t: tokens(typeof o === "string" ? o : o.text) }));
    for (const c of [].concat(candidates).filter(Boolean)) {
      const ct = tokens(c);
      if (!ct.length) continue;
      const hit = opts.find((x) => x.t.join(" ") === ct.join(" "))
        || opts.find((x) => runAt(x.t, ct) === 0)
        || opts.find((x) => runAt(x.t, ct) > 0);
      if (hit) return hit.o;
    }
    return null;
  }

  // Ways a dropdown might word the same answer.
  const SYNONYMS = {
    immediately: ["Immediately", "Immediate", "Immediate joiner", "0 days", "0 Days", "Less than 15 days",
      "15 days or less", "Within 15 days", "0-15 days", "1-15 days", "15 days"],
    linkedin: ["LinkedIn", "LinkedIn Jobs", "Social Media", "Job Board"],
    mobile: ["Mobile", "Cell", "Mobile Phone", "Cell Phone", "Personal Mobile"],
    "prefer not": ["I do not wish to answer", "I don't wish to answer", "Decline to self identify",
      "Decline to answer", "Prefer not to say", "Prefer not to answer", "I prefer not to answer"],
  };

  function candidatesFor(value) {
    if (Array.isArray(value)) return value;
    const syn = SYNONYMS[norm(value)];
    return syn ? [value, ...syn] : [value];
  }

  const DEGREES = [
    [/^b\.?\s?e\b|bachelor of engineering/i, ["Bachelor of Engineering", "B.E.", "BE", "Bachelor of Engineering (BE)"]],
    [/^b\.?\s?tech|bachelor of technology/i, ["Bachelor of Technology", "B.Tech", "BTech", "B.Tech."]],
    [/^b\.?\s?sc|bachelor of science/i, ["Bachelor of Science", "B.Sc", "BSc", "BS"]],
    [/^bca|bachelor of computer app/i, ["Bachelor of Computer Applications", "BCA"]],
    [/^m\.?\s?tech|master of technology/i, ["Master of Technology", "M.Tech", "MTech"]],
    [/^m\.?\s?sc|master of science/i, ["Master of Science", "M.Sc", "MSc", "MS"]],
    [/^mca|master of computer app/i, ["Master of Computer Applications", "MCA"]],
  ];
  const GENERIC = { bachelor: ["Bachelor's Degree", "Bachelors Degree", "Bachelor's", "Bachelors", "Bachelor", "Undergraduate", "Graduate"],
    master: ["Master's Degree", "Masters Degree", "Master's", "Masters", "Master", "Postgraduate", "Post Graduate"] };

  // Workday dropdowns name degrees every way there is; try specific to generic.
  function degreeCandidates(degree) {
    for (const [re, names] of DEGREES) {
      if (re.test(degree)) return [degree, ...names, ...(/^m|master/i.test(degree) ? GENERIC.master : GENERIC.bachelor)];
    }
    return [degree, ...(/master|^m/i.test(degree) ? GENERIC.master : GENERIC.bachelor)];
  }

  // Questions every company asks in its own words. First match wins, so the narrow ones go first.
  const QUESTIONS = [
    [/(require|need).{0,60}(sponsor|visa)/, "sponsorship"],
    [/(authori[sz]ed|eligible|legally (able|permitted)|right|permission) to work|work (authori[sz]ation|permit)/, "authorized"],
    [/sponsor|visa status/, "sponsorship"],  // "...to work without sponsorship?" is the one above
    [/relocat/, "relocate"],
    [/notice period|how soon|earliest (start|joining)|available to (start|join)|joining time/, "noticePeriod"],
    [/18 years|at least 18|legal age|age of majority/, "age18"],
    [/current (ctc|salary|compensation|package)|present (ctc|salary)/, "currentCtc"],
    [/expected (ctc|salary|compensation|package)|salary expectation|desired (salary|compensation)/, "expectedCtc"],
    [/non.?compete|non.?solicit|restrictive covenant/, "nonCompete"],
    [/(relative|family member|related to).{0,80}(work|employ)|(work|employ).{0,80}(relative|family member)/, "relatives"],
    [/government (official|employee)|public official|politically exposed/, "government"],
    [/previously (been )?(employed|worked)|former (employee|worker)|worked (for|at) .{0,40}(before|previously)|previousworker/, "previouslyWorked"],
    [/how did you hear|referral source|source of (application|referral)/, "source"],
    [/\bgender\b|\bsex\b/, "gender"],
    [/veteran|armed forces|military service/, "veteran"],
    [/disabilit/, "disability"],
    [/ethnic|\brace\b/, "ethnicity"],
  ];

  // Your answer for a question, from what you've taught it first, then the standard answers.
  function answerFor(label, profile) {
    const t = tokens(label);
    if (!t.length) return null;
    for (const c of profile.custom || []) {
      const q = tokens(c.q);
      if (q.length && c.a !== "" && runAt(t, q) >= 0) return { value: c.a, why: "your answer" };
    }
    const text = t.join(" ");
    for (const [re, key] of QUESTIONS) {
      if (re.test(text)) {
        const v = profile.answers?.[key];
        return v ? { value: v, why: key } : { value: null, why: key };
      }
    }
    return null;
  }

  const plain = (s) => String(s || "").replace(/\*\*/g, "").trim();

  // A portfolio profile.json (the portfolio repo's format) to this profile, keeping everything the
  // portfolio doesn't publish (phone, address, answers) from what's already saved.
  function fromPortfolio(data, existing) {
    const base = merge(structuredClone(DEFAULT_PROFILE), existing || {});
    const p = data.profile || {};
    const names = String(p.name || "").trim().split(/\s+/);
    if (names[0]) {
      base.personal.firstName = names[0];
      base.personal.lastName = names.length > 1 ? names[names.length - 1] : "";
      base.personal.middleName = names.slice(1, -1).join(" ");
    }
    if (p.email) base.personal.email = p.email;
    const links = p.links || {};
    base.links.linkedin = links.linkedin || base.links.linkedin;
    base.links.github = links.github || base.links.github;
    base.links.portfolio = p.website || base.links.portfolio;

    base.experience = (data.experience || [])
      .filter((e) => (e.kind || "work") === "work" && e.on_resume !== false)
      .map((e) => ({
        title: e.role || "", company: e.org || "",
        location: e.location || "", start: e.start || "", end: e.end || "", current: !e.end,
        description: (e.highlights || []).map((h) => "• " + plain(h.text)).join("\n").slice(0, 2000),
      }));

    base.education = (data.education || [])
      .filter((e) => !/class|grade|cbse|icse|high school|secondary/i.test(e.degree || ""))
      .map((e) => {
        const m = String(e.degree || "").match(/^((?:[BM]\.?\s?(?:E|Tech|Sc|S|A|Com)\.?)|BCA|MCA|MBA|PhD)\s+(.*)$/i);
        return {
          school: e.institution || "", degree: m ? m[1] : e.degree || "", field: m ? m[2] : "",
          gpa: (String(e.score || "").match(/\d+(\.\d+)?/) || [""])[0],
          start: String(e.start || "").slice(0, 4), end: String(e.end || "").slice(0, 4),
        };
      });

    const groups = (data.skills && data.skills.groups) || {};
    const skills = Object.values(groups).flat();
    if (skills.length) base.skills = [...new Set(skills)];
    return base;
  }

  // Saved profiles from older versions get any fields added since.
  function merge(into, from) {
    for (const [k, v] of Object.entries(from || {})) {
      if (v && typeof v === "object" && !Array.isArray(v) && into[k] && typeof into[k] === "object" && !Array.isArray(into[k])) merge(into[k], v);
      else into[k] = v;
    }
    return into;
  }

  const withDefaults = (saved) => merge(structuredClone(DEFAULT_PROFILE), saved || {});

  const api = { DEFAULT_PROFILE, norm, tokens, pick, candidatesFor, degreeCandidates, answerFor, fromPortfolio, withDefaults, runAt };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.WDMatch = api;
})(typeof self !== "undefined" ? self : this);
