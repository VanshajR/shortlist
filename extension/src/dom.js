// Reading and driving Workday's form widgets. Workday is one React app for every company, so
// fields are recognised by its data-automation-id / id naming and by their visible labels,
// which covers both its older (legalNameSection_firstName) and newer (name--legalName--firstName)
// markup.
(function () {
  const M = self.WDMatch;
  const D = (self.WDDom = {});
  const OURS = "#shortlist-fill";

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function waitFor(fn, ms = 2500) {
    const end = Date.now() + ms;
    for (;;) {
      const v = fn();
      if (v || Date.now() > end) return v;
      await sleep(60);
    }
  }
  const visible = (el) => !!el && el.isConnected && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
  const text = (el) => (el ? el.textContent : "").replace(/\s+/g, " ").trim();
  const clean = (t) => t.replace(/\*/g, " ").replace(/\b(required|select one)\b/gi, " ").replace(/\s+/g, " ").trim();
  const auto = (el) => el.getAttribute("data-automation-id") || "";

  function byId(id) {
    try { return document.getElementById(id); } catch { return null; }
  }

  function labelOf(el) {
    let t = "";
    if (el.id) t = text(document.querySelector(`label[for="${CSS.escape(el.id)}"]`));
    if (!t) t = (el.getAttribute("aria-labelledby") || "").split(/\s+/).filter((id) => id && byId(id) !== el)
      .map((id) => text(byId(id))).join(" ");
    if (!t && el.closest("label")) t = text(el.closest("label"));
    if (!t) t = el.getAttribute("aria-label") || "";
    if (!t) {
      const ff = el.closest('[data-automation-id^="formField"], fieldset');
      if (ff) t = text(ff.querySelector("legend, label, [data-automation-id=formLabel]"));
    }
    if (!t) t = el.getAttribute("placeholder") || "";
    return clean(t);
  }

  // The question a group of radios answers: its fieldset legend or radiogroup label.
  function groupLabel(radio) {
    const g = radio.closest('[role="radiogroup"], fieldset');
    if (g) {
      const by = (g.getAttribute("aria-labelledby") || "").split(/\s+/).map((id) => text(byId(id))).join(" ");
      const t = by || text(g.querySelector("legend")) || g.getAttribute("aria-label") || "";
      if (t) return clean(t);
    }
    const ff = radio.closest('[data-automation-id^="formField"]');
    return ff ? clean(text(ff.querySelector("legend, label"))) : "";
  }

  function optionLabel(input) {
    let t = input.id ? text(document.querySelector(`label[for="${CSS.escape(input.id)}"]`)) : "";
    if (!t && input.closest("label")) t = text(input.closest("label"));
    return t || input.getAttribute("aria-label") || input.value || "";
  }

  // What a field is called everywhere at once (ids, automation ids up its ancestry, its label),
  // lower-cased, so one pattern recognises it whichever Workday version drew it.
  function keyOf(el, label) {
    const parts = [el.id, el.getAttribute("name"), auto(el)];
    let a = el.parentElement;
    for (let i = 0; a && i < 6; i++, a = a.parentElement) {
      const id = auto(a);
      if (/formField|Section|workExperience|education|webAddress|language|dateInput/.test(id)) parts.push(id);
    }
    parts.push(label);
    return parts.filter(Boolean).join(" | ").toLowerCase();
  }

  function kindOf(el) {
    if (el.tagName === "SELECT") return "select";
    if (el.tagName === "TEXTAREA") return "text";
    if (el.tagName === "BUTTON") return "dropdown";
    const type = (el.getAttribute("type") || "text").toLowerCase();
    if (type === "checkbox") return "checkbox";
    if (type === "radio") return "radio";
    if (/dateSection/i.test(auto(el) + " " + el.id)) return "date";
    if (el.closest('[data-automation-id="multiselectInputContainer"], [data-uxi-widget-type="multiselect"], [data-uxi-widget-type="selectinput"]')
      || el.getAttribute("role") === "combobox" || auto(el) === "searchBox") return "prompt";
    return "text";
  }

  const SKIP_TYPES = new Set(["hidden", "file", "submit", "button", "image", "reset", "password"]);

  // Headings split the page into sections ("Work Experience") and entries ("Work Experience 2").
  function headings() {
    return [...document.querySelectorAll('h1, h2, h3, h4, h5, [role="heading"]')]
      .filter((h) => !h.closest(OURS) && visible(h) && text(h).length < 80);
  }

  function placeOf(el, hs) {
    let last = null;
    for (const h of hs) {
      if (h === el || h.contains(el)) continue;
      if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) last = h;
      else break;
    }
    const t = last ? text(last) : "";
    const m = t.match(/^(.*?)\s+(\d+)$/);
    return m ? { section: m[1], entry: Number(m[2]) - 1 } : { section: t, entry: 0 };
  }

  // Every fillable thing on the page, one entry per question (a radio group or a date's
  // month/year boxes count once).
  function fields() {
    const hs = headings();
    const out = [];
    const groups = new Map();
    const dates = new Map();
    const els = document.querySelectorAll('input, textarea, select, button[aria-haspopup="listbox"]');
    for (const el of els) {
      if (el.closest(OURS) || el.disabled) continue;
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (el.tagName === "INPUT" && SKIP_TYPES.has(type)) continue;
      const kind = kindOf(el);
      if (kind !== "radio" && kind !== "checkbox" && !visible(el)) continue;
      if ((kind === "radio" || kind === "checkbox") && !visible(el) && !visible(el.parentElement)) continue;
      if (kind === "radio") {
        const name = el.name || groupLabel(el);
        if (!groups.has(name)) {
          const label = groupLabel(el);
          const f = { kind, el, options: [], label, key: keyOf(el, label), ...placeOf(el, hs) };
          groups.set(name, f);
          out.push(f);
        }
        groups.get(name).options.push({ el, text: optionLabel(el) });
        continue;
      }
      if (kind === "date") {
        const box = el.closest('[data-automation-id="dateInputWrapper"]') || el.closest('[data-automation-id^="formField"]') || el.parentElement;
        if (!dates.has(box)) {
          const ff = box.closest('[data-automation-id^="formField"], fieldset') || box;
          const label = clean(text(ff.querySelector("legend, label")) || labelOf(el));
          const f = { kind, el: box, parts: {}, label, key: keyOf(el, label), ...placeOf(el, hs) };
          dates.set(box, f);
          out.push(f);
        }
        const part = /month/i.test(auto(el) + el.id) ? "month" : /day/i.test(auto(el) + el.id) ? "day" : "year";
        dates.get(box).parts[part] = el;
        continue;
      }
      const label = labelOf(el);
      out.push({ kind, el, label, key: keyOf(el, label), ...placeOf(el, hs) });
    }
    return out;
  }

  // ---- driving the widgets -------------------------------------------------------------

  function click(el) {
    el.scrollIntoView({ block: "center", inline: "nearest" });
    const o = { bubbles: true, cancelable: true, view: window };
    el.dispatchEvent(new PointerEvent("pointerdown", o));
    el.dispatchEvent(new MouseEvent("mousedown", o));
    el.dispatchEvent(new PointerEvent("pointerup", o));
    el.dispatchEvent(new MouseEvent("mouseup", o));
    el.dispatchEvent(new MouseEvent("click", o));
  }

  function key(el, k) {
    const code = { Enter: 13, Escape: 27, Tab: 9 }[k] || k.toUpperCase().charCodeAt(0);
    const o = { key: k, code: k.length === 1 ? (/\d/.test(k) ? "Digit" + k : "Key" + k.toUpperCase()) : k, keyCode: code, which: code, bubbles: true, cancelable: true };
    const down = el.dispatchEvent(new KeyboardEvent("keydown", o));
    if (k.length === 1 || k === "Enter") el.dispatchEvent(new KeyboardEvent("keypress", { ...o, charCode: k.length === 1 ? k.charCodeAt(0) : 13 }));
    return down;
  }
  const keyUp = (el, k) => el.dispatchEvent(new KeyboardEvent("keyup", { key: k, bubbles: true }));

  const nativeSet = (el, v) => {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, v);
  };

  // As if typed: insertText fires the beforeinput/input events React listens for; the
  // native setter is the fallback where execCommand isn't allowed.
  function typeText(el, value) {
    el.focus();
    if (el.select) el.select();
    let ok = false;
    try { ok = value === "" ? document.execCommand("delete") : document.execCommand("insertText", false, value); } catch { ok = false; }
    if (!ok || el.value !== value) {
      nativeSet(el, value);
      el.dispatchEvent(new InputEvent("input", { bubbles: true, data: value, inputType: "insertText" }));
    }
  }

  async function setText(el, value) {
    value = String(value);
    if (el.value === value) return true;
    typeText(el, value);
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.blur();
    await sleep(40);
    return el.value === value;
  }

  function closeMenus() {
    const a = document.activeElement || document.body;
    key(a, "Escape");
    keyUp(a, "Escape");
  }

  function openList(owner) {
    const id = owner.getAttribute("aria-controls") || owner.getAttribute("aria-owns");
    const own = id && byId(id);
    if (own && visible(own) && own.querySelector('[role="option"]')) return own;
    return [...document.querySelectorAll('[role="listbox"]')]
      .find((l) => !l.closest(OURS) && visible(l) && l.querySelector('[role="option"], [data-automation-id="promptOption"]'));
  }

  const optionsIn = (list) => [...list.querySelectorAll('[role="option"], [data-automation-id="promptOption"]')]
    .filter((o, i, all) => visible(o) && !all.some((p) => p !== o && p.contains(o)))
    .map((el) => ({ el, text: text(el) }));

  async function chooseDropdown(btn, candidates) {
    const now = clean(text(btn));
    if (now && M.pick([now], candidates)) return true;
    closeMenus();
    click(btn);
    const list = await waitFor(() => openList(btn), 2000);
    if (!list) return false;
    const hit = M.pick(optionsIn(list), candidates);
    if (!hit) {
      closeMenus();
      return false;
    }
    click(hit.el);
    await waitFor(() => !visible(list), 1500);
    await sleep(80);
    return M.pick([clean(text(btn))], candidates) != null || clean(text(btn)) !== now;
  }

  function chosenIn(input) {
    const box = input.closest('[data-automation-id^="formField"]') || input.closest('[data-automation-id="multiselectInputContainer"]')?.parentElement || input.parentElement;
    return [...box.querySelectorAll('[data-automation-id="selectedItem"], [data-automation-id="selectedItemList"] [role="listitem"]')]
      .map(text).filter(Boolean);
  }

  // A search-as-you-type picker (source, country phone code, field of study, skills): type,
  // Enter, take the best result; a category result ("Job Board") opens a level below.
  async function choosePrompt(input, candidates, { many = false } = {}) {
    const before = chosenIn(input);
    if (!many && before.some((t) => M.pick([t], candidates))) return true;
    for (const c of candidates.filter(Boolean).slice(0, 4)) {
      closeMenus();
      typeText(input, String(c));
      key(input, "Enter");
      keyUp(input, "Enter");
      let list = await waitFor(() => openList(input), 2500);
      if (!list) continue;
      await sleep(250);
      let hit = M.pick(optionsIn(list), [c, ...candidates]);
      if (!hit) continue;
      click(hit.el);
      await sleep(350);
      list = openList(input);
      if (list && chosenIn(input).length === before.length) {
        const deeper = M.pick(optionsIn(list), candidates);
        if (deeper) {
          click(deeper.el);
          await sleep(300);
        }
      }
      closeMenus();
      if (chosenIn(input).length > before.length || !before.length) {
        if (input.value) typeText(input, "");
        return true;
      }
    }
    if (input.value) typeText(input, "");
    closeMenus();
    return false;
  }

  async function chooseRadio(field, candidates) {
    const hit = M.pick(field.options, candidates);
    if (!hit) return false;
    if (!hit.el.checked) click(hit.el.id && document.querySelector(`label[for="${CSS.escape(hit.el.id)}"]`) || hit.el);
    await sleep(60);
    if (!hit.el.checked) click(hit.el);
    return hit.el.checked;
  }

  async function setCheckbox(el, want) {
    const on = () => el.checked || el.getAttribute("aria-checked") === "true";
    if (on() !== want) click(el);
    await sleep(80);
    return on() === want;
  }

  function chooseSelect(sel, candidates) {
    const hit = M.pick([...sel.options].map((o) => ({ el: o, text: o.text })), candidates);
    if (!hit) return false;
    sel.value = hit.el.value;
    sel.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  // Workday's date boxes are spin buttons that take keystrokes, one digit at a time.
  async function setDate(field, { month, day, year }) {
    const want = { month, day, year };
    let ok = true;
    for (const part of ["month", "day", "year"]) {
      const el = field.parts[part];
      if (!el || want[part] == null) continue;
      const digits = String(want[part]).padStart(part === "year" ? 4 : 2, "0");
      el.focus();
      if (el.select) el.select();
      for (const d of digits) {
        if (key(el, d)) {
          try { document.execCommand("insertText", false, d); } catch { /* the keydown handler typed it */ }
        }
        keyUp(el, d);
      }
      el.dispatchEvent(new Event("change", { bubbles: true }));
      el.blur();
      await sleep(60);
      const shown = String(el.value || el.getAttribute("aria-valuenow") || el.getAttribute("aria-valuetext") || "");
      if (Number(shown.replace(/\D/g, "")) !== Number(digits)) ok = false;
    }
    return ok;
  }

  function upload(input, resume) {
    const bytes = Uint8Array.from(atob(resume.data), (c) => c.charCodeAt(0));
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], resume.name, { type: resume.type || "application/pdf" }));
    input.files = dt.files;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  // What a field holds right now, as text (to learn your answers and to spot empty ones).
  function valueOf(f) {
    if (!f.el.isConnected) return "";
    switch (f.kind) {
      case "radio": return (f.options.find((o) => o.el.checked) || {}).text || "";
      case "checkbox": return f.el.checked || f.el.getAttribute("aria-checked") === "true" ? "Yes" : "";
      case "dropdown": { const t = clean(text(f.el)); return /^(select one)?$/i.test(t) ? "" : t; }
      case "select": return f.el.selectedIndex > 0 ? f.el.options[f.el.selectedIndex].text : "";
      case "prompt": return chosenIn(f.el).join(", ");
      case "date": return Object.values(f.parts).map((p) => p.value).filter(Boolean).join("/");
      default: return f.el.value || "";
    }
  }

  function isRequired(f) {
    const el = f.kind === "date" ? Object.values(f.parts)[0] : f.kind === "radio" ? f.options[0].el : f.el;
    if (el.required || el.getAttribute("aria-required") === "true") return true;
    const ff = el.closest('[data-automation-id^="formField"], fieldset');
    const label = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    return [label, ff && ff.querySelector("legend, label")].some((l) => l && /\*/.test(l.textContent))
      || !!(ff && ff.querySelector('abbr[title="required" i], [data-automation-id="formLabelRequired"]'));
  }

  // The "Add" / "Add Another" button of a section, between its heading and the next section's.
  function addButton(sectionRe) {
    const hs = headings();
    for (const b of document.querySelectorAll("button")) {
      if (b.closest(OURS) || !visible(b)) continue;
      const t = text(b);
      const aria = b.getAttribute("aria-label") || "";
      if (!/^add( another)?$/i.test(t) && !/^add\b/i.test(aria)) continue;
      if (sectionRe.test(aria) || sectionRe.test(placeOf(b, hs).section)) return b;
    }
    return null;
  }

  function entryCount(sectionRe) {
    return headings().filter((h) => {
      const m = text(h).match(/^(.*?)\s+\d+$/);
      return m && sectionRe.test(m[1]);
    }).length;
  }

  Object.assign(D, {
    sleep, waitFor, visible, text, labelOf, keyOf, fields, click, setText, chooseDropdown, choosePrompt,
    chooseRadio, setCheckbox, chooseSelect, setDate, upload, valueOf, isRequired, addButton, entryCount,
    closeMenus, auto,
  });
})();
