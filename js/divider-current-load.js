/* Independent, signed VMID current load. Positive current flows toward ground. */
(function (root) {
  "use strict";
  const parallel = (a, b) => Math.min(a, b) / (1 + Math.min(a, b) / Math.max(a, b));
  const ends = (a, b) => a === b ? [a] : [a, b];
  const enabled = circuit => circuit.loadType === "current" || !!circuit.iload || !!circuit.iloadTolerance;

  function analyze(vin, r1, r2, rl, iload = 0) {
    const bottom = rl === null ? r2 : parallel(r2, rl), ratio = 1 / (1 + r1 / bottom), resistance = parallel(r1, bottom);
    const vout = vin * ratio - iload * resistance, v1 = vin / (1 + bottom / r1) + iload * resistance;
    const i1 = v1 / r1, i2 = vout / r2, il = (rl === null ? 0 : vout / rl) + iload;
    const p1 = v1 * i1, p2 = vout * i2, pl = vout * il;
    return { ratio, vout, v1, i1, i2, il, p1, p2, pl, total: p1 + p2 + pl, rth: parallel(r1, r2), unloaded: vin / (1 + r1 / r2), bottom };
  }

  function inverse(mode, circuit, target) {
    const result = { ...circuit }, current = circuit.iload || 0, bottom = circuit.rl === null ? circuit.r2 : parallel(circuit.r2, circuit.rl);
    if (mode === "vin") result.vin = target * (1 + circuit.r1 / bottom) + current * circuit.r1;
    else if (mode === "r1") result.r1 = (circuit.vin - target) / (target / bottom + current);
    else if (mode === "r2") result.r2 = target / ((circuit.vin - target) / circuit.r1 - current - (circuit.rl === null ? 0 : target / circuit.rl));
    else if (mode === "rl") { result.rl = null; result.iload = (circuit.vin - target) / circuit.r1 - target / circuit.r2; }
    return result;
  }

  function ranges(circuit, tolerances, overrides = {}) {
    const interval = (value, pct) => [value - Math.abs(value) * (pct || 0) / 100, value + Math.abs(value) * (pct || 0) / 100];
    const [vinMin, vinMax] = interval(circuit.vin, tolerances.vin), [r1Min, r1Max] = overrides.r1 || interval(circuit.r1, tolerances.r1), [r2Min, r2Max] = overrides.r2 || interval(circuit.r2, tolerances.r2);
    const [rlMin, rlMax] = circuit.rl === null ? [null, null] : overrides.rl || interval(circuit.rl, tolerances.rl);
    const iloadMin = (circuit.iload || 0) - (circuit.iloadTolerance || 0), iloadMax = (circuit.iload || 0) + (circuit.iloadTolerance || 0);
    return { vinMin, vinMax, r1Min, r1Max, r2Min, r2Max, rlMin, rlMax, iloadMin, iloadMax };
  }

  function samples(bounds) {
    const values = [];
    for (const vin of ends(bounds.vinMin, bounds.vinMax)) for (const current of ends(bounds.iloadMin, bounds.iloadMax))
      for (const r1 of ends(bounds.r1Min, bounds.r1Max)) for (const r2 of ends(bounds.r2Min, bounds.r2Max)) for (const rl of ends(bounds.rlMin, bounds.rlMax))
        values.push({ vin, current, r1, r2, rl, result: analyze(vin, r1, r2, rl, current) });
    return values;
  }

  function bounds(circuit, tolerances, overrides) {
    const limits = ranges(circuit, tolerances, overrides), outputs = samples(limits).map(sample => sample.result.vout);
    // At fixed other inputs, VMID is linear-fractional in each positive resistance
    // and affine in VTOP/current. Its interval extrema therefore occur at corners.
    const min = Math.min(...outputs), max = Math.max(...outputs), nominal = analyze(circuit.vin, circuit.r1, circuit.r2, circuit.rl, circuit.iload).vout;
    return { ...limits, min, max, deviation: nominal === 0 ? null : 100 * Math.max(Math.abs(min - nominal), Math.abs(max - nominal)) / Math.abs(nominal) };
  }

  function sourceTolerance(circuit, limits, errorPct) {
    const target = analyze(circuit.vin, circuit.r1, circuit.r2, circuit.rl, circuit.iload).vout, spread = Math.abs(target) * errorPct / 100;
    let lower = -Infinity, upper = Infinity;
    for (const sample of samples({ ...limits, vinMin: 0, vinMax: 0 })) {
      const gain = sample.result.ratio, offset = sample.result.vout;
      lower = Math.max(lower, (target - spread - offset) / gain); upper = Math.min(upper, (target + spread - offset) / gain);
    }
    if (circuit.vin === 0) return { feasible: lower <= 0 && upper >= 0, maxPct: null };
    const limit = Math.min(99.999, 100 * Math.min(circuit.vin - lower, upper - circuit.vin) / Math.abs(circuit.vin));
    if (!Number.isFinite(limit)) throw new Error("The calculated VTOP tolerance exceeds the numeric range.");
    return { feasible: limit >= -1e-10, maxPct: limit < -1e-10 ? null : Math.floor(Math.max(0, limit) * 1e6) / 1e6 };
  }

  function envelope(limits) {
    const corners = samples(limits), max = field => Math.max(...corners.map(sample => Math.abs(sample.result[field])));
    let power = max("total");
    // Injected current can return power to VTOP. Its largest magnitude may be
    // at the quadratic minimum inside the source-voltage interval.
    for (const sample of samples({ ...limits, vinMin: 0, vinMax: 0 })) {
      const vin = Math.max(limits.vinMin, Math.min(limits.vinMax, -sample.current * sample.result.bottom / 2));
      power = Math.max(power, Math.abs(analyze(vin, sample.r1, sample.r2, sample.rl, sample.current).total));
    }
    return { top: { voltage: max("v1"), current: max("i1") }, bot: { voltage: max("vout"), current: max("i2") }, power, current: max("i1") };
  }

  function stress(limits) {
    const result = envelope(limits), clamp = (value, min, max) => Math.max(min, Math.min(max, value));
    let topPower = 0, botPower = 0;
    // A resistor's power may peak inside its interval at its Thevenin resistance.
    // For all other independent variables, the largest magnitude lies at an end.
    for (const vin of ends(limits.vinMin, limits.vinMax)) for (const current of ends(limits.iloadMin, limits.iloadMax)) for (const rl of ends(limits.rlMin, limits.rlMax)) {
      for (const r2 of ends(limits.r2Min, limits.r2Max)) {
        const bottom = rl === null ? r2 : parallel(r2, rl), r1 = clamp(bottom, limits.r1Min, limits.r1Max);
        topPower = Math.max(topPower, analyze(vin, r1, r2, rl, current).p1);
      }
      for (const r1 of ends(limits.r1Min, limits.r1Max)) {
        const resistance = rl === null ? r1 : parallel(r1, rl), r2 = clamp(resistance, limits.r2Min, limits.r2Max);
        botPower = Math.max(botPower, analyze(vin, r1, r2, rl, current).p2);
      }
    }
    result.top.power = topPower; result.bot.power = botPower; return result;
  }

  root.DividerCurrentLoad = Object.freeze({ enabled, analyze, inverse, ranges, samples, bounds, sourceTolerance, envelope, stress });
})(globalThis);
