/* Browser-local calculation history. The page adapter owns circuit serialization. */
(function (root) {
  "use strict";
  function create(adapter) {
    const key = "minipcb-divider-memory-v1", limit = 50, delay = 1000;
    const get = id => document.getElementById(id), panel = get("calculatorMemory"), list = get("memoryList");
    const menu = get("memoryMenu"), summary = panel.querySelector("summary"), workspace = get("calculatorWorkspace");
    let entries = [], active = null, pending = null, timer = null, restoring = false, persistent = true, ignored = null;
    let auto = true, expanded = innerWidth >= 1320;
    let menuEntry = null, menuOrigin = null, press = null, suppressClickUntil = 0;
    const clone = value => JSON.parse(JSON.stringify(value));
    const signature = state => JSON.stringify(state);
    function reflectSummary() {
      const error = get("memoryStatus").dataset.error, message = error ? get("memoryStatus").textContent : "";
      summary.toggleAttribute("data-error", !!error);
      summary.setAttribute("aria-label", `${expanded ? "Collapse" : "Expand"} memory${message ? ": " + message : ""}`);
      summary.title = message || "Memory actions: right-click, Shift+F10 or long press";
    }
    const status = (message, error = false) => {
      const output = get("memoryStatus");
      output.textContent = persistent ? message : "Browser storage is unavailable. Memory lasts for this visit.";
      if (error || !persistent) output.dataset.error = "true"; else delete output.dataset.error;
      reflectSummary();
    };
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
    }
    function render() {
      const scrollTop = list.scrollTop;
      get("memoryCount").textContent = String(entries.length);
      list.replaceChildren();
      for (const entry of entries) {
        const row = document.createElement("li"); row.className = "memory-entry"; row.dataset.memoryId = entry.id;
        row.setAttribute("aria-current", String(active === entry.id));
        const button = document.createElement("button"); button.type = "button"; button.className = "memory-restore";
        button.dataset.memoryRestore = entry.id; button.disabled = restoring;
        button.setAttribute("aria-label", `Restore ${entry.title}; ${entry.summary}; saved ${new Date(entry.savedAt).toLocaleString()}`);
        button.setAttribute("aria-haspopup", "menu"); button.setAttribute("aria-controls", "memoryMenu");
        button.title = `${new Date(entry.savedAt).toLocaleString()} · Right-click for actions`;
        for (const [tag, text] of [["strong", entry.title], ["span", entry.summary]]) {
          const node = document.createElement(tag); node.textContent = text; button.append(node);
        }
        row.append(button); list.append(row);
      }
      list.scrollTop = scrollTop;
    }
    function cancel() { clearTimeout(timer); timer = null; pending = null; }
    function capture() { try { return adapter.capture(); } catch (_) { return null; } }
    function save(candidate = capture(), announce = false) {
      cancel();
      if (!candidate) { if (announce) status("Finish a valid calculation or input edit first.", true); return null; }
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
      } catch (error) { status(`Could not restore this calculation: ${error.message}`, true); }
      finally {
        restoring = false; render();
        list.querySelector(`[data-memory-restore="${CSS.escape(id)}"]`)?.focus({ preventScroll: true });
      }
    }
    list.addEventListener("click", event => {
      const restoreButton = event.target.closest("[data-memory-restore]");
      if (restoreButton) restore(restoreButton.dataset.memoryRestore);
    });
    function closeMenu(focus = false) {
      if (menu.hidden) return;
      menu.hidden = true;
      if (focus) (menuOrigin && list.querySelector(`[data-memory-restore="${CSS.escape(menuOrigin)}"]`) || summary).focus({ preventScroll: true });
    }
    function openMenu(target, x, y) {
      if (restoring) return;
      const row = target.closest("[data-memory-id]"); menuEntry = row?.dataset.memoryId || null; menuOrigin = menuEntry;
      const entry = entries.find(item => item.id === menuEntry), info = get("memoryMenuInfo");
      info.hidden = !entry; info.textContent = entry ? new Date(entry.savedAt).toLocaleString() : "";
      for (const action of ["restore", "delete"]) menu.querySelector(`[data-memory-action="${action}"]`).hidden = !entry;
      get("memoryClear").hidden = !entries.length;
      get("memoryAuto").setAttribute("aria-checked", String(auto));
      menu.hidden = false;
      menu.style.left = Math.max(12, Math.min(x, innerWidth - menu.offsetWidth - 12)) + "px";
      menu.style.top = Math.max(12, Math.min(y, innerHeight - menu.offsetHeight - 12)) + "px";
      menu.querySelector("button:not([hidden])").focus({ preventScroll: true });
    }
    panel.addEventListener("contextmenu", event => { event.preventDefault(); event.stopPropagation(); openMenu(event.target, event.clientX, event.clientY); });
    panel.addEventListener("keydown", event => {
      if (event.key === "ContextMenu" || event.shiftKey && event.key === "F10") {
        event.preventDefault(); const box = event.target.getBoundingClientRect(); openMenu(event.target, box.left + 8, box.bottom);
      }
    });
    menu.addEventListener("click", event => {
      const action = event.target.closest("[data-memory-action]")?.dataset.memoryAction, id = menuEntry;
      if (!action) return;
      closeMenu();
      if (action === "restore") { restore(id); return; }
      if (action === "save") save(capture(), true);
      else if (action === "auto") { auto = !auto; get("memoryAuto").setAttribute("aria-checked", String(auto)); cancel(); persist(); if (auto) schedule(); status(auto ? "Autosave on." : "Autosave off."); }
      else if (action === "delete") {
        if (active === id) ignored = signature(capture()?.state);
        entries = entries.filter(entry => entry.id !== id); persist(); render(); status("Saved calculation deleted.");
      } else if (action === "clear") { cancel(); ignored = signature(capture()?.state); entries = []; active = null; persist(); render(); status("Memory cleared."); }
      (menuOrigin && list.querySelector(`[data-memory-restore="${CSS.escape(menuOrigin)}"]`) || summary).focus({ preventScroll: true });
    });
    document.addEventListener("keydown", event => {
      if (menu.hidden) return;
      const items = [...menu.querySelectorAll("button:not([hidden])")], index = items.indexOf(document.activeElement);
      const next = { ArrowDown: (index + 1) % items.length, ArrowUp: (index + items.length - 1) % items.length, Home: 0, End: items.length - 1 }[event.key];
      if (next !== undefined) { event.preventDefault(); items[next].focus(); }
      else if (event.key === "Escape" || event.key === "Tab") { if (event.key === "Escape") event.preventDefault(); closeMenu(true); }
    });
    document.addEventListener("pointerdown", event => { if (!menu.contains(event.target)) closeMenu(); });
    document.addEventListener("pointerdown", () => { suppressClickUntil = 0; }, true);
    document.addEventListener("scroll", () => closeMenu(), true);
    root.addEventListener("resize", () => closeMenu());
    // Long press exposes the same secondary actions without adding mobile buttons.
    const cancelPress = () => { if (press) clearTimeout(press.timer); press = null; };
    panel.addEventListener("pointerdown", event => {
      if (event.pointerType !== "touch") return;
      cancelPress(); const { clientX: x, clientY: y, target } = event;
      press = { x, y, timer: setTimeout(() => { suppressClickUntil = performance.now() + 1000; openMenu(target, x, y); press = null; }, 550) };
    });
    panel.addEventListener("pointermove", event => { if (press && Math.hypot(event.clientX - press.x, event.clientY - press.y) > 10) cancelPress(); });
    panel.addEventListener("pointercancel", cancelPress);
    panel.addEventListener("pointerup", () => {
      cancelPress();
      if (!menu.hidden && performance.now() < suppressClickUntil) setTimeout(() => { if (!menu.hidden) menu.querySelector("button:not([hidden])").focus({ preventScroll: true }); }, 0);
    });
    document.addEventListener("click", event => { if (event.detail && performance.now() < suppressClickUntil) { event.preventDefault(); event.stopPropagation(); } }, true);
    panel.hidden = false; panel.open = expanded;
    const reflectExpanded = () => { workspace.classList.toggle("memory-open", expanded); summary.setAttribute("aria-expanded", String(expanded)); reflectSummary(); };
    workspace.classList.add("memory-ready"); reflectExpanded(); get("memoryAuto").setAttribute("aria-checked", String(auto));
    panel.addEventListener("toggle", () => {
      if (expanded === panel.open) return; // Ignore the queued initialization toggle.
      closeMenu(); expanded = panel.open; reflectExpanded(); persist(); adapter.layout();
    });
    const flush = () => { if (auto && pending && !restoring) save(capture()); };
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flush(); });
    root.addEventListener("pagehide", flush);
    render(); if (auto) save(capture()); else schedule(); adapter.layout();
    return { schedule, save: () => save(capture(), true), restore, flush, get entries() { return clone(entries); }, get restoring() { return restoring; } };
  }
  root.DividerMemory = Object.freeze({ create });
})(globalThis);
