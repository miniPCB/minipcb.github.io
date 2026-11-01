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
      thermal: { enabled: true, minC: 25, maxC: 125, manualTcrPpm: null, manualReferenceC: 25 },
      radiation: { enabled: true, doseKrad: null, qualifiedKrad: null, tnpwPct: null, milPct: null, manualPct: null },
      aging: { enabled: true, hours: 1000, model: "datasheet", tnpwPct: null, milPct: null, manualPct: null, milReferenceFilmC: null }
    };
  }
  function initialOnly() {
    const value = defaults();
    for (const effect of Object.values(value)) effect.enabled = false;
    return value;
  }
  function validate(settings) {
    const finite = (value, name, min = 0, max = Infinity) => {
      if (value !== null && (!Number.isFinite(value) || value < min || value > max)) throw new Error(`${name} is outside its allowed range.`);
    };
    const { thermal, radiation, aging } = settings;
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
    const catalog = part.catalog || part, resistance = part.resistance ?? part.resistanceOhms, initialPct = part.tolerance ?? part.tolerancePct;
    const profile = profiles[catalog.familyId], key = profile?.key || "manual", issues = [], requiredGaps = [];
    const referenceC = profile?.referenceC ?? settings.thermal.manualReferenceC;
    const tcrPpm = profile ? catalog.tcrPpm : settings.thermal.manualTcrPpm;
    let thermalPct = 0, radiationPct = 0, agingPct = 0, agingRelativePct = 0, agingOhms = 0, estimated = false;
    const missing = (name, required = false) => { issues.push(name); if (required) requiredGaps.push(name); };
    if (settings.thermal.enabled) {
      if (!Number.isFinite(tcrPpm)) { thermalPct = null; missing("Manual resistor/RL TCR not set"); }
      else {
        thermalPct = tcrPpm * Math.max(Math.abs(settings.thermal.minC - referenceC), Math.abs(settings.thermal.maxC - referenceC)) / 10000;
        if (profile && (settings.thermal.minC < profile.minC || settings.thermal.maxC > profile.maxC)) missing("Film range outside the catalog TCR qualification", true);
      }
    }
    if (settings.radiation.enabled) {
      const { doseKrad, qualifiedKrad } = settings.radiation;
      if (doseKrad === null) { radiationPct = null; missing("Radiation dose not set"); }
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
          if (profile.lifeAmbientC !== undefined && (!Number.isFinite(catalog.temperatureC) || catalog.temperatureC > profile.lifeAmbientC)) { agingPct = null; missing("M55342 ambient exceeds the published aging-test condition", true); }
          else if (!point) { agingPct = null; missing("Operating life exceeds the published aging envelope", true); }
          else { agingRelativePct = point[1]; agingOhms = point[2]; agingPct = agingRelativePct + 100 * agingOhms / resistance; }
        }
      }
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
    return { min, max, initialPct, thermalPct, radiationPct, agingPct, agingRelativePct: agingPct === null ? null : agingRelativePct, agingOhms: agingPct === null ? null : agingOhms, tcrPpm, referenceC, estimated, issues, requiredGaps, qualified: !issues.length && !estimated, effectivePct: Math.max(resistance - min, max - resistance) / resistance * 100 };
  }
  root.ResistorEnvironment = Object.freeze({ defaults, initialOnly, validate, interval, profiles, sources });
})(globalThis);
