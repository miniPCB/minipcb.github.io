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
    let original = null, originalSignature = null, originalSettings = null, descriptions = new WeakMap(), nameEdit = null;
    const expandedEntries = new Set();
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
      if ([1, 2].includes(saved?.version) && Array.isArray(saved.entries)) {
        entries = saved.entries.filter(entry => typeof entry.id === "string" && typeof entry.title === "string" && typeof entry.summary === "string" && Number.isFinite(Date.parse(entry.savedAt)) && entry.state && typeof entry.state === "object").slice(0, limit);
        original = saved.original?.version === 1 ? saved.original : entries.at(-1)?.state || null;
        originalSignature = original ? signature(original) : null;
        auto = saved.auto !== false; expanded = innerWidth >= 1320 && (typeof saved.expanded === "boolean" ? saved.expanded : true);
      }
    } catch (_) { /* Invalid or inaccessible stored history must not stop the calculator. */ }

    function describe(entry) {
      if (descriptions.has(entry)) return descriptions.get(entry);
      const changes = [], initial = signature(entry.state) === originalSignature;
      try {
        const current = adapter.describe(entry.state);
        originalSettings ||= adapter.describe(original);
        const prior = new Map(originalSettings.fields.map(field => [field.id, field])), priorParts = new Map(originalSettings.parts.map(part => [part.name, part]));
        if (initial) {
          for (const field of current.fields.filter(field => ["vtop", "vmid"].includes(field.id))) changes.push({ text: `${field.label}: ${field.value}` });
          for (const part of current.parts) changes.push({ text: `${part.name}: ${part.summary}` });
          for (const field of current.fields.filter(field => !["vtop", "vmid"].includes(field.id))) changes.push({ text: `${field.label}: ${field.value}` });
        } else {
          for (const field of current.fields) {
            const before = prior.get(field.id);
            if (!before || before.value !== field.value) changes.push({ id: field.id, text: `${field.label}: ${before ? before.value + " → " : ""}${field.value}`, name: `${field.label}: ${field.value}` });
          }
          for (const part of current.parts) {
            const before = priorParts.get(part.name);
            if (!before) changes.push({ text: `Added ${part.name}: ${part.summary}`, name: `Added ${part.name}` });
            else for (const [key, field] of Object.entries(part.values)) {
              const old = before.values[key];
              if (field.active !== false && (!old || old.active === false || old.value !== field.value)) changes.push({ text: `${part.name} ${field.label}: ${old && old.active !== false ? old.value + " → " : ""}${field.value}`, name: `${part.name} ${field.label}: ${field.value}` });
            }
          }
          const names = new Set(current.parts.map(part => part.name));
          for (const part of originalSettings.parts) if (!names.has(part.name)) changes.push({ text: `Removed ${part.name}`, name: `Removed ${part.name}` });
        }
      } catch (_) { /* Older or damaged snapshots remain available for validated recall. */ }
      const lead = changes.find(change => change.id !== "reference" && change.name) || changes[0];
      const title = initial ? "Original state" : changes.length ? lead.name + (changes.length > 1 ? ` (${changes.length} changes)` : "") : "Equivalent to original";
      const description = { initial, title, changes: changes.length ? changes : [{ text: initial ? entry.summary : "No electrical settings differ from the original state." }] };
      descriptions.set(entry, description); return description;
    }
    // Names and descriptions are metadata; neither changes snapshot identity.
    const entryName = entry => typeof entry.name === "string" && entry.name.trim() ? entry.name : describe(entry).title;
    function trim() {
      const baseline = entries.find(entry => signature(entry.state) === originalSignature);
      entries = entries.slice(0, limit);
      if (baseline && !entries.includes(baseline)) entries[limit - 1] = baseline;
    }
    // Keep the reference even if its row is deleted or older variants are pruned.
    const stored = () => JSON.stringify({ version: 2, auto, expanded, original, entries });

    function persist(protectedEntry = null) {
      try {
        // Keep storage bounded even when a saved network has many physical parts.
        let data = stored();
        while (data.length > 1500000 && entries.length > 1) {
          const index = entries.findLastIndex((entry, index) => index > 0 && entry !== protectedEntry && signature(entry.state) !== originalSignature);
          if (index < 0) break;
          entries.splice(index, 1); data = stored();
        }
        localStorage.setItem(key, data); persistent = true;
      } catch (_) { persistent = false; status("Browser storage is unavailable. Memory lasts for this visit."); }
    }
    function render() {
      if (nameEdit) return;
      const scrollTop = list.scrollTop;
      get("memoryCount").textContent = String(entries.length);
      for (const id of expandedEntries) if (!entries.some(entry => entry.id === id)) expandedEntries.delete(id);
      list.replaceChildren();
      for (const entry of entries) {
        const description = describe(entry);
        const row = document.createElement("li"); row.className = "memory-entry"; row.dataset.memoryId = entry.id;
        row.setAttribute("aria-current", String(active === entry.id));
        const heading = document.createElement("div"); heading.className = "memory-entry-heading"; heading.append(nameButton(entry));
        const changes = document.createElement("ul"); changes.className = "memory-changes"; changes.id = "memoryChanges-" + entry.id; changes.hidden = !expandedEntries.has(entry.id);
        for (const change of description.changes) { const item = document.createElement("li"); item.textContent = change.text; changes.append(item); }
        const toggle = document.createElement("button"); toggle.type = "button"; toggle.className = "memory-expand"; toggle.disabled = restoring;
        toggle.setAttribute("aria-controls", changes.id); toggle.setAttribute("aria-expanded", String(!changes.hidden)); labelChangeToggle(entry, toggle);
        const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg"); icon.setAttribute("viewBox", "0 0 24 24"); icon.setAttribute("aria-hidden", "true");
        const path = document.createElementNS(icon.namespaceURI, "path"); path.setAttribute("d", "m9 5 7 7-7 7"); icon.append(path); toggle.append(icon);
        heading.append(toggle); row.append(heading, changes);
        list.append(row);
      }
      list.scrollTop = scrollTop;
    }
    function nameButton(entry) {
      const button = document.createElement("button"); button.type = "button"; button.className = "memory-restore";
      button.dataset.memoryRestore = entry.id; button.disabled = restoring;
      button.setAttribute("aria-label", `Restore ${entryName(entry)}; ${entry.summary}; saved ${new Date(entry.savedAt).toLocaleString()}`);
      button.setAttribute("aria-haspopup", "menu"); button.setAttribute("aria-controls", "memoryMenu");
      button.title = `${new Date(entry.savedAt).toLocaleString()} · Right-click for actions; F2 to rename`;
      const title = document.createElement("strong"); title.textContent = entryName(entry); button.append(title); return button;
    }
    function labelChangeToggle(entry, button) {
      const label = `${button.getAttribute("aria-expanded") === "true" ? "Hide" : "Show"} ${describe(entry).initial ? "original settings" : "changes from original"}: ${entryName(entry)}`;
      button.setAttribute("aria-label", label); button.title = label;
    }
    function rename(id) {
      const entry = entries.find(entry => entry.id === id), button = list.querySelector(`[data-memory-restore="${CSS.escape(id)}"]`);
      if (!entry || !button || restoring) return;
      cancel();
      const input = document.createElement("input");
      input.className = "memory-name-input"; input.type = "text"; input.maxLength = 100; input.value = entryName(entry).slice(0, 100); input.setAttribute("aria-label", "Memory name");
      nameEdit = input; button.replaceWith(input); input.focus({ preventScroll: true }); input.select();
      const finish = (commit, focus) => {
        if (nameEdit !== input) return;
        if (commit && !input.value.trim() && focus) { status("Enter a memory name.", true); return; }
        if (commit && input.value.trim()) { entry.name = input.value.trim().slice(0, 100); persist(entry); }
        nameEdit = null; const replacement = nameButton(entry); input.replaceWith(replacement);
        labelChangeToggle(entry, replacement.parentNode.querySelector(".memory-expand"));
        if (focus) replacement.focus({ preventScroll: true });
        status(commit ? "Memory name updated." : "Rename cancelled."); schedule();
      };
      input.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === "Escape") { event.preventDefault(); event.stopPropagation(); finish(event.key === "Enter", true); } });
      input.addEventListener("blur", () => finish(true, false));
    }
    function cancel() { clearTimeout(timer); timer = null; pending = null; }
    function capture() { try { return adapter.capture(); } catch (_) { return null; } }
    function save(candidate = capture(), announce = false) {
      cancel();
      if (!candidate) { if (announce) status("Finish a valid calculation or input edit first.", true); return null; }
      const fingerprint = signature(candidate.state), existing = entries.find(entry => signature(entry.state) === fingerprint);
      if (existing) { active = existing.id; render(); if (announce) status("This calculation is already saved."); return existing; }
      const entry = { ...clone(candidate), id: root.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`, savedAt: new Date().toISOString() };
      if (!original) { original = clone(entry.state); originalSignature = signature(original); originalSettings = null; descriptions = new WeakMap(); }
      ignored = null;
      entries.unshift(entry); trim(); active = entry.id; persist(); render();
      if (persistent) status(announce ? "Calculation saved in this browser." : "Saved.");
      return entry;
    }
    function schedule() {
      if (restoring || nameEdit) return;
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
      const toggle = event.target.closest(".memory-expand");
      if (toggle) {
        const id = toggle.closest("[data-memory-id]").dataset.memoryId, entry = entries.find(entry => entry.id === id);
        const open = !expandedEntries.has(id); if (open) expandedEntries.add(id); else expandedEntries.delete(id);
        get(toggle.getAttribute("aria-controls")).hidden = !open; toggle.setAttribute("aria-expanded", String(open)); labelChangeToggle(entry, toggle); return;
      }
      const button = event.target.closest("[data-memory-restore]");
      if (button) restore(button.dataset.memoryRestore);
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
      for (const action of ["restore", "rename", "delete"]) menu.querySelector(`[data-memory-action="${action}"]`).hidden = !entry;
      get("memoryClear").hidden = !entries.length;
      get("memoryAuto").setAttribute("aria-checked", String(auto));
      menu.hidden = false;
      menu.style.left = Math.max(12, Math.min(x, innerWidth - menu.offsetWidth - 12)) + "px";
      menu.style.top = Math.max(12, Math.min(y, innerHeight - menu.offsetHeight - 12)) + "px";
      menu.querySelector("button:not([hidden])").focus({ preventScroll: true });
    }
    panel.addEventListener("contextmenu", event => { event.preventDefault(); event.stopPropagation(); openMenu(event.target, event.clientX, event.clientY); });
    panel.addEventListener("keydown", event => {
      if (event.key === "F2" && !event.target.matches("input")) { const id = event.target.closest("[data-memory-id]")?.dataset.memoryId; if (id) { event.preventDefault(); rename(id); } return; }
      if (event.key === "ContextMenu" || event.shiftKey && event.key === "F10") {
        event.preventDefault(); const box = event.target.getBoundingClientRect(); openMenu(event.target, box.left + 8, box.bottom);
      }
    });
    menu.addEventListener("click", event => {
      const action = event.target.closest("[data-memory-action]")?.dataset.memoryAction, id = menuEntry;
      if (!action) return;
      closeMenu();
      if (action === "restore") { restore(id); return; }
      if (action === "rename") { rename(id); return; }
      if (action === "save") save(capture(), true);
      else if (action === "auto") { auto = !auto; get("memoryAuto").setAttribute("aria-checked", String(auto)); cancel(); persist(); if (auto) schedule(); status(auto ? "Autosave on." : "Autosave off."); }
      else if (action === "delete") {
        if (active === id) ignored = signature(capture()?.state);
        entries = entries.filter(entry => entry.id !== id); persist(); render(); status("Saved calculation deleted.");
      } else if (action === "clear") { cancel(); ignored = signature(capture()?.state); entries = []; active = null; original = null; originalSignature = null; originalSettings = null; descriptions = new WeakMap(); persist(); render(); status("Memory cleared."); }
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
