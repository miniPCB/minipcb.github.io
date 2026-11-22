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
  const frameExportDialog = byId("frameExportDialog");
  const resistanceDialog = byId("calculatedResistanceDialog");
  const toleranceDialog = byId("toleranceDialog"), customTolerance = byId("customTolerance");
  const powerRatingDialog = byId("powerRatingDialog"), ratingFootprint = byId("ratingFootprint"), customPowerRating = byId("customPowerRating");
  let frameExportSnapshot, resistanceEdit, toleranceEdit, ratingPartId;
  const modes = { current: "Current", voltage: "Voltage", resistance: "Resistance" };
  const sourceModes = { voltage: ["current", "resistance"], current: ["voltage"] };
  const standardPrefixes = { µ: 1e-6, m: 1e-3, "": 1, k: 1e3, M: 1e6, G: 1e9 };
  const prefixes = { f: 1e-15, n: 1e-9, ...standardPrefixes };
  const units = { voltage: "V", current: "A", resistance: "Ω" };
  const packages = ["0201", "0402", "0603", "0805", "1206", "1210", "2010", "2512"];
  const legacyPackages = ["Through-hole", "Other"];
  const toleranceChoices = [0, 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20];
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
  const defaultResistance = 1000;
  let state = { version: 1, title: "", mode: "current", voltage: 12, current: 0.012, network: newPart(1) };

  function newPart(id) { return { id, resistance: defaultResistance, tolerance: 1, package: "0805" }; }
  function parts(node) { return node.children ? node.children.flatMap(parts) : [node]; }
  function partName(id) { return `R${id}`; }
  function findPart(id) { return parts(state.network).find(part => part.id === id); }
  function selectedPart() { return findPart(selectedId); }
  function partLabel(part) { return part.label || partName(part.id); }
  function partCaption(part) { return part.label ? `${part.label} (${partName(part.id)})` : partName(part.id); }
  function sources(snapshot = state) { return snapshot.sources || []; }
  function primarySourceKind(snapshot = state) { return snapshot.sourceType || "voltage"; }
  function sourceTolerance(snapshot = state) { return snapshot[`${primarySourceKind(snapshot)}Tolerance`] ?? 0; }
  function defaultSourceLabel(snapshot = state) { return primarySourceKind(snapshot) === "voltage" ? "VDC" : "IDC"; }
  function sourceKey(source) { return `${source.kind === "voltage" ? "V" : "I"}${source.id}`; }
  function sourceKind(source) { return source.kind === "voltage" ? "Series voltage" : "Parallel current"; }
  function sourceInputLabel(field, snapshot = state) {
    const currentDriven = primarySourceKind(snapshot) === "current";
    if (currentDriven) return field === "voltage" ? "Load voltage" : "Source current";
    if (field === "voltage") return sources(snapshot).some(source => source.kind === field) ? "Main source voltage" : "Supply voltage";
    if (snapshot.mode === "resistance") return "Target current";
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

  function analyze(legacyTarget = null) {
    const { mode, network } = state;
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
    const invalid = mode !== "resistance" && allParts.find(part => !(part.resistance > 0));
    if (invalid) return { error: `Enter a resistance greater than zero for ${partName(invalid.id)}.` };
    const invalidTolerance = allParts.find(part => part.tolerance === null);
    if (invalidTolerance) return { error: `Enter a tolerance from 0% up to, but below, 100% for ${partName(invalidTolerance.id)}.` };
    let resistances;
    if (mode === "resistance") {
      const wanted = voltage / current;
      if (!(wanted > 0 && Number.isFinite(wanted))) return { error: "To solve for resistance, enter nonzero voltage and current with the same sign." };
      const reference = part => part.resistance ?? defaultResistance;
      if (legacyTarget !== null) {
        const solved = inverse(network, legacyTarget, wanted);
        resistances = new Map(allParts.map(part => [part.id, part.id === legacyTarget ? solved : reference(part)]));
      } else {
        // Scaling a series/parallel network preserves its part ratios.
        let referenceFor = reference, nominal = equivalent(network, referenceFor);
        if (!(nominal > 0 && Number.isFinite(nominal))) {
          const largest = allParts.reduce((max, part) => Math.max(max, reference(part)), 0);
          referenceFor = part => reference(part) / largest;
          nominal = equivalent(network, referenceFor);
        }
        const scale = wanted / nominal;
        resistances = new Map(allParts.map(part => {
          const referenceValue = referenceFor(part), scaled = referenceValue * scale;
          return [part.id, scaled > 0 && Number.isFinite(scaled) ? scaled : (referenceValue / nominal) * wanted];
        }));
      }
      if ([...resistances.values()].some(value => !(value > 0 && Number.isFinite(value)))) {
        return { error: "The calculated resistances exceed the calculator’s numeric range." };
      }
    }
    const resistanceFor = part => resistances ? resistances.get(part.id) : part.resistance;
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
    return { voltage, mainVoltage, current, mainCurrent, resistance, power, resistances, range, readings };
  }

  function partResistance(part) {
    return state.mode === "resistance" ? result.resistances?.get(part.id) : part.resistance;
  }

  function keepSolvedInput(solution) {
    if (solution.error) return;
    const { mode } = state;
    if (mode === "resistance") {
      for (const part of parts(state.network)) part.resistance = solution.resistances.get(part.id);
    } else if (mode === primarySourceKind()) {
      state[mode] = mode === "voltage" ? solution.mainVoltage : solution.mainCurrent;
    } else state[mode] = solution[mode];
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

  function prefixesFor(unit) { return unit === "A" ? prefixes : standardPrefixes; }

  function engineeringPrefix(value, unit) {
    if (!value) return "";
    const magnitude = Number(Math.abs(value).toPrecision(15));
    const available = Object.keys(prefixesFor(unit));
    const smallest = available[0];
    return available.reverse().find(prefix => magnitude >= prefixes[prefix]) ?? smallest;
  }
  function inputPrefix(key, value, unit) {
    const prefix = selectedPrefixes.get(key) ?? engineeringPrefix(value, unit);
    const amount = value / prefixesFor(unit)[prefix];
    return Number.isFinite(amount) && (amount !== 0 || !value) ? prefix : engineeringPrefix(value, unit);
  }

  function unitOptions(kind) {
    const unit = units[kind];
    return Object.keys(prefixesFor(unit)).map(prefix => new Option(prefix + unit, prefix));
  }

  function format(value, unit, precision = 5) {
    if (!Number.isFinite(value)) return "—";
    const prefix = engineeringPrefix(value, unit);
    return `${Number((value / prefixes[prefix]).toPrecision(precision))} ${prefix}${unit}`;
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
      const manual = key === "power" && part.powerRating !== undefined;
      const actual = reading?.[key], limit = manual ? part.powerRating : limits?.[key];
      const value = Number.isFinite(actual) && Number.isFinite(limit) ? Math.abs(actual) / limit * 100 : null;
      const limitLabel = manual ? "Power rating" : `Package ${rating} reference`;
      const description = Number.isFinite(limit) ? `${limitLabel} ${format(limit, unit)}.` : `${limitLabel} unavailable.`;
      return { label, value, description, limit: format(limit, unit), limitLabel };
    });
  }
  function parseQuantity(text, unit, defaultPrefix) {
    const normalized = text.trim().replaceAll("μ", "µ").replaceAll("u", "µ").replace(/ohms?$/i, "Ω");
    const match = normalized.match(/^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\s*([fnµmkKMG]?)([VAΩW])?$/i);
    if (!match || match[3] && match[3].toUpperCase() !== unit) return null;
    const typedUnit = !!(match[2] || match[3]);
    const prefix = typedUnit ? match[2].replace("K", "k") : defaultPrefix;
    const value = Number(match[1]) * prefixesFor(unit)[prefix];
    return Number.isFinite(value) ? { value, prefix } : null;
  }

  function parseInputQuantity(text, kind, prefix) {
    const parsed = parseQuantity(text, units[kind], prefix);
    return parsed && (kind !== "resistance" || parsed.value > 0) ? parsed : null;
  }

  function parsePowerRating(text) {
    const parsed = parseQuantity(text, "W", "m");
    return parsed?.value > 0 ? parsed : null;
  }

  function parseTolerance(text) {
    const amount = text.trim().replace(/^±|%$/g, "").trim(), value = Number(amount);
    return /^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(amount) && value < 100 ? { value } : null;
  }

  function toleranceOptions(value) {
    const values = [...new Set([...toleranceChoices, value])].filter(Number.isFinite).sort((a, b) => a - b);
    const options = values.map(value => new Option(`±${value}%`, value));
    if (value === null) {
      const unset = new Option("—", "");
      unset.disabled = true;
      options.unshift(unset);
    }
    return [...options, new Option("Custom…", "custom")];
  }

  function packageLabel(footprint, powerRating) {
    const name = packages.includes(footprint) ? footprint : "Saved footprint";
    const limit = powerRating ?? packageLimits.get(footprint)?.power;
    const basis = powerRating === undefined && Number.isFinite(limit) ? " ref." : "";
    return `${name} · ${format(limit, "W")}${basis}`;
  }

  function packageOptions(part, selection) {
    const options = packages.map(footprint => new Option(packageLabel(footprint), footprint));
    if (selection === "saved") {
      const saved = new Option(packageLabel(part.package, part.powerRating), selection);
      saved.disabled = true;
      options.unshift(saved);
    }
    return [...options, new Option("Custom…", "custom")];
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
      const kind = getKind(), parsed = parseInputQuantity(input.value, kind, selector.value);
      const value = parsed?.value ?? null, key = getKey(), previous = read();
      const prefix = parsed?.prefix ?? (changingUnit && !input.value.trim() ? selector.value : undefined);
      const prefixChanged = commit && prefix !== undefined && prefix !== inputPrefix(key, previous, units[kind]);
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
      selector.value = inputPrefix(getKey(), value, units[kind]);
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
    const available = sourceModes[primarySourceKind()];
    for (const button of document.querySelectorAll("[data-mode]")) {
      button.disabled = !available.includes(button.dataset.mode);
      button.setAttribute("aria-pressed", String(button.dataset.mode === state.mode));
    }
    byId("voltageField").hidden = state.mode === "voltage";
    byId("currentField").hidden = state.mode === "current";
    showVoltage(); showCurrent(); syncPart(); syncAddedSources();
  }

  function syncPart() {
    const allParts = parts(state.network), part = selectedPart();
    byId("partSelect").replaceChildren(...allParts.map(item => new Option(partCaption(item), item.id)));
    byId("partSelect").value = String(part.id);
    byId("partPackage").value = part.package;
    byId("tolerance").value = part.tolerance ?? "";
    byId("tolerance").setAttribute("aria-invalid", String(part.tolerance === null));
    showResistance();
  }

  function setPartPackage(part, footprint, powerRating) {
    if (!packages.includes(footprint) && footprint !== part.package) return;
    part.package = footprint;
    if (powerRating === undefined) delete part.powerRating;
    else part.powerRating = powerRating;
    selectedId = part.id;
    syncPart();
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
    const { key, input, selector, text, prefix, kind, value, write, choose } = entry;
    if (input.value === text && (!selector || selector.value === prefix)) {
      resetSchematicInput(entry);
      memory?.schedule();
      return;
    }
    if (kind === "tolerance" && input.value === "custom") {
      resetSchematicInput(entry);
      toleranceEdit = entry;
      customTolerance.value = value ?? "";
      customTolerance.setCustomValidity("");
      toleranceDialog.showModal();
      customTolerance.select();
      return;
    }
    if (kind === "package" && input.value === "custom") {
      resetSchematicInput(entry);
      openPowerRating(entry.packagePart);
      return;
    }
    const parsed = kind === "tolerance" ? parseTolerance(input.value)
      : selector ? parseInputQuantity(input.value, kind, selector.value)
      ?? (value === null && !input.value.trim() ? { value: null, prefix: selector.value } : null) : { value: input.value };
    if (!parsed) {
      if (report) {
        input.setAttribute("aria-invalid", "true");
        const message = kind === "resistance" ? "Enter a resistance greater than zero."
          : kind === "tolerance" ? "Enter a tolerance from 0% up to, but below, 100%." : `Enter a valid value in ${units[kind]}.`;
        input.setCustomValidity(message);
        input.reportValidity();
      } else {
        resetSchematicInput(entry);
        memory?.schedule();
      }
      return;
    }
    if (choose && parsed.value !== value) {
      resetSchematicInput(entry);
      choose(parsed.value, parsed.prefix);
      return;
    }
    if (selector) selectedPrefixes.set(key, parsed.prefix);
    resetSchematicInput(entry);
    if (!choose) write(parsed.value);
    refresh();
  }

  function drawField(readout, box, { key, label, kind, value, write, centered, choose, packagePart }) {
    readout.setAttribute("data-field-readout", "");
    readout.setAttribute("aria-hidden", "true");
    let entry = schematicInputs.get(key);
    if (!entry) {
      const object = svg(inputs, "foreignObject");
      const dropdown = kind === "package" || kind === "tolerance";
      const input = document.createElement(dropdown ? "select" : "input");
      input.className = "schematic-input";
      input.dataset.schematicInput = key;
      entry = { key, object, input };
      schematicInputs.set(key, entry);
      if (dropdown) {
        object.append(input);
        input.addEventListener("change", () => commitSchematicInput(entry));
      } else {
        if (units[kind]) {
          const group = document.createElement("div"), selector = document.createElement("select");
          group.className = "schematic-quantity";
          selector.className = "schematic-input";
          selector.dataset.schematicUnit = key;
          selector.append(...unitOptions(kind));
          group.append(input, selector);
          object.append(group);
          entry.selector = selector;
          selector.addEventListener("change", () => commitSchematicInput(entry));
          selector.addEventListener("blur", event => {
            if (event.relatedTarget !== input && draft.has(input)) commitSchematicInput(entry);
          });
        } else object.append(input);
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
          if (!entry.selector || event.relatedTarget !== entry.selector) commitSchematicInput(entry);
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
    if (kind === "tolerance" && entry.value !== value) input.replaceChildren(...toleranceOptions(value));
    if (packagePart && (entry.footprint !== packagePart.package || entry.rating !== packagePart.powerRating || entry.packageLimits !== packageLimits)) {
      input.replaceChildren(...packageOptions(packagePart, value));
      Object.assign(entry, { footprint: packagePart.package, rating: packagePart.powerRating, packageLimits });
    }
    const prefix = selector ? inputPrefix(key, value, units[kind]) : "";
    const fieldText = selector && Number.isFinite(value) ? String(Number((value / prefixes[prefix]).toPrecision(15))) : String(value ?? "");
    Object.assign(entry, { kind, value, write, choose, packagePart, text: fieldText, prefix, seen: true });
    for (const [attr, dimension] of Object.entries(box)) object.setAttribute(attr, dimension);
    input.setAttribute("aria-label", label);
    selector?.setAttribute("aria-label", `${label} unit`);
    const role = readout.dataset.valueRole || "known";
    input.dataset.valueRole = role;
    if (selector) selector.dataset.valueRole = role;
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

  function drawLabel(host, key, description, lines, x, y, { size, fill, centered = false, target, weight = 700, maxWidth = Infinity } = {}) {
    const label = svg(host, "g", { ...control(`label-${key}`, `Edit ${description}: ${lines.join(" ")}`),
      "data-annotation": key, "aria-haspopup": "dialog", ...(target == null ? {} : { "data-network-context": target }) });
    const pitch = size + 3, width = Math.min(maxWidth, Math.max(38, ...lines.map(value => [...value].length * size * .65 + 12)));
    svg(label, "rect", { class: "control-hit", x: centered ? x - width / 2 : x - 5, y: y - size,
      width, height: pitch * (lines.length - 1) + size + 6, rx: 4 });
    lines.forEach((value, index) => {
      const line = text(label, x, y + index * pitch, value, size, fill, { "text-anchor": centered ? "middle" : "start", "font-weight": weight });
      fitText(line, width - 12);
    });
    return label;
  }

  function layout(node, columnWidth, rowHeight, railSpace = 44) {
    if (!node.children) return { node, width: columnWidth, height: rowHeight };
    const children = node.children.map(child => layout(child, columnWidth, rowHeight, railSpace));
    const widths = children.map(child => child.width), heights = children.map(child => child.height);
    if (node.kind === "series") return { node, children, width: Math.max(...widths), height: heights.reduce((sum, h) => sum + h, 0) };
    return { node, children, width: widths.reduce((sum, w) => sum + w, 0), height: Math.max(...heights) + railSpace };
  }

  function drawStress(host, part, x, y, width, compact) {
    const group = svg(host, "g", { "data-resistor-stress": part.id, "data-stress-basis": "nominal" });
    const size = compact ? 11 : 12, gap = 10, cellWidth = (width - gap) / 2;
    stressRows(part).forEach(({ label, value, description }, index) => {
      const row = svg(group, "g", { "data-stress-metric": label }), left = x + index * (cellWidth + gap);
      const fill = value === null ? color.muted : value > 100 ? color.calculated : value === 100 ? color.missing : color.known;
      const caption = text(row, left, y, label, size, color.muted), formatted = formatStress(value);
      fitText(text(row, left + cellWidth, y, formatted, size, fill, { "text-anchor": "end", "data-stress-value": "" }), cellWidth - caption.getComputedTextLength() - 5);
      svg(row, "title", {}, `Nominal ${label} ${formatted}. ${description}`);
    });
  }

  function drawNetwork(host, box, x, y, symbols, topColor) {
    const { node, width, height, children } = box, bottom = y + height;
    if (!children) {
      const calculated = state.mode === "resistance", value = partResistance(node);
      const power = result.readings?.get(node.id)?.power, dissipation = format(power, "W");
      const role = valueRole(value, calculated), fill = color[role];
      const bodyWidth = symbols.width, bodyHeight = symbols.height;
      const top = y + (height - bodyHeight) / 2, end = top + bodyHeight, middle = (top + end) / 2;
      const action = "Resistor options";
      const part = svg(host, "g", { ...control(`part-${node.id}`, `${partCaption(node)}, ${value == null ? "resistance unavailable" : format(value, "Ω")}. Power ${power === undefined ? "unavailable" : dissipation}. ${action}`),
        "data-part": node.id, "aria-pressed": String(node.id === selectedId), "aria-haspopup": "menu" });
      const cardHeight = 224, cardY = middle - cardHeight / 2;
      svg(part, "rect", { class: "part-hit", x: x - resistorBlockInset, y: cardY, width: width - 10, height: cardHeight, fill: "transparent" });
      line(part, x, y, x, top - leadLength, topColor);
      line(part, x, top - leadLength, x, top, fill).dataset.symbolLead = "top";
      line(part, x, end, x, end + leadLength, fill).dataset.symbolLead = "bottom";
      line(part, x, end + leadLength, x, bottom);
      svg(part, "rect", { x: x - bodyWidth / 2, y: top, width: bodyWidth, height: bodyHeight, rx: symbols.radius, fill: "#13202c", stroke: fill, "data-resistor-core": "" });
      const compact = symbols === compactSymbols, size = compact ? 15 : 18;
      const cardX = x + 24, cardWidth = width - 60, valueX = cardX + 12, fieldWidth = cardWidth - 24, caption = partCaption(node);
      const info = svg(part, "g", { "data-resistor-info": node.id });
      svg(info, "rect", { class: "part-info-box", x: cardX, y: cardY, width: cardWidth, height: cardHeight, rx: 10,
        fill: "#142535", stroke: "#39586f", "stroke-width": 1 });
      drawLabel(host, `part-${node.id}`, `${partName(node.id)} label`, [partLabel(node)], valueX, cardY + 28,
        { size, fill, target: node.id, maxWidth: fieldWidth + 10 });
      const readingSize = compact ? 12 : 13, toleranceWidth = compact ? 74 : fieldWidth / 2;
      const setting = (field, left, rowY, fieldSize, content, value, fill, extra = {}) => {
        const box = { x: left, y: rowY, width: fieldSize, height: 34, class: "resistor-field" };
        svg(info, "rect", { x: left, y: rowY, width: fieldSize, height: box.height, rx: 6, fill: "#172c3d", stroke: "#39586f", "stroke-width": 1 });
        const readout = text(info, left + 9, rowY + 22, content, compact ? 13 : 15, fill,
          { [`data-resistor-${field}`]: node.id, "data-network-context": node.id, ...extra });
        fitText(readout, fieldSize - 18);
        return { readout, box, value };
      };
      const resistance = setting("value", valueX, cardY + 40, fieldWidth, format(value, "Ω"), value, fill, { "data-value-role": role });
      text(info, valueX, cardY + 106, "Tolerance", readingSize, color.muted);
      const tolerance = setting("tolerance", valueX + fieldWidth - toleranceWidth, cardY + 84, toleranceWidth, node.tolerance === null ? "—" : `±${node.tolerance}%`,
        node.tolerance, node.tolerance === null ? color.missing : "#c6d7e5");
      for (const [field, kind, key, label] of [
        [resistance, "resistance", resistanceKey(node.id), "resistance"],
        [tolerance, "tolerance", `tolerance-${node.id}`, "tolerance (%)"]
      ]) {
        drawField(field.readout, field.box, { key, kind, label: `${caption} ${label}`, value: field.value,
          choose: calculated && kind === "resistance" ? (next, prefix) => requestResistanceEdit(node.id, next, prefix) : null,
          write(next) { node[kind] = next; selectedId = node.id; syncPart(); } });
      }
      const selection = node.powerRating !== undefined || !packages.includes(node.package) ? "saved" : node.package;
      const footprint = setting("package", valueX, cardY + 126, fieldWidth, packageLabel(node.package, node.powerRating),
        selection, color.known, { "data-footprint": node.package });
      drawField(footprint.readout, footprint.box, {
        key: `package-${node.id}`, label: `${caption} footprint and power rating`, kind: "package", value: footprint.value, packagePart: node,
        write(next) { setPartPackage(node, next); }
      });
      line(info, valueX, cardY + 169, valueX + fieldWidth, cardY + 169, "#39586f").setAttribute("stroke-width", "1");
      const powerY = cardY + 190;
      const powerRow = svg(info, "g"), powerLabel = text(powerRow, valueX, powerY, "Dissipation", readingSize, color.muted);
      fitText(text(powerRow, valueX + fieldWidth, powerY, dissipation, readingSize,
        power === undefined ? color.muted : color.text, { "text-anchor": "end", "data-resistor-power": node.id }),
        fieldWidth - powerLabel.getComputedTextLength() - 6);
      drawStress(info, node, valueX, cardY + 211, fieldWidth, compact);
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
    const reading = format(current, "A"), role = valueRole(current, state.mode === "current");
    const meter = svg(host, "g", { "data-current-indicator": "", role: role === "calculated" ? "img" : "group",
      "aria-label": `Circuit current ${Number.isFinite(current) ? reading : "unavailable"}` });
    if (!result.error && current !== 0) {
      const clockwise = current > 0, gap = clockwise ? 13 : -13;
      const top = y - Math.sqrt(radius ** 2 - gap ** 2);
      meter.dataset.currentDirection = clockwise ? "forward" : "reverse";
      meter.setAttribute("aria-label", `Conventional current ${clockwise ? "clockwise" : "counterclockwise"}, ${reading}`);
      const head = svg(svg(meter, "defs"), "marker", { id: "currentArrowHead", orient: "auto", markerUnits: "userSpaceOnUse",
        markerWidth: 14, markerHeight: 14, refX: 12, refY: 7, viewBox: "0 0 14 14" });
      svg(head, "path", { d: "M2 2L12 7L2 12", fill: "none", stroke: color.text, "stroke-width": 2.5, "stroke-linejoin": "round" });
      svg(meter, "path", { d: `M${x + gap} ${top}A${radius} ${radius} 0 1 ${clockwise ? 1 : 0} ${x - gap} ${top}`,
        fill: "none", stroke: color.text, "stroke-width": 2.5, "marker-end": "url(#currentArrowHead)" });
    } else {
      svg(meter, "circle", { cx: x, cy: y, r: radius, fill: "none", stroke: "#39586f", "stroke-width": 2.5 });
    }
    const value = text(meter, x, y, reading, 18, color[role], { "data-circuit-quantity": "current",
      "data-value-role": role, "data-current-value": "", "text-anchor": "middle",
      "dominant-baseline": "central", "font-weight": 700 });
    fitText(value, 2 * radius - 16);
    drawQuantityField(value, "current", { x: x - radius + 8, y: y - 13, width: 2 * radius - 16, height: 26 }, true);
  }

  function drawVoltmeter(host, x, top, bottom, radius, symbols, topColor, voltage) {
    const y = (top + bottom) / 2;
    const reading = format(voltage, "V");
    const meter = svg(host, "g", { "data-voltmeter": "", role: "group",
      "aria-label": `Voltmeter, load voltage ${Number.isFinite(voltage) ? reading : "unavailable"}` });
    const panelHalfWidth = radius - 2, panelHalfHeight = 30;
    for (const [from, to, stroke] of [[top, y - panelHalfHeight, topColor], [y + panelHalfHeight, bottom, color.net]]) {
      const probe = line(meter, x, from, x, to, stroke);
      probe.setAttribute("stroke-dasharray", "3 6"); probe.setAttribute("stroke-width", "1.5");
    }
    junction(meter, x, top, symbols.junction, topColor);
    junction(meter, x, bottom, symbols.junction);
    svg(meter, "rect", { x: x - panelHalfWidth, y: y - panelHalfHeight, width: 2 * panelHalfWidth, height: 2 * panelHalfHeight,
      rx: 8, fill: "#12354b", stroke: "#39586f", "stroke-width": 1, "data-voltmeter-panel": "" });
    text(meter, x, y - 11, "Load voltage", 12, "#75d5ff", { "text-anchor": "middle" });
    const value = text(meter, x, y + 11, reading, 18, color.calculated, { "data-circuit-quantity": "voltage",
      "data-value-role": "calculated", "data-voltmeter-value": "", "text-anchor": "middle", "dominant-baseline": "central", "font-weight": 700 });
    fitText(value, 2 * panelHalfWidth - 16);
  }

  function drawSourceSymbol(host, source, x, y, top, bottom, symbols, topColor) {
    const radius = symbols.source, upper = y - radius, lower = y + radius;
    line(host, x, top, x, upper - leadLength, topColor);
    line(host, x, lower + leadLength, x, bottom);
    const attributes = source.key ? { "data-added-source": source.key, "data-source-kind": source.kind } : {};
    const group = svg(host, "g", { ...control(source.key ? `source-${source.key}` : "source", source.key ? `${source.key} options` : `${modes[source.kind]} source options`),
      "data-network-context": "source", "aria-haspopup": "menu", ...attributes });
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

  function drawFrameDownload(width, compact) {
    const x = width - (compact ? 56 : 198), y = 14;
    const button = svg(artwork, "g", { id: "downloadCircuit", ...control("download", "Download framed circuit"),
      "aria-haspopup": "dialog", "aria-controls": "frameExportDialog", "data-frame-download": "" });
    svg(button, "rect", { x, y, width: compact ? 44 : 178, height: compact ? 44 : 36, rx: 9, fill: "#1e3547", stroke: "#6a8ca5" });
    svg(button, "path", { d: `M${x + 20} ${y + 9}v13m-5-5 5 5 5-5m-12 7v4h14v-4`, fill: "none",
      stroke: color.net, "stroke-width": 1.8, "stroke-linecap": "round", "stroke-linejoin": "round" });
    if (compact) svg(button, "title", {}, "Download circuit");
    else text(button, x + 37, y + 23, "Download circuit", 14, "#c6e3ff");
  }

  function drawCircuit() {
    if (drawingPointer !== undefined) { pendingDrawing = true; return; }
    pendingDrawing = false;
    const focusedControl = document.activeElement?.dataset.schematicControl;
    for (const entry of schematicInputs.values()) entry.seen = false;
    const compact = mobile.matches && !desktopView, symbols = compact ? compactSymbols : fullSymbols;
    const columnWidth = compact ? 252 : 312, box = layout(state.network, columnWidth, compact ? 250 : 260);
    const series = sources().filter(source => source.kind === "voltage");
    const parallel = sources().filter(source => source.kind === "current");
    const radius = compact ? 57 : 62, railLeft = compact ? 63 : 81, sourceTextWidth = compact ? 106 : 116;
    const instrumentClearance = compact ? 26 : 32;
    const branchWidth = symbols.source + 8 + sourceTextWidth + 32;
    const sourceLeft = railLeft + branchWidth * parallel.length;
    const sourceTextLeft = sourceLeft + symbols.source + 8;
    const firstBlockLeft = sourceTextLeft + sourceTextWidth + 2 * (radius + instrumentClearance);
    const rightPadding = columnWidth / 2 - 12;
    const naturalWidth = Math.ceil(firstBlockLeft + resistorBlockInset + box.width - columnWidth / 2 + rightPadding);
    const width = Math.max(naturalWidth, viewport.clientWidth), offset = (width - naturalWidth) / 2;
    const title = state.title || titleDefault;
    const names = compact ? wrapLabel(title, Math.max(12, Math.floor((viewport.clientWidth - 32) / 12.4))) : [title];
    const titleSize = compact ? 20 : Math.min(34, (width - 64) / (title.length * .62));
    const rowHeight = 2 * (symbols.source + leadLength + 8), seriesHeight = series.length * rowHeight;
    const y = 134 + 24 * names.length, loopHeight = Math.max(box.height, 2 * (radius + 15), rowHeight + seriesHeight + 24);
    const bottom = y + loopHeight, networkY = y + (loopHeight - box.height) / 2;
    const rangeRowHeight = 28, tileTop = bottom + leadLength + 2 * symbols.groundPitch + 13, height = tileTop + 165 + rangeRowHeight;
    const x = naturalWidth - rightPadding - box.width / 2 + offset, sourceX = sourceLeft + offset, sourceY = (y + bottom) / 2;
    const values = displayValues(), kind = primarySourceKind();
    const sourceValue = state[kind], sourceRole = valueRole(sourceValue, false);
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
    drawLabel(artwork, "title", "circuit title", names, width / 2, 112, { size: titleSize, fill: color.text, centered: true, weight: 600 });
    drawFrameDownload(width, compact);

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
    const tolerance = sourceTolerance(), toleranceKey = `${kind}Tolerance`;
    const toleranceReadout = text(drawing, labelX, mainY + 49, `±${tolerance}%`, 14, color.muted, { "data-source-tolerance": kind });
    fitText(toleranceReadout, sourceTextWidth);
    drawField(toleranceReadout, { x: labelX, y: mainY + 31, width: sourceTextWidth, height: 26 }, {
      key: `tolerance-${kind}`, label: `${modes[kind]} source tolerance (%)`, kind: "tolerance", value: tolerance,
      write(next) {
        if (next === 0) delete state[toleranceKey];
        else state[toleranceKey] = next;
      }
    });
    const sourceRight = Math.max(labelX + sourceTextWidth, ...[caption, readout, ...sourceText].map(rightEdge));
    const instrumentX = (sourceRight + firstBlockLeft + offset) / 2;
    if (kind === "current") drawVoltmeter(drawing, instrumentX, y, bottom, radius, symbols, topColor, values.voltage);
    else drawCurrent(drawing, instrumentX, sourceY, radius, values.current);
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
    const tileWidth = (width - 42) / 2, interval = loadRange();
    tiles.forEach(([label, field, unit, accent, background], index) => {
      const tileX = 16 + index % 2 * (tileWidth + 10), tileY = tileTop + Math.floor(index / 2) * (61 + rangeRowHeight);
      const tile = svg(artwork, "g", { "data-operating-point": field });
      const tileHeight = index < 2 ? 54 + rangeRowHeight : 54;
      svg(tile, "rect", { x: tileX, y: tileY, width: tileWidth, height: tileHeight, rx: 8, fill: background });
      svg(tile, "rect", { x: tileX, y: tileY + 9, width: 4, height: tileHeight - 18, rx: 2, fill: accent });
      const labelX = tileX + 14;
      text(tile, labelX, tileY + 16, label, compact ? 14 : 13, accent);
      const role = field === "power" && Number.isFinite(values.power) ? "derived" : valueRole(values[field], field === state.mode);
      const fill = role === "derived" ? color.text : color[role];
      text(tile, labelX, tileY + 40, format(values[field], unit), compact ? 19 : 16, fill,
        { "data-operating-value": field, "data-value-role": role });
      if (field === interval.field) {
        text(tile, labelX, tileY + 58, `Range ${interval.basis}`, 12, accent);
        fitText(text(tile, labelX, tileY + 73, interval.text, 14, color.text, { "data-operating-range": field }), tileWidth - 28);
      }
    });
    const legend = svg(artwork, "g", { transform: `translate(16 ${tileTop + 126 + rangeRowHeight})`, "data-solve-legend": "", role: "group",
      "aria-label": "Circuit color key, green for known values and red for calculated values" });
    for (const [x, label, role, background, badgeWidth] of [[0, "Known", "known", "#173b31", 86], [94, "Calculated", "calculated", "#462b32", 110]]) {
      svg(legend, "rect", { x, y: 0, width: badgeWidth, height: 28, rx: 8, fill: background });
      text(legend, x + 12, 19, label, 14, color[role]);
    }
    for (const [key, entry] of schematicInputs) {
      if (entry.seen) continue;
      resetSchematicInput(entry);
      entry.object.remove();
      schematicInputs.delete(key);
    }
    if (focusedControl) focusControl(focusedControl);
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
    return `${format(Math.min(...values), unit)} to ${format(Math.max(...values), unit)}`;
  }

  function loadRange() {
    const { range, current, voltage, mainCurrent, mainVoltage } = result;
    const voltageVaries = primarySourceKind() === "current";
    const field = voltageVaries ? "voltage" : "current";
    const tolerance = sourceTolerance();
    const nominal = voltageVaries ? current : voltage, source = voltageVaries ? mainCurrent : mainVoltage;
    const delta = Math.abs(source) * (tolerance / 100);
    const sourceEndpoints = [nominal - delta, nominal + delta];
    const endpoints = range?.flatMap(resistance => sourceEndpoints.map(value => voltageVaries ? value * resistance : value / resistance));
    const basis = tolerance ? "with tolerances" : `at fixed ${primarySourceKind()}`;
    return { field, basis, text: rangeText(endpoints, units[field]) };
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
      const mainVoltage = currentDriven ? result.mainVoltage : state.voltage;
      rows.push(["Main source voltage", format(mainVoltage, "V"), "mainVoltage"]);
    }
    if (hasParallel) {
      const mainCurrent = currentDriven ? state.current : result.mainCurrent;
      rows.push([currentDriven ? "Main source current" : "Voltage-source branch current", format(mainCurrent, "A"), currentDriven ? "mainCurrent" : "voltageBranchCurrent"]);
    }
    for (const source of extras) rows.push([`${sourceKey(source)} · ${sourceKind(source).toLowerCase()}`, format(source.value, units[source.kind]), sourceKey(source)]);
    const interval = loadRange();
    rows.push([`${modes[primarySourceKind()]} source tolerance`, `±${sourceTolerance()}%`, "sourceTolerance"],
      [`${modes[interval.field]} range ${interval.basis}`, interval.text, `${interval.field}Range`]);
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
      const data = [["Resistance", format(partResistance(part), "Ω")],
        ["Voltage drop", format(reading?.voltage, "V")], ["Current", format(reading?.current, "A")],
        ["Power", format(reading?.power, "W")],
        ...stressRows(part).flatMap(({ label, value, limit, limitLabel }) => [[`${label} (nominal)`, formatStress(value)], [limitLabel, limit]]),
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
    for (const id of ["ltspiceDownload", "markdownDownload"]) byId(id).disabled = Boolean(result.error);
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
      field("groundLabel", "Ground label", snapshot.groundLabel || groundDefault),
      field("sourceTolerance", "Source tolerance", `±${sourceTolerance(snapshot)}%`));
    if (snapshot.mode !== "voltage") fields.push(field("voltage", sourceInputLabel("voltage", snapshot), format(snapshot.voltage, "V")));
    if (snapshot.mode !== "current") fields.push(field("current", sourceInputLabel("current", snapshot), format(snapshot.current, "A")));
    const describedParts = parts(snapshot.network).map(part => {
      const resistance = format(part.resistance, "Ω"), tolerance = `±${part.tolerance}%`;
      return { name: partName(part.id), summary: `${part.label ? part.label + ", " : ""}${resistance}, ${tolerance}, ${part.package}`, values: {
        label: { label: "label", value: partLabel(part) }, resistance: { label: snapshot.mode === "resistance" ? "reference resistance" : "resistance", value: resistance },
        tolerance: { label: "tolerance", value: tolerance }, package: { label: "package", value: part.package },
        powerRating: { label: "power rating", value: part.powerRating === undefined ? "Package reference" : format(part.powerRating, "W") }
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
    const validTolerance = value => Number.isFinite(value) && value >= 0 && value < 100;
    function validNode(node) {
      if (!node || typeof node !== "object") return false;
      if (node.children) return ["series", "parallel"].includes(node.kind) && Array.isArray(node.children) && node.children.length >= 2 && node.children.every(validNode);
      if (!Number.isSafeInteger(node.id) || node.id < 1 || ids.has(node.id) || !validLabel(node.label)
        || !(packages.includes(node.package) || legacyPackages.includes(node.package))) return false;
      if (!(node.resistance === null || (Number.isFinite(node.resistance) && node.resistance > 0)) || !validTolerance(node.tolerance)) return false;
      if (node.powerRating !== undefined && !(Number.isFinite(node.powerRating) && node.powerRating > 0)) return false;
      ids.add(node.id);
      return true;
    }
    return snapshot?.version === 1 && Object.hasOwn(modes, snapshot.mode) && typeof snapshot.title === "string" && snapshot.title.length <= titleLimit
      && validLabel(snapshot.sourceLabel) && validLabel(snapshot.groundLabel)
      && (snapshot.sourceType === undefined || Object.hasOwn(nextSourceId, snapshot.sourceType))
      && (snapshot.sources === undefined || Array.isArray(snapshot.sources) && snapshot.sources.every(validSource))
      && [snapshot.voltageTolerance, snapshot.currentTolerance].every(value => value === undefined || validTolerance(value))
      && [snapshot.voltage, snapshot.current].every(value => value === null || Number.isFinite(value)) && validNode(snapshot.network)
      && (snapshot.target == null || (snapshot.mode === "resistance" && ids.has(snapshot.target)));
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
    const next = button.dataset.mode;
    if (button.disabled || next === state.mode) return;
    keepSolvedInput(result);
    draft.clear();
    state.mode = next;
    syncControls(); refresh();
  });
  byId("partSelect").addEventListener("change", event => selectPart(Number(event.target.value)));
  byId("partPackage").addEventListener("change", event => {
    if (!packages.includes(event.target.value)) return;
    setPartPackage(selectedPart(), event.target.value);
    refresh();
  });
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
        if (state.mode === "resistance") keepSolvedInput(result);
        state.voltage = kind === "current" ? result.voltage : result.mainVoltage;
        state.current = kind === "current" ? result.mainCurrent : result.current;
      }
      if (kind === "current") state.sourceType = kind;
      else delete state.sourceType;
      state.mode = sourceModes[kind][0];
      draft.clear();
    }
    syncControls();
    refresh();
    focusControl(controlKey);
  }

  byId("sourceSelect").addEventListener("change", event => selectAddedSource(event.target.value));
  function removeSource(key) {
    selectedPrefixes.delete(key);
    state.sources = sources().filter(source => sourceKey(source) !== key);
    if (!state.sources.length) delete state.sources;
    selectAddedSource(undefined);
    refresh();
    focusControl("source");
  }
  const toleranceInput = byId("tolerance");
  trackDraft(toleranceInput, commit => {
    const part = selectedPart(), tolerance = parseTolerance(toleranceInput.value)?.value ?? null;
    const changed = tolerance !== part.tolerance;
    part.tolerance = tolerance;
    toleranceInput.setAttribute("aria-invalid", String(tolerance === null));
    finishEdit(toleranceInput, commit, changed);
  });
  customTolerance.addEventListener("input", () => customTolerance.setCustomValidity(""));
  byId("toleranceForm").addEventListener("submit", event => {
    event.preventDefault();
    const parsed = parseTolerance(customTolerance.value);
    if (!parsed) {
      customTolerance.setCustomValidity("Enter a tolerance from 0% up to, but below, 100%.");
      customTolerance.reportValidity();
      return;
    }
    toleranceEdit.write(parsed.value);
    refresh();
    toleranceDialog.close();
  });
  byId("toleranceCancel").addEventListener("click", () => toleranceDialog.close());
  toleranceDialog.addEventListener("close", () => {
    if (toleranceDialog.open || !toleranceEdit) return;
    toleranceEdit.input.focus({ preventScroll: true });
    toleranceEdit = null;
  });

  function openPowerRating(part) {
    const options = packages.map(footprint => new Option(footprint));
    if (!packages.includes(part.package)) options.unshift(new Option("Keep saved footprint", part.package));
    ratingFootprint.replaceChildren(...options);
    ratingFootprint.value = part.package;
    customPowerRating.value = part.powerRating === undefined ? "" : format(part.powerRating, "W", 15);
    customPowerRating.setCustomValidity("");
    ratingPartId = part.id;
    byId("powerRatingHeading").textContent = `Custom power rating for ${partName(part.id)}`;
    powerRatingDialog.showModal();
    customPowerRating.select();
  }

  customPowerRating.addEventListener("input", () => customPowerRating.setCustomValidity(""));
  byId("powerRatingForm").addEventListener("submit", event => {
    event.preventDefault();
    const parsed = parsePowerRating(customPowerRating.value);
    if (!parsed) {
      customPowerRating.setCustomValidity("Enter a positive rating in W or mW.");
      customPowerRating.reportValidity();
      return;
    }
    const part = findPart(ratingPartId);
    if (part) {
      setPartPackage(part, ratingFootprint.value, parsed.value);
      refresh();
    }
    powerRatingDialog.close();
  });
  byId("powerRatingCancel").addEventListener("click", () => powerRatingDialog.close());
  powerRatingDialog.addEventListener("close", () => {
    if (powerRatingDialog.open) return;
    schematicInputs.get(`package-${ratingPartId}`)?.input.focus({ preventScroll: true });
    ratingPartId = undefined;
  });

  function addResistor(kind, target) {
    const part = newPart(nextId++);
    state.network = insert(state.network, Number(target), kind, part);
    selectPart(part.id);
    return part.id;
  }
  function removePart(id) {
    const allParts = parts(state.network), index = allParts.findIndex(part => part.id === id);
    if (allParts.length < 2) return;
    selectedPrefixes.delete(resistanceKey(id));
    state.network = remove(state.network, id);
    const next = allParts[index + 1] || allParts[index - 1];
    selectPart(next.id);
    focusControl(`part-${next.id}`);
  }
  function openConstruction(anchor, clientX, clientY, componentOptions = false) {
    const target = anchor.dataset.part ?? anchor.dataset.networkContext;
    const addedKey = anchor.dataset.sourceKey || anchor.closest("[data-added-source]")?.dataset.addedSource;
    constructionTarget = { target, addedKey, control: anchor.closest("[data-schematic-control]")?.dataset.schematicControl || "source" };
    const sourceMenu = target === "source";
    const kind = addedKey ? sources().find(source => sourceKey(source) === addedKey)?.kind : primarySourceKind();
    const sourceLabel = addedKey || state.sourceLabel || defaultSourceLabel();
    byId("constructionTarget").textContent = sourceMenu ? sourceLabel : partCaption(findPart(Number(target)));
    for (const button of constructionMenu.querySelectorAll("button")) {
      const choice = button.dataset.changeSource;
      const action = button.dataset.componentAction;
      if (!action) button.hidden = sourceMenu ? !choice || choice === kind : Boolean(choice);
      else if (sourceMenu) button.hidden = !componentOptions || action !== "source" || !addedKey;
      else button.hidden = !componentOptions || action === "source" || (action === "resistor" && parts(state.network).length === 1);
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

  function requestResistanceEdit(id, value, prefix) {
    resistanceEdit = { id, value, prefix };
    byId("calculatedResistanceHelp").textContent = `Use ${format(value, "Ω")} for ${partCaption(findPart(id))} and recalculate the current at the source voltage.`;
    resistanceDialog.showModal();
  }

  byId("applyCalculatedResistance").addEventListener("click", () => {
    if (!resistanceEdit || state.mode !== "resistance") return;
    const { id, value, prefix } = resistanceEdit;
    for (const part of parts(state.network)) {
      part.resistance = part.id === id ? value : partResistance(part) ?? part.resistance ?? defaultResistance;
    }
    state.mode = "current"; selectedId = id;
    selectedPrefixes.set(resistanceKey(id), prefix);
    syncControls(); refresh();
    resistanceDialog.close();
  });
  byId("calculatedResistanceCancel").addEventListener("click", () => resistanceDialog.close());
  resistanceDialog.addEventListener("close", () => {
    if (resistanceDialog.open || !resistanceEdit) return;
    schematicInputs.get(resistanceKey(resistanceEdit.id))?.input.focus({ preventScroll: true });
    resistanceEdit = null;
  });

  function activateSchematicControl(event) {
    const control = event.target.closest("[data-schematic-control]");
    if (!control) return;
    event.preventDefault();
    if (control.hasAttribute("data-frame-download")) openFrameExport();
    else if (control.dataset.annotation) openAnnotation(control.dataset.annotation, () => focusControl(control.dataset.schematicControl));
    else if (control.dataset.networkContext === "source") openConstruction(control, undefined, undefined, true);
    else {
      selectPart(Number(control.dataset.part));
      openConstruction(schematicControl(control.dataset.schematicControl) || control, undefined, undefined, true);
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
    const id = Number(target), key = `part-${id}`;
    switch (action.dataset.componentAction) {
      case "source": removeSource(addedKey); break;
      case "resistor": removePart(id); break;
      case "label": openAnnotation(key, () => focusControl(key)); break;
      default:
        if (target === "source") changeSourceType(action.dataset.changeSource, addedKey);
        else focusControl(`part-${addResistor(action.dataset.connect, target)}`);
    }
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
    toggleView.hidden = !mobile.matches;
    if (toggleView.hidden) desktopView = false;
    viewport.classList.toggle("desktop-view", desktopView);
    if (desktopView) viewport.tabIndex = 0; else viewport.removeAttribute("tabindex");
    toggleView.textContent = desktopView ? "Fit to screen" : "Desktop view";
    toggleView.setAttribute("aria-pressed", String(desktopView));
  }
  function redrawView() {
    updateView();
    drawCircuit();
  }
  toggleView.addEventListener("click", () => { desktopView = !desktopView; redrawView(); });
  mobile.addEventListener("change", redrawView);
  updateView();
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
    if (event.key === "Escape" && !annotationEditor.open && !resistanceDialog.open && !toleranceDialog.open && !powerRatingDialog.open
      && constructionMenu.hidden && !characteristics.inert
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
      const available = sourceModes[primarySourceKind()];
      if (!available.includes(state.mode)) {
        // Recover the old operating point before changing how the circuit is solved.
        keepSolvedInput(analyze(state.target));
        state.mode = available[0];
      } else if (state.target != null) {
        const previous = analyze(state.target);
        if (!previous.error) findPart(state.target).resistance = previous.resistances.get(state.target);
      }
      delete state.target;
      nextId = Math.max(nextId, ...allParts.map(part => part.id + 1));
      selectedSourceKey = undefined;
      for (const source of sources()) nextSourceId[source.kind] = Math.max(nextSourceId[source.kind], source.id + 1);
      syncControls(); refresh();
    },
    canCollapse: () => !annotationEditor.open && !resistanceDialog.open && !toleranceDialog.open && !powerRatingDialog.open
      && !inputs.contains(document.activeElement) && constructionMenu.hidden
      && !document.activeElement?.closest("#characteristicsDrawer, #characteristicsToggle")
  });

  const logoReady = fetch("../logo.png").then(response => {
    if (!response.ok) throw new Error("Logo unavailable");
    return response.blob();
  }).then(blob => new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(blob);
  })).then(url => { embeddedLogo = url; drawCircuit(); }).catch(() => {});
  fetch("build.json", { cache: "no-cache" }).then(response => response.ok ? response.json() : null).then(metadata => {
    if (metadata && /^[a-f0-9]{40}$/i.test(metadata.commit) && typeof metadata.builtAt === "string" && Number.isFinite(Date.parse(metadata.builtAt))) {
      build = { commit: metadata.commit.toLowerCase(), builtAt: new Date(metadata.builtAt).toISOString() };
      drawCircuit();
    }
  }).catch(() => {});
  window.ResistorParts?.load().then(catalog => {
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

  function downloadFile(blob, filename) {
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = filename; link.hidden = true;
    document.body.append(link);
    try { link.click(); } finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000); }
  }

  function fileTitle(title) {
    return /[a-z0-9]/i.test(title.normalize("NFKD")) ? title.replace(/[’']/g, "") : "Ohms Law";
  }

  function openFrameExport() {
    if (frameExportDialog.open) return;
    if (pendingDrawing) drawCircuit();
    const title = state.title || titleDefault, node = schematic.cloneNode(true);
    node.removeAttribute("id"); node.setAttribute("role", "img"); node.setAttribute("aria-label", title);
    for (const hit of node.querySelectorAll(".part-hit, .control-hit, [data-schematic-inputs], [data-frame-download]")) hit.remove();
    for (const readout of node.querySelectorAll("[data-field-readout]")) {
      readout.removeAttribute("data-field-readout"); readout.removeAttribute("aria-hidden");
    }
    for (const control of node.querySelectorAll("[data-schematic-control], [data-network-context]")) {
      for (const attr of ["data-schematic-control", "data-source-key", "data-part", "data-annotation", "data-network-context", "role", "tabindex", "aria-pressed", "aria-label", "aria-haspopup"]) control.removeAttribute(attr);
    }
    frameExportSnapshot = { title, node, width: Number(node.getAttribute("width")), height: Number(node.getAttribute("height")) };
    byId("frameExportTitle").textContent = title;
    byId("frameExportStatus").hidden = true;
    frameExportDialog.setAttribute("aria-busy", "false");
    for (const button of frameExportDialog.querySelectorAll("[data-frame-format]")) button.disabled = false;
    frameExportDialog.showModal();
    frameExportDialog.querySelector("[data-frame-format]").focus();
  }

  byId("frameExportClose").addEventListener("click", () => frameExportDialog.close());
  frameExportDialog.addEventListener("close", () => {
    if (frameExportDialog.open) return;
    frameExportSnapshot = null;
    focusControl("download");
  });
  frameExportDialog.addEventListener("click", async event => {
    const format = event.target.closest("[data-frame-format]")?.dataset.frameFormat, snapshot = frameExportSnapshot;
    if (!format || !snapshot || frameExportDialog.getAttribute("aria-busy") === "true") return;
    const status = byId("frameExportStatus"), buttons = frameExportDialog.querySelectorAll("[data-frame-format]");
    frameExportDialog.setAttribute("aria-busy", "true");
    for (const button of buttons) button.disabled = true;
    status.setAttribute("role", "status"); status.hidden = false; status.textContent = `Preparing ${format.toUpperCase()}…`;
    try {
      await logoReady;
      if (!frameExportDialog.open || snapshot !== frameExportSnapshot) return;
      if (!embeddedLogo) throw new Error("The miniPCB logo could not be embedded. Reload the calculator and try again.");
      snapshot.node.querySelector("[data-circuit-logo]").setAttribute("href", embeddedLogo);
      const markup = new XMLSerializer().serializeToString(snapshot.node);
      const blob = await CircuitImageExport.encode({ markup, width: snapshot.width, height: snapshot.height }, format);
      if (!frameExportDialog.open || snapshot !== frameExportSnapshot) return;
      downloadFile(blob, CircuitImageExport.filename(fileTitle(snapshot.title), format));
      frameExportDialog.close();
    } catch (error) {
      if (frameExportDialog.open && snapshot === frameExportSnapshot) {
        status.setAttribute("role", "alert"); status.textContent = error.message || "Image export failed. Try another format.";
      }
    } finally {
      if (snapshot === frameExportSnapshot) {
        frameExportDialog.setAttribute("aria-busy", "false");
        for (const button of buttons) button.disabled = false;
      }
    }
  });

  function exportModel() {
    const resistors = [];
    let nextNode = 1;
    function visit(node, from, to) {
      if (!node.children) {
        const component = { name: partName(node.id), kind: "resistance", from, to,
          value: partResistance(node) };
        resistors.push(component);
        return component;
      }
      let start = from;
      return { kind: node.kind, children: node.children.map((child, index) => {
        const end = node.kind === "parallel" || index === node.children.length - 1 ? to : `N${nextNode++}`;
        const branch = visit(child, start, end);
        if (node.kind === "series") start = end;
        return branch;
      }) };
    }
    const load = visit(state.network, "LOAD", "0"), kind = primarySourceKind();
    const primary = { name: kind === "voltage" ? "V1" : "IMAIN", kind, value: kind === "voltage" ? result.mainVoltage : result.mainCurrent };
    const withName = source => ({ name: sourceKey(source), kind: source.kind, value: source.value });
    const series = [primary, ...sources().filter(source => source.kind === "voltage").map(withName)];
    let lower = "0";
    const stack = series.map((component, index) => {
      const upper = index === series.length - 1 ? "LOAD" : `VS${index + 1}`;
      const { kind } = component, branch = { ...component, from: kind === "current" ? lower : upper, to: kind === "current" ? upper : lower };
      lower = upper;
      return branch;
    });
    const parallel = sources().filter(source => source.kind === "current").map(source => ({ ...withName(source), from: "0", to: "LOAD" }));
    const components = [...stack, ...parallel, ...resistors];
    const netlist = ["* miniPCB nominal DC circuit", ...components.map(({ name, kind, from, to, value }) =>
      `${name} ${from} ${to} ${kind === "resistance" ? "" : "DC "}${value}`), ".op", ".end"].join("\n");
    return { title: state.title || titleDefault, load, resistors, stack, parallel, components, netlist };
  }

  function ltspiceSchematic(model) {
    const wires = [], symbols = [], labels = new Map();
    const box = layout(model.load, 256, 160, 64), railTop = 112;
    const railBottom = railTop + Math.max(box.height, model.stack.length * 160);
    const sourceX = 96 + model.parallel.length * 192, loadX = sourceX + 160 + box.width / 2;
    labels.set("LOAD", [sourceX, railTop]); labels.set("0", [sourceX, railBottom]);
    function wire(x1, y1, x2, y2) {
      if (x1 !== x2 || y1 !== y2) wires.push(`WIRE ${x2} ${y2} ${x1} ${y1}`);
    }
    function rail(y, contacts) {
      const xs = [...new Set(contacts)].sort((a, b) => a - b);
      xs.slice(1).forEach((x, index) => wire(xs[index], y, x, y));
    }
    function place(component, x, top, bottom) {
      const upper = top + Math.floor((bottom - top - 80) / 32) * 16, lower = upper + 80;
      const { name, kind, from, to, value } = component;
      const current = kind === "current", resistor = kind === "resistance";
      // R0 resistor and voltage symbols have their first pin at the top.
      // Rotate the current symbol to place its first pin at the bottom.
      const symbol = current ? `current ${x} ${lower} R180` : `${resistor ? "res" : "voltage"} ${resistor ? x - 16 : x} ${upper - 16} R0`;
      wire(x, top, x, upper); wire(x, lower, x, bottom);
      symbols.push(`SYMBOL ${symbol}`, `SYMATTR InstName ${name}`, `SYMATTR Value ${value}`);
      const topNode = current ? to : from, bottomNode = current ? from : to;
      if (!labels.has(topNode)) labels.set(topNode, [x, top]);
      if (!labels.has(bottomNode)) labels.set(bottomNode, [x, bottom]);
    }
    function draw(box, x, top) {
      const { node, children, width, height } = box, bottom = top + height;
      if (!children) { place(node, x, top, bottom); return; }
      if (node.kind === "series") {
        for (const child of children) { draw(child, x, top); top += child.height; }
        return;
      }
      let left = x - width / 2;
      const branchTop = top + 32, branchBottom = bottom - 32, contacts = [x];
      for (const child of children) {
        const center = left + child.width / 2, start = branchTop + (height - 64 - child.height) / 2;
        contacts.push(center); left += child.width;
        wire(center, branchTop, center, start);
        draw(child, center, start);
        wire(center, start + child.height, center, branchBottom);
      }
      wire(x, top, x, branchTop); wire(x, branchBottom, x, bottom);
      rail(branchTop, contacts); rail(branchBottom, contacts);
    }
    const stackTop = railTop + (railBottom - railTop - model.stack.length * 160) / 2;
    wire(sourceX, railTop, sourceX, stackTop);
    [...model.stack].reverse().forEach((component, index) => place(component, sourceX, stackTop + index * 160, stackTop + (index + 1) * 160));
    wire(sourceX, stackTop + model.stack.length * 160, sourceX, railBottom);
    const contacts = [sourceX, loadX];
    model.parallel.forEach((component, index) => {
      const x = 96 + index * 192; contacts.push(x); place(component, x, railTop, railBottom);
    });
    const loadTop = railTop + (railBottom - railTop - box.height) / 2;
    wire(loadX, railTop, loadX, loadTop);
    draw(box, loadX, loadTop);
    wire(loadX, loadTop + box.height, loadX, railBottom);
    rail(railTop, contacts); rail(railBottom, contacts);
    const loadCurrent = model.resistors.filter(part => part.from === "LOAD").map(part => `I(${part.name})`).join("+");
    const directives = [".op", ".meas op Load_voltage_V PARAM V(LOAD)", `.meas op Load_current_A PARAM ${loadCurrent}`,
      `.meas op Total_power_W PARAM V(LOAD)*(${loadCurrent})`,
      ...model.resistors.map(({ name, from, to }) => `.meas op P_${name}_W PARAM V(${to === "0" ? from : `${from},${to}`})*I(${name})`)];
    const flags = [...labels].map(([name, [x, y]]) => `FLAG ${x} ${y} ${name}`);
    const title = model.title.replace(/[’‘]/g, "'").normalize("NFKD").replace(/[\u0300-\u036f]|[^\x20-\x7e]/g, "").trim() || "Ohm's Law";
    return ["Version 4", `SHEET 1 ${loadX + box.width / 2 + 128} ${railBottom + 96 + directives.length * 32}`,
      ...wires, ...flags, ...symbols, `TEXT 64 32 Left 2 ;${title}`,
      ...directives.map((line, index) => `TEXT 64 ${railBottom + 64 + index * 32} Left 2 !${line}`), ""].join("\r\n");
  }

  function markdownReport(model) {
    const escape = value => String(value).replace(/[\r\n]+/g, " ").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/[\\`*_#|\[\]]/g, "\\$&");
    const table = rows => [rows[0], rows[0].map(() => "---"), ...rows.slice(1)]
      .map(row => `| ${row.map(escape).join(" | ")} |`).join("\n");
    const sections = [[]];
    for (const row of copyRows) {
      if (row.length) sections.at(-1).push(row);
      else sections.push([]);
    }
    const stamp = build ? `Calculator build ${build.builtAt} · [${build.commit}](https://github.com/miniPCB/minipcb.github.io/commit/${build.commit})`
      : "Calculator build unpublished";
    return [`# ${escape(model.title)}`, stamp, `Solve mode · Find ${modes[state.mode]}`, "## Nominal operating point", table(sections[0]),
      "## Circuit connections", table([["Component", "From", "To", "Value"], ...model.components.map(({ name, kind, from, to, value }) =>
        [name, from, to, format(value, units[kind])])]),
      "## Resistor measurements", ...sections.slice(1).flatMap(([heading, ...rows]) => [`### ${escape(heading[0])}`, table([["Measurement", "Value"], ...rows])]),
      "## Nominal SPICE netlist", `\`\`\`spice\n${model.netlist}\n\`\`\``, ""].join("\n\n");
  }

  for (const [id, extension, mime, generate] of [
    ["ltspiceDownload", "asc", "text/plain", ltspiceSchematic], ["markdownDownload", "md", "text/markdown", markdownReport]
  ]) byId(id).addEventListener("click", () => {
    if (result.error) return;
    const status = byId("exportStatus");
    status.hidden = true;
    try {
      const model = exportModel(), stem = CircuitImageExport.filename(fileTitle(model.title), "svg").replace(/_circuit\.svg$/, "");
      downloadFile(new Blob([generate(model)], { type: mime + ";charset=utf-8" }), `${stem}.${extension}`);
    } catch (error) { status.textContent = error.message; status.hidden = false; }
  });
})();
