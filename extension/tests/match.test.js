// node --test extension/tests
const test = require("node:test");
const assert = require("node:assert/strict");
const M = require("../src/match.js");

test("picks whole words, not prefixes", () => {
  assert.equal(M.pick(["Not applicable", "No", "Yes"], ["No"]), "No");
  assert.equal(M.pick(["Not applicable", "Yes"], ["No"]), null);
  assert.equal(M.pick(["Yes, I am authorised to work in India", "No"], ["Yes"]), "Yes, I am authorised to work in India");
  assert.equal(M.pick(["British Indian Ocean Territory", "India"], ["India"]), "India");
  assert.equal(M.pick(["Indonesia (+62)", "India (+91)"], ["+91"]), "India (+91)");
});

test("tries candidates in order", () => {
  const degrees = ["High School", "Bachelor's Degree", "Master's Degree"];
  assert.equal(M.pick(degrees, M.degreeCandidates("B.E.")), "Bachelor's Degree");
  assert.equal(M.pick([...degrees, "Bachelor of Engineering"], M.degreeCandidates("B.E.")), "Bachelor of Engineering");
  assert.equal(M.pick(["MCA", "Master's Degree"], M.degreeCandidates("MCA")), "MCA");
  assert.equal(M.pick(["15 days or less", "30 days", "60 days"], M.candidatesFor("Immediately")), "15 days or less");
});

test("standard questions in their many wordings", () => {
  const p = M.withDefaults({});
  const ask = (q) => (M.answerFor(q, p) || {}).value;
  assert.equal(ask("Are you legally authorized to work in India?"), "Yes");
  assert.equal(ask("Are you legally eligible to work in the country where this job is located without sponsorship?"), "Yes");
  assert.equal(ask("Will you now or in the future require visa sponsorship to work?"), "No");
  assert.equal(ask("Do you need sponsorship to be authorised to work in India?"), "No");
  assert.equal(ask("Are you willing to relocate?"), "Yes");
  assert.equal(ask("What is your notice period?"), "Immediately");
  assert.equal(ask("Do you have any relatives currently working at Acme?"), "No");
  assert.equal(ask("Are you bound by a non-compete agreement?"), "No");
  assert.equal(ask("Have you ever been convicted of a crime?"), undefined);
  assert.equal(M.answerFor("Gender", p).value, null);  // known question, no saved answer: left for you
});

test("your own answers win, and a phrase answers any question containing it", () => {
  const p = M.withDefaults({ custom: [{ q: "convicted", a: "No" }, { q: "What is your notice period?", a: "30 days" }] });
  assert.equal(M.answerFor("Have you ever been convicted of a criminal offence?", p).value, "No");
  assert.equal(M.answerFor("What is your notice period?", p).value, "30 days");
});

test("imports a portfolio profile.json and keeps private details", () => {
  const data = {
    profile: { name: "Vanshaj Raghuvanshi", email: "v@example.com", website: "https://v.dev",
      links: { github: "https://github.com/v", linkedin: "https://linkedin.com/in/v" } },
    experience: [
      { org: "DXFactor", role: "Software Engineer Intern", kind: "work", location: "Ahmedabad, Gujarat", start: "2026-02", end: "2026-06",
        highlights: [{ text: "Built a layer for **3 LLM providers**." }, { text: "Shipped RAG." }] },
      { org: "CodeClause", role: "AI Intern", kind: "work", on_resume: false, start: "2024-06", end: "2024-07" },
      { org: "Thapar Computer Club", role: "Lead", kind: "leadership", start: "2023-01" },
    ],
    education: [
      { institution: "Thapar Institute of Engineering and Technology", degree: "B.E. Computer Science", score: "CGPA 9.00/10", start: "2022-09", end: "2026-07" },
      { institution: "Delhi Public School", degree: "Class XII (CBSE)", end: "2021-07" },
    ],
    skills: { groups: { Languages: ["Python", "Go"], Backend: ["FastAPI", "Python"] } },
  };
  const saved = M.withDefaults({ personal: { phone: "98765 43210", city: "Dehradun" }, answers: { expectedCtc: "12 LPA" } });
  const p = M.fromPortfolio(data, saved);
  assert.deepEqual([p.personal.firstName, p.personal.middleName, p.personal.lastName], ["Vanshaj", "", "Raghuvanshi"]);
  assert.equal(p.personal.phone, "98765 43210");
  assert.equal(p.personal.city, "Dehradun");
  assert.equal(p.answers.expectedCtc, "12 LPA");
  assert.equal(p.answers.authorized, "Yes");
  assert.equal(p.links.portfolio, "https://v.dev");
  assert.equal(p.experience.length, 1);
  assert.deepEqual(p.experience[0], { title: "Software Engineer Intern", company: "DXFactor", location: "Ahmedabad, Gujarat",
    start: "2026-02", end: "2026-06", current: false, description: "• Built a layer for 3 LLM providers.\n• Shipped RAG." });
  assert.deepEqual(p.education, [{ school: "Thapar Institute of Engineering and Technology", degree: "B.E.", field: "Computer Science",
    gpa: "9.00", start: "2022", end: "2026" }]);
  assert.deepEqual(p.skills, ["Python", "Go", "FastAPI"]);
});
