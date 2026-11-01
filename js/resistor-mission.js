/* Editable mission planning templates; no orbit-to-resistor qualification is inferred. */
(function (root) {
  "use strict";
  const sources = Object.freeze({
    radiation: "https://ntrs.nasa.gov/api/citations/20250006822/downloads/TM-20250006822.pdf#page=15",
    thermal: "https://www.esa.int/esapub/bulletin/bullet87/paroli87.htm",
    assurance: "https://nepp.nasa.gov/pages/Radiation.cfm"
  });
  // NASA/TM-20250006822, pp. 11–12: solar maximum, 95% confidence,
  // silicon dose within aluminum spheres, 2.54 mm shielding. Checked 31-Oct-2026.
  const profiles = Object.freeze([
    { id: "leo", name: "LEO · 550 km / 6°", short: "LEO", orbit: "Circular; 550 km altitude; 6° inclination", years: 1, annualKrad: 2.47, shieldMm: 2.54 },
    { id: "sso", name: "Polar LEO / SSO-like · 800 km / 98°", short: "Polar LEO", orbit: "Circular; 800 km altitude; 98° inclination; use a custom model for a different Sun-synchronous geometry", years: 5, annualKrad: 5.57, shieldMm: 2.54 },
    { id: "meo", name: "MEO · eccentric belt-crossing case", short: "MEO eccentric", orbit: "300 km perigee; 30,000 km apogee; 20° inclination; not a circular GNSS orbit", years: 5, annualKrad: 1195, shieldMm: 2.54 },
    { id: "geo", name: "GEO · 35,793 km / 0°", short: "GEO", orbit: "Circular; 35,793 km altitude; 0° inclination", years: 15, annualKrad: 259, shieldMm: 2.54 },
    { id: "custom", name: "Custom orbit / circular GNSS", short: "Custom orbit", orbit: "Custom orbit", years: 1, annualKrad: null, shieldMm: null }
  ].map(Object.freeze));
  function profile(id) {
    const result = profiles.find(item => item.id === id);
    if (!result) throw new Error("Choose a supported mission profile.");
    return result;
  }
  function defaults(id = "leo") {
    const selected = profile(id);
    return { years: selected.years, dutyPct: 100, ambientMinC: -20, ambientMaxC: 70, selfHeatingC: 10, shieldMm: selected.shieldMm, doseModel: selected.annualKrad === null ? "custom" : "reference", annualKrad: selected.annualKrad, doseMargin: 2, orbit: selected.orbit, modelNotes: "" };
  }
  function validate(id, inputs) {
    const selected = profile(id);
    const finite = (key, min, max, optional = false) => {
      if (optional && inputs[key] === null) return;
      if (!Number.isFinite(inputs[key]) || inputs[key] < min || inputs[key] > max) throw new Error(`Mission ${key} is outside its allowed range.`);
    };
    finite("years", 0, 100); finite("dutyPct", 0, 100);
    finite("ambientMinC", -273.15, 1000); finite("ambientMaxC", -273.15, 1000); finite("selfHeatingC", 0, 1000);
    finite("shieldMm", 0, 1000, true); finite("annualKrad", 0, 1e9, true); finite("doseMargin", 1, 100);
    if (inputs.ambientMinC > inputs.ambientMaxC) throw new Error("Enter an ordered mission equipment temperature range.");
    if (!["reference", "custom"].includes(inputs.doseModel)) throw new Error("Choose a radiation dose model.");
    if (inputs.doseModel === "reference" && (selected.annualKrad === null || inputs.shieldMm !== selected.shieldMm || inputs.orbit !== selected.orbit)) throw new Error("The reference dose requires the published orbit and 2.54 mm aluminum shielding. Use a custom annual dose for other conditions.");
    if (typeof inputs.orbit !== "string" || !inputs.orbit.trim() || inputs.orbit.length > 240) throw new Error("Describe the mission orbit in 1 to 240 characters.");
    if (typeof inputs.modelNotes !== "string" || inputs.modelNotes.length > 600) throw new Error("Keep custom radiation analysis notes within 600 characters.");
    return inputs;
  }
  function snapshot(settings) {
    return JSON.stringify([settings.thermal, settings.radiation, settings.aging]);
  }
  function create(id, parameters = {}, base = root.ResistorEnvironment.defaults()) {
    const selected = profile(id), inputs = { ...defaults(id), ...parameters };
    validate(id, inputs);
    const rate = inputs.doseModel === "reference" ? selected.annualKrad : inputs.annualKrad;
    const next = JSON.parse(JSON.stringify(base));
    next.thermal = { ...next.thermal, enabled: true, minC: inputs.ambientMinC, maxC: inputs.ambientMaxC + inputs.selfHeatingC };
    next.radiation = { enabled: true, doseKrad: inputs.years === 0 ? 0 : rate === null ? null : rate * inputs.years * inputs.doseMargin, qualifiedKrad: null, tnpwPct: null, milPct: null, manualPct: null };
    next.aging = { enabled: true, hours: inputs.years * 8760 * inputs.dutyPct / 100, model: "datasheet", tnpwPct: null, milPct: null, manualPct: null, milReferenceFilmC: null };
    root.ResistorEnvironment.validate(next);
    next.mission = { profileId: inputs.orbit === selected.orbit ? id : "custom", templateId: id, parameters: inputs, baseline: snapshot(next) };
    return next;
  }
  function edited(settings) {
    return !!settings.mission && snapshot(settings) !== settings.mission.baseline;
  }
  function summary(settings) {
    const mission = settings?.mission;
    if (!mission) return "Custom environmental inputs";
    const selected = profile(mission.profileId), inputs = mission.parameters;
    return `${selected.short} · ${inputs.years} yr · ${inputs.dutyPct}% duty${edited(settings) ? " · inputs edited" : " · planning defaults"}`;
  }
  root.ResistorMission = Object.freeze({ sources, profiles, defaults, validate, create, edited, summary });
})(globalThis);
