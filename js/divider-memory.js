/* Browser-local calculation history. The page adapter owns circuit serialization. */
(function (root) {
  "use strict";
  function create(adapter) {
    const key = "minipcb-divider-memory-v1", limit = 50, delay = 1000;
    const get = id => document.getElementById(id), panel = get("calculatorMemory"), list = get("memoryList");
    const menu = get("memoryMenu"), summary = panel.querySelector("summary"), workspace = get("calculatorWorkspace"), resizer = get("memoryResize");
    let entries = [], active = null, pending = null, timer = null, restoring = false, persistent = true, ignored = null;
    let auto = true, expanded = innerWidth >= 1320, paneWidth = 300, drag = null, layoutFrame = null;
    let menuEntry = null, menuOrigin = null, press = null, suppressClickUntil = 0, pointerActive = false, groupsDirty = false, groupTimer = null;
    let original = null, originalSignature = null, originalSettings = null, descriptions = new WeakMap(), nameEdit = null;
    const expandedEntries = new Set(), groupExpansion = new Map();
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
      reflectSummary(); fitHeight();
    };
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "null");
      if ([1, 2].includes(saved?.version) && Array.isArray(saved.entries)) {
        entries = saved.entries.filter(entry => typeof entry.id === "string" && typeof entry.title === "string" && typeof entry.summary === "string" && Number.isFinite(Date.parse(entry.savedAt)) && entry.state && typeof entry.state === "object").slice(0, limit);
        original = saved.original?.version === 1 ? saved.original : entries.at(-1)?.state || null;
        originalSignature = original ? signature(original) : null;
        auto = saved.auto !== false; expanded = innerWidth >= 1320 && (typeof saved.expanded === "boolean" ? saved.expanded : true);
        if (Number.isFinite(saved.paneWidth)) paneWidth = Math.max(220, Math.min(520, saved.paneWidth));
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
            if (!before || before.value !== field.value) changes.push({ text: `${field.label}: ${before ? before.value + " → " : ""}${field.value}` });
          }
          for (const part of current.parts) {
            const before = priorParts.get(part.name);
            if (!before) changes.push({ text: `Added ${part.name}: ${part.summary}` });
            else for (const [key, field] of Object.entries(part.values)) {
              const old = before.values[key];
              if (field.active !== false && (!old || old.active === false || old.value !== field.value)) changes.push({ text: `${part.name} ${field.label}: ${old && old.active !== false ? old.value + " → " : ""}${field.value}` });
            }
          }
          const names = new Set(current.parts.map(part => part.name));
          for (const part of originalSettings.parts) if (!names.has(part.name)) changes.push({ text: `Removed ${part.name}` });
        }
      } catch (_) { /* Older or damaged snapshots remain available for validated recall. */ }
      const description = { initial, changes: changes.length ? changes : [{ text: initial ? entry.summary : "No electrical settings differ from the original state." }] };
      descriptions.set(entry, description); return description;
    }
    // Names and descriptions are metadata; neither changes snapshot identity.
    function localStamp(savedAt) {
      const date = new Date(savedAt), pad = value => String(value).padStart(2, "0");
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    }
    const entryName = entry => typeof entry.name === "string" && entry.name.trim() ? entry.name : (describe(entry).initial ? "Original · " : "") + localStamp(entry.savedAt);
    // Grouping is presentation only. Every member retains its independent snapshot.
    function groupedEntries() {
      const groups = new Map(); let session = null;
      for (const entry of [...entries].reverse().sort((a, b) => Date.parse(a.savedAt) - Date.parse(b.savedAt))) {
        const value = Array.isArray(entry.state.controls) ? entry.state.controls.find(row => Array.isArray(row) && row[0] === "circuitTitle")?.[1] : "";
        const title = typeof value === "string" && value.trim().toLowerCase() !== "voltage divider" ? value.trim() : "";
        const name = typeof entry.name === "string" && !/^(?:Original · )?\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/.test(entry.name) ? entry.name.trim() : "";
        const time = Date.parse(entry.savedAt), day = localStamp(entry.savedAt).slice(0, 10); let group;
        if (title) {
          const key = "title:" + title.toLowerCase();
          if (!groups.has(key)) groups.set(key, { key, label: title, entries: [] });
          group = groups.get(key); session = null;
        } else {
          if (!session || session.day !== day || time - session.time > 5 * 60 * 1000 || name && session.label && name.toLowerCase() !== session.label.toLowerCase()) {
            const key = "time:" + entry.id; session = { key, label: "", day, entries: [] }; groups.set(key, session);
          }
          group = session; if (name) group.label = name;
        }
        group.entries.push(entry); group.time = time;
      }
      return [...groups.values()].sort((a, b) => b.time - a.time || entries.indexOf(a.entries.at(-1)) - entries.indexOf(b.entries.at(-1)));
    }
    function groupLabel(group) {
      if (group.label) return group.label;
      const first = localStamp(group.entries[0].savedAt), last = localStamp(group.entries.at(-1).savedAt);
      return `${first.slice(0, 10)} · ${first.slice(11, 16)}${first.slice(11, 16) !== last.slice(11, 16) ? "–" + last.slice(11, 16) : ""}`;
    }
    function trim() {
      const baseline = entries.find(entry => signature(entry.state) === originalSignature);
      entries = entries.slice(0, limit);
      if (baseline && !entries.includes(baseline)) entries[limit - 1] = baseline;
    }
    // Keep the reference even if its row is deleted or older variants are pruned.
    const stored = () => JSON.stringify({ version: 2, auto, expanded, paneWidth, original, entries });

    function fitHeight() {
      if (innerWidth >= 1320 && expanded) {
        panel.style.height = `${Math.max(180, innerHeight - Math.max(0, panel.getBoundingClientRect().top) - 12)}px`;
        list.style.maxHeight = `${Math.max(80, panel.getBoundingClientRect().bottom - list.getBoundingClientRect().top - 12)}px`;
      } else { panel.style.removeProperty("height"); list.style.maxHeight = "none"; }
    }
    function setPaneWidth(value, redraw = true) {
      paneWidth = Math.max(220, Math.min(520, Math.round(value)));
      workspace.style.setProperty("--memory-width", paneWidth + "px");
      resizer.setAttribute("aria-valuenow", String(paneWidth)); resizer.setAttribute("aria-valuetext", paneWidth + " pixels");
      fitHeight();
      if (redraw && layoutFrame === null) layoutFrame = requestAnimationFrame(() => { layoutFrame = null; adapter.layout(); fitHeight(); });
    }

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
      groupsDirty = false;
      const scrollTop = list.scrollTop;
      const focused = list.contains(document.activeElement) ? document.activeElement : null, focusedEntry = focused?.closest("[data-memory-id]")?.dataset.memoryId;
      const focusClass = ["memory-restore", "memory-rename", "memory-expand"].find(name => focused?.classList.contains(name)), focusedGroup = focused?.matches(".memory-group-heading") ? focused.parentNode.dataset.memoryGroup : null;
      get("memoryCount").textContent = String(entries.length);
      for (const id of expandedEntries) if (!entries.some(entry => entry.id === id)) expandedEntries.delete(id);
      const groups = groupedEntries(), keys = new Set(groups.map(group => group.key));
      for (const key of groupExpansion.keys()) if (!keys.has(key)) groupExpansion.delete(key);
      list.replaceChildren();
      for (const [index, group] of groups.entries()) {
        const section = document.createElement("li"); section.className = "memory-group";
        const details = document.createElement("details"); details.dataset.memoryGroup = group.key;
        let open = groupExpansion.get(group.key) ?? (index === 0 || group.entries.some(entry => entry.id === active)); details.open = open;
        const heading = document.createElement("summary"); heading.className = "memory-group-heading";
        const title = document.createElement("span"); title.textContent = groupLabel(group);
        const count = document.createElement("span"); count.className = "memory-group-count"; count.textContent = String(group.entries.length); heading.append(title, count);
        heading.setAttribute("aria-label", `${title.textContent}; ${group.entries.length} saved calculation${group.entries.length === 1 ? "" : "s"}`);
        heading.title = `${localStamp(group.entries[0].savedAt)} → ${localStamp(group.entries.at(-1).savedAt)}`;
        const members = document.createElement("ol"); members.className = "memory-group-list"; members.setAttribute("aria-label", title.textContent + " calculations");
        details.append(heading, members); section.append(details); list.append(section);
        details.addEventListener("toggle", () => { if (open === details.open) return; open = details.open; groupExpansion.set(group.key, open); fitHeight(); });
        for (const entry of [...group.entries].reverse()) {
          const description = describe(entry);
          const row = document.createElement("li"); row.className = "memory-entry"; row.dataset.memoryId = entry.id;
          row.setAttribute("aria-current", String(active === entry.id));
          const heading = document.createElement("div"); heading.className = "memory-entry-heading"; heading.append(nameButton(entry));
          const changes = document.createElement("ul"); changes.className = "memory-changes"; changes.id = "memoryChanges-" + entry.id; changes.hidden = !expandedEntries.has(entry.id);
          for (const change of description.changes) { const item = document.createElement("li"); item.textContent = change.text; changes.append(item); }
          const toggle = document.createElement("button"); toggle.type = "button"; toggle.className = "memory-expand"; toggle.disabled = restoring;
          toggle.setAttribute("aria-controls", changes.id); toggle.setAttribute("aria-expanded", String(!changes.hidden)); labelChangeToggle(entry, toggle);
          toggle.append(actionIcon("m9 5 7 7-7 7"));
          const edit = document.createElement("button"); edit.type = "button"; edit.className = "memory-rename"; edit.disabled = restoring;
          labelRename(entry, edit); edit.append(actionIcon("M16 3l5 5L8 21H3v-5L16 3ZM14 5l5 5"));
          heading.append(edit, toggle); row.append(heading, changes);
          members.append(row);
        }
      }
      fitHeight(); list.scrollTop = scrollTop;
      if (focusedEntry && focusClass) list.querySelector(`[data-memory-id="${CSS.escape(focusedEntry)}"] .${focusClass}`)?.focus({ preventScroll: true });
      else if (focusedGroup) list.querySelector(`[data-memory-group="${CSS.escape(focusedGroup)}"] > summary`)?.focus({ preventScroll: true });
    }
    function refreshGroups() {
      groupsDirty = true; clearTimeout(groupTimer);
      if (!pointerActive) groupTimer = setTimeout(() => { if (groupsDirty && !pointerActive && !nameEdit) render(); }, 0);
    }
    function actionIcon(pathData) {
      const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg"); icon.setAttribute("viewBox", "0 0 24 24"); icon.setAttribute("aria-hidden", "true");
      const path = document.createElementNS(icon.namespaceURI, "path"); path.setAttribute("d", pathData); icon.append(path); return icon;
    }
    function labelRename(entry, button) { button.setAttribute("aria-label", "Rename memory: " + entryName(entry)); button.title = "Rename"; }
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
      const input = document.createElement("input"), edit = button.parentNode.querySelector(".memory-rename"); edit.disabled = true;
      input.className = "memory-name-input"; input.type = "text"; input.maxLength = 100; input.value = entryName(entry).slice(0, 100); input.setAttribute("aria-label", "Memory name");
      nameEdit = input; button.replaceWith(input); input.focus({ preventScroll: true }); input.select();
      const finish = (commit, focus) => {
        if (nameEdit !== input) return;
        if (commit && !input.value.trim() && focus) { status("Enter a memory name.", true); return; }
        if (commit && input.value.trim()) { entry.name = input.value.trim().slice(0, 100); persist(entry); }
        const group = groupedEntries().find(group => group.entries.some(item => item.id === id)); if (group) groupExpansion.set(group.key, true);
        nameEdit = null; const replacement = nameButton(entry); input.replaceWith(replacement);
        edit.disabled = false; labelRename(entry, edit);
        labelChangeToggle(entry, replacement.parentNode.querySelector(".memory-expand"));
        if (focus) replacement.focus({ preventScroll: true });
        status(commit ? "Memory name updated." : "Rename cancelled.");
        if (focus) render(); else refreshGroups();
        fitHeight(); schedule();
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
        const group = groupedEntries().find(group => group.entries.some(item => item.id === id)); if (group) groupExpansion.set(group.key, true);
      } catch (error) { status(`Could not restore this calculation: ${error.message}`, true); }
      finally {
        restoring = false; render();
        list.querySelector(`[data-memory-restore="${CSS.escape(id)}"]`)?.focus({ preventScroll: true });
      }
    }
    list.addEventListener("click", event => {
      const edit = event.target.closest(".memory-rename");
      if (edit) { rename(edit.closest("[data-memory-id]").dataset.memoryId); return; }
      const toggle = event.target.closest(".memory-expand");
      if (toggle) {
        const id = toggle.closest("[data-memory-id]").dataset.memoryId, entry = entries.find(entry => entry.id === id);
        const open = !expandedEntries.has(id); if (open) expandedEntries.add(id); else expandedEntries.delete(id);
        get(toggle.getAttribute("aria-controls")).hidden = !open; toggle.setAttribute("aria-expanded", String(open)); labelChangeToggle(entry, toggle); fitHeight(); return;
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
    document.addEventListener("pointerdown", () => { suppressClickUntil = 0; pointerActive = true; }, true);
    const releasePointer = () => { pointerActive = false; if (groupsDirty) refreshGroups(); };
    document.addEventListener("pointerup", releasePointer, true); document.addEventListener("pointercancel", releasePointer, true);
    document.addEventListener("scroll", () => closeMenu(), true);
    root.addEventListener("resize", () => { closeMenu(); fitHeight(); });
    root.addEventListener("scroll", fitHeight, { passive: true });
    resizer.addEventListener("pointerdown", event => {
      if (event.button !== 0 || innerWidth < 1320 || !expanded) return;
      event.preventDefault(); event.stopPropagation(); closeMenu();
      drag = { id: event.pointerId, x: event.clientX, width: paneWidth };
      resizer.setPointerCapture(event.pointerId); workspace.classList.add("memory-resizing");
    });
    resizer.addEventListener("pointermove", event => { if (drag?.id === event.pointerId) setPaneWidth(drag.width + event.clientX - drag.x); });
    const finishResize = event => {
      if (drag?.id !== event.pointerId) return;
      drag = null; workspace.classList.remove("memory-resizing"); persist(); fitHeight();
    };
    resizer.addEventListener("pointerup", finishResize); resizer.addEventListener("pointercancel", finishResize); resizer.addEventListener("lostpointercapture", finishResize);
    resizer.addEventListener("keydown", event => {
      const value = { ArrowLeft: paneWidth - 20, ArrowRight: paneWidth + 20, Home: 220, End: 520 }[event.key];
      if (value === undefined) return;
      event.preventDefault(); event.stopPropagation(); setPaneWidth(value); persist();
    });
    // Long press exposes the same secondary actions without adding mobile buttons.
    const cancelPress = () => { if (press) clearTimeout(press.timer); press = null; };
    panel.addEventListener("pointerdown", event => {
      if (event.pointerType !== "touch" || event.target === resizer) return;
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
      closeMenu(); expanded = panel.open; reflectExpanded(); persist(); adapter.layout(); fitHeight();
    });
    const flush = () => { if (auto && pending && !restoring) save(capture()); };
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flush(); });
    root.addEventListener("pagehide", flush);
    setPaneWidth(paneWidth, false); render(); if (auto) save(capture()); else schedule(); adapter.layout(); fitHeight();
    return { schedule, save: () => save(capture(), true), restore, flush, get entries() { return clone(entries); }, get restoring() { return restoring; } };
  }
  root.DividerMemory = Object.freeze({ create });
})(globalThis);
