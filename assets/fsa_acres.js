// FSA reported acres → planted / harvested / production vs USDA (data/fsa/cotton.json, data/fsa/grains.json from models/fsa_*.py).
// FsaAcres.card(crop) resolves to the card HTML; callers insert it inside their own try/catch so a failure here leaves the tab intact.
const FsaAcres = (() => {
  const m = (v, d = 2) => v == null ? '–' : fmt(v / 1e6, d);
  const pct = (v, d = 1) => v == null ? '–' : fmt(v * 100, d) + '%';
  const vs = (a, b) => a == null || !b ? '' : ` <span class="note">(${sgn((a / b - 1) * 100, 1, '%')} vs USDA)</span>`;
  const err = v => v == null ? '–' : sgn(v, 1, '%');
  const NAMES = { cotton: 'Cotton (upland)', corn: 'Corn', soybeans: 'Soybeans', wheat: 'Wheat' };

  function backtest(B, unitProd) {
    if (!B || !(B.seasons || []).length) return '<p class="note">Backtest: not enough past FSA releases stored yet.</p>';
    const S = B.summary || {};
    const sum = ['planted', 'harvested', 'prod'].filter(k => S[k]).map(k => `<tr><td class="l">${k === 'prod' ? 'Production' : k[0].toUpperCase() + k.slice(1)}</td>
      <td class="n">${fmt(S[k].fsa_mae_pct, 1)}%</td><td class="n">${fmt(S[k].usda_mae_pct, 1)}%</td><td class="n">${S[k].fsa_closer}/${S[k].n}</td>
      <td class="n">${sgn(S[k].fsa_bias_pct, 1, '%')}</td><td class="n">${sgn(S[k].usda_bias_pct, 1, '%')}</td></tr>`).join('');
    const yrs = B.seasons.map(r => `<tr><td class="l">${r.year}</td><td class="l">${r.release}</td>
      <td class="n">${err(r.fsa_planted_err_pct)}</td><td class="n">${err(r.usda_planted_err_pct)}</td>
      <td class="n">${err(r.fsa_harvested_err_pct)}</td><td class="n">${err(r.usda_harvested_err_pct)}</td>
      <td class="n">${err(r.fsa_prod_err_pct)}</td><td class="n">${err(r.usda_prod_err_pct)}</td></tr>`).join('');
    return `<h3 style="margin-top:10px">Backtest: FSA release at the same point of the season vs USDA's final</h3>
      <div class="tbl"><table><tr><th class="l"></th><th class="n">FSA-based miss</th><th class="n">USDA same-month miss</th><th class="n">FSA closer</th><th class="n">FSA bias</th><th class="n">USDA bias</th></tr>${sum}</table></div>
      <details><summary class="note">By season (miss vs final, %)</summary><div class="tbl"><table>
      <tr><th class="l">Season</th><th class="l">FSA release</th><th class="n">Planted FSA</th><th class="n">USDA</th><th class="n">Harvested FSA</th><th class="n">USDA</th><th class="n">Production FSA</th><th class="n">USDA</th></tr>${yrs}</table></div></details>
      <p class="note">Mean absolute miss vs USDA's final; each season uses only the FSA releases out by then and relations fitted on earlier seasons. USDA same-month = USDA's estimate published in the month of that FSA release. Production = FSA-based harvested × USDA's same-month yield (${unitProd}).</p>`;
  }

  function cottonCard(C) {
    const U = C.us, T = C.texas || {}, X = T.conditional || {};
    const st = (C.states || []).slice(0, 8).map(r => `<tr><td class="l">${r.name}</td><td class="n">${m(r.fsa_total)}</td><td class="n">${pct(r.fail_share)}</td>
      <td class="n">${m(r.planted)}</td><td class="n">${m(r.usda_planted)}</td><td class="n">${pct(r.abandonment, 0)}</td><td class="n">${m(r.harvested)}</td><td class="n">${m(r.usda_harvested)}</td>
      <td class="n">${m(r.prod)}</td><td class="n">${m(r.usda_prod)}</td></tr>`).join('');
    const tx = X.texas ? `<p><b>Texas (as on the crop progress page):</b> FSA failed acres ${pct(T.fsa_note?.fail_share)} of planted (${T.fsa_note?.release} release).
      Final abandonment ${pct(X.tx_abandonment.central, 1)} (95% ${pct(X.tx_abandonment.lo95, 0)}–${pct(X.tx_abandonment.hi95, 0)}) from drought + ratings (${pct(T.abandonment_drought_ratings?.central, 1)}) and ratings + FSA failed share, averaged;
      harvested ${fmt(X.tx_harvested_acres.central, 2)}m of ${fmt(X.tx_planted_acres, 2)}m planted acres × USDA's in-season yield ${X.tx_yield.central} lb → <b>${fmt(X.texas.central, 2)}m bales</b> (95% ${fmt(X.texas.lo95, 2)}–${fmt(X.texas.hi95, 2)}).</p>` : '';
    return `<div class="card" style="margin-bottom:8px"><h2>FSA reported acres vs USDA: ${NAMES.cotton} <span class="note">FSA release ${C.fsa_release} · USDA = NASS estimate of the same month</span></h2>
      <div class="tbl"><table><tr><th class="l">US upland</th><th class="n">FSA-based</th><th class="n">USDA</th></tr>
        <tr><td class="l">FSA reported (planted + failed), m acres</td><td class="n">${m(U.fsa_total)}</td><td class="n"></td></tr>
        <tr><td class="l">FSA failed acres, m</td><td class="n">${m(U.fsa_failed)}</td><td class="n"></td></tr>
        <tr><td class="l">Planted, m acres</td><td class="n"><b>${m(U.planted)}</b>${vs(U.planted, U.usda_planted)}</td><td class="n">${m(U.usda_planted)}</td></tr>
        <tr><td class="l">Harvested, m acres</td><td class="n"><b>${m(U.harvested)}</b>${vs(U.harvested, U.usda_harvested)}</td><td class="n">${m(U.usda_harvested)}</td></tr>
        <tr><td class="l">Abandonment</td><td class="n">${pct(U.abandonment)}</td><td class="n">${U.usda_planted ? pct(1 - U.usda_harvested / U.usda_planted) : '–'}</td></tr>
        <tr><td class="l">Production, m 480-lb bales</td><td class="n"><b>${m(U.prod)}</b>${vs(U.prod, U.usda_prod)}</td><td class="n">${m(U.usda_prod)}</td></tr></table></div>
      ${tx}
      <h3 style="margin-top:10px">Top states</h3><div class="tbl"><table><tr><th class="l">State</th><th class="n">FSA acres (m)</th><th class="n">Failed</th><th class="n">Planted</th><th class="n">USDA</th><th class="n">Abandon.</th><th class="n">Harvested</th><th class="n">USDA</th><th class="n">Prod. (m bales)</th><th class="n">USDA</th></tr>${st}</table></div>
      ${backtest(C.backtest, 'state yields, 480-lb bales')}
      <p class="note">Variables: USDA FSA planted and failed acres by state; NASS planted and harvested acres; NASS crop condition (poor + very poor); US Drought Monitor D2–D4 on cotton area; USDA in-season state yields. Built ${C.built}; inputs through ${Object.entries(C.inputs_through || {}).filter(([k]) => k !== 'usda_month').map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · ')}.</p></div>`;
  }

  function grainCard(G, crop) {
    const U = G.us, A = G.usda || {};
    const st = (G.states || []).slice(0, 8).map(r => `<tr><td class="l">${r.name}</td><td class="n">${m(r.fsa_total)}</td><td class="n">${pct(r.fail_share)}</td>
      <td class="n">${m(r.planted)}</td><td class="n">${pct(r.abandonment, 1)}</td><td class="n">${m(r.harvested)}</td><td class="n">${m(r.nass_planted_prev)}</td></tr>`).join('');
    return `<div class="card" style="margin-top:12px"><h2>FSA reported acres vs USDA: ${NAMES[crop]} <span class="note">FSA release ${G.fsa_release} · USDA ${A.report || '–'}</span></h2>
      <div class="tbl"><table><tr><th class="l">US</th><th class="n">FSA-based</th><th class="n">USDA</th></tr>
        <tr><td class="l">FSA reported (planted + failed), m acres</td><td class="n">${fmt(U.fsa_total_m, 2)}</td><td class="n"></td></tr>
        <tr><td class="l">FSA failed acres, m</td><td class="n">${fmt(U.fsa_failed_m, 2)}</td><td class="n"></td></tr>
        <tr><td class="l">Planted, m acres</td><td class="n"><b>${fmt(U.planted_m, 2)}</b>${vs(U.planted_m, A.planted)}</td><td class="n">${fmt(A.planted, 1)}</td></tr>
        <tr><td class="l">Harvested, m acres</td><td class="n"><b>${fmt(U.harvested_m, 2)}</b>${vs(U.harvested_m, A.harvested)}</td><td class="n">${fmt(A.harvested, 1)}</td></tr>
        <tr><td class="l">Harvested / planted</td><td class="n">${pct(1 - U.abandonment)}</td><td class="n">${A.planted ? pct(A.harvested / A.planted) : '–'}</td></tr>
        <tr><td class="l">Yield (USDA, bu/acre)</td><td class="n">${fmt(U.yield, 1)}</td><td class="n">${fmt(A.yield, 1)}</td></tr>
        <tr><td class="l">Production, m bu</td><td class="n"><b>${fmt(U.prod, 0)}</b>${vs(U.prod, A.prod)}</td><td class="n">${fmt(A.prod, 0)}</td></tr></table></div>
      <h3 style="margin-top:10px">Top states</h3><div class="tbl"><table><tr><th class="l">State</th><th class="n">FSA acres (m)</th><th class="n">Failed</th><th class="n">Planted</th><th class="n">Abandon.</th><th class="n">Harvested</th><th class="n">NASS planted last yr</th></tr>${st}</table></div>
      ${backtest(G.backtest, 'US yield, m bu')}
      <p class="note">Variables: USDA FSA planted and failed acres by state (${NAMES[crop]}${crop === 'corn' ? '; sweet corn and popcorn excluded' : crop === 'wheat' ? '; grain, grain/graze and seed uses' : ''}); NASS planted and harvested acres; NASS crop condition (poor + very poor); USDA WASDE planted, harvested, yield and production. No drought input for grains.${crop === 'corn' ? ' Harvested is for grain, so the abandonment column includes acres cut for silage.' : ''} Built ${G.built || ''}.</p></div>`;
  }

  async function card(crop) {
    if (crop === 'cotton') {
      const C = await getJSON('data/fsa/cotton.json');
      if (!C || !C.us) throw new Error('no FSA cotton build');
      return cottonCard(C);
    }
    const D = await getJSON('data/fsa/grains.json');
    const G = D && D.crops && D.crops[crop];
    if (!G) throw new Error('no FSA build for ' + crop);
    if (G.error) return `<div class="card" style="margin-top:12px"><h2>FSA reported acres vs USDA: ${NAMES[crop]}</h2><p class="note">Not ready: ${G.error}. The FSA backfill runs in stages.</p></div>`;
    return grainCard({ ...G, built: D.built }, crop);
  }
  return { card };
})();
