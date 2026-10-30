// Cotton > India: desk crop projection from area and cotton-district rainfall, monsoon against history, balance sheets
// (COCPC official, CAI trade, USDA) in 480-lb bales, monthly trade, Shankar-6 vs ICE. Data: data/india/india.json (models/india_cotton.py).
const IndiaCotton = (() => {
  let D = null, unit = 'm480', rainReg = 'Maharashtra', trKey = 'raw_import';
  const md = s => String(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  const a = (u, l) => `<a href="${u}" target="_blank" rel="noopener">${l} ↗</a>`;
  const kpi = (l, v, s2) => `<div class="card kpi"><div class="lbl">${l}</div><div class="val">${v}</div><div class="sub">${s2}</div></div>`;
  const f = (v, d = 2) => v == null || Number.isNaN(v) ? '–' : fmt(v, d);
  const pc = v => v == null ? '–' : `${v > 0 ? '+' : ''}${fmt(v, 0)}%`;
  const rainCls = v => v == null ? '' : v <= -20 ? 'dn' : v >= 20 ? 'up' : '';
  const MONS = ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep'];
  const seasonOf = ym => { const [y, m] = ym.split('-').map(Number); const s = m >= 10 ? y : y - 1; return `${s}-${String((s + 1) % 100).padStart(2, '0')}`; };

  async function mount(el) {
    el.innerHTML = '<div class="card"><p class="note">Loading India cotton…</p></div>';
    D = await getJSON('data/india/india.json').catch(() => null);
    if (!D || !D.projection) { el.innerHTML = '<div class="card"><p class="note">India cotton data not built yet.</p></div>'; return; }
    const P = D.projection, R = D.rain || {}, X = (D.prices || {}).latest || {}, B = D.balance || {};
    const ix = R.cotton_area_index || {}, ky = String(R.kharif_year), yrs = Object.keys(ix).sort();
    const rank = yrs.length ? yrs.slice().sort((a, b) => ix[a] - ix[b]).indexOf(ky) + 1 : null;
    el.innerHTML = `
      <div class="card"><h2>India cotton brief</h2>
        ${(D.brief || []).map(b => `<p><b>${b.h}.</b> ${md(b.t)}</p>`).join('')}
        <p class="note">Updated ${D.built}. ${D.conv.note}. Sources: Cotton Association of India and the Committee on Cotton Production and Consumption (COCPC) via ${a('https://www.caionline.in/', 'caionline.in')},
        USDA PSD, NASA POWER rainfall, Ministry of Agriculture sowing data, Yahoo (USD/INR, ICE). Research use only.</p></div>
      <div class="grid g4" style="margin-top:12px">
        ${kpi(`Desk crop ${P.season}`, `${f(P.m480)} m bales`, `range ${f(P.lo_m480)}–${f(P.hi_m480)} · ${f(P.lakh, 0)} lakh Indian bales · USDA ${f(P.usda_m480)} · last season ${f(P.last_season.m480)}`)}
        ${kpi('Monsoon in cotton areas', ix[ky] != null ? pc(ix[ky]) : '–', `June–September rain vs ${R.normal} normal, weighted by cotton area${rank ? ` · ${ordinal(rank)} driest of ${yrs.length} years` : ''}`)}
        ${kpi('Shankar-6', X.rs_candy ? `₹${fmt(X.rs_candy, 0)}` : '–', X.rs_candy ? `per candy · ${f(X.clb, 1)}¢/lb · ${X.premium_ice != null ? `${X.premium_ice > 0 ? '+' : ''}${f(X.premium_ice, 1)}¢ vs ICE` : ''} · ${pc(X.chg_1y_pct)} y/y · ${X.date}` : '')}
        ${kpi('Cotton area', `${f(P.area_lakh_ha, 1)} lakh ha`, `${P.area_change_pct > 0 ? '+' : ''}${f(P.area_change_pct, 1)}% vs last season, the Ministry's sowing change applied to the Cotton Advisory Board area · ${P.area_note || ''}`)}
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Desk crop projection by region (${P.season})</h2><div class="tbl" id="inProj"></div>
          <p class="note">Production = sown area × yield. Yield starts from each region's average of the last three seasons and moves with this season's rainfall at its main cotton districts. Variables used: ${P.variables.join('; ')}.
          * North (Punjab, Haryana, Rajasthan) is mostly irrigated, so rain is not used there. Normal yield = average of the last three seasons. Range: the model's typical miss in past seasons.</p></div>
        <div class="card"><h2>India production by season (m 480-lb bales)</h2><div class="chart"><canvas id="cInProd"></canvas></div>
          <p class="note">Cotton Advisory Board / COCPC production converted to US bales; the last bar is the desk projection with its range, beside USDA.</p></div>
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Monsoon rain in the cotton districts (${R.kharif_year})</h2><div class="tbl" id="inRain"></div>
          <p class="note">Rain at 2–7 main cotton districts per region (NASA POWER) against the ${R.normal} average. Red: 20% or more below normal. Rank: where this June–September sits among ${yrs.length} years since ${yrs[0]}, 1 = driest.</p></div>
        <div class="card"><h2>Cotton-area monsoon index by year (% vs normal)</h2><div class="chart"><canvas id="cInIdx"></canvas></div>
          <p class="note">June–September rain across the cotton regions weighted by their area. Dots: national yield vs its three-season average (right axis).</p></div>
      </div>
      <div class="card" style="margin-top:12px"><h2>Monthly rain by region (mm)</h2><div class="ctrls" id="inRainSel"></div><div class="chart"><canvas id="cInRainM"></canvas></div><p class="note" id="inRainNote"></p></div>
      <div class="card" style="margin-top:12px"><h2>Balance sheets side by side</h2><div class="ctrls" id="inUnitSel"></div><div class="tbl" id="inBal"></div>
        <p class="note">COCPC: the government's Committee on Cotton Production and Consumption (official). CAI: the trade's crop committee, monthly. USDA: August–July year in 480-lb bales; COCPC and CAI use the October–September season.
        The sources differ a lot in level, so the revisions matter more than the gaps between them.</p><p class="note" id="inDeskNote"></p>
        <h3 style="margin-top:12px">Imports and the 11% duty (USDA year, m 480-lb bales)</h3><div class="tbl" id="inImpSc"></div><p class="note" id="inImpScNote"></p></div>
      ${D.notes?.cci ? cciCard(D.notes.cci) : ''}
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>CAI estimate revisions, this season and last</h2><div class="chart"><canvas id="cInRev"></canvas></div><p class="note" id="inRevNote"></p></div>
        <div class="card"><h2>Monthly trade by season (thousand t)</h2><div class="ctrls" id="inTrSel"></div><div class="chart"><canvas id="cInTr"></canvas></div><p class="note" id="inTrNote"></p></div>
      </div>
      ${D.origins?.split ? `<div class="card" style="margin-top:12px"><h2>Where India's imports come from</h2>
        <div class="chart" style="height:300px"><canvas id="cInOrg"></canvas></div><p class="note" id="inOrgNote"></p>
        <div class="grid g2" style="margin-top:8px"><div class="tbl" id="inOrgWin"></div><div class="tbl" id="inOrgSplit"></div></div>
        <div class="grid g2" style="margin-top:8px"><div class="tbl" id="inOrgCost"></div><div class="tbl" id="inOrgSup"></div></div>
        <p class="note">Origins: India-reported imports of raw cotton (HS 5201) from UN Comtrade, by month. Africa = all African origins except Egypt (shown apart: extra-long staple). Least-developed African countries ship duty-free under India's DFTP scheme; Australia ships duty-free within the 51,000 t ECTA quota.
        Origin split of the desk scenarios: each month's imports shared out by that calendar month's origin mix since 2022 under the same duty status, weighted by each origin's exportable supply for the new season against last season (USDA; the US on the desk crop). Landed cost = ICE nearby + basis (desk trade levels), before freight.</p></div>` : ''}
      <div class="card" style="margin-top:12px"><h2>Shankar-6 vs ICE (¢/lb, weekly)</h2><div class="chart"><canvas id="cInPx"></canvas></div><p class="note" id="inPxNote"></p></div>
      ${(D.notes?.policy || []).length ? `<div class="card" style="margin-top:12px"><h2>Policy</h2>${D.notes.policy.map(p => `<p>${md(p.t)}</p>`).join('')}</div>` : ''}`;
    proj(); prodChart(); rainTable(); idxChart(); rainSel(); balance(); deskNote(); impScen(); origins(); revChart(); tradeSel(); pxChart();
  }

  function cciCard(c) {
    const left = c.procured - c.sold, k = D.conv.lakh170_to_m480;
    return `<div class="card" style="margin-top:12px"><h2>Government stocks: Cotton Corporation of India (CCI)</h2>
      <div class="tbl"><table><tr><th class="l">Crop</th><th>Bought at MSP</th><th>Sold</th><th>Left</th><th>As of</th></tr>
      <tr><td class="l">${c.season}</td><td>${f(c.procured, 1)} lakh (${f(c.procured * k)} m)</td><td>${f(c.sold, 1)} lakh</td><td><b>${f(left, 1)} lakh (${f(left * k)} m)</b></td><td>${c.as_of}</td></tr>
      ${(c.history || []).filter(h => h.sold != null).map(h => `<tr><td class="l">${h.season}</td><td>${f(h.procured, 1)} lakh</td><td>${f(h.sold, 1)} lakh</td><td>${f(h.procured - h.sold, 1)} lakh</td><td>${h.as_of}</td></tr>`).join('')}</table></div>
      <p class="note">CCI buys kapas at the minimum support price when market prices fall below it and sells the lint by weekly e-auction. Recent sales pace about ${f(c.weekly, 1)} lakh bales a week, so the 2025-26 reserve is close to sold out.
      Its stock is part of the national closing stock in every balance sheet above, not extra. Source: ${c.source}.</p></div>`;
  }

  const ordinal = n => n + (['th', 'st', 'nd', 'rd'][(n % 100 > 10 && n % 100 < 14) ? 0 : (n % 10 < 4 ? n % 10 : 0)] || 'th');

  function proj() {
    const P = D.projection, rows = P.regions;
    const t = rows.map(r => `<tr><td class="l">${r.region}${r.irrigated ? '*' : ''}</td><td>${f(r.area, 1)}</td><td>${r.irrigated ? '–' : `<span class="${rainCls(r.rain_as_pct)}">${pc(r.rain_as_pct)}</span>`}</td>
      <td>${fmt(r.yield, 0)} <span class="note">${pc(r.yield_vs_normal_pct)}</span></td><td><b>${f(r.prod_m480)}</b></td><td>${f(r.last_prod_lakh * D.conv.lakh170_to_m480)}</td></tr>`).join('');
    const tot = rows.reduce((s, r) => s + r.prod_m480, 0), last = rows.reduce((s, r) => s + r.last_prod_lakh, 0) * D.conv.lakh170_to_m480;
    document.getElementById('inProj').innerHTML = `<table><tr><th class="l">Region</th><th>Area<br>lakh ha</th><th>Aug–Sep<br>rain</th><th>Yield kg/ha<br>vs normal</th><th>Crop<br>m bales</th><th>Last<br>season</th></tr>${t}
      ${P.unmodelled_lakh > 0.05 ? `<tr><td class="l">Other states</td><td></td><td></td><td></td><td>${f(P.unmodelled_lakh * D.conv.lakh170_to_m480)}</td><td>${f(P.unmodelled_lakh * D.conv.lakh170_to_m480)}</td></tr>` : ''}
      <tr><td class="l"><b>India</b></td><td><b>${f(P.area_lakh_ha, 1)}</b></td><td></td><td></td><td><b>${f(P.m480)}</b></td><td><b>${f(P.last_season.m480)}</b></td></tr></table>`;
  }

  function prodChart() {
    const H = D.history, ys = Object.keys(H).sort().filter(y => +y >= 2005), P = D.projection;
    const lab = ys.map(y => `${+y - 1}-${y.slice(2)}`).concat([P.season]);
    chart('cInProd', { type: 'bar', data: { labels: lab, datasets: [
      { label: 'COCPC / CAB production', data: ys.map(y => H[y].prod_m480).concat([null]), backgroundColor: '#8aa4c8' },
      { label: 'Desk projection', data: ys.map(() => null).concat([P.m480]), backgroundColor: '#c0504d' },
      { label: 'USDA', type: 'line', data: lab.map(s => B480('usda', s)), borderColor: '#333', pointRadius: 2, showLine: false }] },
      options: { plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { afterBody: it => it[0].dataIndex === lab.length - 1 ? `Range ${f(P.lo_m480)}–${f(P.hi_m480)}` : '' } } } } });
  }
  const B480 = (src, s) => D.balance?.[src]?.[s]?.m480?.crop ?? null;

  function rainTable() {
    const R = D.rain, regs = Object.keys(R.regions).sort((a, b) => (R.regions[b].area_share || 0) - (R.regions[a].area_share || 0));
    document.getElementById('inRain').innerHTML = `<table><tr><th class="l">Region</th><th>Area share</th><th>Jun–Jul</th><th>Aug–Sep</th><th>Jun–Sep</th><th>Oct</th><th>Rank (1 = driest)</th></tr>${regs.map(r => { const g = R.regions[r];
      return `<tr><td class="l">${r}</td><td>${fmt(100 * (g.area_share || 0), 0)}%</td>${['jj_pct', 'as_pct', 'jjas_pct', 'oct_pct'].map(k => `<td class="${rainCls(g[k])}">${pc(g[k])}</td>`).join('')}<td>${g.rank_driest ?? '–'} of ${g.years}</td></tr>`; }).join('')}</table>`;
  }

  function idxChart() {
    const ix = D.rain.cotton_area_index, ys = Object.keys(ix).sort(), H = D.history;
    const dev = ys.map(y => { const s = +y + 1, p = [1, 2, 3].map(k => H[s - k]?.yield).filter(v => v); return H[s]?.yield && p.length >= 3 ? Math.round(100 * (H[s].yield / (p.reduce((a, b) => a + b, 0) / p.length) - 1)) : null; });
    chart('cInIdx', { type: 'bar', data: { labels: ys, datasets: [
      { label: 'Monsoon rain vs normal (%)', data: ys.map(y => ix[y]), backgroundColor: ys.map(y => y === String(D.rain.kharif_year) ? '#c0504d' : ix[y] < 0 ? '#d9a35b' : '#6f9fcf') },
      { label: 'Yield vs 3-season average (%)', type: 'line', data: dev, borderColor: '#333', pointRadius: 3, showLine: false, yAxisID: 'y2' }] },
      options: { plugins: { legend: { position: 'bottom' } }, scales: { y2: { position: 'right', grid: { display: false } } } } });
  }

  function rainSel() {
    const regs = Object.keys(D.rain.regions);
    if (!regs.includes(rainReg)) rainReg = regs[0];
    document.getElementById('inRainSel').innerHTML = regs.map(r => `<button class="btn ${r === rainReg ? 'on' : ''}" data-r="${r}">${r}</button>`).join('');
    document.querySelectorAll('#inRainSel button').forEach(b => b.onclick = () => { rainReg = b.dataset.r; rainSel(); });
    const g = D.rain.regions[rainReg], ms = Object.keys(g.monthly).sort(), names = ms.map(m => MON[+m - 1]);
    chart('cInRainM', { type: 'bar', data: { labels: names, datasets: [
      { label: String(D.rain.kharif_year), data: ms.map(m => g.monthly[m].cur), backgroundColor: '#c0504d' },
      { label: 'Last year', data: ms.map(m => g.monthly[m].last), backgroundColor: '#bbb' },
      { label: `Normal ${D.rain.normal}`, type: 'line', data: ms.map(m => g.monthly[m].normal), borderColor: '#333', pointRadius: 2 }] }, options: { plugins: { legend: { position: 'bottom' } } } });
    document.getElementById('inRainNote').textContent = `${rainReg}: June–September ${pc(g.jjas_pct)} vs normal (${g.jjas_mm ?? '–'} mm), rank ${g.rank_driest ?? '–'} of ${g.years} (1 = driest). Current month is to date.`;
  }

  function balance() {
    const U = [['m480', 'm 480-lb bales'], ['lakh', 'lakh 170-kg bales']];
    document.getElementById('inUnitSel').innerHTML = U.map(([k, l]) => `<button class="btn ${k === unit ? 'on' : ''}" data-u="${k}">${l}</button>`).join('');
    document.querySelectorAll('#inUnitSel button').forEach(b => b.onclick = () => { unit = b.dataset.u; balance(); });
    const B = D.balance, seasons = [...new Set([...Object.keys(B.cocpc), ...Object.keys(B.cai), ...Object.keys(B.usda)])].sort().slice(-3);
    const cols = [];
    seasons.forEach(s => ['cocpc', 'cai', 'usda'].forEach(src => { if (B[src][s]) cols.push([src, s]); }));
    const DB = D.desk_balance || {}; ['usda', 'cocpc', 'cai'].forEach(src => { if (DB.cases?.[src]) cols.push(['desk_' + src, DB.season]); });
    const val = (src, s, k) => { if (src.startsWith('desk_')) return DB.cases[src.slice(5)][unit][k]; const v = B[src][s]; if (src === 'usda') return unit === 'm480' ? v.m480[k] : v.m480[k] / D.conv.lakh170_to_m480; return v[unit]?.[k]; };
    const rows = [['opening', 'Opening stock'], ['crop', 'Crop'], ['imports', 'Imports'], ['supply', 'Total supply'], ['consumption', 'Consumption'], ['exports', 'Exports'], ['closing', 'Closing stock']];
    const nm = { cocpc: 'COCPC', cai: 'CAI', usda: 'USDA', desk_usda: 'Desk, on USDA', desk_cocpc: 'Desk, COCPC base', desk_cai: 'Desk, CAI base' }, d = unit === 'm480' ? 2 : 1;
    document.getElementById('inBal').innerHTML = `<table><tr><th class="l"></th>${cols.map(([src, s]) => `<th${src.startsWith('desk_') ? ' style="background:#fbeeee"' : ''}>${s}<br><span class="note">${nm[src]}${src === 'cai' && B.cai[s].as_of ? ' ' + B.cai[s].as_of : ''}</span></th>`).join('')}</tr>
      ${rows.map(([k, l]) => `<tr><td class="l">${l}</td>${cols.map(([src, s]) => `<td>${f(val(src, s, k), d)}</td>`).join('')}</tr>`).join('')}
      <tr><td class="l">Stocks / use</td>${cols.map(([src, s]) => { const c = val(src, s, 'closing'), u = (val(src, s, 'consumption') || 0) + (val(src, s, 'exports') || 0); return `<td>${u ? fmt(100 * c / u, 0) + '%' : '–'}</td>`; }).join('')}</tr></table>`;
  }

  function deskNote() {
    const DB = D.desk_balance; if (!DB?.cases?.cocpc) return;
    const c = DB.cases.cocpc, a = DB.cases.cai, pi = DB.imports_customs[DB.prev], pe = DB.exports_customs[DB.prev];
    document.getElementById('inDeskNote').innerHTML = `<b>Desk ${DB.season} (shaded):</b> built on each sheet. Opening stock = that sheet's ${DB.prev} closing corrected for actual customs trade: HS 5201 imports ${f(pi.actual, 1)} lakh bales through ${pi.through}
      (${f(pi.projected, 0)} for the season at the recent pace of ${f(pi.pace_month, 1)} a month) vs ${f(c.prev_imports_sheet, 0)} in COCPC and ${f(a?.prev_imports_sheet, 0)} in CAI; exports ${f(pe?.actual, 1)} (${f(pe?.projected, 0)}) vs ${f(c.prev_exports_sheet, 0)} and ${f(a?.prev_exports_sheet, 0)}.
      COCPC's past import and export lines match these customs figures. Crop = desk projection; imports and exports at the customs pace; consumption at each sheet's ${DB.prev} level.
      <br><b>Desk, on USDA:</b> USDA's ${DB.prev} as published (August–July), then the desk crop and customs trade for ${DB.season}${DB.cases.usda ? ` (imports: the expected-duty case in the table below); use at USDA's ${DB.season} figure. USDA's own ${DB.prev} imports (${f(DB.cases.usda.prev_usda_imports)} m) match customs (${f(DB.cases.usda.prev_customs_imports_m480)} m).` : ''}
      To hold ${DB.prev}'s stocks/use (${f(c.prev_stocks_use, 0)}% on COCPC) India would need about ${f(c.imports_to_hold_m480)} m 480-lb bales of imports (${f(c.imports_to_hold_stocks_use, 0)} lakh).`;
  }

  function impScen() {
    const I = D.desk_balance?.import_scenarios, u = D.desk_balance?.cases?.usda; if (!I || !u) return;
    const S = I.scenarios, mons = I.months.map(m => MON[+m.slice(5) - 1]);
    document.getElementById('inImpSc').innerHTML = `<table><tr><th class="l">Case</th>${mons.map(m => `<th>${m}</th>`).join('')}<th>Imports</th><th>Ending stocks</th><th>Stocks/use</th></tr>
      ${Object.values(S).map(v => `<tr><td class="l">${v.label}</td>${v.path.map((x, i) => `<td${I.reported.includes(I.months[i]) ? ' style="font-weight:600"' : ''}>${f(x)}</td>`).join('')}<td><b>${f(v.m480, 1)}</b></td><td><b>${f(v.closing_m480, 1)}</b></td><td>${fmt(v.stocks_use, 0)}%</td></tr>`).join('')}
      <tr><td class="l">USDA</td>${mons.map(() => '<td></td>').join('')}<td>${f(u.usda_imports, 1)}</td><td>${f(u.usda_closing, 1)}</td><td></td></tr></table>`;
    document.getElementById('inImpScNote').textContent = `Bold months are reported customs (HS 5201). Duty-free months at the last three duty-free months' pace (${f(I.free_pace)} m a month), duty months at the last five duty months' pace (${f(I.duty_pace)} m); before a duty return importers pull shipments forward (December 2025 was twice the months before) and the first duty month still carries part of it. All cases keep USDA's ${D.desk_balance.prev} ending stocks (${f(u.m480.opening)} m), the desk crop (${f(u.m480.crop)} m), USDA's use (${f(u.m480.consumption)} m) and exports at the customs pace (${f(u.m480.exports)} m). In the 2025 duty-free window imports ran faster (0.6 m a month in September–November), which would put the all-season case near 7 m.`;
  }

  function origins() {
    const O = D.origins; if (!O?.split) return;
    const OR = ['USA', 'Brazil', 'Australia', 'Africa', 'Egypt', 'Other'], COL = { USA: '#1f4e79', Brazil: '#2e8b57', Australia: '#d9a35b', Africa: '#8b5a2b', Egypt: '#9b59b6', Other: '#bbb' };
    const ms = Object.keys(O.monthly_kt).sort(), free = new Set(O.free_months);
    chart('cInOrg', { type: 'bar', data: { labels: ms.map(m => (free.has(m) ? '★ ' : '') + MON[+m.slice(5) - 1] + ' ' + m.slice(2, 4)), datasets: OR.map(o => ({ label: o, data: ms.map(m => O.monthly_kt[m][o]), backgroundColor: COL[o], stack: 's' })) },
      options: { plugins: { legend: { position: 'bottom' } }, scales: { x: { stacked: true, ticks: { maxTicksLimit: 30, font: { size: 9 } } }, y: { stacked: true, title: { display: true, text: 'thousand t' } } } } });
    document.getElementById('inOrgNote').textContent = `★ = duty-free month. Last 12 months (${O.last12.from} to ${O.last12.to}): ${f(O.last12.kt, 0)} kt — ${OR.map(o => `${o} ${fmt(O.last12.share[o], 0)}%`).join(', ')}.`;
    document.getElementById('inOrgWin').innerHTML = `<table><tr><th class="l">Duty-free window</th><th>kt</th>${OR.slice(0, 4).map(o => `<th>${o}</th>`).join('')}</tr>${O.windows.map(w => `<tr><td class="l">${w.window}${w.through < w.window ? '' : ''}</td><td>${f(w.kt, 0)}</td>${OR.slice(0, 4).map(o => `<td>${fmt(w.share[o], 0)}%</td>`).join('')}</tr>`).join('')}</table>`;
    const SP = O.split, lab = { notified: 'Duty back Nov', expected: 'Waiver to Dec', all_year: 'Waiver all season' };
    document.getElementById('inOrgSplit').innerHTML = `<table><tr><th class="l">2026/27 imports by origin, m bales</th>${OR.slice(0, 4).map(o => `<th>${o}</th>`).join('')}<th>Total</th></tr>${Object.keys(SP).map(k => `<tr><td class="l">${lab[k]}</td>${OR.slice(0, 4).map(o => `<td>${f(SP[k][o])}</td>`).join('')}<td>${f(OR.reduce((a, o) => a + SP[k][o], 0))}</td></tr>`).join('')}
      <tr><td class="l">Extra vs duty back Nov: to Dec</td>${OR.slice(0, 4).map(o => `<td>+${f(O.extra_expected[o])}</td>`).join('')}<td></td></tr><tr><td class="l">Extra: all season</td>${OR.slice(0, 4).map(o => `<td>+${f(O.extra_all_year[o])}</td>`).join('')}<td></td></tr></table>`;
    document.getElementById('inOrgCost').innerHTML = `<table><tr><th class="l">Landed guide, ¢/lb (ICE ${f(O.ice, 1)})</th><th>Basis</th><th>Duty-free</th><th>With duty</th></tr>${Object.entries(O.cost).map(([o, c]) => `<tr><td class="l" title="${c.treatment}">${o}</td><td>+${c.basis}</td><td>${f(c.free, 1)}</td><td>${f(c.duty, 1)}${c.above_quota ? ` <span class="note">(${f(c.above_quota, 1)} above quota)</span>` : ''}</td></tr>`).join('')}</table>`;
    document.getElementById('inOrgSup').innerHTML = `<table><tr><th class="l">Exportable supply, m bales</th><th>Last season</th><th>This season</th><th>Change</th></tr>${Object.entries(O.supply).map(([o, v]) => `<tr><td class="l">${o}</td><td>${f(v.prev, 1)}</td><td>${f(v.new, 1)}</td><td>${pc(100 * (v.index - 1))}</td></tr>`).join('')}</table>`;
  }

  function revChart() {
    const C = D.balance.cai, ss = Object.keys(C).sort().slice(-2);
    const ds = [];
    const at = (r, k) => { const a = Array(12).fill(null); r.forEach(x => { a[(+x.month.slice(5) + 2) % 12] = x[k]; }); return a; };
    ss.forEach((s, i) => { const r = C[s].revisions || []; ds.push({ label: `${s} crop`, data: at(r, 'crop'), borderColor: i ? '#c0504d' : '#999', pointRadius: 2, spanGaps: true });
      ds.push({ label: `${s} closing stock`, data: at(r, 'closing'), borderColor: i ? '#c0504d' : '#999', borderDash: [5, 4], pointRadius: 2, spanGaps: true }); });
    chart('cInRev', { type: 'line', data: { labels: MONS, datasets: ds }, options: { plugins: { legend: { position: 'bottom' } } } });
    const cur = C[ss[ss.length - 1]];
    document.getElementById('inRevNote').textContent = cur ? `CAI crop committee, lakh 170-kg bales, by month of the October–September season. Latest: ${cur.as_of}, crop ${f(cur.lakh.crop, 1)}, closing stock ${f(cur.lakh.closing, 1)} lakh bales (${f(cur.m480.crop)} and ${f(cur.m480.closing)} m 480-lb bales).` : '';
  }

  function tradeSel() {
    const T = D.trade || {}, K = [['raw_import', 'Raw cotton imports'], ['raw_export', 'Raw cotton exports'], ['yarn_export', 'Cotton yarn exports']].filter(([k]) => T[k] && Object.keys(T[k]).length);
    if (!K.length) { document.getElementById('inTrNote').textContent = 'Trade data not loaded yet.'; return; }
    if (!K.find(([k]) => k === trKey)) trKey = K[0][0];
    document.getElementById('inTrSel').innerHTML = K.map(([k, l]) => `<button class="btn ${k === trKey ? 'on' : ''}" data-k="${k}">${l}</button>`).join('');
    document.querySelectorAll('#inTrSel button').forEach(b => b.onclick = () => { trKey = b.dataset.k; tradeSel(); });
    const rows = T[trKey], byS = {};
    Object.entries(rows).forEach(([ym, v]) => { const s = v.season || seasonOf(ym), i = (+ym.slice(5) + 2) % 12; (byS[s] ||= Array(12).fill(null))[i] = v.t ? v.t / 1000 : null; });
    const ss = Object.keys(byS).sort().slice(-4), cols = ['#ccc', '#aaa', '#777', '#c0504d'].slice(-ss.length);
    chart('cInTr', { type: 'bar', data: { labels: MONS, datasets: ss.map((s, i) => ({ label: s, data: byS[s], backgroundColor: cols[i] })) }, options: { plugins: { legend: { position: 'bottom' } } } });
    const cur = ss[ss.length - 1], prev = ss[ss.length - 2], n = byS[cur].filter(v => v).length;
    const ytd = s => byS[s]?.slice(0, n).reduce((a, b) => a + (b || 0), 0);
    document.getElementById('inTrNote').textContent = `Thousand tonnes, from CAI's monthly trade tables (raw cotton: HS 5201–5203; yarn: HS 5205). ${cur} so far (${n} months): ${fmt(ytd(cur), 0)} kt vs ${fmt(ytd(prev), 0)} kt in the same months of ${prev} (${pc(100 * (ytd(cur) / ytd(prev) - 1))})` + (trKey.startsWith('raw') ? `, about ${f(ytd(cur) * 1e6 / 217.7243 / 1e6)} m 480-lb bales.` : '.');
  }

  function pxChart() {
    const W = D.prices?.weekly; if (!W) return;
    chart('cInPx', { type: 'line', data: { labels: W.date, datasets: [
      { label: 'Shankar-6 (¢/lb)', data: W.clb, borderColor: '#c0504d', pointRadius: 0, borderWidth: 2 },
      { label: 'ICE nearby (¢/lb)', data: W.ice, borderColor: '#333', pointRadius: 0 },
      { label: 'Premium to ICE (¢/lb)', data: W.clb.map((v, i) => v != null && W.ice[i] != null ? +(v - W.ice[i]).toFixed(1) : null), borderColor: '#6f9fcf', pointRadius: 0, yAxisID: 'y2' }] },
      options: { plugins: { legend: { position: 'bottom' } }, scales: { x: { ticks: { maxTicksLimit: 10 } }, y2: { position: 'right', grid: { display: false } } } } });
    const L = D.prices.latest, M = D.prices.msp;
    document.getElementById('inPxNote').innerHTML = `${D.prices.note}. Latest ${L.date}: ₹${fmt(L.rs_candy, 0)}/candy = ${f(L.clb, 1)}¢/lb at ₹${f(L.inr, 2)}/$${L.ice != null ? `, ICE ${f(L.ice, 2)}¢` : ''}.` +
      (M ? ` MSP ${M.season}: kapas ₹${fmt(M.kapas_medium, 0)}/quintal (medium staple) ≈ lint ₹${fmt(M.lint_rs_candy, 0)}/candy = ${f(M.lint_clb, 1)}¢/lb (${M.assumptions}); below that, CCI buys at MSP and supports the market.` : '');
  }

  return { mount };
})();
