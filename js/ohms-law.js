(function () {
  "use strict";

  const byId = id => document.getElementById(id);
  const schematic = byId("schematic"), viewport = byId("schematicViewport");
  const artwork = svg(schematic, "g"), inputs = svg(schematic, "g", { "data-schematic-inputs": "" });
  const schematicInputs = new Map();
  const memoryPanel = byId("calculatorMemory"), characteristics = byId("characteristicsDrawer"), characteristicsTab = byId("characteristicsToggle");
  const titleDefault = "Ohm’s Law";
  const groundDefault = "GND", labelLimit = 24, titleLimit = 72;
  const constructionMenu = byId("constructionMenu"), annotationEditor = byId("annotationEditor"), annotationInput = byId("annotationInput");
  const modes = { current: "Current", voltage: "Voltage", resistance: "Resistance" };
  const prefixes = { µ: 1e-6, m: 1e-3, "": 1, k: 1e3, M: 1e6, G: 1e9 };
  const units = { voltage: "V", current: "A", resistance: "Ω" };
  const packages = ["0201", "0402", "0603", "0805", "1206", "1210", "2010", "2512", "Through-hole", "Other"];
  const color = { net: "#54d2ff", known: "#6ee7ac", calculated: "#ff8e8e", missing: "#ffcf73", text: "#eaf6ff", muted: "#a8bece" };
  // Match the voltage divider's full and compact schematic dimensions.
  const leadLength = 20;
  const resistorBlockInset = 24;
  const fullSymbols = { width: 20, height: 52, radius: 2, stroke: 3, junction: 5, source: 30, ground: [20, 12, 4], groundPitch: 10 };
  const compactSymbols = { width: 14, height: 38, radius: 1, stroke: 2.5, junction: 4, source: 19, ground: [14, 9, 4], groundPitch: 7 };
  const mobile = matchMedia("(max-width: 780px)");
  const draft = new Set();
  const selectedPrefixes = new Map();
  // Keep the voltage divider's documented 0805 reference available offline.
  let packageLimits = new Map([["0805", { power: 0.14, voltage: 50 }]]);
  let selectedId = 1, nextId = 2, desktopView = false, memory, result, build, embeddedLogo, copyRows, constructionTarget, annotationEdit;
  let selectedSourceKey, drawingPointer, pendingDrawing;
  const nextSourceId = { voltage: 2, current: 1 };
  let state = { version: 1, title: "", mode: "current", voltage: 12, current: 0.012, target: null, network: newPart(1) };

  function newPart(id) { return { id, resistance: 1000, tolerance: 1, package: "0805" }; }
  function parts(node) { return node.children ? node.children.flatMap(parts) : [node]; }
  function partName(id) { return `R${id}`; }
  function findPart(id) { return parts(state.network).find(part => part.id === id); }
  function selectedPart() { return findPart(selectedId); }
  function partLabel(part) { return part.label || partName(part.id); }
  function partCaption(part) { return part.label ? `${part.label} (${partName(part.id)})` : partName(part.id); }
  function sources(snapshot = state) { return snapshot.sources || []; }
  function primarySourceKind(snapshot = state) { return snapshot.sourceType || "voltage"; }
  function defaultSourceLabel(snapshot = state) { return primarySourceKind(snapshot) === "voltage" ? "VDC" : "IDC"; }
  function sourceKey(source) { return `${source.kind === "voltage" ? "V" : "I"}${source.id}`; }
  function sourceKind(source) { return source.kind === "voltage" ? "Series voltage" : "Parallel current"; }
  function sourceInputLabel(field, snapshot = state) {
    const currentDriven = primarySourceKind(snapshot) === "current";
    if (currentDriven) return field === "voltage" ? "Load voltage" : "Source current";
    if (field === "voltage") return sources(snapshot).some(source => source.kind === field) ? "Main source voltage" : "Supply voltage";
    return sources(snapshot).some(source => source.kind === field) ? "Load current" : "Circuit current";
  }
  function selectedSource() { return sources().find(source => sourceKey(source) === selectedSourceKey); }
  function sourceTotal(kind) {
    return sources().filter(source => source.kind === kind).reduce((sum, source) => sum + (source.value ?? NaN), 0);
  }
  function parallel(values) {
    const minimum = Math.min(...values);
    return minimum / values.reduce((sum, value) => sum + minimum / value, 0);
  }
  function combine(kind, values) { return kind === "series" ? values.reduce((sum, value) => sum + value, 0) : parallel(values); }

  function equivalent(node, resistanceFor) {
    return node.children ? combine(node.kind, node.children.map(child => equivalent(child, resistanceFor))) : resistanceFor(node);
  }

  function inverse(node, target, wanted) {
    if (!node.children) return wanted;
    const branch = node.children.find(child => parts(child).some(part => part.id === target));
    const others = node.children.filter(child => child !== branch).map(child => equivalent(child, part => part.resistance));
    const known = combine(node.kind, others);
    if (node.kind === "series") return inverse(branch, target, wanted - known);
    if (wanted >= known) return NaN;
    return inverse(branch, target, wanted / (1 - wanted / known));
  }

  function distribute(node, voltage, current, resistanceFor, readings) {
    if (!node.children) {
      readings.set(node.id, { voltage, current, power: voltage * current });
      return;
    }
    for (const child of node.children) {
      const resistance = equivalent(child, resistanceFor);
      if (node.kind === "series") distribute(child, current * resistance, current, resistanceFor, readings);
      else distribute(child, voltage, voltage / resistance, resistanceFor, readings);
    }
  }

  function analyze() {
    const { mode, network, target } = state;
    const currentDriven = primarySourceKind() === "current";
    const allParts = parts(network);
    for (const field of ["voltage", "current"]) {
      if (mode !== field && !Number.isFinite(state[field])) return { error: `Enter a valid ${sourceInputLabel(field).toLowerCase()}.` };
    }
    const missingSource = sources().find(source => !Number.isFinite(source.value));
    if (missingSource) return { error: `Enter a valid value for ${sourceKey(missingSource)}.` };
    const seriesVoltage = sourceTotal("voltage");
    const parallelCurrent = sourceTotal("current");
    // Only the ideal source on the main branch sets a load quantity. Series
    // voltages and parallel currents shift the branch-to-load relationship.
    let voltage = mode === "voltage" ? 0 : state.voltage + (currentDriven ? 0 : seriesVoltage);
    let current = mode === "current" ? 0 : state.current + (currentDriven ? parallelCurrent : 0);
    if (![seriesVoltage, parallelCurrent, voltage, current].every(Number.isFinite)) {
      return { error: "The combined sources exceed the calculator’s numeric range." };
    }
    const invalid = allParts.find(part => part.id !== target && !(part.resistance > 0));
    if (invalid) return { error: `Enter a resistance greater than zero for ${partName(invalid.id)}.` };
    const invalidTolerance = allParts.find(part => part.tolerance === null);
    if (invalidTolerance) return { error: `Enter a tolerance from 0% up to, but below, 100% for ${partName(invalidTolerance.id)}.` };
    let solved;
    if (mode === "resistance") {
      const wanted = voltage / current;
      if (!(wanted > 0 && Number.isFinite(wanted))) return { error: "To solve for resistance, enter nonzero voltage and current with the same sign." };
      solved = inverse(network, target, wanted);
      if (!(solved > 0 && Number.isFinite(solved))) return { error: `${partName(target)} cannot reach ${format(wanted, "Ω")} with the other resistors at their present values.` };
    }
    const resistanceFor = part => part.id === target ? solved : part.resistance;
    const resistance = equivalent(network, resistanceFor);
    if (mode === "voltage") voltage = current * resistance;
    if (mode === "current") current = voltage / resistance;
    const mainVoltage = !currentDriven && mode !== "voltage" ? state.voltage : voltage - seriesVoltage;
    const mainCurrent = currentDriven && mode !== "current" ? state.current : current - parallelCurrent;
    const power = voltage * current;
    const range = [-1, 1].map(sign => equivalent(network, part => resistanceFor(part) * (1 + sign * part.tolerance / 100)));
    if (!(range[0] > 0) || ![voltage, mainVoltage, current, mainCurrent, power, resistance, ...range].every(Number.isFinite)) return { error: "These inputs exceed the calculator’s numeric range." };
    const readings = new Map();
    distribute(network, voltage, current, resistanceFor, readings);
    if ([...readings.values()].some(reading => !Object.values(reading).every(Number.isFinite))) return { error: "A resistor’s operating point exceeds the calculator’s numeric range." };
    return { voltage, mainVoltage, current, mainCurrent, resistance, power, solved, range, readings };
  }

  function insert(node, id, kind, added) {
    if (node.id === id) return { kind, children: [node, added] };
    if (!node.children) return node;
    const index = node.children.findIndex(child => child.id === id);
    if (index !== -1 && node.kind === kind) {
      const children = node.children.slice();
      children.splice(index + 1, 0, added);
      return { kind, children };
    }
    return { kind: node.kind, children: node.children.map(child => insert(child, id, kind, added)) };
  }

  function remove(node, id) {
    if (!node.children) return node.id === id ? null : node;
    const children = node.children.map(child => remove(child, id)).filter(Boolean)
      .flatMap(child => child.kind === node.kind ? child.children : [child]);
    return children.length === 1 ? children[0] : { kind: node.kind, children };
  }

  function engineeringPrefix(value) {
    if (!value) return "";
    return [...Object.keys(prefixes)].reverse().find(prefix => Math.abs(value) >= prefixes[prefix]) ?? "µ";
  }
  function inputPrefix(key, value) {
    const prefix = selectedPrefixes.get(key) ?? engineeringPrefix(value);
    const amount = value / prefixes[prefix];
    return Number.isFinite(amount) && (amount !== 0 || !value) ? prefix : engineeringPrefix(value);
  }

  function unitOptions(kind) {
    return Object.keys(prefixes).map(prefix => new Option(prefix + units[kind], prefix));
  }

  function format(value, unit) {
    if (!Number.isFinite(value)) return "—";
    const prefix = engineeringPrefix(value);
    return `${Number((value / prefixes[prefix]).toPrecision(5))} ${prefix}${unit}`;
  }

  function displayValues() {
    const { mode, network } = state;
    const currentDriven = primarySourceKind() === "current";
    const resistance = mode === "resistance" ? result.resistance : result.resistance ?? equivalent(network, part => part.resistance ?? NaN);
    return {
      voltage: mode === "voltage" ? result.voltage : (state.voltage ?? NaN) + (currentDriven ? 0 : sourceTotal("voltage")),
      current: mode === "current" ? result.current : (state.current ?? NaN) + (currentDriven ? sourceTotal("current") : 0),
      resistance: Number.isFinite(resistance) && resistance > 0 ? resistance : undefined,
      power: result.power
    };
  }

  function valueRole(value, calculated) {
    return calculated ? "calculated" : Number.isFinite(value) ? "known" : "missing";
  }

  function formatStress(value) {
    if (value === Infinity) return "∞%";
    if (!Number.isFinite(value)) return "—";
    return `${value >= 1e6 ? value.toExponential(2) : value.toFixed(2)}%`;
  }

  function stressRows(part) {
    const reading = result.readings?.get(part.id), limits = packageLimits.get(part.package);
    return [["Pstress", "power", "W", "power"], ["Vstress", "voltage", "V", "continuous working voltage"]].map(([label, key, unit, rating]) => {
      const actual = reading?.[key], limit = limits?.[key];
      const value = Number.isFinite(actual) && Number.isFinite(limit) ? Math.abs(actual) / limit * 100 : null;
      const description = Number.isFinite(limit) ? `Package ${rating} reference ${format(limit, unit)}.` : `A package ${rating} reference is required.`;
      return { label, value, description, limit: format(limit, unit), rating };
    });
  }
  function parseQuantity(text, unit, defaultPrefix) {
    const normalized = text.trim().replaceAll("μ", "µ").replaceAll("u", "µ").replace(/ohms?$/i, "Ω");
    const match = normalized.match(/^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\s*([µmkKMG]?)([VAΩ])?$/i);
    if (!match || match[3] && match[3].toUpperCase() !== unit) return null;
    const typedUnit = !!(match[2] || match[3]);
    const prefix = typedUnit ? match[2].replace("K", "k") : defaultPrefix;
    const value = Number(match[1]) * prefixes[prefix];
    return Number.isFinite(value) ? { value, prefix } : null;
  }

  function parseInputQuantity(text, kind, prefix) {
    const parsed = parseQuantity(text, units[kind], prefix);
    return parsed && (kind !== "resistance" || parsed.value > 0) ? parsed : null;
  }

  function trackDraft(input, edit) {
    input.addEventListener("input", () => edit(false));
    input.addEventListener("change", () => edit(true));
    input.addEventListener("blur", () => { if (draft.has(input)) edit(true); });
  }

  function finishEdit(input, commit, changed) {
    if (commit) draft.delete(input); else draft.add(input);
    if (changed) refresh(); else memory?.schedule();
  }

  function setupQuantity(id, read, write, getKind = () => id, getKey = () => id) {
    const input = byId(id), selector = byId(`${id}Unit`);
    function update(commit, changingUnit = false) {
      const parsed = parseInputQuantity(input.value, getKind(), selector.value);
      const value = parsed?.value ?? null, key = getKey(), previous = read();
      const prefix = parsed?.prefix ?? (changingUnit && !input.value.trim() ? selector.value : undefined);
      const prefixChanged = commit && prefix !== undefined && prefix !== inputPrefix(key, previous);
      write(value);
      input.setAttribute("aria-invalid", String(!parsed));
      if (commit && prefix !== undefined) {
        selectedPrefixes.set(key, prefix);
        selector.value = prefix;
        if (parsed) input.value = value / prefixes[prefix];
      }
      finishEdit(input, commit, value !== previous || prefixChanged);
    }
    trackDraft(input, update);
    selector.addEventListener("change", () => update(true, true));
    return () => {
      const kind = getKind();
      if (selector.dataset.kind !== kind) {
        selector.replaceChildren(...unitOptions(kind));
        selector.dataset.kind = kind;
      }
      const value = read();
      selector.value = inputPrefix(getKey(), value);
      input.value = value === null ? "" : value / prefixes[selector.value];
      input.setAttribute("aria-invalid", String(value === null));
    };
  }

  const showVoltage = setupQuantity("voltage", () => state.voltage, value => { state.voltage = value; });
  const showCurrent = setupQuantity("current", () => state.current, value => { state.current = value; });
  const resistanceKey = id => `resistance-${id}`;
  const showResistance = setupQuantity("resistance", () => selectedPart().resistance, value => { selectedPart().resistance = value; },
    () => "resistance", () => resistanceKey(selectedId));
  const showAddedSource = setupQuantity("addedSource", () => selectedSource()?.value ?? null, value => {
    const source = selectedSource();
    if (source) source.value = value;
  }, () => selectedSource()?.kind || "voltage", () => selectedSourceKey);

  function syncAddedSources() {
    const entries = sources(), select = byId("sourceSelect");
    byId("sourceEditor").hidden = !entries.length;
    for (const field of ["voltage", "current"]) byId(`${field}Field`).querySelector("label").textContent = sourceInputLabel(field);
    if (!selectedSource()) selectedSourceKey = entries.length ? sourceKey(entries[0]) : undefined;
    select.replaceChildren(...entries.map(source => new Option(`${sourceKey(source)} · ${sourceKind(source)}`, sourceKey(source))));
    if (!entries.length) return;
    select.value = selectedSourceKey;
    byId("addedSourceLabel").textContent = selectedSource().kind === "voltage" ? "Series voltage" : "Current into supply rail";
    showAddedSource();
  }

  function syncControls() {
    for (const button of document.querySelectorAll("[data-mode]")) button.setAttribute("aria-pressed", String(button.dataset.mode === state.mode));
    byId("voltageField").hidden = state.mode === "voltage";
    byId("currentField").hidden = state.mode === "current";
    showVoltage(); showCurrent(); syncPart(); syncAddedSources();
  }

  function syncPart() {
    const allParts = parts(state.network), part = selectedPart();
    byId("partSelect").replaceChildren(...allParts.map(item => new Option(partCaption(item) + (item.id === state.target ? " (calculated)" : ""), item.id)));
    byId("partSelect").value = String(part.id);
    byId("partPackage").value = part.package;
    byId("tolerance").value = part.tolerance ?? "";
    byId("tolerance").setAttribute("aria-invalid", String(part.tolerance === null));
    byId("removePart").disabled = allParts.length === 1;
    byId("resistanceField").hidden = part.id === state.target;
    byId("solvedResistance").hidden = part.id !== state.target;
    byId("solveSelected").hidden = state.mode !== "resistance" || part.id === state.target;
    showResistance();
  }

  function selectPart(id) {
    draft.delete(byId("resistance")); draft.delete(byId("tolerance"));
    selectedId = id;
    syncPart(); refresh();
  }

  function svg(host, name, attributes = {}, content) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
    if (content !== undefined) element.textContent = content;
    host.append(element);
    return element;
  }
  function line(host, x1, y1, x2, y2, stroke = color.net) {
    return svg(host, "line", { x1, y1, x2, y2, stroke });
  }
  function junction(host, cx, cy, r, fill = color.net) { svg(host, "circle", { cx, cy, r, fill, "data-wire-junction": "" }); }
  function text(host, x, y, content, size = 16, fill = color.text, extra = {}) {
    return svg(host, "text", { x, y, fill, "font-size": size, "font-family": "Consolas, monospace", ...extra }, content);
  }

  function fitText(label, width) {
    if (label.getComputedTextLength() > width) {
      label.setAttribute("textLength", width);
      label.setAttribute("lengthAdjust", "spacingAndGlyphs");
    }
  }

  function control(key, label) { return { "data-schematic-control": key, role: "button", tabindex: 0, "aria-label": label }; }

  function resetSchematicInput(entry) {
    const { input, selector, text, prefix, value } = entry;
    draft.delete(input);
    if (input.value !== text) input.value = text;
    if (selector && selector.value !== prefix) selector.value = prefix;
    if (value === null) input.setAttribute("aria-invalid", "true");
    else input.removeAttribute("aria-invalid");
    input.setCustomValidity("");
  }

  function commitSchematicInput(entry, report = false) {
    const { key, input, selector, text, prefix, kind, value, write } = entry;
    if (input.value === text && (!selector || selector.value === prefix)) {
      resetSchematicInput(entry);
      memory?.schedule();
      return;
    }
    const parsed = selector ? parseInputQuantity(input.value, kind, selector.value)
      ?? (value === null && !input.value.trim() ? { value: null, prefix: selector.value } : null) : { value: input.value };
    if (!parsed) {
      if (report) {
        input.setAttribute("aria-invalid", "true");
        input.setCustomValidity(kind === "resistance" ? "Enter a resistance greater than zero." : `Enter a valid value in ${units[kind]}.`);
        input.reportValidity();
      } else {
        resetSchematicInput(entry);
        memory?.schedule();
      }
      return;
    }
    if (selector) selectedPrefixes.set(key, parsed.prefix);
    resetSchematicInput(entry);
    write(parsed.value);
    refresh();
  }

  function drawField(readout, box, { key, label, kind, value, write, centered }) {
    readout.setAttribute("data-field-readout", "");
    readout.setAttribute("aria-hidden", "true");
    let entry = schematicInputs.get(key);
    if (!entry) {
      const object = svg(inputs, "foreignObject");
      const input = document.createElement(kind === "package" ? "select" : "input");
      input.className = "schematic-input";
      input.dataset.schematicInput = key;
      entry = { key, object, input };
      schematicInputs.set(key, entry);
      if (kind === "package") {
        object.append(input);
        input.append(...packages.map(pkg => new Option(pkg)));
        input.addEventListener("change", () => commitSchematicInput(entry));
      } else {
        const group = document.createElement("div"), selector = document.createElement("select");
        group.className = "schematic-quantity";
        selector.className = "schematic-input";
        selector.dataset.schematicUnit = key;
        selector.append(...unitOptions(kind));
        group.append(input, selector);
        object.append(group);
        entry.selector = selector;
        input.type = "text";
        input.inputMode = "decimal";
        input.autocomplete = "off";
        input.spellcheck = false;
        input.addEventListener("input", () => {
          draft.add(input);
          input.removeAttribute("aria-invalid");
          input.setCustomValidity("");
        });
        input.addEventListener("blur", event => {
          if (event.relatedTarget !== selector) commitSchematicInput(entry);
        });
        selector.addEventListener("change", () => commitSchematicInput(entry));
        selector.addEventListener("blur", event => {
          if (event.relatedTarget !== input && draft.has(input)) commitSchematicInput(entry);
        });
        input.addEventListener("keydown", event => {
          if (event.isComposing || !["Enter", "Escape"].includes(event.key)) return;
          event.preventDefault();
          event.stopPropagation();
          if (event.key === "Enter") commitSchematicInput(entry, true);
          else { resetSchematicInput(entry); memory?.schedule(); }
        });
      }
    }
    const { object, input, selector } = entry;
    const prefix = selector ? inputPrefix(key, value) : "";
    const fieldText = kind === "package" ? value : Number.isFinite(value)
      ? String(Number((value / prefixes[prefix]).toPrecision(15))) : "";
    Object.assign(entry, { kind, value, write, text: fieldText, prefix, seen: true });
    for (const [attr, dimension] of Object.entries(box)) object.setAttribute(attr, dimension);
    input.setAttribute("aria-label", label);
    selector?.setAttribute("aria-label", `${label} unit`);
    input.toggleAttribute("data-centered", !!centered);
    if (!draft.has(input)) resetSchematicInput(entry);
  }

  function drawQuantityField(readout, kind, box, centered = false) {
    if (state.mode === kind) return;
    drawField(readout, box, { key: kind, label: sourceInputLabel(kind), kind, value: state[kind], centered,
      write(value) { state[kind] = value; (kind === "voltage" ? showVoltage : showCurrent)(); } });
  }

  function schematicControl(key) { return schematic.querySelector(`[data-schematic-control="${CSS.escape(key)}"]`); }
  function focusControl(key) {
    schematicControl(key)?.focus({ preventScroll: true });
  }

  function wrapLabel(value, max) {
    const lines = [];
    while ([...value].length > max) {
      const prefix = [...value].slice(0, max + 1).join(""), space = prefix.lastIndexOf(" ");
      const end = space > 0 ? space : [...prefix].slice(0, max).join("").length;
      lines.push(value.slice(0, end));
      value = value.slice(end).trimStart();
    }
    return [...lines, value];
  }

  function drawLabel(host, key, description, lines, x, y, { size, fill, centered = false, target, weight = 700 } = {}) {
    const label = svg(host, "g", { ...control(`label-${key}`, `Edit ${description}: ${lines.join(" ")}`),
      "data-annotation": key, "aria-haspopup": "dialog", ...(target == null ? {} : { "data-network-context": target }) });
    const pitch = size + 3, width = Math.max(38, ...lines.map(value => [...value].length * size * .65 + 12));
    svg(label, "rect", { class: "control-hit", x: centered ? x - width / 2 : x - 5, y: y - size,
      width, height: pitch * (lines.length - 1) + size + 6, rx: 4 });
    lines.forEach((value, index) => {
      const line = text(label, x, y + index * pitch, value, size, fill, { "text-anchor": centered ? "middle" : "start", "font-weight": weight });
      fitText(line, width - 12);
    });
    return label;
  }

  function layout(node, columnWidth, rowHeight) {
    if (!node.children) return { node, width: columnWidth, height: rowHeight };
    const children = node.children.map(child => layout(child, columnWidth, rowHeight));
    const widths = children.map(child => child.width), heights = children.map(child => child.height);
    if (node.kind === "series") return { node, children, width: Math.max(...widths), height: heights.reduce((sum, h) => sum + h, 0) };
    return { node, children, width: widths.reduce((sum, w) => sum + w, 0), height: Math.max(...heights) + 44 };
  }

  function drawStress(host, part, x, y, width, compact) {
    const group = svg(host, "g", { "data-resistor-stress": part.id, "data-stress-basis": "nominal" });
    const size = compact ? 12 : 13;
    stressRows(part).forEach(({ label, value, description }, index) => {
      const row = svg(group, "g", { "data-stress-metric": label });
      const baseline = y + index * 16;
      const fill = value === null ? color.muted : value > 100 ? color.calculated : value === 100 ? color.missing : color.known;
      const caption = text(row, x, baseline, label, size, color.muted), formatted = formatStress(value);
      fitText(text(row, x + width, baseline, formatted, size, fill, { "text-anchor": "end", "data-stress-value": "" }), width - caption.getComputedTextLength() - 6);
      svg(row, "title", {}, `Nominal ${label} ${formatted}. ${description}`);
    });
  }

  function drawNetwork(host, box, x, y, symbols, topColor) {
    const { node, width, height, children } = box, bottom = y + height;
    if (!children) {
      const calculated = node.id === state.target, value = calculated ? result.solved : node.resistance;
      const power = result.readings?.get(node.id)?.power, dissipation = format(power, "W");
      const role = valueRole(value, calculated), fill = color[role];
      const bodyWidth = symbols.width, bodyHeight = symbols.height;
      const top = y + (height - bodyHeight) / 2, end = top + bodyHeight, middle = (top + end) / 2;
      const action = calculated ? "Select calculated resistor" : "Edit resistor";
      const part = svg(host, "g", { ...control(`part-${node.id}`, `${partCaption(node)}, ${value == null ? "resistance unavailable" : format(value, "Ω")}. Power ${power === undefined ? "unavailable" : dissipation}. ${action}`),
        "data-part": node.id, "aria-pressed": String(node.id === selectedId) });
      svg(part, "rect", { class: "part-hit", x: x - resistorBlockInset, y: middle - 53, width: width - 10, height: 146, rx: 8, "stroke-width": 1 });
      line(part, x, y, x, top - leadLength, topColor);
      line(part, x, top - leadLength, x, top, fill).dataset.symbolLead = "top";
      line(part, x, end, x, end + leadLength, fill).dataset.symbolLead = "bottom";
      line(part, x, end + leadLength, x, bottom);
      svg(part, "rect", { x: x - bodyWidth / 2, y: top, width: bodyWidth, height: bodyHeight, rx: symbols.radius, fill: "#13202c", stroke: fill, "data-resistor-core": "" });
      const compact = symbols === compactSymbols, size = compact ? 12 : 15, lines = wrapLabel(partLabel(node), compact ? 10 : 12);
      drawLabel(host, `part-${node.id}`, `${partName(node.id)} label`, lines, x + 24, middle - 33 - (lines.length - 1) * (size + 3),
        { size, fill, target: node.id });
      const caption = partCaption(node), formatted = format(value, "Ω"), valueX = x + 24, fieldWidth = width - 62;
      const resistance = text(host, valueX, middle - 10, formatted, compact ? 12 : 14, fill,
        { "data-resistor-value": node.id, "data-value-role": role, "data-network-context": node.id });
      fitText(resistance, fieldWidth);
      if (!calculated) drawField(resistance, { x: valueX, y: middle - 26, width: fieldWidth, height: 25 },
        { key: resistanceKey(node.id), label: `${caption} resistance`, kind: "resistance", value,
          write(next) { node.resistance = next; selectedId = node.id; syncPart(); } });
      const readingSize = compact ? 12 : 13;
      const footprint = text(host, valueX, middle + 20, node.package, readingSize, color.known,
        { "data-resistor-package": node.id, "data-network-context": node.id });
      fitText(footprint, fieldWidth);
      drawField(footprint, { x: valueX, y: middle + 5, width: fieldWidth, height: 25 },
        { key: `package-${node.id}`, label: `${caption} package`, kind: "package", value: node.package,
          write(next) { node.package = next; selectedId = node.id; syncPart(); } });
      const powerRow = svg(part, "g"), powerLabel = text(powerRow, valueX, middle + 48, "Power", readingSize, color.muted);
      fitText(text(powerRow, valueX + fieldWidth, middle + 48, dissipation, readingSize,
        power === undefined ? color.muted : color.text, { "text-anchor": "end", "data-resistor-power": node.id }),
        fieldWidth - powerLabel.getComputedTextLength() - 6);
      drawStress(part, node, valueX, middle + 64, fieldWidth, compact);
      return;
    }
    if (node.kind === "series") {
      let offset = 0;
      for (const child of children) {
        drawNetwork(host, child, x, y + offset, symbols, offset ? color.net : topColor);
        offset += child.height;
      }
      return;
    }
    let left = x - width / 2;
    const anchors = children.map(child => {
      const anchor = left + child.width / 2;
      left += child.width;
      return anchor;
    });
    const railTop = y + 22, railBottom = bottom - 22;
    const contacts = [...new Set([x, ...anchors])].sort((a, b) => a - b);
    line(host, x, y, x, railTop, topColor); line(host, x, railBottom, x, bottom);
    line(host, contacts[0], railTop, contacts.at(-1), railTop, topColor);
    line(host, contacts[0], railBottom, contacts.at(-1), railBottom);
    children.forEach((child, index) => {
      const anchor = anchors[index], childTop = railTop + (height - 44 - child.height) / 2;
      if (childTop > railTop) line(host, anchor, railTop, anchor, childTop, topColor);
      drawNetwork(host, child, anchor, childTop, symbols, topColor);
      if (childTop + child.height < railBottom) line(host, anchor, childTop + child.height, anchor, railBottom);
    });
    contacts.forEach((anchor, index) => {
      const connections = Number(anchor === x) + Number(anchors.includes(anchor)) + Number(index > 0) + Number(index < contacts.length - 1);
      if (connections > 2) { junction(host, anchor, railTop, symbols.junction, topColor); junction(host, anchor, railBottom, symbols.junction); }
    });
  }

  function drawCurrent(host, x, y, radius, current) {
    if (!Number.isFinite(current) || current === 0) return;
    const clockwise = current > 0, gap = clockwise ? 13 : -13;
    const top = y - Math.sqrt(radius ** 2 - gap ** 2), role = valueRole(current, state.mode === "current");
    const editable = primarySourceKind() === "voltage";
    const arrow = svg(host, "g", { "data-current-direction": clockwise ? "forward" : "reverse", role: editable && role !== "calculated" ? "group" : "img",
      "aria-label": `Conventional current ${clockwise ? "clockwise" : "counterclockwise"}, ${format(Math.abs(current), "A")}` });
    const head = svg(svg(arrow, "defs"), "marker", { id: "currentArrowHead", orient: "auto", markerUnits: "userSpaceOnUse",
      markerWidth: 14, markerHeight: 14, refX: 12, refY: 7, viewBox: "0 0 14 14" });
    svg(head, "path", { d: "M2 2L12 7L2 12", fill: "none", stroke: color.text, "stroke-width": 2.5, "stroke-linejoin": "round" });
    svg(arrow, "path", { d: `M${x + gap} ${top}A${radius} ${radius} 0 1 ${clockwise ? 1 : 0} ${x - gap} ${top}`,
      fill: "none", stroke: color.text, "stroke-width": 2.5, "marker-end": "url(#currentArrowHead)" });
    const value = text(arrow, x, y, format(current, "A"), 18, color[role], { ...(editable ? { "data-circuit-quantity": "current" } : {}),
      "data-value-role": role, "data-current-value": "", "text-anchor": "middle",
      "dominant-baseline": "central", "font-weight": 700 });
    fitText(value, 2 * radius - 16);
    if (editable) drawQuantityField(value, "current", { x: x - radius + 8, y: y - 13, width: 2 * radius - 16, height: 26 }, true);
  }

  function drawSourceSymbol(host, source, x, y, top, bottom, symbols, topColor) {
    const radius = symbols.source, upper = y - radius, lower = y + radius;
    line(host, x, top, x, upper - leadLength, topColor);
    line(host, x, lower + leadLength, x, bottom);
    const attributes = source.key ? { "data-added-source": source.key, "data-source-kind": source.kind } : { "aria-haspopup": "menu" };
    const group = svg(host, "g", { ...control(source.key ? `source-${source.key}` : "source", source.key ? `Edit ${source.key}` : `${modes[source.kind]} source options`),
      "data-network-context": "source", ...attributes });
    const hitRadius = radius + 4;
    svg(group, "rect", { class: "control-hit", x: x - hitRadius, y: y - hitRadius, width: 2 * hitRadius, height: 2 * hitRadius, rx: 8 });
    line(group, x, upper - leadLength, x, upper, source.fill).dataset.symbolLead = "top";
    line(group, x, lower, x, lower + leadLength, source.fill).dataset.symbolLead = "bottom";
    svg(group, "circle", { cx: x, cy: y, r: radius, fill: "#13202c", stroke: source.fill,
      [source.key ? "data-added-source-core" : `data-${source.kind}-source`]: "" });
    if (source.kind === "current") {
      const half = radius * .48, head = Math.min(6, radius * .25);
      svg(group, "path", { d: `M${x} ${y + half}V${y - half}m${-head} ${head}l${head} ${-head} ${head} ${head}`,
        fill: "none", stroke: source.fill, "stroke-linejoin": "round", "data-source-direction": "into-supply" });
    } else {
      const compact = symbols === compactSymbols;
      text(group, x, y - 2, "+", compact ? 14 : 18, source.fill, { "text-anchor": "middle" });
      text(group, x, y + (compact ? 11 : 15), "−", compact ? 14 : 18, source.fill, { "text-anchor": "middle" });
    }
    return group;
  }

  function drawAddedSource(host, source, x, y, top, bottom, symbols, topColor, textWidth) {
    const key = sourceKey(source), fill = color[valueRole(source.value, false)];
    const branch = svg(host, "g");
    const group = drawSourceSymbol(branch, { key, kind: source.kind, fill }, x, y, top, bottom, symbols, topColor);
    const labelX = x + symbols.source + 8;
    text(group, labelX, y - 6, key, 13, fill, { "font-weight": 700 });
    const readout = text(branch, labelX, y + 17, format(source.value, units[source.kind]), 14, fill,
      { "data-added-source-value": key, "data-network-context": "source", "data-source-key": key });
    fitText(readout, textWidth);
    drawField(readout, { x: labelX, y: y, width: textWidth, height: 26 },
      { key, label: `${key} ${sourceKind(source).toLowerCase()}`, kind: source.kind, value: source.value,
        write(next) { source.value = next; selectAddedSource(key); } });
    return branch;
  }

  function rightEdge(element) {
    const bounds = element.getBBox();
    return bounds.x + bounds.width;
  }

  function drawCircuit() {
    if (drawingPointer !== undefined) { pendingDrawing = true; return; }
    pendingDrawing = false;
    const focusedControl = document.activeElement?.dataset.schematicControl;
    for (const entry of schematicInputs.values()) entry.seen = false;
    const compact = mobile.matches && !desktopView, symbols = compact ? compactSymbols : fullSymbols;
    const columnWidth = compact ? 176 : 190, box = layout(state.network, columnWidth, compact ? 198 : 208);
    const series = sources().filter(source => source.kind === "voltage");
    const parallel = sources().filter(source => source.kind === "current");
    const radius = compact ? 57 : 62, railLeft = compact ? 63 : 81, sourceTextWidth = compact ? 106 : 116;
    const branchWidth = symbols.source + 8 + sourceTextWidth + 32;
    const sourceLeft = railLeft + branchWidth * parallel.length;
    const sourceTextLeft = sourceLeft + symbols.source + 8;
    const firstBlockLeft = sourceTextLeft + sourceTextWidth + 2 * (radius + 10);
    const naturalWidth = Math.ceil(firstBlockLeft + resistorBlockInset + box.width - columnWidth / 2 + 95);
    const width = Math.max(naturalWidth, viewport.clientWidth), offset = (width - naturalWidth) / 2;
    const names = wrapLabel(state.title || titleDefault, Math.floor((width - 38) / 13));
    const rowHeight = 2 * (symbols.source + leadLength + 8), seriesHeight = series.length * rowHeight;
    const y = 116 + 23 * names.length, loopHeight = Math.max(box.height, 2 * (radius + 15), rowHeight + seriesHeight);
    const bottom = y + loopHeight, networkY = y + (loopHeight - box.height) / 2;
    const tileTop = bottom + leadLength + 2 * symbols.groundPitch + 13, height = tileTop + 184;
    const x = naturalWidth - 95 - box.width / 2 + offset, sourceX = sourceLeft + offset, sourceY = (y + bottom) / 2;
    const values = displayValues(), kind = primarySourceKind();
    const sourceCalculated = state.mode === kind;
    const sourceValue = sourceCalculated ? (kind === "voltage" ? result.mainVoltage : result.mainCurrent) : state[kind];
    const sourceRole = valueRole(sourceValue, sourceCalculated);
    const topColor = state.mode === "voltage" ? color.calculated : color.net, sourceColor = color[sourceRole];
    artwork.replaceChildren();
    schematic.setAttribute("width", width); schematic.setAttribute("height", height);
    schematic.setAttribute("viewBox", `0 0 ${width} ${height}`);
    viewport.style.setProperty("--drawing-width", `${width}px`);
    svg(artwork, "rect", { x: 1, y: 1, width: width - 2, height: height - 2, rx: 13, fill: "#101823", stroke: "#39586f", "stroke-width": 1.5 });
    svg(artwork, "image", { x: 16, y: 13, width: 112, height: 36, href: embeddedLogo || "../logo.png", "data-circuit-logo": "" });
    const stamp = build ? svg(artwork, "a", { href: `https://github.com/miniPCB/minipcb.github.io/commit/${build.commit}`, target: "_blank", rel: "noopener noreferrer", "data-built-at": build.builtAt, "data-build-commit": build.commit }) : artwork;
    const buildLabel = build ? `${build.builtAt.slice(0, 19).replace("T", " ")} UTC · ${build.commit.slice(0, 7)}` : "Unpublished source";
    text(stamp, 16, 65, buildLabel, 11, color.muted);
    drawLabel(artwork, "title", "circuit title", names, width / 2, 94, { size: 20, fill: color.text, centered: true });

    const drawing = svg(artwork, "g", { "stroke-width": symbols.stroke, "stroke-linecap": "round" });
    line(drawing, railLeft + offset, y, x, y, topColor); line(drawing, railLeft + offset, bottom, x, bottom);
    if (networkY > y) {
      line(drawing, x, y, x, networkY, topColor);
      line(drawing, x, networkY + box.height, x, bottom);
    }
    parallel.forEach((source, index) => {
      const branchX = railLeft + offset + index * branchWidth;
      drawAddedSource(drawing, source, branchX, sourceY, y, bottom, symbols, topColor, sourceTextWidth);
      if (index > 0) {
        junction(drawing, branchX, y, symbols.junction, topColor);
        junction(drawing, branchX, bottom, symbols.junction);
      }
    });
    if (parallel.length) junction(drawing, sourceX, y, symbols.junction, topColor);

    const mainY = sourceY + seriesHeight / 2, sourceText = [];
    [...series].reverse().forEach((source, index) => {
      const center = mainY - (series.length - index) * rowHeight;
      sourceText.push(drawAddedSource(drawing, source, sourceX, center, index ? center - rowHeight / 2 : y,
        center + rowHeight / 2, symbols, index ? color.net : topColor, sourceTextWidth));
    });
    drawSourceSymbol(drawing, { kind, fill: sourceColor }, sourceX, mainY,
      series.length ? mainY - rowHeight / 2 : y, bottom, symbols, series.length ? color.net : topColor);
    const sourceLabel = wrapLabel(state.sourceLabel || defaultSourceLabel(), compact ? 10 : 11);
    const labelX = sourceTextLeft + offset;
    const caption = drawLabel(drawing, "source", "source label", sourceLabel, labelX, mainY - 6 - (sourceLabel.length - 1) * 16,
      { size: 13, fill: sourceColor, target: "source" });
    const readout = text(drawing, labelX, mainY + 17, format(sourceValue, units[kind]), 14, sourceColor,
      { "data-circuit-quantity": kind, "data-value-role": sourceRole, "data-network-context": "source" });
    fitText(readout, sourceTextWidth);
    drawQuantityField(readout, kind, { x: labelX, y: mainY, width: sourceTextWidth, height: 26 });
    const sourceRight = Math.max(labelX + sourceTextWidth, ...[caption, readout, ...sourceText].map(rightEdge));
    drawCurrent(drawing, (sourceRight + firstBlockLeft + offset) / 2, sourceY, radius, result.current);
    const groundX = sourceX, ground = svg(drawing, "g", { "data-ground-symbol": "" });
    junction(drawing, groundX, bottom, symbols.junction);
    line(ground, groundX, bottom, groundX, bottom + leadLength).dataset.symbolLead = "ground";
    symbols.ground.forEach((half, index) => line(ground, groundX - half, bottom + leadLength + symbols.groundPitch * index, groundX + half, bottom + leadLength + symbols.groundPitch * index));
    drawLabel(drawing, "ground", "ground label", [state.groundLabel || groundDefault],
      groundX + (compact ? 20 : 28), bottom + leadLength + (compact ? 16 : 22),
      { size: compact ? 12 : 16, fill: color.net, weight: 400 });
    drawNetwork(drawing, box, x, networkY, symbols, topColor);

    const tiles = [
      [series.length || kind === "current" ? "Load voltage" : "Voltage", "voltage", "V", "#75d5ff", "#12354b"],
      [parallel.length ? "Load current" : "Current", "current", "A", "#81e6b8", "#143d35"],
      ["Resistance", "resistance", "Ω", "#ffd083", "#44331c"],
      ["Total power", "power", "W", "#d0acff", "#2c2348"]
    ];
    const tileWidth = (width - 42) / 2;
    tiles.forEach(([label, field, unit, accent, background], index) => {
      const tileX = 16 + index % 2 * (tileWidth + 10), tileY = tileTop + Math.floor(index / 2) * 61;
      const tile = svg(artwork, "g", { "data-operating-point": field });
      svg(tile, "rect", { x: tileX, y: tileY, width: tileWidth, height: 54, rx: 8, fill: background });
      svg(tile, "rect", { x: tileX, y: tileY + 9, width: 4, height: 36, rx: 2, fill: accent });
      const labelX = tileX + 14;
      text(tile, labelX, tileY + 16, label, compact ? 14 : 13, accent);
      const role = field === "power" && Number.isFinite(values.power) ? "derived" : valueRole(values[field], field === state.mode);
      const fill = role === "derived" ? color.text : color[role];
      const quantityInput = kind === "current" ? field === "voltage"
        : field === "current" && (!Number.isFinite(result.current) || result.current === 0);
      const value = text(tile, labelX, tileY + 40, format(values[field], unit), compact ? 19 : 16, fill,
        { "data-operating-value": field, "data-value-role": role, ...(quantityInput ? { "data-circuit-quantity": field } : {}) });
      if (quantityInput) drawQuantityField(value, field, { x: labelX, y: tileY + 22, width: Math.min(118, tileWidth - 28), height: 26 });
    });
    const legend = svg(artwork, "g", { transform: `translate(16 ${tileTop + 126})`, "data-solve-legend": "", role: "group",
      "aria-label": "Circuit color key, green for known values and red for calculated values" });
    for (const [x, label, role, background, badgeWidth] of [[0, "Known", "known", "#173b31", 86], [94, "Calculated", "calculated", "#462b32", 110]]) {
      svg(legend, "rect", { x, y: 0, width: badgeWidth, height: 28, rx: 8, fill: background });
      text(legend, x + 12, 19, label, 14, color[role]);
    }
    text(artwork, 16, height - 11, "Nominal stress · package reference limits", 12, color.muted);
    for (const [key, entry] of schematicInputs) {
      if (entry.seen) continue;
      resetSchematicInput(entry);
      entry.object.remove();
      schematicInputs.delete(key);
    }
    if (focusedControl) focusControl(focusedControl);
    updateView();
  }

  function addRows(table, rows) {
    const body = table.tBodies[0] || table.createTBody();
    body.replaceChildren();
    for (const [label, value, id] of rows) {
      const row = body.insertRow(), heading = document.createElement("th");
      heading.scope = "row"; heading.textContent = label; row.append(heading);
      const cell = row.insertCell(); cell.textContent = value;
      if (id) cell.dataset.field = id;
    }
  }

  function rangeText(values, unit) {
    if (!values?.every(Number.isFinite)) return "—";
    const [lower, upper] = [...values].sort((a, b) => a - b);
    return `${format(lower, unit)} to ${format(upper, unit)}`;
  }

  function renderCharacteristics() {
    const { voltage, current, resistance, power } = displayValues(), { range, readings } = result;
    const extras = sources(), hasSeries = extras.some(source => source.kind === "voltage"), hasParallel = extras.some(source => source.kind === "current");
    const currentDriven = primarySourceKind() === "current";
    const rows = [
      [hasSeries || currentDriven ? "Voltage across load" : "Supply voltage", format(voltage, "V"), "voltage"],
      [hasParallel ? "Load current" : "Circuit current", format(current, "A"), "current"],
      ["Equivalent resistance", format(resistance, "Ω"), "resistance"], ["Total power", format(power, "W"), "power"],
      ["Equivalent resistance range", rangeText(range, "Ω"), "resistanceRange"]
    ];
    if (hasSeries) {
      const mainVoltage = currentDriven || state.mode === "voltage" ? result.mainVoltage : state.voltage;
      rows.push(["Main source voltage", format(mainVoltage, "V"), "mainVoltage"]);
    }
    if (hasParallel) {
      const mainCurrent = currentDriven && state.mode !== "current" ? state.current : result.mainCurrent;
      rows.push([currentDriven ? "Main source current" : "Voltage-source branch current", format(mainCurrent, "A"), currentDriven ? "mainCurrent" : "voltageBranchCurrent"]);
    }
    for (const source of extras) rows.push([`${sourceKey(source)} · ${sourceKind(source).toLowerCase()}`, format(source.value, units[source.kind]), sourceKey(source)]);
    if (state.mode === "voltage") rows.push(["Voltage range at fixed current", rangeText(range?.map(value => current * value), "V"), "voltageRange"]);
    else rows.push(["Current range at fixed voltage", rangeText(range?.map(value => voltage / value), "A"), "currentRange"]);
    addRows(byId("characteristicsTable"), rows);
    copyRows = [["Characteristic", "Value"], ...rows.map(([label, value]) => [label, value])];

    const reports = byId("partCharacteristics"), existing = new Map([...reports.children].map(item => [Number(item.dataset.reportId), item]));
    for (const part of parts(state.network)) {
      const name = partCaption(part), reading = readings?.get(part.id);
      const details = existing.get(part.id) || document.createElement("details");
      existing.delete(part.id);
      if (!details.hasChildNodes()) {
        details.dataset.reportId = part.id;
        const summary = document.createElement("summary"), table = document.createElement("table");
        details.append(summary, table); reports.append(details);
      }
      details.firstElementChild.textContent = name;
      details.lastElementChild.setAttribute("aria-label", `${name} measurements`);
      const data = [["Resistance", format(part.id === state.target ? result.solved : part.resistance, "Ω")],
        ["Voltage drop", format(reading?.voltage, "V")], ["Current", format(reading?.current, "A")],
        ["Power", format(reading?.power, "W")],
        ...stressRows(part).flatMap(({ label, value, limit, rating }) => [[`${label} (nominal)`, formatStress(value)], [`Package ${rating} reference`, limit]]),
        ["Tolerance", part.tolerance === null ? "—" : `±${part.tolerance}%`], ["Package", part.package]];
      addRows(details.lastElementChild, data);
      copyRows.push([], [name, "Value"], ...data);
    }
    for (const details of existing.values()) details.remove();
  }

  function refresh() {
    result = analyze();
    const status = byId("calculationStatus");
    status.hidden = !result.error; status.textContent = result.error || "";
    byId("solvedResistance").textContent = format(result.solved, "Ω");
    drawCircuit(); renderCharacteristics();
    memory?.schedule();
  }

  function networkText(node) {
    return node.children ? `(${node.children.map(networkText).join(node.kind === "series" ? " + " : " ∥ ")})` : partName(node.id);
  }

  function describe(snapshot) {
    const field = (id, label, value) => ({ id, label, value });
    const fields = [field("mode", "Solve for", modes[snapshot.mode]), field("topology", "Network", networkText(snapshot.network))];
    fields.push(field("title", "Circuit title", snapshot.title || titleDefault),
      field("sourceType", "Source type", modes[primarySourceKind(snapshot)]),
      field("sourceLabel", "Source label", snapshot.sourceLabel || defaultSourceLabel(snapshot)),
      field("groundLabel", "Ground label", snapshot.groundLabel || groundDefault));
    if (snapshot.mode !== "voltage") fields.push(field("voltage", sourceInputLabel("voltage", snapshot), format(snapshot.voltage, "V")));
    if (snapshot.mode !== "current") fields.push(field("current", sourceInputLabel("current", snapshot), format(snapshot.current, "A")));
    if (snapshot.target) fields.push(field("target", "Calculated resistor", partName(snapshot.target)));
    const describedParts = parts(snapshot.network).map(part => {
      const resistance = part.id === snapshot.target ? "Calculated" : format(part.resistance, "Ω"), tolerance = `±${part.tolerance}%`;
      return { name: partName(part.id), summary: `${part.label ? part.label + ", " : ""}${resistance}, ${tolerance}, ${part.package}`, values: {
        label: { label: "label", value: partLabel(part) }, resistance: { label: "resistance", value: resistance },
        tolerance: { label: "tolerance", value: tolerance }, package: { label: "package", value: part.package }
      } };
    });
    for (const source of sources(snapshot)) {
      const value = format(source.value, units[source.kind]);
      describedParts.push({ name: sourceKey(source), summary: `${sourceKind(source)} ${value}`, values: { source: { label: "value", value } } });
    }
    return { fields, parts: describedParts };
  }

  function validSnapshot(snapshot) {
    const ids = new Set();
    const sourceKeys = new Set();
    const validSource = source => {
      if (!source || !Object.hasOwn(nextSourceId, source.kind) || !Number.isSafeInteger(source.id)
        || source.id < (source.kind === "voltage" ? 2 : 1) || !Number.isFinite(source.value)) return false;
      const key = sourceKey(source);
      if (sourceKeys.has(key)) return false;
      sourceKeys.add(key);
      return true;
    };
    const validLabel = value => value === undefined || typeof value === "string" && value.length <= labelLimit;
    function validNode(node) {
      if (!node || typeof node !== "object") return false;
      if (node.children) return ["series", "parallel"].includes(node.kind) && Array.isArray(node.children) && node.children.length >= 2 && node.children.every(validNode);
      if (!Number.isSafeInteger(node.id) || node.id < 1 || ids.has(node.id) || !packages.includes(node.package) || !validLabel(node.label)) return false;
      if (!(node.resistance === null || (Number.isFinite(node.resistance) && node.resistance > 0)) || !Number.isFinite(node.tolerance) || node.tolerance < 0 || node.tolerance >= 100) return false;
      ids.add(node.id);
      return true;
    }
    return snapshot?.version === 1 && Object.hasOwn(modes, snapshot.mode) && typeof snapshot.title === "string" && snapshot.title.length <= titleLimit
      && validLabel(snapshot.sourceLabel) && validLabel(snapshot.groundLabel)
      && (snapshot.sourceType === undefined || Object.hasOwn(nextSourceId, snapshot.sourceType))
      && (snapshot.sources === undefined || Array.isArray(snapshot.sources) && snapshot.sources.every(validSource))
      && [snapshot.voltage, snapshot.current].every(value => value === null || Number.isFinite(value)) && validNode(snapshot.network)
      && (snapshot.mode === "resistance" ? ids.has(snapshot.target) : snapshot.target === null);
  }

  function drawersOverlap() {
    return memoryPanel.offsetWidth + characteristics.offsetWidth + 96 > document.documentElement.clientWidth;
  }
  function openCharacteristics(expand, focus = false) {
    if (expand && drawersOverlap()) memoryPanel.open = false;
    const restoreFocus = focus || characteristics.contains(document.activeElement);
    characteristics.classList.toggle("is-open", expand);
    characteristics.inert = !expand;
    characteristics.setAttribute("aria-hidden", String(!expand));
    characteristicsTab.setAttribute("aria-expanded", String(expand));
    if (!expand && restoreFocus) characteristicsTab.focus({ preventScroll: true });
  }

  byId("partPackage").replaceChildren(...packages.map(value => new Option(value)));
  for (const button of document.querySelectorAll("[data-mode]")) button.addEventListener("click", () => {
    if (button.dataset.mode === state.mode) return;
    draft.clear();
    state.mode = button.dataset.mode;
    state.target = state.mode === "resistance" ? selectedId : null;
    syncControls(); refresh();
  });
  byId("partSelect").addEventListener("change", event => selectPart(Number(event.target.value)));
  byId("solveSelected").addEventListener("click", () => {
    state.target = selectedId; syncPart(); refresh(); byId("partSelect").focus();
  });
  byId("partPackage").addEventListener("change", event => { selectedPart().package = event.target.value; refresh(); });
  function selectAddedSource(key) {
    draft.delete(byId("addedSource"));
    selectedSourceKey = key;
    syncAddedSources();
  }

  function changeSourceType(kind, key) {
    let controlKey = "source";
    if (key) {
      const source = sources().find(source => sourceKey(source) === key);
      if (!source || source.kind === kind) return;
      // The existing value uses a different unit. Start the replacement at zero.
      selectedPrefixes.delete(key);
      Object.assign(source, { id: nextSourceId[kind]++, kind, value: 0 });
      selectedSourceKey = sourceKey(source);
      controlKey = `source-${selectedSourceKey}`;
    } else {
      if (primarySourceKind() === kind) return;
      // Keep the load operating point when the source has a valid solution.
      if (!result.error) {
        state.voltage = kind === "current" ? result.voltage : result.mainVoltage;
        state.current = kind === "current" ? result.mainCurrent : result.current;
      }
      if (kind === "current") state.sourceType = kind;
      else delete state.sourceType;
    }
    syncControls();
    refresh();
    focusControl(controlKey);
  }

  byId("sourceSelect").addEventListener("change", event => selectAddedSource(event.target.value));
  byId("removeSource").addEventListener("click", () => {
    if (!selectedSource()) return;
    selectedPrefixes.delete(selectedSourceKey);
    state.sources = sources().filter(source => sourceKey(source) !== selectedSourceKey);
    if (!state.sources.length) delete state.sources;
    selectAddedSource(undefined);
    refresh();
    if (selectedSource()) byId("sourceSelect").focus();
    else focusControl("source");
  });
  const toleranceInput = byId("tolerance");
  trackDraft(toleranceInput, commit => {
    const part = selectedPart(), value = toleranceInput.valueAsNumber;
    const tolerance = value >= 0 && value < 100 ? value : null, changed = tolerance !== part.tolerance;
    part.tolerance = tolerance;
    toleranceInput.setAttribute("aria-invalid", String(tolerance === null));
    finishEdit(toleranceInput, commit, changed);
  });
  function addResistor(kind, target) {
    const part = newPart(nextId++);
    state.network = insert(state.network, Number(target), kind, part);
    selectPart(part.id);
    return part.id;
  }
  for (const button of document.querySelectorAll("[data-add]")) button.addEventListener("click", () => addResistor(button.dataset.add, selectedId));
  byId("removePart").addEventListener("click", () => {
    const allParts = parts(state.network), index = allParts.findIndex(part => part.id === selectedId);
    if (allParts.length < 2) return;
    selectedPrefixes.delete(resistanceKey(selectedId));
    state.network = remove(state.network, selectedId);
    const next = allParts[index + 1] || allParts[index - 1];
    if (state.target === selectedId) state.target = next.id;
    selectPart(next.id);
    if (byId("removePart").disabled) byId("partSelect").focus();
  });
  function openConstruction(anchor, clientX, clientY) {
    const target = anchor.dataset.part ?? anchor.dataset.networkContext;
    const addedKey = anchor.dataset.sourceKey || anchor.closest("[data-added-source]")?.dataset.addedSource;
    constructionTarget = { target, addedKey, control: anchor.closest("[data-schematic-control]")?.dataset.schematicControl || "source" };
    const sourceMenu = target === "source";
    const kind = addedKey ? sources().find(source => sourceKey(source) === addedKey)?.kind : primarySourceKind();
    const sourceLabel = addedKey || state.sourceLabel || defaultSourceLabel();
    byId("constructionTarget").textContent = sourceMenu ? sourceLabel : partCaption(findPart(Number(target)));
    for (const button of constructionMenu.querySelectorAll("button")) {
      const choice = button.dataset.changeSource;
      button.hidden = sourceMenu ? !choice || choice === kind : Boolean(choice);
    }
    constructionMenu.hidden = false;
    const bounds = anchor.getBoundingClientRect();
    const { clientWidth, clientHeight } = document.documentElement;
    constructionMenu.style.left = `${Math.max(12, Math.min(clientX ?? bounds.left, clientWidth - constructionMenu.offsetWidth - 12))}px`;
    constructionMenu.style.top = `${Math.max(12, Math.min(clientY ?? bounds.bottom, clientHeight - constructionMenu.offsetHeight - 12))}px`;
    constructionMenu.querySelector("button:not([hidden])").focus({ preventScroll: true });
  }

  function closeConstruction(restoreFocus = false) {
    if (constructionMenu.hidden) return;
    constructionMenu.hidden = true;
    if (restoreFocus) focusControl(constructionTarget.control);
    constructionTarget = null;
  }

  function openAnnotation(key, focus) {
    const part = key.startsWith("part-") ? findPart(Number(key.slice(5))) : null;
    const field = part ? "label" : key === "title" ? "title" : `${key}Label`;
    const fallback = part ? partName(part.id) : key === "title" ? titleDefault : key === "source" ? defaultSourceLabel() : groundDefault;
    const owner = part || state;
    annotationEdit = { owner, field, fallback, focus };
    byId("annotationHeading").textContent = key === "title" ? "Edit circuit title" : `Edit ${part ? partName(part.id) : key} label`;
    annotationInput.maxLength = key === "title" ? titleLimit : labelLimit;
    annotationInput.placeholder = fallback;
    annotationInput.value = owner[field] || fallback;
    annotationEditor.showModal(); annotationInput.select();
  }

  function closeAnnotation(commit) {
    const { owner, field, fallback, focus } = annotationEdit;
    if (commit) {
      const value = annotationInput.value.trim().slice(0, annotationInput.maxLength);
      if (value && value !== fallback) owner[field] = value;
      else if (field === "title") owner.title = "";
      else delete owner[field];
      if (field === "label") syncPart();
      refresh();
    }
    annotationEditor.close(); annotationEdit = null;
    focus();
  }

  byId("annotationForm").addEventListener("submit", event => { event.preventDefault(); closeAnnotation(true); });
  byId("annotationCancel").addEventListener("click", () => closeAnnotation(false));
  annotationEditor.addEventListener("cancel", event => { event.preventDefault(); closeAnnotation(false); });
  byId("editResistorLabel").addEventListener("click", event => {
    const button = event.currentTarget;
    openAnnotation(`part-${selectedId}`, () => button.focus({ preventScroll: true }));
  });

  function activateSchematicControl(event) {
    const control = event.target.closest("[data-schematic-control]");
    if (!control) return;
    event.preventDefault();
    if (control.dataset.addedSource) {
      selectAddedSource(control.dataset.addedSource);
      byId("addedSource").focus();
    } else if (control.dataset.annotation) openAnnotation(control.dataset.annotation, () => focusControl(control.dataset.schematicControl));
    else if (control.dataset.networkContext === "source") openConstruction(control);
    else {
      selectPart(Number(control.dataset.part));
      byId(selectedId === state.target ? "partSelect" : "resistance").focus();
    }
  }
  schematic.addEventListener("click", activateSchematicControl);
  function constructionFromEvent(event, pointer = false) {
    const anchor = event.target.closest("[data-part], [data-network-context]");
    if (!anchor) return;
    event.preventDefault();
    if (pointer) openConstruction(anchor, event.clientX, event.clientY);
    else openConstruction(anchor);
  }
  schematic.addEventListener("contextmenu", event => constructionFromEvent(event, event.button === 2 || !!(event.clientX || event.clientY)));
  schematic.addEventListener("keydown", event => {
    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) constructionFromEvent(event);
    else if (["Enter", " "].includes(event.key)) activateSchematicControl(event);
  });
  constructionMenu.addEventListener("click", event => {
    const action = event.target.closest("button:not([hidden])");
    if (!action || !constructionTarget) return;
    const { target, addedKey } = constructionTarget;
    closeConstruction();
    if (target === "source") changeSourceType(action.dataset.changeSource, addedKey);
    else focusControl(`part-${addResistor(action.dataset.connect, target)}`);
  });
  constructionMenu.addEventListener("keydown", event => {
    if (["Escape", "Tab"].includes(event.key)) {
      if (event.key === "Escape") event.preventDefault();
      closeConstruction(true);
    } else if (["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const buttons = [...constructionMenu.querySelectorAll("button:not([hidden])")];
      const index = buttons.indexOf(document.activeElement);
      buttons[event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowUp" ? -1 : 1) + buttons.length) % buttons.length].focus();
    }
  });
  document.addEventListener("pointerdown", event => {
    if (!constructionMenu.contains(event.target)) closeConstruction();
    // Keep the artwork under the pointer until a click completes. Blurring a
    // field can otherwise replace the SVG target before it receives the click.
    if (artwork.contains(event.target)) drawingPointer = event.pointerId;
  });
  for (const name of ["pointerup", "pointercancel", "blur"]) window.addEventListener(name, event => {
    if (drawingPointer === undefined || (name !== "blur" && event.pointerId !== drawingPointer)) return;
    drawingPointer = undefined;
    if (pendingDrawing) requestAnimationFrame(() => { if (pendingDrawing) drawCircuit(); });
  });
  document.addEventListener("scroll", event => {
    if (!constructionMenu.contains(event.target)) closeConstruction(true);
  }, true);
  window.addEventListener("resize", () => closeConstruction(true));

  const toggleView = byId("viewToggle");
  function updateView() {
    toggleView.hidden = !mobile.matches && !desktopView && Number(schematic.getAttribute("width")) <= viewport.clientWidth;
    viewport.classList.toggle("desktop-view", desktopView);
    if (desktopView) viewport.tabIndex = 0; else viewport.removeAttribute("tabindex");
    toggleView.textContent = desktopView ? "Fit to screen" : "Desktop view";
    toggleView.setAttribute("aria-pressed", String(desktopView));
  }
  toggleView.addEventListener("click", () => { desktopView = !desktopView; drawCircuit(); });
  mobile.addEventListener("change", drawCircuit);
  let viewportWidth;
  new ResizeObserver(() => {
    if (viewportWidth === viewport.clientWidth) return;
    viewportWidth = viewport.clientWidth; drawCircuit();
  }).observe(viewport);
  new ResizeObserver(() => document.documentElement.style.setProperty("--nav-height", `${byId("toolNav").offsetHeight}px`)).observe(byId("toolNav"));

  const closeOverlappingCharacteristics = () => { if (memoryPanel.open && drawersOverlap()) openCharacteristics(false); };
  memoryPanel.addEventListener("toggle", closeOverlappingCharacteristics);
  memoryPanel.addEventListener("memoryresize", closeOverlappingCharacteristics);
  window.addEventListener("resize", closeOverlappingCharacteristics);
  characteristicsTab.addEventListener("click", () => openCharacteristics(characteristics.inert));
  byId("characteristicsClose").addEventListener("click", () => openCharacteristics(false, true));
  document.addEventListener("keydown", event => {
    const inCharacteristics = event.target.closest?.("#characteristicsDrawer, #characteristicsToggle");
    if (event.key === "Escape" && !annotationEditor.open && constructionMenu.hidden && !characteristics.inert
      && (!memoryPanel.open || inCharacteristics) && !event.defaultPrevented && byId("memoryMenu").hidden) {
      event.preventDefault(); openCharacteristics(false, true);
    }
  });
  byId("copyCharacteristics").addEventListener("click", async () => {
    const text = copyRows.map(row => row.join("\t")).join("\n"), fallback = byId("copyFallback");
    try {
      await navigator.clipboard.writeText(text);
      fallback.hidden = true; byId("copyStatus").textContent = "Circuit characteristics copied.";
    } catch (_) {
      fallback.hidden = false; fallback.value = text; fallback.select(); fallback.focus();
      byId("copyStatus").textContent = "Copy the selected measurements to your clipboard.";
    }
  });

  syncControls(); refresh();
  memory = CalculatorMemory.create({
    storageKey: "minipcb-ohms-law-memory-v1", defaultTitle: titleDefault, circuitTitle: snapshot => snapshot.title, describe,
    capture: () => result.error || draft.size ? null : { title: state.title || titleDefault, summary: `${format(result.voltage, "V")} · ${format(result.current, "A")} · ${format(result.resistance, "Ω")}`, state },
    restore(snapshot) {
      if (!validSnapshot(snapshot)) throw new Error("The saved circuit is invalid.");
      state = snapshot; draft.clear(); selectedPrefixes.clear();
      const allParts = parts(state.network);
      selectedId = state.target ?? allParts[0].id;
      nextId = Math.max(nextId, ...allParts.map(part => part.id + 1));
      selectedSourceKey = undefined;
      for (const source of sources()) nextSourceId[source.kind] = Math.max(nextSourceId[source.kind], source.id + 1);
      syncControls(); refresh();
    },
    canCollapse: () => !annotationEditor.open && !inputs.contains(document.activeElement) && constructionMenu.hidden
      && !document.activeElement?.closest("#characteristicsDrawer, #characteristicsToggle")
  });

  const logoReady = fetch("../logo.png").then(response => {
    if (!response.ok) throw new Error("Logo unavailable");
    return response.blob();
  }).then(blob => new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(blob);
  })).then(url => { embeddedLogo = url; drawCircuit(); }).catch(() => {});
  const buildReady = fetch("build.json", { cache: "no-cache" }).then(response => response.ok ? response.json() : null).then(metadata => {
    if (metadata && /^[a-f0-9]{40}$/i.test(metadata.commit) && typeof metadata.builtAt === "string" && Number.isFinite(Date.parse(metadata.builtAt))) {
      build = { commit: metadata.commit.toLowerCase(), builtAt: new Date(metadata.builtAt).toISOString() };
      drawCircuit();
    }
  }).catch(() => {});
  const ratingsReady = window.ResistorParts?.load().then(catalog => {
    const references = new Map();
    for (const family of catalog.families) {
      for (const pkg of family.packages) {
        const limits = references.get(pkg.case) || { power: Infinity, voltage: Infinity };
        const power = pkg.powerW[family.defaults.mode];
        if (Number.isFinite(power)) limits.power = Math.min(limits.power, power);
        limits.voltage = Math.min(limits.voltage, pkg.workingVoltageV);
        references.set(pkg.case, limits);
      }
    }
    packageLimits = references;
    drawCircuit(); renderCharacteristics();
  }).catch(() => { /* Keep the documented 0805 reference when catalogs are unavailable. */ });

  byId("downloadCircuit").addEventListener("click", async event => {
    const button = event.currentTarget, status = byId("exportStatus");
    button.disabled = true; status.hidden = true;
    try {
      await Promise.all([logoReady, buildReady, ratingsReady]);
      if (!embeddedLogo) throw new Error("The miniPCB logo could not be embedded. Reload the calculator and try again.");
      const snapshot = schematic.cloneNode(true);
      snapshot.removeAttribute("id"); snapshot.setAttribute("role", "img"); snapshot.setAttribute("aria-label", state.title || titleDefault);
      for (const hit of snapshot.querySelectorAll(".part-hit, .control-hit, [data-schematic-inputs]")) hit.remove();
      for (const readout of snapshot.querySelectorAll("[data-field-readout]")) {
        readout.removeAttribute("data-field-readout"); readout.removeAttribute("aria-hidden");
      }
      for (const control of snapshot.querySelectorAll("[data-schematic-control], [data-network-context]")) {
        for (const attr of ["data-schematic-control", "data-source-key", "data-part", "data-annotation", "data-network-context", "role", "tabindex", "aria-pressed", "aria-label", "aria-haspopup"]) control.removeAttribute(attr);
      }
      const width = Number(snapshot.getAttribute("width")), height = Number(snapshot.getAttribute("height"));
      const imageFormat = byId("imageFormat").value;
      const blob = await CircuitImageExport.encode({ markup: new XMLSerializer().serializeToString(snapshot), width, height }, imageFormat);
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = CircuitImageExport.filename(state.title || "Ohms Law", imageFormat);
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      status.textContent = error.message; status.hidden = false;
    } finally { button.disabled = false; }
  });
})();
