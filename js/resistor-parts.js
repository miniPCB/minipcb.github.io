/* Shared resistor catalogs. Data and sources live in ../parts/, independent of any UI. */
(function (root) {
  "use strict";
  const baseUrl = new URL("../parts/", document.currentScript.src);
  const pending = new Map();
  const close = (a, b) => Math.abs(a - b) <= 1e-9 * Math.max(Math.abs(a), Math.abs(b));
  const positive = value => typeof value === "number" && Number.isFinite(value) && value > 0;
  const find = (items, code) => items.find(item => item.code === code);
  const need = (condition, message) => { if (!condition) throw new Error(message); };
  const seriesFor = (limit, tolerance) => limit.series || [tolerance.series, ...(tolerance.additionalSeries || [])];

  function validate(index, families) {
    need(index && index.schemaVersion === 1 && typeof index.revision === "string", "Unsupported parts manifest version.");
    need(index.series && Array.isArray(index.families) && index.families.length > 0, "Incomplete parts manifest.");
    for (const [name, values] of Object.entries(index.series)) {
      need(/^E\d+$/.test(name) && Array.isArray(values) && values.length === Number(name.slice(1)), `Invalid preferred series ${name}.`);
      need(values.every((v, i) => Number.isInteger(v) && v >= 100 && v < 1000 && (i === 0 || v > values[i - 1])), `Invalid values in ${name}.`);
    }
    need(families.length === index.families.length && new Set(families.map(f => f.id)).size === families.length, "Duplicate or missing resistor families.");
    for (const family of families) {
      need(family.schemaVersion === 1 && index.families.some(f => f.id === family.id), "Unsupported resistor family version or ID.");
      need(["mil55342", "rkm4"].includes(family.encoding) && family.component === "resistor", "Unsupported resistor encoding.");
      need(family.name && family.manufacturer && family.revision && family.scope, "Missing family identity or scope.");
      need(family.stock?.status === "unknown" && family.stock.checkedAt === null, "Supplier availability must not be inferred from a family catalog.");
      need(Array.isArray(family.sources) && family.sources.length && family.sources.every(s => s.id && s.verifiedOn && /^https:\/\//.test(s.url)), "Family requires dated primary sources.");
      for (const key of ["packages", "tcrCodes", "toleranceCodes", "packaging", "powerModes", "verifiedParts"]) need(Array.isArray(family[key]), `Missing ${key}.`);
      need(family.packages.length && new Set(family.packages.map(p => p.code)).size === family.packages.length, "Duplicate or empty packages.");
      need(family.tcrCodes.every(t => /^[A-Z]$/.test(t.code) && positive(t.ppm)) && family.toleranceCodes.every(t => positive(t.pct)), "Invalid tolerance or TCR.");
      need(family.packaging.every(p => /^[A-Z0-9]{2}$/.test(p.code)), "Invalid packaging encoding.");
      need(new Set(family.tcrCodes.map(t => t.code)).size === family.tcrCodes.length && new Set(family.toleranceCodes.map(t => t.pct)).size === family.toleranceCodes.length && new Set(family.packaging.map(p => p.code)).size === family.packaging.length, "Duplicate TCR, tolerance, or packaging code.");
      need(family.defaults && family.packages.some(p => p.code === family.defaults.package), "Invalid family defaults.");
      need(find(family.tcrCodes, family.defaults.tcrCode) && family.toleranceCodes.some(t => t.pct === family.defaults.tolerancePct), "Unknown default TCR or tolerance.");
      const defaultPackage = find(family.packages, family.defaults.package);
      need(defaultPackage.packagingCodes.includes(family.defaults.packaging) && positive(defaultPackage.powerW[family.defaults.mode]), "Invalid default packaging or power mode.");
      for (const mode of family.powerModes) need(mode.id && [mode.ratedAtC, mode.zeroAtC, mode.minimumAmbientC, mode.maximumAmbientC].every(Number.isFinite) && mode.zeroAtC > mode.ratedAtC && mode.minimumAmbientC < mode.ratedAtC && mode.maximumAmbientC === mode.zeroAtC && mode.condition, "Invalid derating mode.");
      for (const pkg of family.packages) {
        need(pkg.code && pkg.case && pkg.model && positive(pkg.workingVoltageV) && pkg.powerW && pkg.limits.length, "Incomplete package limits.");
        need(family.encoding !== "rkm4" || (/^\d{4}$/.test(pkg.code) && pkg.model === family.prefix + pkg.code), "Package model does not match its family prefix.");
        need(family.encoding !== "mil55342" || (/^\d{2}$/.test(pkg.code) && pkg.model === (pkg.code === "07" ? "D55342" : "M55342")), "Invalid military model/style mapping.");
        for (const [mode, watts] of Object.entries(pkg.powerW)) need(positive(watts) && family.powerModes.some(m => m.id === mode), "Invalid power rating/mode.");
        need(pkg.packagingCodes.length && pkg.packagingCodes.every(c => find(family.packaging, c)), "Unknown packaging code.");
        for (const limit of pkg.limits) {
          need(positive(limit.minOhms) && limit.maxOhms >= limit.minOhms, "Invalid resistance range.");
          need(limit.tcrCodes.length && limit.tcrCodes.every(c => find(family.tcrCodes, c)), "Unknown range TCR.");
          need(limit.tolerancesPct.length && limit.tolerancesPct.every(t => family.toleranceCodes.some(c => c.pct === t)), "Unknown range tolerance.");
          const series = limit.series || family.toleranceCodes.filter(t => limit.tolerancesPct.includes(t.pct)).flatMap(t => seriesFor(limit, t));
          need(series.length && series.every(s => index.series[s]), "Unknown preferred series.");
        }
      }
      if (family.encoding === "mil55342") {
        need(family.terminationCodes?.length && family.failureRates?.length && family.suffixRules, "Missing military numbering fields.");
        need(find(family.failureRates, family.defaults.failureRate), "Unknown default military failure rate.");
        need([...family.terminationCodes, ...family.failureRates].every(c => /^[A-Z]$/.test(c.code)) && /^[A-Z]$/.test(family.suffixRules.thinFilmSuffix) && /^[A-Z]$/.test(family.suffixRules.markingSuffix), "Invalid military ordering code.");
        need(family.toleranceCodes.every(t => /^[A-Z]{3}$/.test(t.letters) && index.series[t.series]), "Invalid military tolerance encoding.");
      } else need(/^[A-Z0-9]+$/.test(family.prefix) && family.toleranceCodes.every(t => /^[A-Z]$/.test(t.code)), "Invalid RKM encoding.");
      for (const part of family.verifiedParts) need(part.mpn && part.kind && family.sources.some(s => s.id === part.sourceId) && Number.isInteger(part.page) && part.page > 0, "Part evidence requires a source and page.");
    }
    return { ...index, families };
  }

  async function load(url = baseUrl) {
    const base = new URL(url, location.href).href;
    if (pending.has(base)) return pending.get(base);
    const request = (async () => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 10000);
      const read = async path => {
        const response = await fetch(new URL(path, base), { signal: controller.signal });
        if (!response.ok) throw new Error(`Parts catalog unavailable (${response.status}).`);
        return response.json();
      };
      try {
        const index = await read("index.json");
        need(index.schemaVersion === 1 && Array.isArray(index.families), "Unsupported parts manifest version.");
        need(index.families.every(f => /^[a-z0-9-]+$/.test(f.id) && /^resistors\/[a-z0-9-]+\.json$/.test(f.file)), "Invalid catalog path.");
        const families = await Promise.all(index.families.map(async entry => {
          const family = await read(entry.file);
          need(family.id === entry.id, "Catalog file ID mismatch.");
          return family;
        }));
        const catalog = validate(index, families);
        // Examples are evidence, never a bypass around electrical/numbering rules.
        for (const family of families) for (const part of family.verifiedParts) decode(catalog, family.id, part.mpn);
        return catalog;
      } finally { clearTimeout(timer); }
    })();
    pending.set(base, request);
    try { return await request; } catch (error) { pending.delete(base); throw error; }
  }

  function family(catalog, id) {
    const result = catalog.families.find(f => f.id === id);
    need(result, "Unknown resistor family.");
    return result;
  }

  function preferred(catalog, resistance, series) {
    const mantissa = resistance / Math.pow(10, Math.floor(Math.log10(resistance))) * 100;
    return series.some(name => catalog.series[name].some(value => close(value, mantissa)));
  }

  function valueCode(resistance, letters) {
    const bucket = resistance >= 1e6 ? 2 : resistance >= 1e3 ? 1 : 0;
    const scaled = resistance / Math.pow(1000, bucket);
    const text = scaled.toPrecision(3);
    const code = text.includes(".") ? text.replace(".", letters[bucket]) : text + letters[bucket];
    need(/^[0-9A-Z]{4}$/.test(code), "Resistance needs more than three significant digits.");
    return code;
  }

  function evaluate(catalog, id, input) {
    const f = family(catalog, id);
    const options = { ...f.defaults, temperatureC: 70, ...input };
    const pkg = find(f.packages, options.package);
    const tcr = find(f.tcrCodes, options.tcrCode);
    const tolerance = f.toleranceCodes.find(t => t.pct === options.tolerancePct);
    const packing = find(f.packaging, options.packaging);
    const mode = f.powerModes.find(m => m.id === options.mode);
    need(pkg && tcr && tolerance, "Unsupported package, tolerance, or TCR.");
    need(mode && positive(pkg.powerW[mode.id]), "This package does not support that power mode.");
    need(Number.isFinite(options.temperatureC) && options.temperatureC >= mode.minimumAmbientC && options.temperatureC < mode.zeroAtC, `Ambient must be ${mode.minimumAmbientC} °C to below ${mode.zeroAtC} °C for this mode.`);
    need(options.legacy || (packing && pkg.packagingCodes.includes(packing.code) && (!packing.tcrCodes || packing.tcrCodes.includes(tcr.code))), "Unsupported packaging/TCR combination.");
    let resistance = options.resistanceOhms;
    need(positive(resistance), "Resistance must be positive and finite.");
    const range = pkg.limits.find(limit => limit.tcrCodes.includes(tcr.code) && limit.tolerancesPct.includes(tolerance.pct) && resistance >= limit.minOhms * (1 - 1e-10) && resistance <= limit.maxOhms * (1 + 1e-10));
    need(range, "Resistance is outside this package/TCR/tolerance range.");
    need(preferred(catalog, resistance, seriesFor(range, tolerance)), "Value is outside the catalog's supported preferred series.");
    resistance = Number(resistance.toPrecision(3));
    let mpn;
    if (f.encoding === "mil55342") {
      need(find(f.failureRates, options.failureRate), "Unsupported failure-rate code.");
      const termination = options.termination || "B";
      need(find(f.terminationCodes, termination), "Unsupported termination.");
      const suffixRules = f.suffixRules;
      const required = suffixRules.requiredThinFilmCodes.includes(tcr.code) && tolerance.pct >= suffixRules.minimumTolerancePct;
      const suffix = options.suffix === undefined ? required && !options.legacy ? suffixRules.thinFilmSuffix : "" : options.suffix;
      need(["", suffixRules.thinFilmSuffix, suffixRules.markingSuffix].includes(suffix), "Unsupported thin-film/marking suffix.");
      need(!required || suffix === suffixRules.thinFilmSuffix || options.legacy, "This Vishay thin-film combination requires the V suffix.");
      need(suffix !== suffixRules.thinFilmSuffix || required, "V suffix is only supported for K/L/M and tolerance ≥ 1%.");
      need(suffix !== suffixRules.markingSuffix || !suffixRules.markingExcludedPackages.includes(pkg.code), "Part marking is unavailable for this case size.");
      mpn = pkg.model + tcr.code + pkg.code + termination + valueCode(resistance, tolerance.letters) + options.failureRate + (options.legacy ? "" : packing.code) + suffix;
    } else mpn = pkg.model + valueCode(resistance, "RKM") + tolerance.code + tcr.code + packing.code;
    const ratedPowerW = pkg.powerW[mode.id];
    const factor = Math.min(1, (mode.zeroAtC - options.temperatureC) / (mode.zeroAtC - mode.ratedAtC));
    const evidence = f.verifiedParts.find(p => p.mpn === mpn);
    const source = f.sources.find(s => s.id === evidence?.sourceId) || f.sources[0];
    return { familyId: f.id, manufacturer: f.manufacturer, familyName: f.name, catalogRevision: f.revision, mpn, package: pkg.code, case: pkg.case, resistanceOhms: resistance, tolerancePct: tolerance.pct, tcrPpm: tcr.ppm, tcrCode: tcr.code, packaging: options.legacy ? "" : packing.code, failureRate: options.failureRate || "", mode: mode.id, temperatureC: options.temperatureC, ratedPowerW, powerW: ratedPowerW * factor, workingVoltageV: pkg.workingVoltageV, condition: mode.condition, status: evidence ? "manufacturer-documented" : "rules-validated", evidence: evidence || null, stockStatus: "unknown", stockCheckedAt: null, sourceUrl: source.url + (evidence ? `#page=${evidence.page}` : ""), sourceRevision: source.revision || null, verifiedOn: source.verifiedOn };
  }

  function decode(catalog, id, number, settings = {}) {
    const f = family(catalog, id);
    const mpn = String(number || "").trim().toUpperCase();
    let options = { ...settings };
    if (f.encoding === "rkm4") {
      const prefix = f.prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const match = mpn.match(new RegExp("^" + prefix + "(\\d{4})([0-9RKM]{4})([A-Z])([A-Z])([A-Z]{2})$"));
      need(match, "Unsupported TNPW part-number format (standard parts only).");
      const [, pkg, code, tol, tcr, packing] = match;
      const letter = code.match(/[RKM]/g);
      need(letter?.length === 1, "Invalid resistance code.");
      options = { ...options, package: pkg, resistanceOhms: Number(code.replace(letter[0], ".")) * Math.pow(1000, "RKM".indexOf(letter[0])), tolerancePct: find(f.toleranceCodes, tol)?.pct, tcrCode: tcr, packaging: packing };
    } else {
      const match = mpn.match(/^(M55342|D55342)([A-Z])(\d{2})([A-Z])([0-9A-Z]{4})([A-Z])(?:([A-Z0-9]{2})([A-Z])?)?$/);
      need(match, "Unsupported M/D55342 part-number format.");
      const modelCode = match[1], tcr = match[2], pkgCode = match[3], termination = match[4], code = match[5], failure = match[6], packing = match[7] || "", suffix = match[8] || "";
      need(find(f.packages, pkgCode)?.model === modelCode, "D55342 is required only for /07; other styles use M55342.");
      const letters = code.match(/[A-Z]/g);
      need(letters?.length === 1 && /^\d/.test(code) && code.replace(letters[0], "").length === 3, "Invalid military resistance code.");
      const tol = f.toleranceCodes.find(t => t.letters.includes(letters[0]));
      need(tol, "Unknown military tolerance letter.");
      options = { ...options, package: pkgCode, tcrCode: tcr, termination, resistanceOhms: Number(code.replace(letters[0], ".")) * Math.pow(1000, tol.letters.indexOf(letters[0])), tolerancePct: tol.pct, failureRate: failure, packaging: packing, suffix, legacy: !packing };
    }
    const result = evaluate(catalog, id, options);
    // Retain the supplied representation for historical, equivalent decimal encodings.
    const evidence = f.verifiedParts.find(p => p.mpn === mpn);
    return { ...result, mpn, status: evidence ? "manufacturer-documented" : "rules-validated", evidence: evidence || null };
  }

  function suggest(catalog, id, request) {
    const f = family(catalog, id);
    const options = { ...f.defaults, ...request };
    const pkg = find(f.packages, options.package);
    need(pkg && positive(request.resistanceOhms), "Select a package and valid target resistance.");
    const tolerances = f.toleranceCodes.filter(t => t.pct <= (request.maxTolerancePct ?? options.tolerancePct)).sort((a, b) => b.pct - a.pct);
    const results = [];
    const seen = new Set();
    for (const tolerance of tolerances) for (const range of pkg.limits.filter(l => l.tcrCodes.includes(options.tcrCode) && l.tolerancesPct.includes(tolerance.pct))) {
      for (const series of seriesFor(range, tolerance)) for (const mantissa of catalog.series[series]) {
        const decade = Math.floor(Math.log10(request.resistanceOhms / (mantissa / 100)));
        for (const exponent of [decade - 1, decade, decade + 1]) {
          const resistanceOhms = Number((mantissa / 100 * Math.pow(10, exponent)).toPrecision(12));
          const rawError = (resistanceOhms / request.resistanceOhms - 1) * 100;
          const errorPct = Math.abs(rawError) < 1e-9 ? 0 : rawError;
          if (Math.abs(errorPct) > (request.maxErrorPct ?? 5) + 1e-9) continue;
          try {
            const part = evaluate(catalog, id, { ...options, resistanceOhms, tolerancePct: tolerance.pct });
            if (!seen.has(part.mpn)) { seen.add(part.mpn); results.push({ ...part, errorPct }); }
          } catch (_) { /* The range/combination is outside this catalog's supported subset. */ }
        }
      }
    }
    return results.sort((a, b) => Math.abs(a.errorPct) - Math.abs(b.errorPct) || b.tolerancePct - a.tolerancePct || a.mpn.localeCompare(b.mpn)).slice(0, request.limit ?? 12);
  }

  root.ResistorParts = Object.freeze({ load, validate, family, evaluate, decode, suggest, preferred });
})(window);
