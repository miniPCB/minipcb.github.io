/* Independent bounded resistor drift. Nominal values and ordering tolerances stay unchanged. */
(function (root) {
  "use strict";
  const sources = {
    tnpw: "https://www.vishay.com/docs/28758/tnpw_e3.pdf",
    mil: "https://www.vishay.com/docs/60018/eh.pdf",
    aging: "https://www.vishay.com/docs/28809/driftcalculation.pdf"
  };
  // Vishay 28758 rev. 10-Apr-2026, 60018 rev. 15-Sep-2026; checked 31-Oct-2026.
  const profiles = {
    "vishay-tnpw-e3": {
      key: "tnpw", referenceC: 20, minC: -55, maxC: 125,
      ranges: { "0201": [22, 40000], "0402": [10, 100000], "0603": [1, 332000], "0805": [1, 1000000], "1206": [1, 2000000], "1210": [10, 3010000] },
      filmC: { general: 125, power: 155, advanced: 175 },
      // [test hours, permissible percent change, additional ohms], datasheet p. 12.
      life: { general: [[1000, 0.05, 0.01], [8000, 0.1, 0.02], [225000, 0.3, 0.05]], power: [[1000, 0.1, 0.01], [8000, 0.2, 0.02], [225000, 0.6, 0.05]], advanced: [[1000, 0.2, 0.05]] }
    },
    "vishay-eh-m55342": {
      key: "mil", referenceC: 25, minC: -55, maxC: 125,
      lifeAmbientC: 70,
      filmC: { rated: 150 },
      // Use the MIL-spec limits, not the lower Vishay performance figures (p. 3).
      life: { rated: [[2000, 0.5, 0], [10000, 2, 0]] }
    }
  };
  function defaults() {
    return {
      thermal: { enabled: true, minC: -55, maxC: 125, manualTcrPpm: null, manualReferenceC: 25 },
      radiation: { enabled: true, doseKrad: null, qualifiedKrad: null, tnpwPct: null, milPct: null, manualPct: null },
      aging: { enabled: true, hours: 1000, model: "datasheet", tnpwPct: null, milPct: null, manualPct: null, milReferenceFilmC: null }
    };
  }
  function initialOnly() {
    const value = defaults();
    for (const effect of Object.values(value)) effect.enabled = false;
    return value;
  }
  function estimateDefaults() {
    return {
      basis: "ambient-estimate",
      thermal: { enabled: true, minC: -55, maxC: 70, selfHeatingC: 10, manualTcrPpm: 25, manualReferenceC: 25, tcrPpm: 25 },
      radiation: { enabled: true, allowancePct: 0.1 },
      aging: { enabled: true, model: "allowance", tnpwPct: null, milPct: null, manualPct: 0.1, allowancePct: 0.1 }
    };
  }
  function validate(settings) {
    const finite = (value, name, min = 0, max = Infinity) => {
      if (value !== null && (!Number.isFinite(value) || value < min || value > max)) throw new Error(`${name} is outside its allowed range.`);
    };
    const { thermal, radiation, aging } = settings;
    if (settings.basis === "ambient-estimate") {
      for (const key of ["minC", "maxC", "selfHeatingC", "manualTcrPpm", "manualReferenceC"]) {
        if (!Number.isFinite(thermal[key])) throw new Error("Enter finite ambient temperature and TCR inputs.");
        finite(thermal[key], key, ["minC", "maxC", "manualReferenceC"].includes(key) ? -273.15 : 0);
      }
      if (thermal.minC > thermal.maxC) throw new Error("Minimum ambient temperature must not exceed maximum ambient temperature.");
      for (const key of ["tnpwPct", "milPct", "manualPct"]) finite(aging[key], "Drift allowance", 0, 99.999);
      if (thermal.tcrPpm !== undefined) finite(thermal.tcrPpm, "TCR allowance");
      for (const effect of [radiation, aging]) if (effect.allowancePct !== undefined) finite(effect.allowancePct, "Resistance drift allowance", 0, 99.999);
      if (radiation.enabled && !Number.isFinite(radiation.allowancePct)) throw new Error("Select a finite radiation resistance allowance.");
      if (aging.manualPct === null) throw new Error("Enter a drift allowance for unassigned resistors and RL.");
      return settings;
    }
    finite(thermal.minC, "Minimum film temperature", -273.15);
    finite(thermal.maxC, "Maximum film temperature", -273.15);
    finite(thermal.manualReferenceC, "Manual reference temperature", -273.15);
    finite(thermal.manualTcrPpm, "Manual TCR");
    if (thermal.enabled && thermal.manualTcrPpm !== null && thermal.manualReferenceC === null) throw new Error("Enter a reference temperature for the manual TCR.");
    if (thermal.enabled && (thermal.minC === null || thermal.maxC === null) || thermal.minC !== null && thermal.maxC !== null && thermal.minC > thermal.maxC) throw new Error("Enter an ordered minimum and maximum resistor film temperature.");
    finite(radiation.doseKrad, "Mission radiation dose");
    finite(radiation.qualifiedKrad, "Qualified radiation dose");
    finite(aging.hours, "Operating life", 0, 1e9);
    finite(aging.milReferenceFilmC, "M55342 aging-test film temperature", -273.15);
    if (aging.enabled && aging.hours === null) throw new Error("Enter an operating life in hours.");
    if (!["datasheet", "estimate"].includes(aging.model)) throw new Error("Choose a supported aging model.");
    for (const effect of [radiation, aging]) for (const key of ["tnpwPct", "milPct", "manualPct"]) finite(effect[key], "Resistance drift", 0, 99.999);
    return settings;
  }
  function interval(part, settings = initialOnly()) {
    if (settings.basis === "ambient-estimate") return estimateInterval(part, settings);
    const catalog = part.catalog || part, resistance = part.resistance ?? part.resistanceOhms, initialPct = part.tolerance ?? part.tolerancePct;
    const profile = profiles[catalog.familyId], key = profile?.key || "manual", issues = [], requiredGaps = [];
    const referenceC = profile?.referenceC ?? settings.thermal.manualReferenceC;
    const tcrPpm = profile ? catalog.tcrPpm : settings.thermal.manualTcrPpm;
    let thermalPct = 0, radiationPct = 0, agingPct = 0, agingRelativePct = 0, agingOhms = 0, estimated = false;
    const missing = (name, required = false) => { issues.push(name); if (required) requiredGaps.push(name); };
    const mission = settings.mission?.parameters;
    if (profile && mission && (!Number.isFinite(catalog.temperatureC) || mission.ambientMaxC > Math.max(70, catalog.temperatureC))) missing("Catalog rating ambient is below the mission maximum", true);
    if (settings.thermal.enabled) {
      if (!Number.isFinite(tcrPpm)) { thermalPct = null; missing("Manual resistor/RL TCR not set"); }
      else {
        thermalPct = tcrPpm * Math.max(Math.abs(settings.thermal.minC - referenceC), Math.abs(settings.thermal.maxC - referenceC)) / 10000;
        if (profile && (settings.thermal.minC < profile.minC || settings.thermal.maxC > profile.maxC)) missing("Film range outside the catalog TCR qualification", true);
      }
    }
    if (settings.radiation.enabled) {
      const { doseKrad, qualifiedKrad } = settings.radiation;
      if (doseKrad === null) { radiationPct = null; missing("Radiation dose not set", !!settings.mission); }
      else if (doseKrad > 0) {
        const bound = settings.radiation[`${key}Pct`];
        if (bound === null || qualifiedKrad === null || qualifiedKrad < doseKrad) { radiationPct = null; missing("Radiation drift is not qualified through the mission dose", true); }
        else radiationPct = bound;
      }
    }
    if (settings.aging.enabled && settings.aging.hours > 0) {
      const override = settings.aging[`${key}Pct`];
      if (override !== null) agingPct = agingRelativePct = override;
      else if (!profile) { agingPct = null; missing("Manual resistor/RL aging drift not set"); }
      else {
        const mode = catalog.mode, life = profile.life[mode], range = profile.ranges?.[catalog.case], filmC = profile.filmC[mode];
        const filmMax = settings.thermal.maxC;
        if (!life || range && (resistance < range[0] || resistance > range[1]) || filmMax === null || filmMax > filmC) { agingPct = null; missing("Aging test conditions do not cover this part/film range", true); }
        else if (settings.aging.model === "estimate") {
          const [hours, pct, ohms] = life[0];
          estimated = true;
          // E/H gives a test ambient, not a measured test film temperature.
          // Its operating-temperature limit is not an Arrhenius reference.
          const referenceFilmC = profile.key === "mil" ? settings.aging.milReferenceFilmC : filmC;
          if (referenceFilmC === null) { agingPct = null; missing("M55342 aging-test film temperature not set", true); }
          else {
            const factor = Math.cbrt(settings.aging.hours / hours) * Math.pow(2, (filmMax - referenceFilmC) / 30);
            agingRelativePct = pct * factor; agingOhms = ohms * factor;
            agingPct = agingRelativePct + 100 * agingOhms / resistance;
          }
        } else {
          const point = life.find(([hours]) => hours >= settings.aging.hours);
          // A conservative power-rating temperature need not be the mission ambient.
          const ambientC = mission?.ambientMaxC ?? catalog.temperatureC;
          if (profile.lifeAmbientC !== undefined && (!Number.isFinite(ambientC) || ambientC > profile.lifeAmbientC)) { agingPct = null; missing("M55342 ambient exceeds the published aging-test condition", true); }
          else if (!point) { agingPct = null; missing("Operating life exceeds the published aging envelope", true); }
          else { agingRelativePct = point[1]; agingOhms = point[2]; agingPct = agingRelativePct + 100 * agingOhms / resistance; }
        }
      }
    }
    if (settings.aging.enabled && mission?.years > 0 && mission.dutyPct < 100 && settings.aging[`${key}Pct`] === null) {
      agingPct = null; missing("Unpowered mission aging needs a full-mission drift override", true);
    }
    const terms = [initialPct, thermalPct, radiationPct, agingRelativePct].filter(value => value !== null);
    if (!Number.isFinite(resistance) || resistance <= 0 || terms.some(value => !Number.isFinite(value) || value < 0 || value >= 100)) throw new Error("The resistor drift stack must keep every resistance finite and positive.");
    // Endurance is affine: percentage of the initial resistance PLUS fixed ohms.
    // Do not convert the ohmic term to nominal percent before the lower bound.
    const agedMin = resistance * (1 - initialPct / 100) * (1 - agingRelativePct / 100) - agingOhms;
    const agedMax = resistance * (1 + initialPct / 100) * (1 + agingRelativePct / 100) + agingOhms;
    const drift = [thermalPct, radiationPct].filter(value => value !== null);
    const min = agedMin * drift.reduce((factor, pct) => factor * (1 - pct / 100), 1);
    const max = agedMax * drift.reduce((factor, pct) => factor * (1 + pct / 100), 1);
    if (!Number.isFinite(min) || !Number.isFinite(max) || min <= 0) throw new Error("The environmental resistance interval exceeds the numeric range.");
    return { min, max, initialPct, thermalPct, radiationPct, agingPct, agingRelativePct: agingPct === null ? null : agingRelativePct, agingOhms: agingPct === null ? null : agingOhms, tcrPpm, referenceC, estimated, issues, requiredGaps, qualified: !issues.length && !estimated && !settings.mission, effectivePct: Math.max(resistance - min, max - resistance) / resistance * 100 };
  }
  function estimateInterval(part, settings) {
    const catalog = part.catalog || part, profile = profiles[catalog.familyId];
    const resistance = part.resistance ?? part.resistanceOhms, initialPct = part.tolerance ?? part.tolerancePct;
    const orderedTcr = profile ? catalog.tcrPpm : settings.thermal.manualTcrPpm;
    // A shared allowance may be more conservative than the ordered part, but
    // cannot improve an assigned part's actual TCR rating.
    const selectedTcr = settings.thermal.tcrPpm ?? settings.thermal.manualTcrPpm ?? 25;
    const tcrPpm = profile ? Math.max(orderedTcr, selectedTcr) : selectedTcr, referenceC = profile?.referenceC ?? settings.thermal.manualReferenceC;
    const thermalPct = settings.thermal.enabled ? tcrPpm * Math.max(Math.abs(settings.thermal.minC - referenceC), Math.abs(settings.thermal.maxC + settings.thermal.selfHeatingC - referenceC)) / 10000 : 0;
    const key = profile?.key || "manual", override = settings.aging.allowancePct ?? settings.aging[`${key}Pct`], benchmark = profile?.life[catalog.mode]?.[0];
    const agingRelativePct = !settings.aging.enabled ? 0 : override ?? benchmark?.[1] ?? settings.aging.manualPct;
    const agingOhms = settings.aging.enabled && override === null ? benchmark?.[2] ?? 0 : 0;
    const radiationPct = settings.radiation.enabled ? settings.radiation.allowancePct ?? 0 : 0;
    const issues = [], requiredGaps = [];
    if (catalog.familyId && !profile) requiredGaps.push("No drift estimate profile for this resistor family");
    if (profile && settings.thermal.enabled && (settings.thermal.minC < profile.minC || settings.thermal.maxC + settings.thermal.selfHeatingC > profile.maxC)) requiredGaps.push("Temperature range including self heating is outside the catalog TCR range");
    if (profile && !benchmark && settings.aging.enabled && override === null) requiredGaps.push("No drift benchmark for this catalog operating mode");
    const terms = [initialPct, thermalPct, radiationPct, agingRelativePct];
    if (!Number.isFinite(resistance) || resistance <= 0 || terms.some(value => !Number.isFinite(value) || value < 0 || value >= 100)) throw new Error("The resistor drift stack must keep every resistance finite and positive.");
    const min = (resistance * (1 - initialPct / 100) * (1 - agingRelativePct / 100) - agingOhms) * (1 - thermalPct / 100) * (1 - radiationPct / 100);
    const max = (resistance * (1 + initialPct / 100) * (1 + agingRelativePct / 100) + agingOhms) * (1 + thermalPct / 100) * (1 + radiationPct / 100);
    if (!Number.isFinite(min) || !Number.isFinite(max) || min <= 0) throw new Error("The environmental resistance interval exceeds the numeric range.");
    issues.push(...requiredGaps);
    return { min, max, initialPct, thermalPct, radiationPct, agingPct: agingRelativePct + 100 * agingOhms / resistance, agingRelativePct, agingOhms, tcrPpm, referenceC, estimated: true, issues, requiredGaps, qualified: false, effectivePct: Math.max(resistance - min, max - resistance) / resistance * 100 };
  }
  function allowedPower(catalog, settings) {
    // Manufacturer P70 curves: Pallowed = P70 * clamp((Tzero - Tambient,max)
    // / (Tzero - 70 C), 0, 1), limited further by the selected base allowance.
    // TNPW: https://www.vishay.com/docs/28758/tnpw_e3.pdf (pp. 1-2, 6-7).
    // M55342: https://www.vishay.com/docs/60018/eh.pdf (pp. 2-3).
    // The chosen TNPW operation mode determines P70 and Tzero; it is not a
    // different ordering-code resistor. PCB thermal management must meet the
    // datasheet conditions. The TCR self-heating allowance models resistance
    // drift only; adding it to this ambient-based curve would derate twice.
    // Always start from the original P70/base data; never feed the previous
    // computed powerW back as a new base or cooling cannot restore the allowance.
    const zeroAtC = profiles[catalog.familyId]?.filmC[catalog.mode];
    if (settings.basis !== "ambient-estimate" || !zeroAtC || !Number.isFinite(catalog.ratedPowerW)) return catalog.powerW;
    return Math.min(catalog.powerW, catalog.ratedPowerW * Math.max(0, Math.min(1, (zeroAtC - settings.thermal.maxC) / (zeroAtC - 70))));
  }
  root.ResistorEnvironment = Object.freeze({ defaults, estimateDefaults, initialOnly, validate, interval, allowedPower, profiles, sources });
})(globalThis);
