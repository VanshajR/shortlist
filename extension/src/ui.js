// The Fill button on Workday application pages, and the panel saying what's left for you.
(function () {
  const D = self.WDDom;
  const F = self.WDFill;
  let host, root, busy = false;

  const CSS = `
    :host { all: initial; }
    .wrap { position: fixed; right: 20px; bottom: 20px; z-index: 2147483646; font: 13px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; color: #1c1917; }
    button.fill { display: flex; align-items: center; gap: 8px; padding: 10px 16px; border: 0; border-radius: 999px;
      background: #1c1917; color: #fafaf9; font: 600 13px system-ui, sans-serif; cursor: pointer; box-shadow: 0 4px 14px rgba(0,0,0,.25); }
    button.fill:hover { background: #292524; }
    button.fill[disabled] { opacity: .7; cursor: progress; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #34d399; }
    .panel { position: absolute; right: 0; bottom: 52px; width: 320px; max-height: 60vh; overflow: auto; background: #fff;
      border: 1px solid #e7e5e4; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,.18); padding: 14px 16px; }
    .panel h3 { margin: 0 0 4px; font-size: 14px; }
    .panel p { margin: 4px 0; color: #57534e; }
    .panel ul { margin: 6px 0 0; padding: 0; list-style: none; }
    .panel li { padding: 6px 8px; margin: 2px -8px; border-radius: 6px; cursor: pointer; }
    .panel li:hover { background: #fef3c7; }
    .panel .row { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; gap: 8px; }
    .panel a { color: #1d4ed8; cursor: pointer; text-decoration: underline; }
    .x { border: 0; background: none; font-size: 16px; cursor: pointer; color: #78716c; float: right; }
  `;

  function mount() {
    if (host) return;
    host = document.createElement("div");
    host.id = "shortlist-fill";
    root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${CSS}</style><div class="wrap"><div class="panel" hidden></div>
      <button class="fill" title="Fill this page from your saved details (Alt+Shift+F)"><span class="dot"></span>Fill this page</button></div>`;
    root.querySelector("button.fill").addEventListener("click", run);
    document.documentElement.appendChild(host);
  }

  function unmount() {
    host?.remove();
    host = root = null;
  }

  const onApplyPage = () => /\/apply\b/.test(location.pathname)
    || !!document.querySelector('[data-automation-id="applyFlowPage"], [data-automation-id="progressBar"]');

  let marked = [];

  function mark(f) {
    const el = f.kind === "date" ? f.el : f.kind === "radio" ? f.options[0].el.closest("fieldset, [role=radiogroup]") || f.options[0].el : f.el;
    const box = el.closest('[data-automation-id^="formField"]') || el;
    box.style.outline = "2px solid #f59e0b";
    box.style.outlineOffset = "4px";
    box.style.borderRadius = "4px";
    marked.push(box);
    return box;
  }

  function unmarkAll() {
    for (const box of marked) box.style.outline = box.style.outlineOffset = box.style.borderRadius = "";
    marked = [];
  }

  function show(html, items = []) {
    const panel = root.querySelector(".panel");
    panel.innerHTML = `<button class="x" title="Close">×</button>` + html;
    panel.hidden = false;
    panel.querySelector(".x").onclick = () => (panel.hidden = true);
    const ul = panel.querySelector("ul");
    for (const f of items) {
      const li = document.createElement("li");
      li.textContent = f.label || "(unlabelled field)";
      li.onclick = () => mark(f).scrollIntoView({ behavior: "smooth", block: "center" });
      ul?.appendChild(li);
    }
    panel.querySelector("[data-options]")?.addEventListener("click", () => chrome.runtime.sendMessage({ type: "options" }));
  }

  async function run() {
    if (busy) return;
    mount();
    busy = true;
    const btn = root.querySelector("button.fill");
    btn.disabled = true;
    btn.lastChild.textContent = "Filling…";
    try {
      const { profile, resume } = await chrome.storage.local.get(["profile", "resume"]);
      if (!profile || !profile.personal?.firstName) {
        show(`<h3>Add your details first</h3><p>Nothing is saved yet. Import your portfolio and add your phone, address and answers once.</p>
          <div class="row"><a data-options>Open my details</a></div>`);
        return;
      }
      unmarkAll();
      const r = await F.fillPage(profile, resume);
      const left = [...new Map([...r.missed, ...r.unknown].map((f) => [f.label + f.key, f])).values()];
      left.forEach(mark);
      const head = `<h3>Filled ${r.filled.length} field${r.filled.length === 1 ? "" : "s"}</h3>`;
      if (!left.length) {
        show(head + `<p>Nothing required is left on this page. Look it over, then press Save and Continue.</p>
          <div class="row"><a data-options>My details</a></div>`);
      } else {
        show(head + `<p>${left.length} need${left.length === 1 ? "s" : ""} you (outlined in amber). Answers you type into
          questions it didn't know are remembered for next time when you press Save and Continue.</p><ul></ul>
          <div class="row"><a data-options>My details</a></div>`, left);
      }
    } catch (e) {
      console.error("[shortlist-fill]", e);
      show(`<h3>Something went wrong</h3><p>${String(e.message || e).replace(/</g, "&lt;")}</p>`);
    } finally {
      busy = false;
      btn.disabled = false;
      btn.lastChild.textContent = "Fill this page";
    }
  }

  // Remember answers you typed yourself when you move on.
  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest("button");
    if (!b || b.closest("#shortlist-fill")) return;
    const id = D.auto(b);
    if (/pageFooterNextButton|bottom-navigation-next-button/.test(id) || /^(save and continue|next|continue|submit)$/i.test(D.text(b))) {
      F.learn().then((n) => {
        if (n && root) show(`<h3>Remembered ${n} answer${n === 1 ? "" : "s"}</h3><p>They'll be filled in on the next application. Change them in <a data-options>My details</a>.</p>`);
      });
    }
  }, true);

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "fill") run();
  });

  // Workday is a single-page app: keep the button in step with where you are.
  setInterval(() => (onApplyPage() ? mount() : unmount()), 1000);
  if (onApplyPage()) mount();
})();
