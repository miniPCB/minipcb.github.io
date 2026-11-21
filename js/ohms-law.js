(function () {
  "use strict";

  const byId = id => document.getElementById(id);
  const schematic = byId("schematic"), viewport = byId("schematicViewport");
  const memoryPanel = byId("calculatorMemory"), characteristics = byId("characteristicsDrawer"), characteristicsTab = byId("characteristicsToggle");
  const titleDefault = "Ohm’s Law";
  const modes = { current: "Current", voltage: "Voltage", resistance: "Resistance" };
  const prefixes = { µ: 1e-6, m: 1e-3, "": 1, k: 1e3, M: 1e6, G: 1e9 };
  const units = { voltage: "V", current: "A", resistance: "Ω" };
  const packages = ["0201", "0402", "0603", "0805", "1206", "1210", "2010", "2512", "Through-hole", "Other"];
  const color = { net: "#54d2ff", known: "#6ee7ac", calculated: "#ff8e8e", missing: "#ffcf73", text: "#eaf6ff", muted: "#a8bece" };
  // Match the voltage divider's full and compact schematic dimensions.
  const leadLength = 20;
  const fullSymbols = { width: 20, height: 52, radius: 2, stroke: 3, junction: 5, source: 30, ground: [20, 12, 4], groundPitch: 10 };
  const compactSymbols = { width: 14, height: 38, radius: 1, stroke: 2.5, junction: 4, source: 19, ground: [14, 9, 4], groundPitch: 7 };
  const mobile = matchMedia("(max-width: 780px)");
  const draft = new Set();
  let selectedId = 1, nextId = 2, desktopView = false, memory, result, build, embeddedLogo, copyRows;
  let state = { version: 1, title: "", mode: "current", voltage: 12, current: 0.012, target: null, network: newPart(1) };

  function newPart(id) { return { id, resistance: 1000, tolerance: 1, package: "0805" }; }
  function parts(node) { return node.children ? node.children.flatMap(parts) : [node]; }
  function partName(id) { return `R${id}`; }
  function selectedPart() { return parts(state.network).find(part => part.id === selectedId); }
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
    const allParts = parts(network);
    let { voltage, current } = state;
    if (mode !== "voltage" && !Number.isFinite(voltage)) return { error: "Enter a valid supply voltage." };
    if (mode !== "current" && !Number.isFinite(current)) return { error: "Enter a valid circuit current." };
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
    const power = voltage * current;
    const range = [-1, 1].map(sign => equivalent(network, part => resistanceFor(part) * (1 + sign * part.tolerance / 100)));
    if (!(range[0] > 0) || ![voltage, current, power, resistance, ...range].every(Number.isFinite)) return { error: "These inputs exceed the calculator’s numeric range." };
    const readings = new Map();
    distribute(network, voltage, current, resistanceFor, readings);
    if ([...readings.values()].some(reading => !Object.values(reading).every(Number.isFinite))) return { error: "A resistor’s operating point exceeds the calculator’s numeric range." };
    return { voltage, current, resistance, power, solved, range, readings };
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
  function format(value, unit) {
    if (!Number.isFinite(value)) return "—";
    const prefix = engineeringPrefix(value);
    return `${Number((value / prefixes[prefix]).toPrecision(5))} ${prefix}${unit}`;
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

  function trackDraft(input, edit) {
    input.addEventListener("input", () => edit(false));
    input.addEventListener("change", () => edit(true));
    input.addEventListener("blur", () => { if (draft.has(input)) edit(true); });
  }

  function finishEdit(input, commit, changed) {
    if (commit) draft.delete(input); else draft.add(input);
    if (changed) refresh(); else memory?.schedule();
  }

  function setupQuantity(id, read, write) {
    const input = byId(id), selector = byId(`${id}Unit`), unit = units[id];
    const available = Object.keys(prefixes);
    selector.replaceChildren(...available.map(prefix => new Option(prefix + unit, prefix)));
    function update(commit) {
      const parsed = parseQuantity(input.value, unit, selector.value);
      const valid = parsed && (id !== "resistance" || parsed.value > 0);
      const value = valid ? parsed.value : null, changed = value !== read();
      write(value);
      input.setAttribute("aria-invalid", String(!valid));
      if (commit && valid) {
        selector.value = parsed.prefix;
        input.value = value / prefixes[parsed.prefix];
      }
      finishEdit(input, commit, changed);
    }
    trackDraft(input, update);
    selector.addEventListener("change", () => update(true));
    return () => {
      const value = read(), prefix = engineeringPrefix(value);
      selector.value = available.includes(prefix) ? prefix : available.at(-1);
      input.value = value === null ? "" : value / prefixes[selector.value];
      input.setAttribute("aria-invalid", String(value === null));
    };
  }

  const showVoltage = setupQuantity("voltage", () => state.voltage, value => { state.voltage = value; });
  const showCurrent = setupQuantity("current", () => state.current, value => { state.current = value; });
  const showResistance = setupQuantity("resistance", () => selectedPart().resistance, value => { selectedPart().resistance = value; });

  function syncControls() {
    for (const button of document.querySelectorAll("[data-mode]")) button.setAttribute("aria-pressed", String(button.dataset.mode === state.mode));
    byId("voltageField").hidden = state.mode === "voltage";
    byId("currentField").hidden = state.mode === "current";
    byId("circuitTitle").value = state.title;
    showVoltage(); showCurrent(); syncPart();
  }

  function syncPart() {
    const allParts = parts(state.network), part = selectedPart();
    byId("partSelect").replaceChildren(...allParts.map(item => new Option(partName(item.id) + (item.id === state.target ? " (calculated)" : ""), item.id)));
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
  function dot(host, cx, cy, fill = color.net) { svg(host, "circle", { cx, cy, r: 4, fill }); }
  function junction(host, cx, cy, r, fill = color.net) { svg(host, "circle", { cx, cy, r, fill, "data-wire-junction": "" }); }
  function text(host, x, y, content, size = 16, fill = color.text, extra = {}) {
    return svg(host, "text", { x, y, fill, "font-size": size, "font-family": "Consolas, monospace", ...extra }, content);
  }

  function layout(node, compact) {
    if (!node.children) return { node, width: compact ? 143 : 174, height: compact ? 110 : 124 };
    const children = node.children.map(child => layout(child, compact));
    const widths = children.map(child => child.width), heights = children.map(child => child.height);
    if (node.kind === "series") return { node, children, width: Math.max(...widths), height: heights.reduce((sum, h) => sum + h, 0) };
    return { node, children, width: widths.reduce((sum, w) => sum + w, 0), height: Math.max(...heights) + 44 };
  }

  function drawNetwork(host, box, x, y, symbols, topColor) {
    const { node, width, height, children } = box, bottom = y + height;
    if (!children) {
      const known = node.id !== state.target, value = known ? node.resistance : result.solved;
      const role = value == null ? color.missing : known ? color.known : color.calculated;
      const bodyWidth = symbols.width, bodyHeight = symbols.height;
      const top = y + (height - bodyHeight) / 2, end = top + bodyHeight, middle = (top + end) / 2;
      const part = svg(host, "g", { "data-part": node.id, role: "button", tabindex: 0,
        "aria-label": `${partName(node.id)}, ${value == null ? "resistance unavailable" : format(value, "Ω")}. Edit resistor`, "aria-pressed": String(node.id === selectedId) });
      svg(part, "rect", { class: "part-hit", x: x - 24, y: middle - 39, width: width - 10, height: 78, rx: 8, "stroke-width": 1 });
      line(part, x, y, x, top - leadLength, topColor);
      line(part, x, top - leadLength, x, top, role).dataset.symbolLead = "top";
      line(part, x, end, x, end + leadLength, role).dataset.symbolLead = "bottom";
      line(part, x, end + leadLength, x, bottom);
      svg(part, "rect", { x: x - bodyWidth / 2, y: top, width: bodyWidth, height: bodyHeight, rx: symbols.radius, fill: "#13202c", stroke: role, "data-resistor-core": "" });
      text(part, x + 24, middle - 3, partName(node.id), 16, role, { "font-weight": 700 });
      text(part, x + 24, middle + 17, format(value, "Ω"), symbols === compactSymbols ? 12 : 14);
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

  function titleLines(title, width) {
    const max = Math.floor((width - 32) / 12), lines = [];
    while (title.length > max) {
      const space = title.lastIndexOf(" ", max), end = space > 0 ? space : max;
      lines.push(title.slice(0, end));
      title = title.slice(end).trimStart();
    }
    return [...lines, title];
  }

  function drawCircuit() {
    const focusId = document.activeElement?.closest("#schematic [data-part]")?.dataset.part;
    const compact = mobile.matches && !desktopView, box = layout(state.network, compact), symbols = compact ? compactSymbols : fullSymbols;
    const naturalWidth = Math.max(compact ? 348 : 432, box.width + (compact ? 200 : 224));
    const width = Math.max(naturalWidth, viewport.clientWidth), offset = (width - naturalWidth) / 2;
    const names = titleLines(state.title || titleDefault, width);
    const y = 102 + 23 * names.length, bottom = y + box.height, tileTop = bottom + leadLength + 2 * symbols.groundPitch + 13, height = tileTop + 134;
    const x = naturalWidth - 95 - box.width / 2 + offset, sourceX = (compact ? 63 : 81) + offset, sourceY = (y + bottom) / 2;
    const sourceVoltage = state.mode === "voltage" ? result.voltage : state.voltage;
    const topColor = state.mode === "voltage" && sourceVoltage != null ? color.calculated : color.net;
    const sourceColor = sourceVoltage == null ? color.missing : state.mode === "voltage" ? color.calculated : color.known;
    schematic.replaceChildren();
    schematic.setAttribute("width", width); schematic.setAttribute("height", height);
    schematic.setAttribute("viewBox", `0 0 ${width} ${height}`);
    viewport.style.setProperty("--drawing-width", `${width}px`);
    svg(schematic, "rect", { x: 1, y: 1, width: width - 2, height: height - 2, rx: 13, fill: "#101823", stroke: "#39586f", "stroke-width": 1.5 });
    svg(schematic, "image", { x: 16, y: 13, width: 112, height: 36, href: embeddedLogo || "../logo.png", "data-circuit-logo": "" });
    const stamp = build ? svg(schematic, "a", { href: `https://github.com/miniPCB/minipcb.github.io/commit/${build.commit}`, target: "_blank", rel: "noopener noreferrer", "data-built-at": build.builtAt, "data-build-commit": build.commit }) : schematic;
    const buildLabel = build ? `${build.builtAt.slice(0, 19).replace("T", " ")} UTC · ${build.commit.slice(0, 7)}` : "Unpublished source";
    text(stamp, 16, 65, buildLabel, 11, color.muted);
    names.forEach((name, index) => text(schematic, 16, 94 + index * 23, name, 20, color.text, { "font-weight": 700 }));

    const drawing = svg(schematic, "g", { "stroke-width": symbols.stroke, "stroke-linecap": "round" });
    line(drawing, sourceX, y, x, y, topColor); line(drawing, sourceX, bottom, x, bottom);
    const sourceTop = sourceY - symbols.source, sourceBottom = sourceY + symbols.source;
    line(drawing, sourceX, y, sourceX, sourceTop - leadLength, topColor);
    line(drawing, sourceX, sourceTop - leadLength, sourceX, sourceTop, sourceColor);
    line(drawing, sourceX, sourceBottom, sourceX, sourceBottom + leadLength, sourceColor);
    line(drawing, sourceX, sourceBottom + leadLength, sourceX, bottom);
    svg(drawing, "circle", { cx: sourceX, cy: sourceY, r: symbols.source, fill: "#13202c", stroke: sourceColor, "data-voltage-source": "" });
    text(drawing, sourceX, sourceY - 2, "+", compact ? 14 : 18, sourceColor, { "text-anchor": "middle" });
    text(drawing, sourceX, sourceY + (compact ? 11 : 15), "−", compact ? 14 : 18, sourceColor, { "text-anchor": "middle" });
    text(drawing, sourceX + symbols.source + 8, sourceY - 6, "VDC", 13, sourceColor);
    text(drawing, sourceX + symbols.source + 8, sourceY + 14, format(sourceVoltage, "V"), 14);
    const groundX = sourceX, ground = svg(drawing, "g", { "data-ground-symbol": "" });
    junction(drawing, groundX, bottom, symbols.junction);
    line(ground, groundX, bottom, groundX, bottom + leadLength).dataset.symbolLead = "ground";
    symbols.ground.forEach((half, index) => line(ground, groundX - half, bottom + leadLength + symbols.groundPitch * index, groundX + half, bottom + leadLength + symbols.groundPitch * index));
    drawNetwork(drawing, box, x, y, symbols, topColor);

    const values = [["Voltage", "voltage", "V"], ["Current", "current", "A"], ["Resistance", "resistance", "Ω"], ["Power", "power", "W"]];
    const tileWidth = (width - 42) / 2;
    values.forEach(([label, field, unit], index) => {
      const tileX = 16 + index % 2 * (tileWidth + 10), tileY = tileTop + Math.floor(index / 2) * 51;
      svg(schematic, "rect", { x: tileX, y: tileY, width: tileWidth, height: 44, rx: 6, fill: "#152635", stroke: "#304c61" });
      text(schematic, tileX + 9, tileY + 16, label, compact ? 14 : 12, color.muted);
      text(schematic, tileX + 9, tileY + 35, format(result[field], unit), compact ? 19 : 16, field === state.mode ? color.calculated : color.text);
    });
    [["Known", "known", 16], ["Calculated", "calculated", 104], ["Missing", "missing", 230]].forEach(([label, role, keyX]) => {
      dot(schematic, keyX + 4, height - 15, color[role]);
      text(schematic, keyX + 15, height - 11, label, 12, color.muted);
    });
    if (focusId) schematic.querySelector(`[data-part="${focusId}"]`)?.focus({ preventScroll: true });
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
    const { voltage, current, resistance, power, range, readings } = result;
    const rows = [
      ["Supply voltage", format(voltage, "V"), "voltage"], ["Circuit current", format(current, "A"), "current"],
      ["Equivalent resistance", format(resistance, "Ω"), "resistance"], ["Total power", format(power, "W"), "power"],
      ["Equivalent resistance range", rangeText(range, "Ω"), "resistanceRange"]
    ];
    if (state.mode === "voltage") rows.push(["Voltage range at fixed current", rangeText(range?.map(value => current * value), "V"), "voltageRange"]);
    else rows.push(["Current range at fixed voltage", rangeText(range?.map(value => voltage / value), "A"), "currentRange"]);
    addRows(byId("characteristicsTable"), rows);
    copyRows = [["Characteristic", "Value"], ...rows.map(([label, value]) => [label, value])];

    const reports = byId("partCharacteristics"), existing = new Map([...reports.children].map(item => [Number(item.dataset.reportId), item]));
    for (const part of parts(state.network)) {
      const name = partName(part.id), reading = readings?.get(part.id);
      const details = existing.get(part.id) || document.createElement("details");
      existing.delete(part.id);
      if (!details.hasChildNodes()) {
        details.dataset.reportId = part.id;
        const summary = document.createElement("summary"), table = document.createElement("table");
        summary.textContent = name; table.setAttribute("aria-label", `${name} measurements`);
        details.append(summary, table); reports.append(details);
      }
      const data = [["Resistance", format(part.id === state.target ? result.solved : part.resistance, "Ω")],
        ["Voltage drop", format(reading?.voltage, "V")], ["Current", format(reading?.current, "A")],
        ["Power", format(reading?.power, "W")], ["Tolerance", part.tolerance === null ? "—" : `±${part.tolerance}%`], ["Package", part.package]];
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
    if (snapshot.title) fields.push(field("title", "Circuit title", snapshot.title));
    if (snapshot.mode !== "voltage") fields.push(field("voltage", "Supply voltage", format(snapshot.voltage, "V")));
    if (snapshot.mode !== "current") fields.push(field("current", "Circuit current", format(snapshot.current, "A")));
    if (snapshot.target) fields.push(field("target", "Calculated resistor", partName(snapshot.target)));
    return { fields, parts: parts(snapshot.network).map(part => {
      const resistance = part.id === snapshot.target ? "Calculated" : format(part.resistance, "Ω"), tolerance = `±${part.tolerance}%`;
      return { name: partName(part.id), summary: `${resistance}, ${tolerance}, ${part.package}`, values: {
        resistance: { label: "resistance", value: resistance }, tolerance: { label: "tolerance", value: tolerance }, package: { label: "package", value: part.package }
      } };
    }) };
  }

  function validSnapshot(snapshot) {
    const ids = new Set();
    function validNode(node) {
      if (!node || typeof node !== "object") return false;
      if (node.children) return ["series", "parallel"].includes(node.kind) && Array.isArray(node.children) && node.children.length >= 2 && node.children.every(validNode);
      if (!Number.isSafeInteger(node.id) || node.id < 1 || ids.has(node.id) || !packages.includes(node.package)) return false;
      if (!(node.resistance === null || (Number.isFinite(node.resistance) && node.resistance > 0)) || !Number.isFinite(node.tolerance) || node.tolerance < 0 || node.tolerance >= 100) return false;
      ids.add(node.id);
      return true;
    }
    return snapshot?.version === 1 && Object.hasOwn(modes, snapshot.mode) && typeof snapshot.title === "string" && snapshot.title.length <= 72
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
  const toleranceInput = byId("tolerance"), titleInput = byId("circuitTitle");
  trackDraft(toleranceInput, commit => {
    const part = selectedPart(), value = toleranceInput.valueAsNumber;
    const tolerance = value >= 0 && value < 100 ? value : null, changed = tolerance !== part.tolerance;
    part.tolerance = tolerance;
    toleranceInput.setAttribute("aria-invalid", String(tolerance === null));
    finishEdit(toleranceInput, commit, changed);
  });
  trackDraft(titleInput, commit => {
    const title = titleInput.value.trim(), changed = title !== state.title;
    state.title = title;
    finishEdit(titleInput, commit, changed);
  });
  for (const button of document.querySelectorAll("[data-add]")) button.addEventListener("click", () => {
    const part = newPart(nextId++);
    state.network = insert(state.network, selectedId, button.dataset.add, part);
    selectPart(part.id);
  });
  byId("removePart").addEventListener("click", () => {
    const allParts = parts(state.network), index = allParts.findIndex(part => part.id === selectedId);
    if (allParts.length < 2) return;
    state.network = remove(state.network, selectedId);
    const next = allParts[index + 1] || allParts[index - 1];
    if (state.target === selectedId) state.target = next.id;
    selectPart(next.id);
    if (byId("removePart").disabled) byId("partSelect").focus();
  });
  function editSchematicPart(event) {
    const part = event.target.closest("[data-part]");
    if (!part) return;
    event.preventDefault();
    selectPart(Number(part.dataset.part));
    byId(selectedId === state.target ? "partSelect" : "resistance").focus();
  }
  schematic.addEventListener("click", editSchematicPart);
  schematic.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) editSchematicPart(event); });

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
    if (event.key === "Escape" && !characteristics.inert && (!memoryPanel.open || inCharacteristics) && !event.defaultPrevented && byId("memoryMenu").hidden) {
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
  memory = DividerMemory.create({
    storageKey: "minipcb-ohms-law-memory-v1", defaultTitle: titleDefault, circuitTitle: snapshot => snapshot.title, describe,
    capture: () => result.error || draft.size ? null : { title: state.title || titleDefault, summary: `${format(result.voltage, "V")} · ${format(result.current, "A")} · ${format(result.resistance, "Ω")}`, state },
    restore(snapshot) {
      if (!validSnapshot(snapshot)) throw new Error("The saved circuit is invalid.");
      state = snapshot; draft.clear();
      const allParts = parts(state.network);
      selectedId = state.target ?? allParts[0].id;
      nextId = Math.max(nextId, ...allParts.map(part => part.id + 1));
      syncControls(); refresh();
    },
    canCollapse: () => !document.activeElement?.closest("#characteristicsDrawer, #characteristicsToggle")
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

  byId("downloadCircuit").addEventListener("click", async event => {
    const button = event.currentTarget, status = byId("exportStatus");
    button.disabled = true; status.hidden = true;
    try {
      await Promise.all([logoReady, buildReady]);
      if (!embeddedLogo) throw new Error("The miniPCB logo could not be embedded. Reload the calculator and try again.");
      const snapshot = schematic.cloneNode(true);
      snapshot.removeAttribute("id"); snapshot.setAttribute("role", "img"); snapshot.setAttribute("aria-label", state.title || titleDefault);
      for (const part of snapshot.querySelectorAll("[data-part]")) {
        part.querySelector(".part-hit").remove();
        for (const attr of ["data-part", "role", "tabindex", "aria-pressed", "aria-label"]) part.removeAttribute(attr);
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
