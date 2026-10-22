// Lean hogs section.
const Hogs = (() => {
  const L = 'data/livestock/derived/';
  let built = false, tab = 'h-primer', H, SDH, CV, EX, F, CB, BIAS;
  function shell() {
    $('#hogs').innerHTML = `<nav class="tabs" id="hTabs"><button data-t="h-primer" class="on">1 · Primer</button><button data-t="h-geo">Where it's produced, trade &amp; weather</button><button data-t="h-sd">2 · Supply &amp; demand</button>
      <button data-t="h-flows">3 · Futures, options &amp; COT</button><button data-t="h-outlook">4 · Outlook</button></nav><main><div id="hBody"></div></main>`;
    $$('#hTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; $$('#hTabs button').forEach(x => x.classList.toggle('on', x === b)); render(); });
  }
  async function show() {
    if (!built) {
      shell();
      [H, SDH, CV, EX, F, CB, BIAS] = await Promise.all([getJSON(L + 'hogs.json'), getJSON(L + 'hogs_sd.json').catch(() => null), getJSON(L + 'hogs_convergence.json').catch(() => null),
        getJSON(L + 'hogs_expiry.json').catch(() => null), getJSON(L + 'flows.json').catch(() => null), getJSON('data/derived/cot_backtest.json').catch(() => null), getJSON('data/derived/convergence_bias.json').catch(() => null)]);
      built = true;
    }
    const h = location.hash.slice(1); if (/^h-/.test(h)) { tab = h; $$('#hTabs button').forEach(x => x.classList.toggle('on', x.dataset.t === tab)); }
    render();
  }
  function render() { history.replaceState(null, '', '#' + tab); ({ 'h-primer': primer, 'h-geo': () => Geo.mount($('#hBody'), 'pork'), 'h-sd': sd, 'h-flows': flows, 'h-outlook': outlook })[tab](); }
  const body = html => { $('#hBody').innerHTML = html; };

  function primer() {
    const ld = H.last_days || [];
    body(Specs.slot('hogs') + `<div class="grid g2">
      <div class="card"><h2>Lean hog futures</h2><div class="tbl"><table>
        <tr><td>Contract</td><td class="l">CME Lean Hogs (HE)</td></tr><tr><td>Size</td><td class="l">40,000 lb carcass weight</td></tr>
        <tr><td>Quote / tick</td><td class="l">¢/lb; 0.025¢ = $10</td></tr><tr><td>Months</td><td class="l">Feb, Apr, May, Jun, Jul, Aug, Oct, Dec</td></tr>
        <tr><td>Settlement</td><td class="l">Cash-settled to the CME Lean Hog Index on the last trading day (10th business day of the contract month)</td></tr></table></div>
        <h3>The CME Lean Hog Index</h3><p>A two-day weighted average of producer-sold barrow and gilt carcass prices from USDA's daily prior-day slaughtered swine report (LM_HG201). Only three purchase types count: <b>negotiated</b>, <b>swine or pork market formula</b> and <b>negotiated formula</b>. Each is weighted by head × average carcass weight. Packer-owned hogs and other formula/contract arrangements are excluded. The desk rebuilds the index from USDA data and matches CME's published values to the cent, typically a day before CME posts it.</p>
        <h3>Why futures and cash differ</h3><p>Hog prices are strongly seasonal: few hogs and peak grilling demand lift summer prices, heavy fall marketings depress them. The futures curve carries that seasonality, so deferred contracts trade far from today's cash. At expiry the expiring contract is pinned to the index by cash settlement.</p></div>
      <div class="card"><h2>Index calculator: last two slaughter days</h2><p class="note">Edit the USDA numbers to see how each purchase type moves the index. Confidential values (USDA withholds a price when too few packers trade) are left out, as in the official calculation.</p>
        <div class="tbl"><table id="hIdx"></table></div><div class="bigout"><div><div class="note">Two-day index</div><div class="v" id="hIdxV"></div></div></div></div></div>
      <div class="grid g2" style="margin-top:12px">
      <div class="card"><h2>How each supply-and-demand line moves price</h2><div class="tbl"><table><tr><th class="l">Line</th><th class="l">Mechanism</th><th class="l">Watch</th></tr>
        <tr><td class="l">Breeding herd and farrowings</td><td class="l">Sets supply 6–10 months out; pigs per litter has trended up ~1%/yr.</td><td class="l">Quarterly Hogs and Pigs</td></tr>
        <tr><td class="l">Market hogs by weight</td><td class="l">The pipeline: ≥180 lb reach slaughter within a month, 120–179 next month, 50–119 in two to three, &lt;50 in three to five.</td><td class="l">Hogs and Pigs weight groups</td></tr>
        <tr><td class="l">Slaughter pace and weights</td><td class="l">Heavy carcass weights mean producers are behind in marketings, a bearish backlog. Falling weights signal current supply.</td><td class="l">Daily slaughter, LM_HG201 weights</td></tr>
        <tr><td class="l">Pork cutout and packer margin</td><td class="l">Packers bid hogs off the cutout value. A wide cutout-minus-index margin gives packers room to bid up; negative margins push cash lower.</td><td class="l">LM_PK602 cutout</td></tr>
        <tr><td class="l">Exports</td><td class="l">~25% of production; Mexico, China, Japan, Korea. Trade policy and the peso move demand.</td><td class="l">Export sales, Census trade</td></tr>
        <tr><td class="l">Cold storage</td><td class="l">Frozen pork stocks (bellies, hams) buffer seasonal swings; high stocks cap rallies.</td><td class="l">NASS Cold Storage</td></tr></table></div></div>
      <div class="card"><h2>Linkages</h2><ul class="read">
        <li><b>Corn and soybean meal:</b> ~60% of production cost; the hog/corn ratio drives expansion.</li>
        <li><b>Cattle and chicken:</b> competing proteins; record beef prices shift retail and food-service demand toward pork.</li>
        <li><b>Pork cutout futures and bellies:</b> the bacon index tracks the most volatile primal.</li>
        <li><b>Disease:</b> ASF/PRRS abroad lifts US exports; a US outbreak would shut export markets.</li>
        <li><b>Mexico:</b> the largest export buyer; the peso and tariffs matter.</li></ul>
        <h3>Seasonality</h3><p>Cash typically bottoms in Nov–Dec on peak marketings and peaks in Jun–Jul. The curve prices that each year; the question is whether this year's supply pipeline makes the curve too steep or too flat.</p></div></div>`);
    const rows = []; ld.forEach((d, di) => d.types.forEach((t, ti) => rows.push({ di, ti, d: d.date, ...t })));
    const draw = () => { let w = 0, v = 0; rows.forEach(r => { if (r.head && r.weight && r.price) { w += r.head * r.weight; v += r.head * r.weight * r.price; } }); $('#hIdxV').textContent = w ? '$' + (v / w).toFixed(2) : '–'; };
    $('#hIdx').innerHTML = `<tr><th>Slaughter day</th><th class="l">Purchase type</th><th>Head</th><th>Carcass wt</th><th>Net price</th></tr>` + rows.map((r, i) =>
      `<tr><td>${r.d}</td><td class="l">${r.type}</td><td><input data-i="${i}" data-k="head" value="${r.head ?? ''}" size="7"></td><td><input data-i="${i}" data-k="weight" value="${r.weight ?? ''}" size="6"></td><td><input data-i="${i}" data-k="price" value="${r.price ?? ''}" size="6"></td></tr>`).join('');
    $$('#hIdx input').forEach(x => x.oninput = () => { rows[x.dataset.i][x.dataset.k] = parseFloat(x.value) || null; draw(); }); draw();
  }

  function sd() {
    const cur = SDH?.current, bt = SDH?.slaughter_backtest?.['2015-2026'];
    body(`<div class="grid g2">
      <div class="card"><h2>Lean Hog Index (desk rebuild) and pork cutout</h2><div class="chart"><canvas id="hIdxC"></canvas></div><p class="note">Index through ${H.index.date.at(-1)}; CME publishes with a two-business-day lag. Cutout = USDA LM_PK602 carcass value.</p></div>
      <div class="card"><h2>Packer margin proxy: cutout − index ($/cwt)</h2><div class="chart"><canvas id="hMgn"></canvas></div><p class="note">Ignores by-product value and processing costs; read the level against its own history.</p></div>
      <div class="card"><h2>Hogs and Pigs: market hogs by weight (${cur?.report ?? '–'})</h2><div class="tbl"><table>
        <tr><th>Weight group</th><th>Head</th><th>y/y</th><th>Reaches slaughter</th></tr>
        ${cur ? Object.entries(cur.inventory).map(([g, v]) => `<tr><td>${g.toLowerCase()}</td><td>${fmt(v / 1e6, 2)}m</td><td>${sgn(cur.yoy_pct[g], 1, '%')}</td><td>${{ 'GE 180 LBS': 'this month', '120 TO 179 LBS': '+1 month', '50 TO 119 LBS': '+2 months', 'LT 50 LBS': '+3–4 months' }[g]}</td></tr>`).join('') : ''}</table></div>
        <h3>Slaughter forecast from the pipeline</h3><div class="tbl"><table><tr><th>Month</th><th>Forecast head/day</th><th>Actual</th></tr>
        ${cur ? cur.months.map(m => `<tr><td>${m.target}</td><td>${fmt(m.forecast_per_day, 0)}</td><td>${m.actual_per_day ? fmt(m.actual_per_day, 0) : '–'}</td></tr>`).join('') : ''}</table></div>
        ${bt ? `<p class="note">Backtest on first-print reports (2015–26): mean abs error ${Object.values(bt).map(x => x.mape_hp).join('/')}% for 0–4 months ahead vs ${Object.values(bt).map(x => x.mape_naive).join('/')}% for the pre-report slaughter trend; the pipeline wins ${Object.values(bt).map(x => Math.round(100 * x.hp_beats_naive)).join('/')}% of the time. A modest edge.</p>` : ''}</div>
      <div class="card"><h2>Frozen pork in cold storage (mil lb)</h2><div class="chart"><canvas id="hCold"></canvas></div></div></div>`);
    const n = 750, d = H.index.date.slice(-n), co = H.cutout;
    const cmap = Object.fromEntries(co.date.map((x, i) => [x, co.carcass[i]]));
    chart('hIdxC', { type: 'line', data: { labels: d, datasets: [{ label: 'Lean Hog Index', data: H.index.index.slice(-n), borderColor: PAL[0], pointRadius: 0, borderWidth: 1.6 },
      { label: 'Pork cutout', data: d.map(x => cmap[x] ?? null), borderColor: PAL[1], pointRadius: 0, borderWidth: 1.2, spanGaps: true }] } });
    chart('hMgn', { type: 'line', data: { labels: co.date.slice(-n), datasets: [{ label: 'cutout − index', data: co.margin.slice(-n), borderColor: PAL[2], pointRadius: 0, borderWidth: 1.2, spanGaps: true }] } });
    if (H.pork_stocks) { const s = seasonal(H.pork_stocks.month, H.pork_stocks.mil_lb); chart('hCold', { type: 'line', data: { labels: MON, datasets: seasonalDatasets(s) }, options: { plugins: { legend: legendNoMin } } }); }
  }

  function flows() {
    const c = F?.cot?.HE; if (!c) { body('<div class="card"><p class="note">Flows data not available yet.</p></div>'); return; }
    const sm = c.summary, cv = H.curve;
    body(`<div id="hCotDesk" style="margin-bottom:12px"></div><div class="card"><h2>Lean hogs positioning (secondary)</h2><div class="tbl"><table><tr><th>Report</th><th>Open int.</th><th>MM net</th><th>w/w</th><th>% OI</th><th>Pctl all</th><th>Pctl 3y</th><th>Prod/merch</th><th>Swap</th></tr>
      <tr><td>${sm.date}</td><td>${fmt(sm.oi, 0)}</td><td>${sgn(sm.mm_net, 0)}</td><td>${sgn(sm.mm_net_wow, 0)}</td><td>${fmt(sm.mm_net_pct_oi, 1)}%</td><td>${fmt(sm.mm_net_percentile_all, 0)}</td><td>${fmt(sm.mm_net_percentile_3y, 0)}</td><td>${sgn(sm.pm_net, 0)}</td><td>${sgn(sm.sw_net, 0)}</td></tr></table></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h3>Futures curve vs cash index (${cv?.trade_date}, index ${cv?.index_date} $${fmt(cv?.index)})</h3><div class="chart"><canvas id="hCurve"></canvas></div><p class="note">Bars: each contract minus today's index. The expiring contract converges to the index; deferred months carry the seasonal path.</p></div>
        <div class="card"><h3>Price (continuous front month)</h3><div class="chart"><canvas id="hPx"></canvas></div></div>
        <div class="card"><h3>Managed money vs producer/merchant net</h3><div class="chart"><canvas id="hCot"></canvas></div></div>
        <div class="card"><h3 id="hOiT">Open interest by month</h3><div class="chart"><canvas id="hOi"></canvas></div></div></div>
      <div class="card" style="margin-top:12px"><h2>Options open interest by strike</h2><div class="ctrls" id="hOptM"></div><div class="chart tall"><canvas id="hOpt"></canvas></div></div>`);
    if (cv) chart('hCurve', { type: 'bar', data: { labels: cv.month, datasets: [{ type: 'line', label: 'settle', data: cv.settle, borderColor: PAL[0], yAxisID: 'y', pointRadius: 2 },
      { label: 'vs index', data: cv.vs_index, backgroundColor: cv.vs_index.map(v => v >= 0 ? 'rgba(31,122,58,.5)' : 'rgba(179,38,30,.5)'), yAxisID: 'y1' }] },
      options: { scales: { y1: { position: 'right', grid: { display: false } } } } });
    const px = F.prices.HE; if (px) chart('hPx', { type: 'line', data: { labels: px.date.slice(-750), datasets: [{ label: 'Lean hogs ¢/lb', data: px.c1.slice(-750), borderColor: PAL[0], pointRadius: 0, borderWidth: 1.3 }] } });
    const s = c.series, n = 260;
    chart('hCot', { type: 'line', data: { labels: s.date.slice(-n), datasets: [{ label: 'Managed money net', data: s.mm_net.slice(-n), borderColor: PAL[1], pointRadius: 0, borderWidth: 2 },
      { label: 'Producer/merchant net', data: s.pm_net.slice(-n), borderColor: PAL[2], pointRadius: 0 }, { label: 'Swap net', data: s.sw_net.slice(-n), borderColor: '#999', pointRadius: 0 }] } });
    const oi = F.oi.HE; if (oi) { $('#hOiT').textContent = `Open interest by month · ${oi.date}`; chart('hOi', { type: 'bar', data: { labels: oi.month, datasets: [{ label: 'Open interest', data: oi.oi, backgroundColor: 'rgba(47,107,58,.55)', yAxisID: 'y' }, { label: 'Change', data: oi.oi_change, backgroundColor: oi.oi_change.map(v => v >= 0 ? '#1f7a3a' : '#b3261e'), yAxisID: 'y1' }] }, options: { scales: { y1: { position: 'right', grid: { display: false } } } } }); }
    const o = F.options?.HE; if (o) { const ms = Object.keys(o.months); let om = ms[Math.min(1, ms.length - 1)];
      const draw = () => { $('#hOptM').innerHTML = ms.map(m => `<button class="btn ${m === om ? 'on' : ''}" data-m="${m}">${m}</button>`).join(' ') + ` <span class="note">${o.date} · put/call OI ${o.months[om].put_call_oi ?? '–'}</span>`;
        $$('#hOptM button').forEach(b => b.onclick = () => { om = b.dataset.m; draw(); }); const x = o.months[om];
        chart('hOpt', { type: 'bar', data: { labels: x.strike, datasets: [{ label: 'Call OI', data: x.call_oi, backgroundColor: 'rgba(31,122,58,.7)' }, { label: 'Put OI', data: x.put_oi.map(v => -v), backgroundColor: 'rgba(179,38,30,.7)' }] },
          options: { indexAxis: 'y', scales: { x: { ticks: { callback: v => Math.abs(v) } } }, plugins: { tooltip: { callbacks: { label: q => `${q.dataset.label}: ${Math.abs(q.raw)}` } } } } }); }; draw(); }
    CotDesk.mount($('#hCotDesk'), ['HE']);
  }

  function outlook() {
    const cv = H.curve, cur = SDH?.current, sm = F?.cot?.HE?.summary, co = H.cutout, Lr = [];
    if (cv) Lr.push(`<b>Cash vs curve:</b> index $${fmt(cv.index)} (${cv.index_date}); ${cv.month.slice(0, 4).map((m, i) => `${m} ${sgn(cv.vs_index[i], 2)}`).join(', ')} vs cash. The market prices the seasonal path; the expiring contract is pinned to the index.`);
    const lastM = co.margin.filter(v => v != null).at(-1); if (lastM != null) Lr.push(`<b>Packer margin proxy:</b> cutout − index ${sgn(lastM, 2)} $/cwt (latest).`);
    if (cur) Lr.push(`<b>Supply pipeline (${cur.report} Hogs and Pigs):</b> ${Object.entries(cur.yoy_pct).map(([g, v]) => `${g.toLowerCase()} ${sgn(v, 1, '%')}`).join(', ')} y/y.`);
    if (sm) Lr.push(`<b>Positioning (secondary):</b> managed money ${sm.mm_net >= 0 ? 'long' : 'short'} ${fmt(Math.abs(sm.mm_net), 0)} (${fmt(sm.mm_net_percentile_3y, 0)} pctl 3y).`);
    const t = CV?.tests, e = EX?.tests;
    const row = (n, x) => x ? `<tr><td>${n}</td><td>${fmt(x.mae_model ?? x.mae_model, 2)}</td><td>${fmt(x.mae_futures_post ?? x.mae_futures, 2)}</td><td>${fmt(x.gap_vs_convergence_corr, 2)}</td></tr>` : '';
    const b = BIAS?.HE;
    body(`<div id="hogsPlaybook" data-playbook="data/livestock/derived/playbook_hogs.json" style="margin-bottom:12px"></div><div id="hTech" style="margin-bottom:12px"></div><div class="grid g2"><div class="card"><h2>Lean hogs desk readout</h2><ul class="read">${Lr.map(x => `<li>${x}</li>`).join('')}</ul><p class="note">What the numbers say, not a trade recommendation.</p></div>
      <div class="card"><h2>What the models have been tested to do</h2>
        <h3>Convergence: forecasting the final Lean Hog Index ($/cwt mean abs error)</h3>
        <div class="tbl"><table><tr><th>Model (origin)</th><th>Model</th><th>Futures</th><th>Gap→convergence corr</th></tr>
          ${t ? row('Cash + seasonal (after each Hogs and Pigs)', t['cash+seasonal']) + row('+ supply surprise', t['cash+seasonal+supply_delta']) + row('Year-ago + supply + cash', t['supply+cash']) : ''}
          ${e ? row('Daily, last 30 bdays: cash + seasonal', e['cash+seasonal']) + row('Daily: + momentum, margin, slaughter, weights', e['all']) : ''}</table></div>
        <p class="note">Futures beat every fundamental model at every horizon, and the best-fit blend weight on the models is zero: the market prices USDA hog data as it is published. The supply pipeline still forecasts slaughter better than trend (S&amp;D tab), and the index rebuild gives the cash number a day before CME posts it.</p>
        ${b && b.h20 ? `<h3>Futures vs their own final settlement</h3><p>From 20 business days out ${sgn(b.h20.mean_pct, 2, '%')} (${Math.round(100 * b.h20.up_share)}% up), from 60 ${sgn(b.h60.mean_pct, 2, '%')}: no reliable bias.</p>` : ''}
      </div></div>`);
    Playbook.mount($('#hogsPlaybook')); Tech.mount($('#hTech'), ['HE']);
  }
  return { show };
})();
