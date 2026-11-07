/* Browser-local calculation history. The page adapter owns circuit serialization. */
(function (root) {
  "use strict";
  function create(adapter) {
    const key = "minipcb-divider-memory-v1", limit = 50, delay = 1000;
    const get = id => document.getElementById(id), panel = get("calculatorMemory"), list = get("memoryList");
    let entries = [], active = null, pending = null, timer = null, restoring = false, persistent = true, ignored = null;
    let auto = true, expanded = innerWidth >= 1320;
    const clone = value => JSON.parse(JSON.stringify(value));
    const signature = state => JSON.stringify(state);
    const status = message => { get("memoryStatus").textContent = message; };
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "null");
      if (saved?.version === 1 && Array.isArray(saved.entries)) {
        entries = saved.entries.filter(entry => typeof entry.id === "string" && typeof entry.title === "string" && typeof entry.summary === "string" && Number.isFinite(Date.parse(entry.savedAt)) && entry.state && typeof entry.state === "object").slice(0, limit);
        auto = saved.auto !== false; expanded = innerWidth >= 1320 && (typeof saved.expanded === "boolean" ? saved.expanded : true);
      }
    } catch (_) { /* Invalid or inaccessible stored history must not stop the calculator. */ }

    function persist() {
      try {
        // Keep storage bounded even when a saved network has many physical parts.
        let data = JSON.stringify({ version: 1, auto, expanded, entries });
        while (data.length > 1500000 && entries.length > 1) { entries.pop(); data = JSON.stringify({ version: 1, auto, expanded, entries }); }
        localStorage.setItem(key, data); persistent = true;
      } catch (_) { persistent = false; status("Browser storage is unavailable. Memory lasts for this visit."); }
      panel.querySelector(".memory-note").textContent = persistent ? "This browser · 50 recent calculations" : "This visit only · browser storage unavailable";
    }
    function render() {
      const scrollTop = list.scrollTop;
      get("memoryCount").textContent = String(entries.length);
      get("memoryClear").disabled = !entries.length;
      list.replaceChildren();
      for (const entry of entries) {
        const row = document.createElement("li"); row.className = "memory-entry"; row.dataset.memoryId = entry.id;
        row.setAttribute("aria-current", String(active === entry.id));
        const button = document.createElement("button"); button.type = "button"; button.className = "memory-restore";
        button.dataset.memoryRestore = entry.id; button.disabled = restoring;
        button.setAttribute("aria-label", `Restore ${entry.title}; ${entry.summary}; saved ${new Date(entry.savedAt).toLocaleString()}`);
        button.title = "Restore inputs and recalculate with this calculator";
        for (const [tag, text] of [["strong", entry.title], ["span", entry.summary], ["small", new Date(entry.savedAt).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })]]) {
          const node = document.createElement(tag); node.textContent = text; button.append(node);
        }
        const remove = document.createElement("button"); remove.type = "button"; remove.className = "memory-delete"; remove.textContent = "×";
        remove.dataset.memoryDelete = entry.id; remove.setAttribute("aria-label", `Delete saved calculation ${entry.title}`); remove.disabled = restoring;
        row.append(button, remove); list.append(row);
      }
      list.scrollTop = scrollTop;
    }
    function cancel() { clearTimeout(timer); timer = null; pending = null; }
    function capture() { try { return adapter.capture(); } catch (_) { return null; } }
    function save(candidate = capture(), announce = false) {
      cancel();
      if (!candidate) { if (announce) status("Finish a valid calculation or input edit first."); return null; }
      const fingerprint = signature(candidate.state), existing = entries.find(entry => signature(entry.state) === fingerprint);
      if (existing) { active = existing.id; render(); if (announce) status("This calculation is already saved."); return existing; }
      const entry = { ...clone(candidate), id: root.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`, savedAt: new Date().toISOString() };
      ignored = null;
      entries.unshift(entry); entries = entries.slice(0, limit); active = entry.id; persist(); render();
      if (persistent) status(announce ? "Calculation saved in this browser." : "Saved.");
      return entry;
    }
    function schedule() {
      if (restoring) return;
      const candidate = capture();
      if (!candidate) { cancel(); return; }
      const fingerprint = signature(candidate.state), existing = entries.find(entry => signature(entry.state) === fingerprint);
      if (fingerprint === ignored) { cancel(); return; }
      ignored = null;
      const nextActive = existing?.id || null;
      if (active !== nextActive) { active = nextActive; render(); }
      if (existing || !auto) { cancel(); return; }
      if (pending?.fingerprint === fingerprint) return;
      cancel(); pending = { fingerprint };
      timer = setTimeout(() => {
        const current = capture();
        if (current && signature(current.state) === fingerprint) save(current);
        else cancel();
      }, delay);
    }
    async function restore(id) {
      if (restoring) return;
      const entry = entries.find(item => item.id === id); if (!entry) return;
      if (auto) save(capture()); else cancel();
      restoring = true; render();
      try {
        const result = await adapter.restore(clone(entry.state));
        active = entry.id; status(result?.message || "Calculation restored and recalculated.");
      } catch (error) { status(`Could not restore this calculation: ${error.message}`); }
      finally {
        restoring = false; render();
        list.querySelector(`[data-memory-restore="${CSS.escape(id)}"]`)?.focus({ preventScroll: true });
      }
    }
    list.addEventListener("click", event => {
      const restoreButton = event.target.closest("[data-memory-restore]"), remove = event.target.closest("[data-memory-delete]");
      if (restoreButton) restore(restoreButton.dataset.memoryRestore);
      else if (remove) {
        if (active === remove.dataset.memoryDelete) ignored = signature(capture()?.state);
        entries = entries.filter(entry => entry.id !== remove.dataset.memoryDelete); persist(); render(); status("Saved calculation deleted.");
        get("memorySave").focus({ preventScroll: true });
      }
    });
    get("memorySave").addEventListener("click", () => save(capture(), true));
    get("memoryAuto").checked = auto;
    get("memoryAuto").addEventListener("change", () => { auto = get("memoryAuto").checked; cancel(); persist(); if (auto) schedule(); status(auto ? "Autosave on." : "Autosave off. Use Save now."); });
    get("memoryClear").addEventListener("click", () => { cancel(); ignored = signature(capture()?.state); entries = []; active = null; persist(); render(); status("Memory cleared."); get("memorySave").focus({ preventScroll: true }); });
    panel.hidden = false; panel.open = expanded;
    document.getElementById("calculatorWorkspace").classList.toggle("memory-open", expanded);
    panel.addEventListener("toggle", () => {
      if (expanded === panel.open) return; // Ignore the queued initialization toggle.
      expanded = panel.open; document.getElementById("calculatorWorkspace").classList.toggle("memory-open", expanded); persist(); adapter.layout();
    });
    const flush = () => { if (auto && pending && !restoring) save(capture()); };
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flush(); });
    root.addEventListener("pagehide", flush);
    render(); if (auto) save(capture()); else schedule(); adapter.layout();
    return { schedule, save: () => save(capture(), true), restore, flush, get entries() { return clone(entries); }, get restoring() { return restoring; } };
  }
  root.DividerMemory = Object.freeze({ create });
})(globalThis);
