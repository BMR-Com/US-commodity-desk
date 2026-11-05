// Grain summary: broker-style weekly grains pack (yields, states, balances, export sales, price vs tightness,
// spreads, positioning, world and South America) built from public data in data/grains/derived/pack.json.
const GrainPack = (() => {
  let P = null, crop = 'corn';
  const f0 = v => fmt(v, 0), f1 = v => fmt(v, 1), f2 = v => fmt(v, 2);
  const pctCell = v => v == null ? '<td>–</td>' : `<td style="background:${v > 0 ? '#e3f4e6' : v < 0 ? '#fbe3e1' : '#fff'};color:${v > 0 ? '#1f7a3a' : v < 0 ? '#b3261e' : '#333'}">${v > 0 ? '+' : ''}${fmt(v, 1)}%</td>`;
  const card = (title, body, note = '') => `<div class="card"><h2>${title}</h2>${body}${note ? `<p class="note">${note}</p>` : ''}</div>`;
  const cv = (id, cls = '') => `<div class="chart ${cls}"><canvas id="${id}"></canvas></div>`;
  const btns = (name, opts, on) => `<span class="ctrls" data-grp="${name}">${opts.map(([k, l]) => `<button class="btn ${k === on ? 'on' : ''}" data-v="${k}">${l}</button>`).join('')}</span>`;
  const NAMES = { AL: 'Alabama', AR: 'Arkansas', CO: 'Colorado', DE: 'Delaware', GA: 'Georgia', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', MD: 'Maryland', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri', NE: 'Nebraska', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', PA: 'Pennsylvania', SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', VA: 'Virginia', WA: 'Washington', WI: 'Wisconsin', NJ: 'New Jersey', CA: 'California', AZ: 'Arizona', MT: 'Montana', WY: 'Wyoming', NM: 'New Mexico', UT: 'Utah', OR: 'Oregon', NV: 'Nevada', WV: 'West Virginia', FL: 'Florida', ME: 'Maine', VT: 'Vermont', NH: 'New Hampshire', MA: 'Massachusetts', CT: 'Connecticut', RI: 'Rhode Island', US: 'United States' };
  // tile-grid map of the lower 48 (row, col)
  const TILE = { WA: [0, 1], ID: [0, 2], MT: [0, 3], ND: [0, 4], MN: [0, 5], WI: [0, 6], MI: [0, 8], NY: [0, 9], VT: [0, 10], ME: [0, 11],
    OR: [1, 1], NV: [1, 2], WY: [1, 3], SD: [1, 4], IA: [1, 5], IL: [1, 6], IN: [1, 7], OH: [1, 8], PA: [1, 9], NJ: [1, 10], NH: [1, 11],
    CA: [2, 1], UT: [2, 2], CO: [2, 3], NE: [2, 4], MO: [2, 5], KY: [2, 6], WV: [2, 7], VA: [2, 8], MD: [2, 9], DE: [2, 10], MA: [2, 11],
    AZ: [3, 2], NM: [3, 3], KS: [3, 4], AR: [3, 5], TN: [3, 6], NC: [3, 7], SC: [3, 8], CT: [3, 10], RI: [3, 11],
    OK: [4, 4], LA: [4, 5], MS: [4, 6], AL: [4, 7], GA: [4, 8], TX: [5, 4], FL: [5, 8] };
  function tileMap(vals, dec, title) {
    const mx = Math.max(0.01, ...Object.values(vals).map(v => Math.abs(v)));
    const col = v => { if (v == null) return '#eceeea'; const a = Math.min(1, Math.abs(v) / mx); return v > 0 ? `rgba(44,111,187,${0.18 + 0.82 * a})` : v < 0 ? `rgba(192,57,43,${0.18 + 0.82 * a})` : '#c9ccc6'; };
    const cells = Object.entries(TILE).map(([s, [r, c]]) => { const v = vals[s];
      return `<div title="${NAMES[s] || s}: ${v == null ? 'n/a' : (v > 0 ? '+' : '') + fmt(v, dec)}" style="grid-row:${r + 1};grid-column:${c + 1};background:${col(v)};color:${v != null && Math.abs(v) / mx > .55 ? '#fff' : '#222'};border-radius:4px;padding:3px 2px;text-align:center;font-size:10.5px;line-height:1.15"><b>${s}</b><br>${v == null ? '' : (v > 0 ? '+' : '') + fmt(v, dec)}</div>`; }).join('');
    return `<h3>${title}</h3><div style="display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:3px;max-width:640px">${cells}</div>`;
  }

  async function mount(root) {
    root.innerHTML = '<div class="card"><p class="note">Loading grain summary…</p></div>';
    P = P || await getJSON('data/grains/derived/pack.json').catch(() => null);
    if (!P) { root.innerHTML = '<div class="card"><p class="note">Grain summary not built yet (models/grains_pack.py).</p></div>'; return; }
    root.innerHTML = `
      <div class="card"><h2>Grain summary · outlook</h2>
        <p class="note">What the public numbers say as of ${P.generated} (crop year ${P.crop_year}). Rule-based readout of the charts below — USDA, CFTC, CME and Comex Stat data only, no private estimates; not a trade recommendation.</p>
        <div class="grid g2" style="margin-top:8px">${P.outlook.map(o => `<div><h3>${o.name}</h3><ul class="read">${o.lines.map(l => `<li>${l}</li>`).join('')}</ul></div>`).join('')}</div></div>
      <div class="ctrls" style="margin:12px 2px">${btns('crop', [['corn', 'Corn'], ['soybeans', 'Soybeans']], crop)}<span class="note">switches the corn / soybean sections below; wheat and world sections are fixed</span></div>
      <div id="gpBody" class="grid" style="gap:12px"></div>`;
    root.querySelectorAll('[data-grp="crop"] button').forEach(b => b.onclick = () => { crop = b.dataset.v; root.querySelectorAll('[data-grp="crop"] button').forEach(x => x.classList.toggle('on', x === b)); body(); });
    body();
  }

  function body() {
    const B = $('#gpBody'); const c = crop, Cn = c === 'corn' ? 'Corn' : 'Soybeans';
    const Y = P.yields[c], T = P.tightness[c];
    B.innerHTML = `
      <div class="grid g2">${yieldTable('corn')}${yieldTable('soybeans')}</div>
      <div class="card"><h2>${Cn}: state changes in the USDA yield forecast</h2>
        <div class="ctrls"><select id="gpMap">${Y.maps.map((m, i) => `<option value="${i}" ${i === Y.maps.length - 1 ? 'selected' : ''}>${m.label}</option>`).join('')}</select><span class="note" id="gpMapNote"></span></div>
        <div class="grid g2"><div id="gpMapA"></div><div id="gpMapB"></div></div>
        <div class="tbl" id="gpStates" style="margin-top:10px;max-height:420px;overflow:auto"></div>
        <p class="note">NASS Crop Production. Impact = yield change × state harvested acres ÷ US harvested acres (bu/ac on the national yield). Trend = linear fit of NASS final state yields 1986 to last year.</p></div>
      <div class="grid g2">
        <div class="card"><h2>${Cn}: state yield history vs trend</h2><div class="ctrls"><select id="gpHistSt">${Object.keys(Y.hist).map(s => `<option value="${s}" ${s === 'IA' ? 'selected' : ''}>${NAMES[s] || s}</option>`).join('')}</select><span class="note" id="gpHistNote"></span></div>${cv('gpHist')}<p class="note">NASS final yields; red point = current-year USDA forecast.</p></div>
        <div class="card"><h2>USDA September → October change in new-crop ending stocks</h2>${cv('gpRev')}<p class="note">WASDE new-crop US ending stocks, October minus September report (m bu). The report this replicates shows the surprise vs the analyst poll; no free poll exists, so this is USDA's own revision.</p></div>
      </div>
      <div class="grid" id="gpSD"></div>
      <div class="card"><h2>US export sales model: projected final exports by week</h2>
        <div class="grid g3" id="gpProj"></div>
        <p class="note">FAS weekly export sales. Projection at week w = current commitments ÷ the median share of the final (ESR) total that was committed by week w in the last 10 completed seasons; band = 10th–90th percentile of that share. Dashed pink = latest USDA WASDE exports. ESR basis, so it can differ from Census exports.</p></div>
      <div class="card"><h2>YTD shipments, outstanding sales and commitments at the same week (MMT)</h2><div class="grid g3" id="gpYTD"></div></div>
      <div class="grid g2">
        <div class="card"><h2>${Cn}: weekly net sales vs 5-year average ('000 t)</h2>${cv('gpWeekly')}</div>
        <div class="card"><h2>Managed money net position (million t)</h2>${cv('gpCot')}<p class="note">CFTC disaggregated futures + options, managed money long − short × 5,000 bu.</p></div>
      </div>
      <div class="grid g2">
        <div class="card"><h2>${Cn}: price vs tightness curve (avg ${T.contract.slice(0, 3)} during ${T.month})</h2>${cv('gpCurve', 'tall')}
          <p class="note">Each dot: average price of the new-crop ${c === 'corn' ? 'December' : 'November'} contract during ${T.month} of the harvest year vs US stocks/use in the WASDE known then, ${T.n} seasons 2007+ (log-log fit, R² ${T.r2}); bands ±1 sd. Lines: USDA S/U and the market-implied S/U at today's price.</p></div>
        <div class="card"><h2>${Cn}: market-derived ${P.crop_year}/${String(P.crop_year + 1).slice(2)} S/U vs USDA</h2>${cv('gpMktSU', 'tall')}
          <p class="note">Market-derived = the S/U at which the curve gives ${T.contract}'s daily settle. Below USDA → the market prices a tighter balance than USDA.</p></div>
      </div>
      <div class="card"><h2>${Cn}: calendar spreads vs history</h2><div class="tbl" id="gpSpreads"></div><p class="note">Cents. "This time of year" = same pair, same calendar date ±5 days, 19 earlier years; "near expiry" = average of the last 10 sessions of the first leg. FV columns from the report need a private balance and are left out.</p></div>
      <div class="grid g2">
        <div class="card"><h2>${Cn}: ${c === 'corn' ? 'December/December' : 'November/November'} spread by year</h2>${cv('gpDec', 'tall')}<p class="note">Old-crop minus new-crop same-month contract, x-axis = days to the first leg's expiry. Thick black = median of completed years.</p></div>
        <div class="card"><h2>${Cn}: Iowa interior basis vs history</h2>${cv('gpBasis', 'tall')}<p class="note">USDA AgTransport weekly bids (cents/bu vs nearby). Bands: 10–90th and 30–70th percentile of earlier seasons, by day of season.</p></div>
      </div>
      <div class="card"><h2>World corn export availability (PSD, MMT)</h2><div class="tbl" id="gpWC"></div>${cv('gpWCy', 'short')}<p class="note">USDA PSD exports by each country's local marketing year (the report uses a common Sep/Aug year). Line: y/y change in world imports excluding the EU and China.</p></div>
      <div class="card"><h2>World wheat balance (PSD, MMT)</h2><div class="ctrls">${btns('ww', Object.keys(P.world.wheat.years).map(k => [k, k]), Object.keys(P.world.wheat.years).at(-1))}</div><div class="tbl" id="gpWW"></div></div>
      <div class="card"><h2>Brazil exports (Comex Stat, MMT)</h2><div class="grid g2"><div><h3>Corn by month, Sep/Aug season</h3>${cv('gpBRc')}</div><div><h3>Soybeans by month, calendar year</h3>${cv('gpBRs')}</div></div></div>
      <div id="gpSoyCx" class="grid" style="gap:12px"></div>
      ${card('Not replicated (no public data in the desk yet)', `<ul class="read">${P.missing.map(m => `<li>${m}</li>`).join('')}</ul>`)}`;
    stateMap(); history(); revisions(); sdTables(); exportsSec(); weekly(); cot(); curve(); mktSU(); spreads(); decdec(); basis(); world(); brazil(); soyComplex();
  }

  function yieldTable(k) {
    const Y = P.yields[k], s = Y.stats;
    const rows = Y.table.map(r => `<tr><td>${r.my}</td><td>${f1(r.sep)}</td><td>${f1(r.oct)}</td><td>${f1(r.nov)}</td><td>${f1(r.final)}</td>${pctCell(r.oct_sep)}${pctCell(r.final_oct)}</tr>`).join('');
    return card(`USDA ${k === 'corn' ? 'corn' : 'soybean'} yields (bu/ac)`, `<div class="tbl"><table><tr><th></th><th>Sep</th><th>Oct</th><th>Nov</th><th>Final</th><th>Oct vs Sep</th><th>Final vs Oct</th></tr>${rows}
      <tr><td><b>Average</b></td><td></td><td></td><td></td><td></td>${pctCell(s.avg_oct_sep)}${pctCell(s.avg_final_oct)}</tr>
      <tr><td><b>% higher</b></td><td></td><td></td><td></td><td></td><td>${s.pct_up_oct_sep}%</td><td>${s.pct_up_final_oct}%</td></tr>
      <tr><td><b>Avg abs change</b></td><td></td><td></td><td></td><td></td><td>${s.avg_abs_oct_sep}%</td><td>${s.avg_abs_final_oct}%</td></tr></table></div>`,
      'NASS Crop Production national forecasts (Sep/Oct/Nov) and final yield, 2005+. No October report in 2013 or 2025 (government shutdowns).');
  }

  function stateMap() {
    const Y = P.yields[crop], draw = () => {
      const m = Y.maps[+$('#gpMap').value]; const chg = {}, imp = {};
      m.states.forEach(s => { chg[s.st] = s.chg; imp[s.st] = s.impact; });
      $('#gpMapNote').textContent = `US ${m.us_prev} → ${m.us} bu/ac (${m.us - m.us_prev >= 0 ? '+' : ''}${fmt(m.us - m.us_prev, 1)})`;
      $('#gpMapA').innerHTML = tileMap(chg, 0, 'Change in state yield (bu/ac)');
      $('#gpMapB').innerHTML = tileMap(imp, 2, 'State impact on the national yield (bu/ac)');
      const tr = Object.fromEntries(Y.vs_trend.map(r => [r.st, r]));
      $('#gpStates').innerHTML = `<table><tr><th>State</th><th>Harv. acres ('000)</th><th>USDA prev</th><th>USDA latest</th><th>Change</th><th>Impact on US</th><th>Last year</th><th>Trend</th><th>vs trend</th></tr>
        ${m.states.map(s => `<tr><td>${NAMES[s.st] || s.st}</td><td>${f0(s.acres)}</td><td>${f1(s.y_prev)}</td><td>${f1(s.y)}</td><td>${sgn(s.chg, 1)}</td><td>${sgn(s.impact, 2)}</td><td>${f1(s.y_ly)}</td><td>${tr[s.st] && m.year === P.crop_year ? f1(tr[s.st].trend) : '–'}</td><td>${tr[s.st] && m.year === P.crop_year ? sgn(tr[s.st].dev_pct, 1, '%') : '–'}</td></tr>`).join('')}
        <tr><td><b>United States</b></td><td></td><td>${f1(m.us_prev)}</td><td>${f1(m.us)}</td><td>${sgn(m.us - m.us_prev, 1)}</td><td></td><td>${f1(m.us_ly)}</td><td>${tr.US && m.year === P.crop_year ? f1(tr.US.trend) : '–'}</td><td>${tr.US && m.year === P.crop_year ? sgn(tr.US.dev_pct, 1, '%') : '–'}</td></tr></table>`;
    };
    $('#gpMap').onchange = draw; draw();
  }

  function history() {
    const draw = () => {
      const h = P.yields[crop].hist[$('#gpHistSt').value]; const yrs = [...h.years, h.cur_year];
      $('#gpHistNote').textContent = `trend ${h.slope > 0 ? '+' : ''}${h.slope} bu/ac per year; ${h.cur_year} forecast ${h.cur ?? '–'} vs trend ${h.trend.at(-1)}`;
      chart('gpHist', { type: 'line', data: { labels: yrs, datasets: [
        { label: 'NASS yield', data: [...h.y, null], borderColor: '#2c6fbb', borderWidth: 1.6, pointRadius: 0 },
        { label: `${h.cur_year} USDA forecast`, data: [...h.y.map((_, i) => i === h.y.length - 1 ? h.y.at(-1) : null), h.cur], borderColor: '#c0392b', borderWidth: 2.2, pointRadius: 3 },
        { label: 'Trend', data: h.trend, borderColor: '#d68910', borderWidth: 1.4, pointRadius: 0 }] } });
    };
    $('#gpHistSt').onchange = draw; draw();
  }

  function revisions() {
    const R = P.revisions[crop];
    chart('gpRev', { type: 'bar', data: { labels: R.map(r => r.year), datasets: [{ label: 'Oct − Sep (m bu)', data: R.map(r => r.chg), backgroundColor: R.map(r => r.chg >= 0 ? '#1d5f86' : '#c0392b') }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: i => `Sep ${R[i.dataIndex].before} → Oct ${R[i.dataIndex].after}` } } } } });
  }

  const LAB = { area_planted: 'Area planted (m ac)', area_harvested: 'Area harvested (m ac)', yield: 'Yield', beg_stocks: 'Beginning stocks', production: 'Production', imports: 'Imports', supply: 'Total supply',
    feed_residual: 'Feed & residual', ethanol: 'Ethanol', fsi: 'Food, seed & industrial', domestic: 'Total domestic', exports: 'Exports', use: 'Total use', end_stocks: 'Ending stocks', su: 'Stocks/use %', price: 'Season-avg farm price',
    seed: 'Seed', residual: 'Residual', crush: 'Crush', food: 'Food', biofuel: 'Biofuel', food_other: 'Food, feed & other' };
  const BOLD = new Set(['production', 'supply', 'use', 'end_stocks', 'domestic']);
  function sdTables() {
    const order = crop === 'corn' ? ['corn', 'wheat'] : ['soybeans', 'meal', 'oil'];
    $('#gpSD').innerHTML = order.map(k => { const S = P.sd[k]; if (!S) return '';
      const unit = { corn: 'm bu', soybeans: 'm bu', wheat: 'm bu', meal: "'000 short t", oil: 'm lb' }[k];
      const groups = []; S.cols.forEach(c => { const g = groups.at(-1); if (g && g.my === c.my) g.n++; else groups.push({ my: c.my, n: 1 }); });
      const dec = a => ['yield', 'price'].includes(a) ? 2 : a === 'su' ? 1 : ['area_planted', 'area_harvested'].includes(a) ? 1 : 0;
      const rows = S.rows.map(a => `<tr style="${BOLD.has(a) ? 'font-weight:600;background:#f6f8f5' : ''}"><td class="l">${LAB[a] || a}</td>${S.cols.map((c, i) => {
        const v = c.v[a], pv = i > 0 && S.cols[i - 1].my === c.my ? S.cols[i - 1].v[a] : null;
        const ch = pv != null && v != null && Math.abs(v - pv) > 1e-9 ? (v > pv ? 'color:#1f7a3a' : 'color:#b3261e') : '';
        return `<td style="${ch}">${v == null ? '–' : a === 'su' ? fmt(v, 1) + '%' : fmt(v, dec(a))}</td>`; }).join('')}</tr>`).join('');
      return card(`US ${k === 'meal' ? 'soybean meal' : k === 'oil' ? 'soybean oil' : k} balance (${unit})`, `<div class="tbl"><table>
        <tr><th></th>${groups.map(g => `<th colspan="${g.n}" style="text-align:center">${g.my}</th>`).join('')}</tr>
        <tr><th></th>${S.cols.map(c => `<th>${c.label || 'latest'}</th>`).join('')}</tr>${rows}</table></div>`, 'WASDE. Green/red = changed vs the previous report. Your own column can be added later.');
    }).join('');
  }

  function exportsSec() {
    const keys = crop === 'corn' ? ['corn', 'wheat', 'HRW', 'SRW', 'HRS', 'White'] : ['soybeans', 'meal', 'wheat', 'HRW', 'SRW', 'HRS'];
    $('#gpProj').innerHTML = keys.filter(k => P.exports[k]?.proj?.length).map(k => `<div><h3>${k === 'meal' ? 'Soybean meal' : k[0].toUpperCase() + k.slice(1)} ${P.exports[k].my} (${P.exports[k].unit})</h3>${cv('gpP' + k, 'short')}</div>`).join('');
    keys.forEach(k => { const E = P.exports[k]; if (!E?.proj?.length) return;
      const wk = Array.from({ length: 52 }, (_, i) => i + 1), m = a => { const o = Object.fromEntries(a); return wk.map(w => o[w] ?? null); };
      const ds = [{ label: 'High', data: m(E.hi), borderWidth: 0, backgroundColor: 'rgba(240,128,150,.3)', fill: '+1', pointRadius: 0 },
        { label: 'Low', data: m(E.lo), borderWidth: 0, pointRadius: 0, fill: false },
        { label: 'Projected', data: m(E.proj), borderColor: '#2c6fbb', borderWidth: 1.8, pointRadius: 0 }];
      if (E.usda) ds.push({ label: `USDA ${f0(E.usda)}`, data: wk.map(() => E.usda), borderColor: '#e055e0', borderDash: [5, 4], borderWidth: 1.2, pointRadius: 0 });
      chart('gpP' + k, { type: 'line', data: { labels: wk, datasets: ds }, options: { spanGaps: true, plugins: { legend: { labels: { filter: i => !['High', 'Low'].includes(i.text), boxWidth: 10, font: { size: 10 } } } }, scales: { x: { title: { display: true, text: 'week of marketing year', font: { size: 10 } } } } } });
    });
    const yk = crop === 'corn' ? ['corn', 'wheat'] : ['soybeans', 'meal'];
    $('#gpYTD').innerHTML = yk.flatMap(k => ['shipped', 'outstanding', 'commit'].map(f => `<div><h3>${k} · ${f === 'commit' ? 'commitments' : f} (wk ${P.exports[k]?.week})</h3>${cv(`gpY${k}${f}`, 'short')}</div>`)).join('');
    yk.forEach(k => { const E = P.exports[k]; if (!E) return; ['shipped', 'outstanding', 'commit'].forEach(f =>
      chart(`gpY${k}${f}`, { type: 'bar', data: { labels: E.ytd.map(r => r.my), datasets: [{ label: f, data: E.ytd.map(r => r[f]), backgroundColor: E.ytd.map((_, i) => i === E.ytd.length - 1 ? '#c0392b' : '#2f6b3a') }] }, options: { plugins: { legend: { display: false } } } })); });
  }

  function weekly() {
    const W = P.exports[crop]?.weekly; if (!W) return;
    chart('gpWeekly', { type: 'line', data: { labels: W.wk, datasets: [
      { label: P.exports[crop].my, data: W.cur, borderColor: '#2f6b3a', borderWidth: 2, pointRadius: 2 },
      { label: '5-yr avg', data: W.avg5, borderColor: '#7d3c98', borderDash: [4, 3], borderWidth: 1.4, pointRadius: 0 }] } });
  }

  function cot() {
    const ds = ['corn', 'soybeans', 'wheat'].map((k, i) => ({ label: k, data: P.cot[k].date.map((d, j) => ({ x: d, y: P.cot[k].mmt[j] })), borderColor: PAL[i], borderWidth: 1.2, pointRadius: 0 }));
    const labels = P.cot.corn.date;
    chart('gpCot', { type: 'line', data: { labels, datasets: ds.map(d => ({ ...d, data: d.data.map(p => p.y) })) }, options: { scales: { x: { ticks: { callback: function (v) { return String(this.getLabelForValue(v)).slice(0, 4); } } } } } });
  }

  function curve() {
    const T = P.tightness[crop];
    const pts = T.points.filter(p => !p.partial).map(p => ({ x: p.su, y: p.price, my: p.my }));
    const line = (i, lab, colr, w, dash) => ({ type: 'line', label: lab, data: T.curve.map(r => ({ x: r[0], y: r[i] })), borderColor: colr, borderWidth: w, borderDash: dash, pointRadius: 0 });
    const ymax = Math.max(...T.curve.map(r => r[2])), ymin = Math.min(...T.curve.map(r => r[3]));
    const vline = (x, lab, colr) => ({ type: 'line', label: lab, data: [{ x, y: ymin }, { x, y: ymax }], borderColor: colr, borderDash: [5, 4], borderWidth: 1.4, pointRadius: 0 });
    const ds = [line(1, 'Price curve', '#1e8449', 2.4), line(2, '+1 sd', '#82c99a', 1), line(3, '−1 sd', '#82c99a', 1),
      { type: 'scatter', label: 'Seasons', data: pts, backgroundColor: '#2c6fbb', pointRadius: 3 },
      { type: 'line', label: `${T.contract} $${fmt(T.price, 2)}`, data: [{ x: T.curve[0][0], y: T.price }, { x: T.curve.at(-1)[0], y: T.price }], borderColor: '#d4ac0d', borderWidth: 1.6, pointRadius: 0 }];
    if (T.usda_su) ds.push(vline(T.usda_su, `USDA S/U ${T.usda_su}% → $${fmt(T.fv_usda, 2)}`, '#c0392b'));
    if (T.mkt_su) ds.push(vline(T.mkt_su, `Market S/U ${T.mkt_su}%`, '#e67e22'));
    chart('gpCurve', { type: 'scatter', data: { datasets: ds }, options: { interaction: { mode: 'nearest', intersect: true },
      plugins: { tooltip: { callbacks: { label: i => i.raw.my ? `${i.raw.my}: S/U ${i.raw.x}% · $${fmt(i.raw.y, 2)}` : `${i.dataset.label}: ${fmt(i.raw.x, 2)}% · $${fmt(i.raw.y, 2)}` } } },
      scales: { x: { type: 'linear', title: { display: true, text: 'US stocks/use %' } }, y: { title: { display: true, text: '$/bu' } } } } });
  }

  function mktSU() {
    const T = P.tightness[crop];
    const usda = T.usda.map(([d, v]) => ({ x: d, y: v }));
    const labels = T.mkt.map(r => r[0]);
    const step = labels.map(d => { let v = null; usda.forEach(u => { if (u.x <= d) v = u.y; }); return v; });
    chart('gpMktSU', { type: 'line', data: { labels, datasets: [
      { label: 'Market-derived S/U', data: T.mkt.map(r => r[1]), borderColor: '#a93226', borderWidth: 2, pointRadius: 0 },
      { label: 'USDA S/U', data: step, borderColor: '#7f8c8d', borderWidth: 2, stepped: true, pointRadius: 0 }] },
      options: { scales: { y: { ticks: { callback: v => v + '%' } } } } });
  }

  function spreads() {
    const S = P.spreads[crop];
    $('#gpSpreads').innerHTML = `<table><tr><th>Pair</th><th>Current</th><th>Pctile now</th><th colspan="3" style="text-align:center">This time of year</th><th colspan="3" style="text-align:center">Near expiry</th></tr>
      <tr><th></th><th></th><th></th><th>Median</th><th>10%</th><th>90%</th><th>Median</th><th>10%</th><th>90%</th></tr>
      ${S.map(s => `<tr><td>${s.c1.slice(2)} / ${s.c2.slice(2)}</td><td><b>${fmt(s.current, 1)}</b></td><td>${s.pct_rank ?? '–'}</td><td>${f1(s.now_med)}</td><td>${f1(s.now_p10)}</td><td>${f1(s.now_p90)}</td><td>${f1(s.exp_med)}</td><td>${f1(s.exp_p10)}</td><td>${f1(s.exp_p90)}</td></tr>`).join('')}</table>`;
  }

  function decdec() {
    const D = P.decdec[crop], yrs = Object.keys(D.years);
    const ds = yrs.map((y, i) => { const last = i === yrs.length - 1, prev = i === yrs.length - 2;
      return { label: `${y}/${+y + 1}`, data: D.years[y].map(([x, v]) => ({ x, y: v })), borderColor: last ? '#c0392b' : prev ? '#1e8449' : `hsla(${(i * 37) % 360},45%,60%,.55)`, borderWidth: last || prev ? 2.4 : 1, pointRadius: 0 }; });
    ds.push({ label: 'Median', data: D.median.map(([x, v]) => ({ x, y: v })), borderColor: '#000', borderWidth: 2.6, pointRadius: 0 });
    chart('gpDec', { type: 'line', data: { datasets: ds }, options: { parsing: true, interaction: { mode: 'nearest', intersect: false },
      plugins: { legend: { labels: { filter: i => i.datasetIndex >= ds.length - 3, boxWidth: 10, font: { size: 10 } } } },
      scales: { x: { type: 'linear', title: { display: true, text: 'days to first-leg expiry' } }, y: { title: { display: true, text: 'cents' } } } } });
  }

  function basis() {
    const B = P.basis[crop]; if (!B) return;
    const xy = i => B.band.map(r => ({ x: r[0], y: r[i] }));
    chart('gpBasis', { type: 'line', data: { datasets: [
      { label: '90th', data: xy(5), borderWidth: 0, backgroundColor: 'rgba(93,173,226,.25)', fill: '+3', pointRadius: 0 },
      { label: '70th', data: xy(4), borderWidth: 0, backgroundColor: 'rgba(36,113,163,.35)', fill: '+1', pointRadius: 0 },
      { label: '30th', data: xy(2), borderWidth: 0, pointRadius: 0 },
      { label: '10th', data: xy(1), borderWidth: 0, pointRadius: 0 },
      { label: 'Median', data: xy(3), borderColor: '#1b2631', borderWidth: 1.6, pointRadius: 0 },
      { label: `${B.cur_year} (current)`, data: B.cur.map(([x, v]) => ({ x, y: v })), borderColor: '#c0392b', borderWidth: 2.4, pointRadius: 0 }] },
      options: { interaction: { mode: 'nearest', intersect: false }, plugins: { legend: { labels: { filter: i => ['Median', `${B.cur_year} (current)`].includes(i.text), boxWidth: 10 } } },
        scales: { x: { type: 'linear', title: { display: true, text: 'day of season' } }, y: { title: { display: true, text: 'cents/bu' } } } } });
  }

  function world() {
    const W = P.world.corn, n = W.mys.length;
    $('#gpWC').innerHTML = `<table><tr><th></th>${W.mys.map(m => `<th>${m}</th>`).join('')}<th>Δ last vs prior</th></tr>
      ${W.rows.map(r => `<tr><td>${r.name}</td>${r.v.map(v => `<td>${f1(v)}</td>`).join('')}<td>${sgn(r.v[n - 1] - r.v[n - 2], 1)}</td></tr>`).join('')}
      <tr style="font-weight:600"><td>World exports</td>${W.world.map(v => `<td>${f1(v)}</td>`).join('')}<td>${sgn(W.world[n - 1] - W.world[n - 2], 1)}</td></tr></table>`;
    chart('gpWCy', { type: 'line', data: { labels: W.mys, datasets: [{ label: 'World imports ex EU & China, y/y %', data: W.yoy_imports, borderColor: '#2c6fbb', borderWidth: 2, pointRadius: 3 },
      { label: 'Average', data: W.mys.map(() => { const v = W.yoy_imports.filter(x => x != null); return +(v.reduce((a, b) => a + b, 0) / v.length).toFixed(1); }), borderColor: '#c0392b', borderWidth: 1.4, pointRadius: 0 }] } });
    const drawW = my => { const Y = P.world.wheat.years[my], R = P.world.wheat.rows;
      const lab = { 'Area Harvested': 'Area harvested (m ha)', Yield: 'Yield (t/ha)', 'su': 'Stocks/use %' };
      $('#gpWW').innerHTML = `<table><tr><th></th>${Y.map(c => `<th>${c.name}</th>`).join('')}</tr>${R.map(a => `<tr style="${['Production', 'Total Supply', 'Ending Stocks', 'Exports'].includes(a) ? 'font-weight:600;background:#f6f8f5' : ''}"><td class="l">${lab[a] || a}</td>${Y.map(c => `<td>${c.v[a] == null ? '–' : a === 'su' ? fmt(c.v[a], 1) + '%' : fmt(c.v[a], a === 'Yield' ? 2 : 1)}</td>`).join('')}</tr>`).join('')}</table>`; };
    document.querySelectorAll('[data-grp="ww"] button').forEach(b => b.onclick = () => { document.querySelectorAll('[data-grp="ww"] button').forEach(x => x.classList.toggle('on', x === b)); drawW(b.dataset.v); });
    drawW(Object.keys(P.world.wheat.years).at(-1));
  }

  function brazil() {
    const mk = (id, B, labels) => { const ks = Object.keys(B.monthly);
      chart(id, { type: 'line', data: { labels, datasets: ks.map((k, i) => ({ label: `${B.mys[i]} (${fmt(B.totals[k], 1)})`, data: B.monthly[k], borderColor: i === ks.length - 1 ? '#c0392b' : PAL[i + 1], borderWidth: i === ks.length - 1 ? 2.4 : 1.4, pointRadius: 0, borderDash: i === ks.length - 1 ? [5, 3] : [] })) } }); };
    const sep = ['Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug'];
    mk('gpBRc', P.brazil.corn, sep); mk('gpBRs', P.brazil.soybeans, MON);
  }
  // ── Brazil, Argentina and US soybean complex: balances and monthly usage ──
  const MOS = { 1: MON, 4: ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar'], 9: ['Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug'] };
  const SAL = { 'Beginning Stocks': 'Beginning stocks', 'Area Harvested': 'Area harvested (m ha)', Yield: 'Yield (t/ha)', 'Total Supply': 'Total supply', Crush: 'Crush (soybeans)', 'Other domestic': 'Seed, feed & residual',
    'Domestic Consumption': 'Total domestic', 'Industrial Dom. Cons.': 'Industrial (biodiesel)', 'Food Use Dom. Cons.': 'Food use', 'Ending Stocks': 'Ending stocks', su: 'Stocks/use %' };
  const SAB = new Set(['Production', 'Total Supply', 'Total use', 'Ending Stocks']);
  function saTable(B, title) {
    const rows = B.rows.filter(a => B.cols.some(c => c.v[a] != null));
    return `<div><h3>${title}</h3><div class="tbl"><table><tr><th></th>${B.cols.map((c, i) => `<th style="${i === B.cols.length - 1 ? 'background:#fdf3e1' : ''}">${c.my}</th>`).join('')}</tr>
      ${rows.map(a => `<tr style="${SAB.has(a) ? 'font-weight:600;background:#f6f8f5' : ''}"><td class="l">${SAL[a] || a}</td>${B.cols.map(c => `<td>${c.v[a] == null ? '–' : a === 'su' ? fmt(c.v[a], 1) + '%' : fmt(c.v[a], a === 'Yield' ? 2 : 1)}</td>`).join('')}</tr>`).join('')}</table></div></div>`;
  }
  // monthly usage table: months x seasons, each with a cumulative column (like the report's usage blocks)
  function usage(blocks, start, title, dec = 2) {
    const mo = MOS[start];
    const head1 = blocks.map(b => `<th colspan="${b.M.seasons.length * 2}" style="text-align:center;border-left:2px solid #ccc">${b.name}</th>`).join('');
    const head2 = blocks.map(b => b.M.seasons.map((s, j) => `<th style="${j === 0 ? 'border-left:2px solid #ccc' : ''}">${s}</th><th style="color:#2f6b3a">cum</th>`).join('')).join('');
    const cum = v => { let c = 0; return v.map(x => x == null ? null : (c += x)); };
    const C = blocks.map(b => b.M.seasons.map(s => ({ v: b.M.values[s], c: b.stock ? null : cum(b.M.values[s]) })));
    const body = mo.map((m, i) => `<tr><td>${m}</td>${C.map(bl => bl.map((x, j) => `<td style="${j === 0 ? 'border-left:2px solid #ccc' : ''}">${x.v[i] == null ? '' : fmt(x.v[i], dec)}</td><td style="color:#2f6b3a;font-style:italic">${x.c && x.c[i] != null ? fmt(x.c[i], dec) : ''}</td>`).join('')).join('')}</tr>`).join('');
    const tot = `<tr style="font-weight:600"><td>Total</td>${C.map((bl, k) => bl.map((x, j) => `<td style="${j === 0 ? 'border-left:2px solid #ccc' : ''}">${blocks[k].stock ? '' : fmt(x.v.reduce((a, b) => a + (b || 0), 0), dec)}</td><td></td>`).join('')).join('')}</tr>`;
    return `<h3>${title}</h3><div class="tbl"><table style="font-size:11.5px"><tr><th></th>${head1}</tr><tr><th>Month</th>${head2}</tr>${body}${tot}</table></div>`;
  }
  function bandChart(id, M, start, unit) {
    const s = M.seasons, cur = s.at(-1), prev = s.at(-2);
    chart(id, { type: 'line', data: { labels: MOS[start], datasets: [
      { label: 'Max 10', data: M.max10, borderWidth: 0, backgroundColor: 'rgba(160,190,140,.28)', fill: '+1', pointRadius: 0 },
      { label: 'Min 10', data: M.min10, borderWidth: 0, pointRadius: 0, fill: false },
      { label: '10-yr avg', data: M.avg10, borderColor: '#222', borderDash: [2, 3], borderWidth: 1.4, pointRadius: 0 },
      { label: prev, data: M.values[prev], borderColor: '#1f3a5f', borderWidth: 2, pointRadius: 2 },
      { label: cur, data: M.values[cur], borderColor: '#d62020', borderWidth: 2.4, pointRadius: 3 }] },
      options: { plugins: { legend: { labels: { filter: i => i.text !== 'Min 10', boxWidth: 10, font: { size: 10 } } } }, scales: { y: { title: { display: true, text: unit } } } } });
  }
  function soyComplex() {
    const S = P.sa_soy, U = P.us_fo, el = $('#gpSoyCx'); if (!el) return;
    let h = '';
    if (S) {
      const B = S.brazil, A = S.argentina;
      h += card('Brazil soybean complex: balance sheets (USDA PSD, million t)', `<div class="grid">${saTable(B.balance.soybeans, 'Soybeans')}${saTable(B.balance.meal, 'Soybean meal')}${saTable(B.balance.oil, 'Soybean oil')}</div>`,
        'USDA PSD, Brazil local marketing years (soybeans Feb/Jan: 2025/26 = the crop harvested early 2026). Last column = USDA\'s first projection for the next season. ABIOVE and CONAB balances are not open data (ABIOVE monthly crush is members-only).');
      h += card('Brazil soybean complex: monthly exports (million t)', usage([{ name: 'Soybeans', M: B.monthly.exports.soybeans }, { name: 'Soybean meal', M: B.monthly.exports.meal }, { name: 'Soybean oil', M: B.monthly.exports.oil }], 1, 'Exports by calendar year, with cumulative', 2), 'Comex Stat (Brazil Ministry of Development), NCM 1201 / 2304 / 1507. Brazil monthly crush and stocks are not published openly.');
      h += card('Argentina soybean complex: balance sheets (USDA PSD, million t)', `<div class="grid">${saTable(A.balance.soybeans, 'Soybeans')}${saTable(A.balance.meal, 'Soybean meal')}${saTable(A.balance.oil, 'Soybean oil')}</div>`,
        'USDA PSD, Argentina local marketing years (soybeans Apr/Mar).');
      if (A.monthly) {
        const M = A.monthly;
        h += card(`Argentina soybean complex: monthly crush, output and stocks (million t, Apr/Mar)`,
          usage([{ name: 'Soybean crush', M: M.crush }, { name: 'Meal production', M: M.meal_prod }, { name: 'Oil production', M: M.oil_prod }], 4, 'Crush and production', 2)
          + usage([{ name: 'Meal: implied exports + domestic use', M: M.meal_disp }, { name: 'Meal stocks (end of month)', M: M.meal_stocks, stock: true }, { name: 'Oil stocks (end of month)', M: M.oil_stocks, stock: true }], 4, 'Meal disappearance and stocks', 2),
          `${A.source}. Crush to ${A.crush_asof}, stocks to ${A.stocks_asof} (MAGyP surveys stocks at the start of a month; shown as the previous month's ending stocks). Meal = pellets + expellers; trailing-12-month extraction: meal ${A.yields.meal}%, oil ${A.yields.oil}%. Implied disappearance = production + opening − closing stocks (MAGyP does not publish monthly meal exports; domestic use is ~0.25 Mt/month).`);
        h += `<div class="card"><h2>Argentine monthly soymeal picture (million t, Apr/Mar)</h2><div class="grid g3"><div><h3>Monthly soybean crush</h3>${cv('gpArCr')}</div><div><h3>Monthly meal disappearance (≈ exports)</h3>${cv('gpArEx')}</div><div><h3>Monthly meal ending stocks</h3>${cv('gpArSt')}</div></div><p class="note">Band = min/max of the previous 10 seasons; dotted = 10-season average.</p></div>`;
      }
    }
    if (U && U.monthly) {
      const M = U.monthly, keys = Object.keys(M);
      h += `<div class="card"><h2>US soybean crush, meal and oil (NASS Fats &amp; Oils, Sep/Aug)</h2><div class="grid g3">${keys.map(k => `<div><h3>${k.replace(/_/g, ' ')} (${U.units[k]})</h3>${cv('gpUS' + k)}</div>`).join('')}</div>
        ${usage(keys.filter(k => ['crush', 'meal_prod', 'oil_crude_prod'].includes(k)).map(k => ({ name: k.replace(/_/g, ' '), M: M[k] })), 9, 'Monthly production with cumulative', 1)}
        <p class="note">USDA NASS Fats &amp; Oils (QuickStats API), data to ${U.asof}. Trailing-12-month yields: meal ${U.meal_yield_lb_bu ?? '–'} lb/bu, oil ${U.oil_yield_lb_bu ?? '–'} lb/bu. Series: ${Object.values(U.chosen).map(c => c.desc).join('; ')}.</p></div>`;
    } else if (U && U.found) h += card('US soybean crush (NASS Fats & Oils)', `<p class="note">Series found but not matched yet: ${U.found.slice(0, 20).join('; ')}</p>`);
    el.innerHTML = h;
    if (S?.argentina?.monthly) { const M = S.argentina.monthly; bandChart('gpArCr', M.crush, 4, 'Mt'); bandChart('gpArEx', M.meal_disp, 4, 'Mt'); bandChart('gpArSt', M.meal_stocks, 4, 'Mt'); }
    if (U?.monthly) Object.keys(U.monthly).forEach(k => bandChart('gpUS' + k, U.monthly[k], 9, U.units[k]));
  }
  return { mount };
})();
