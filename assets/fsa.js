// FSA reported acres vs USDA: one card per crop (cotton, corn, soybeans, wheat, sorghum) from data/fsa/estimates.json
// (models/fsa_crops.py). Used on Cotton → Crop progress and the grains WASDE tabs. Isolated: failures leave a short note.
const FsaView = (() => {
  let D = null;
  const f = (v, d = 2) => v == null || Number.isNaN(v) ? '–' : fmt(v, d);
  const pc = v => v == null ? '–' : `${v > 0 ? '+' : ''}${fmt(v, 1)}%`;
  async function card(key) {
    D = D || await getJSON('data/fsa/estimates.json').catch(() => null);
    const C = D?.crops?.[key];
    if (!C || !C.estimate) return `<div class="card" style="margin-top:12px"><h2>FSA reported acres</h2><p class="note">${C?.error || 'FSA acreage estimate not built yet.'}</p></div>`;
    const E = C.estimate, U = C.usda, F = C.fsa, B = C.backtest, py = F.prev_year_same_date;
    const pd = (a, b) => a != null && b ? pc(100 * (a / b - 1)) : '–';
    const dp = C.unit.includes('bales') ? 2 : 0;
    return `<div class="card" style="margin-top:12px"><h2>${C.label}: FSA reported acres vs USDA <span class="note">FSA as of ${D.fsa_asof} · ${D.crop_year} crop</span></h2>
      <div class="tbl"><table><tr><th class="l"></th><th>FSA-based</th><th>USDA ${D.fsa_asof.slice(0, 7)}</th><th>Difference</th></tr>
        <tr><td class="l">Planted, m acres</td><td><b>${f(E.planted_m)}</b></td><td>${f(U.planted_m)}</td><td>${pd(E.planted_m, U.planted_m)}</td></tr>
        <tr><td class="l">Abandoned</td><td>${f(E.abandon_pct, 1)}%</td><td>${f(U.abandon_pct, 1)}%</td><td></td></tr>
        <tr><td class="l">Harvested, m acres</td><td><b>${f(E.harvested_m)}</b> <span class="note">${f(E.harv_lo_m)}–${f(E.harv_hi_m)}</span></td><td>${f(U.harvested_m)}</td><td>${pd(E.harvested_m, U.harvested_m)}</td></tr>
        <tr><td class="l">Production, ${C.unit} <span class="note">at USDA's yield ${f(E.yield, C.unit.includes('bales') ? 0 : 1)}</span></td><td><b>${f(E.prod, dp)}</b> <span class="note">${f(E.prod_lo, dp)}–${f(E.prod_hi, dp)}</span></td><td>${f(U.prod, dp)}</td><td>${pd(E.prod, U.prod)}</td></tr></table></div>
      <p>FSA has <b>${f(F.pf_m)} m acres</b> planted or failed so far (${f(100 * F.failed_share, 1)}% failed, ${f(F.prevented_m)} m prevented)${py ? `; a year earlier, at ${py.asof}, it had ${f(py.pf_m)} m (${f(100 * py.failed_share, 1)}% failed)` : ''}.
        Final USDA planted area has run ${f(E.r_plant, 3)}× FSA's count at this point of the season (median of past years).</p>
      <details><summary>Top states</summary><div class="tbl"><table><tr><th class="l">State</th><th>FSA planted + failed, k ac</th><th>Failed</th><th>Year earlier</th></tr>
        ${C.states.map(s => `<tr><td class="l">${s.state}</td><td>${f(s.pf_k, 0)}</td><td>${f(s.failed_pct, 1)}%</td><td>${f(s.prev_pf_k, 0)}</td></tr>`).join('')}</table></div></details>
      <details><summary>Backtest: ${B.years} seasons</summary><p class="note">Each past season re-estimated without itself from the FSA release at the same point of the season, against USDA's final figures. Average miss on harvested area: FSA-based ${f(B.mae_harv_pct, 1)}%, USDA's same-month number ${f(B.usda_mae_harv_pct, 1)}%; on planted area ${f(B.mae_plant_pct, 1)}% vs ${f(B.usda_mae_plant_pct, 1)}%. The range above is the widest miss either way.</p>
        <div class="tbl"><table><tr><th class="l">Crop year</th><th>FSA as of</th><th>FSA-based harvested</th><th>USDA same month</th><th>Final</th><th>Miss</th><th>USDA miss</th></tr>
        ${B.rows.map(r => `<tr><td class="l">${r.year}</td><td>${r.fsa_asof}</td><td>${f(r.est_harvested)}</td><td>${f(r.usda_harvested)}</td><td>${f(r.final_harvested)}</td><td>${pc(r.err_harv_pct)}</td><td>${pc(r.usda_err_harv_pct)}</td></tr>`).join('')}</table></div></details>
      <p class="note">${D.method} Source: <a href="${D.fsa_url}" target="_blank" rel="noopener">FSA crop acreage data ↗</a>, USDA WASDE. Built ${D.built}.</p></div>`;
  }
  async function append(el, key) {
    try { el.insertAdjacentHTML('beforeend', await card(key)); } catch (e) { console.error('fsa', e); }
  }
  return { append, card };
})();
