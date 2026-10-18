// The details page: everything binds to one profile object, saved to chrome.storage as you type.
const M = self.WDMatch;
let profile;
let timer;

const $ = (s) => document.querySelector(s);
const status = (msg, err = false) => {
  const el = $("#status");
  el.textContent = msg;
  el.className = err ? "err" : "";
};

const getPath = (obj, path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
function setPath(obj, path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  keys.reduce((o, k) => (o[k] ??= {}), obj)[last] = value;
}

function save() {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    await chrome.storage.local.set({ profile });
    status("Saved");
  }, 300);
}

function bindScalars() {
  for (const el of document.querySelectorAll("[data-path]")) {
    const v = getPath(profile, el.dataset.path);
    if (el.type === "checkbox") el.checked = !!v;
    else el.value = v ?? "";
    el.oninput = el.onchange = () => {
      setPath(profile, el.dataset.path, el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value);
      save();
    };
  }
  const skills = $("#skills");
  skills.value = profile.skills.join(", ");
  skills.oninput = () => {
    profile.skills = skills.value.split(",").map((s) => s.trim()).filter(Boolean);
    save();
  };
}

// A list of editable cards; `fields` are [key, label, options].
const LISTS = {
  experience: {
    blank: { title: "", company: "", location: "", start: "", end: "", current: false, description: "" },
    fields: [["title", "Job title"], ["company", "Company"], ["location", "Location"], ["start", "Start (YYYY-MM)"],
      ["end", "End (YYYY-MM, empty if current)"], ["current", "I currently work here", "check"], ["description", "Description", "area"]],
  },
  education: {
    blank: { school: "", degree: "", field: "", gpa: "", start: "", end: "" },
    fields: [["school", "School"], ["degree", "Degree (e.g. B.E.)"], ["field", "Field of study"], ["gpa", "GPA / CGPA"],
      ["start", "From (year)"], ["end", "To (year)"]],
  },
  languages: {
    blank: { language: "", proficiency: "Fluent" },
    fields: [["language", "Language"], ["proficiency", "Proficiency (Native, Fluent, …)"]],
  },
};

function renderList(name) {
  const box = $("#" + name);
  box.textContent = "";
  profile[name].forEach((item, i) => {
    const card = document.createElement("div");
    card.className = "item";
    const grid = document.createElement("div");
    grid.className = "grid";
    for (const [key, label, type] of LISTS[name].fields) {
      const wrap = document.createElement("label");
      let input;
      if (type === "check") {
        wrap.className = "check";
        input = document.createElement("input");
        input.type = "checkbox";
        input.checked = !!item[key];
        input.onchange = () => { item[key] = input.checked; save(); };
        wrap.append(input, label);
      } else {
        input = document.createElement(type === "area" ? "textarea" : "input");
        if (type === "area") { input.rows = 4; wrap.className = "wide"; }
        input.value = item[key] ?? "";
        input.oninput = () => { item[key] = input.value; save(); };
        wrap.append(label, input);
      }
      grid.append(wrap);
    }
    const remove = document.createElement("button");
    remove.className = "remove";
    remove.title = "Remove";
    remove.textContent = "×";
    remove.onclick = () => { profile[name].splice(i, 1); renderList(name); save(); };
    card.append(remove, grid);
    box.append(card);
  });
}

function renderCustom() {
  const box = $("#custom");
  box.textContent = "";
  $("#custom-count").textContent = profile.custom.length ? `(${profile.custom.length})` : "";
  profile.custom.forEach((c, i) => {
    const row = document.createElement("div");
    row.className = "qa";
    const q = Object.assign(document.createElement("input"), { value: c.q, placeholder: "Question, or a phrase in it" });
    const a = Object.assign(document.createElement("input"), { value: c.a, placeholder: "Answer" });
    q.oninput = () => { c.q = q.value; save(); };
    a.oninput = () => { c.a = a.value; save(); };
    const x = Object.assign(document.createElement("button"), { textContent: "×", title: "Remove" });
    x.onclick = () => { profile.custom.splice(i, 1); renderCustom(); save(); };
    row.append(q, a, x);
    if (c.learned) row.append(Object.assign(document.createElement("div"), { className: "learned", textContent: `Learned from your answer on ${c.learned}'s application` }));
    box.append(row);
  });
}

function renderAll() {
  bindScalars();
  ["experience", "education", "languages"].forEach(renderList);
  renderCustom();
  $("#import-url").value = profile.settings.importUrl || "";
}

for (const b of document.querySelectorAll("[data-add]")) {
  b.onclick = () => {
    const name = b.dataset.add;
    if (name === "custom") { profile.custom.push({ q: "", a: "" }); renderCustom(); }
    else { profile[name].push(structuredClone(LISTS[name].blank)); renderList(name); }
    save();
  };
}

$("#import").onclick = async () => {
  const url = $("#import-url").value.trim();
  if (!url) return status("Paste the address of your profile.json first", true);
  try {
    const origin = new URL(url).origin + "/*";
    if (!(await chrome.permissions.request({ origins: [origin] }))) return status("Needs permission to read that site", true);
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`${r.status} from ${new URL(url).host}`);
    profile = M.fromPortfolio(await r.json(), profile);
    profile.settings.importUrl = url;
    renderAll();
    await chrome.storage.local.set({ profile });
    status(`Imported ${profile.experience.length} roles, ${profile.education.length} education, ${profile.skills.length} skills`);
  } catch (e) {
    status("Import failed: " + e.message, true);
  }
};

$("#import-file").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    profile = data.personal ? M.withDefaults(data) : M.fromPortfolio(data, profile);
    renderAll();
    await chrome.storage.local.set({ profile });
    status("Restored from " + file.name);
  } catch (err) {
    status("Couldn't read that file: " + err.message, true);
  }
  e.target.value = "";
};

$("#export").onclick = () => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" }));
  a.download = "shortlist-fill-details.json";
  a.click();
  URL.revokeObjectURL(a.href);
};

async function showResume() {
  const { resume } = await chrome.storage.local.get("resume");
  $("#resume-name").textContent = resume ? `${resume.name} (${Math.max(1, Math.round(resume.size / 1024))} KB)` : "None saved";
  $("#resume-clear").hidden = !resume;
}

$("#resume").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const bytes = new Uint8Array(await file.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  await chrome.storage.local.set({ resume: { name: file.name, type: file.type, size: file.size, data: btoa(bin) } });
  showResume();
  status("Resume saved");
  e.target.value = "";
};

$("#resume-clear").onclick = async () => {
  await chrome.storage.local.remove("resume");
  showResume();
};

// Answers learned on an application while this page is open show up straight away.
chrome.storage.onChanged.addListener((changes) => {
  if (changes.profile && JSON.stringify(changes.profile.newValue) !== JSON.stringify(profile)) {
    profile = M.withDefaults(changes.profile.newValue);
    renderAll();
  }
});

(async () => {
  profile = M.withDefaults((await chrome.storage.local.get("profile")).profile);
  renderAll();
  showResume();
})();
