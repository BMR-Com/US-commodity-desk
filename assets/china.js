// Cotton > China: crop progress and estimates (China Cotton Association surveys), cotton and cotton-yarn imports
// (China customs, UN Comtrade), domestic prices in ¢/lb vs ICE, Cotlook A landed and the Xinjiang target price.
// Data: data/china/cotton.json (models/china_cotton.py).
const ChinaCotton = (() => {
  let D = null, progKey = 'xinjiang_pick', impKey = 'yarn';
  const md = s => String(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  const kpi = (l, v, s2) => `<div class="card kpi"><div class="lbl">${l}</div><div class="val">${v}</div><div class="sub">${s2}</div></div>`;
  const pct = (v, d = 1) => v == null ? '–' : sgn(v, d, '%');
  const dayLabel = d => { const t = new Date(Date.UTC(2001, 8, 1) + d * 864e5); return `${MON[t.getUTCMonth()]} ${t.getUTCDate()}`; };

  async function mount(el) {
    el.innerHTML = '<div class="card"><p class="note">Loading China cotton…</p></div>';
    D = await getJSON('data/china/cotton.json').catch(() => null);
    if (!D || !D.brief) {   // a failed build never overwrites cotton.json, but fall back to the last dated copy just in case
      const ix = await getJSON('data/china/history/index.json').catch(() => null);
      if (ix?.latest) D = await getJSON('data/china/history/' + ix.latest).catch(() => null);
    }
    if (!D) { el.innerHTML = '<div class="card"><p class="note">China cotton data not built yet.</p></div>'; return; }
    const E = D.estimates || {}, P = D.progress || {}, I = D.imports || {}, X = D.prices || {}, L = X.latest || {};
    const xj = P.latest?.xinjiang_pick, ya = I.yarn, co = I.cotton;
    el.innerHTML = `
      <div class="card"><h2>China cotton brief</h2>
        ${D.brief.map(b => `<p><b>${b.h}.</b> ${md(b.t)}</p>`).join('')}
        <p class="note">Updated ${D.generated}. Sources: China Cotton Association surveys and price indices (${a(D.sources.cca, 'china-cotton.org')}), China customs monthly bulletin (${a(D.sources.gacc, 'GACC')}),
        UN Comtrade (origins), Zhengzhou CF/CY and ICE from TradingView, USDA PSD. Rule-based read; research use only.</p></div>
      <div class="grid g4" style="margin-top:12px">
        ${kpi('CCA crop estimate', E.latest ? `${fmt(E.latest.prod_kt / 1000, 2)} mt` : '–', E.latest ? `${E.latest.survey} survey · last season ${fmt((E.last_year_final_kt || 0) / 1000, 2)} mt · projected final ${E.projection ? fmt(E.projection.kt / 1000, 2) : '–'}` : '')}
        ${kpi('Xinjiang picking', xj ? `${fmt(xj.pct, 1)}%` : '–', xj ? `at ${xj.obs} · last year ${fmt(xj.last_year, 1)}% · avg ${fmt(xj.avg5, 1)}%` : '')}
        ${kpi('Cotton yarn imports YTD', ya ? `${fmt(ya.ytd_kt[ya.year], 0)} kt` : '–', ya ? `Jan–${MON[ya.last_month - 1]} ${ya.year}: ${pct(ya.ytd_yoy_pct)} y/y · ${pct(ya.ytd_vs_avg5_pct)} vs 5-yr avg` : '')}
        ${kpi('CCIndex 3128B', L.cc ? `${fmt(L.cc_clb, 1)}¢/lb` : '–', L.cc ? `${fmt(L.cc, 0)} yuan/t · ${sgn(L.cc_vs_target, 0)} vs 18,600 target · ${sgn(L.imp_margin_1pct, 0)} vs imports (1% duty)` : '')}
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Picking and selling progress by season</h2><div class="ctrls" id="cnProgSel"></div><div class="chart"><canvas id="cCnProg"></canvas></div>
          <p class="note" id="cnProgNote"></p></div>
        <div class="card"><h2>CCA crop estimate by survey (mt)</h2><div class="chart"><canvas id="cCnEst"></canvas></div>
          <p class="note">China Cotton Association monthly farm surveys (Jul–Nov). Bold line: this season. Dots at December: the association's final figure where published.</p></div>
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Imports by month (China customs, thousand t)</h2><div class="ctrls" id="cnImpSel"></div><div class="chart"><canvas id="cCnImp"></canvas></div>
          <p class="note" id="cnImpNote"></p></div>
        <div class="card"><h2>Year to date by year (thousand t)</h2><div class="chart"><canvas id="cCnYtd"></canvas></div>
          <p class="note" id="cnYtdNote"></p></div>
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Cumulative imports (thousand t)</h2><div class="ctrls" id="cnCumSel"></div><div class="chart"><canvas id="cCnCum"></canvas></div>
          <p class="note" id="cnCumNote"></p></div>
        <div class="card"><h2>USDA check: marketing-year imports and mill use</h2><div class="tbl" id="cnUsda"></div><p class="note" id="cnUsdaNote"></p></div>
      </div>
      <div class="card" style="margin-top:12px" id="cnPolyCard"><h2>Cotton vs polyester in China (weekly)</h2><div class="chart"><canvas id="cCnPoly"></canvas></div><p class="note" id="cnPolyNote"></p></div>
      <div class="card" style="margin-top:12px"><h2>Demand pulled into the countries that sell China yarn</h2><div class="tbl" id="cnOrgD"></div><p class="note" id="cnOrgDNote"></p></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>China vs world prices (¢/lb, weekly)</h2><div class="ctrls" id="cnPxSel"></div><div class="chart"><canvas id="cCnPx"></canvas></div>
          <p class="note">CCIndex 3128B (spot, delivered to mill) and Zhengzhou cotton front month converted at USD/CNY; both include 9% VAT, shown ex-VAT with the toggle. Target price: 18,600 yuan/t, Xinjiang, 2026–28.</p></div>
        <div class="card"><h2>Import margin, target-price gap and spinning margin (yuan/t)</h2><div class="chart"><canvas id="cCnMg"></canvas></div>
          <p class="note">Import margin = CCIndex 3128B minus Cotlook A landed in China (1% in-quota duty and sliding-scale duty, with VAT and port costs, as published by the CCA). Target-price gap = CCIndex 3128B minus 18,600 (below zero: Xinjiang growers receive the difference as subsidy). Spinning margin proxy = Zhengzhou yarn (CY) minus cotton (CF).</p></div>
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Crop estimates by source (thousand t)</h2><div class="tbl" id="cnEstTbl"></div>
          <p class="note">September survey and last survey: China Cotton Association. CCA final: the association's published final / balance-sheet production. NBS: National Bureau of Statistics. USDA: PSD (480-lb bales converted). Agencies differ in level; compare revisions.</p></div>
        <div class="card"><h2>Where China's yarn comes from (HS 5205, share %)</h2><div class="tbl" id="cnOrg"></div>
          <p class="note">UN Comtrade (latest year China has reported). Sept 2026 per trade press: Vietnam 46%, India 16%, Pakistan 12%, Uzbekistan 8.5%.</p></div>
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>China grain and fibre imports, year to date (customs, thousand t)</h2><div class="tbl" id="cnGr"></div></div>
        <div class="card"><h2>Seed-cotton price paid to farmers (yuan/kg, CCA surveys)</h2><div class="chart"><canvas id="cCnSeed"></canvas></div></div>
      </div>`;
    for (const f of [progress, estimates, imports, cumulative, usdaCheck, originDemand, polyester, prices, tables]) { try { f(); } catch (e) { console.error('china', f.name, e); } }
  }
  const a = (u, l) => `<a href="${u}" target="_blank" rel="noopener">${l} ↗</a>`;

  function progress() {
    const S = D.progress?.series || {};
    const keys = [['xinjiang_pick', 'Xinjiang picking'], ['xinjiang_sell', 'Xinjiang selling'], ['national_pick', 'National picking'], ['national_sell', 'National selling']].filter(k => S[k[0]]);
    const draw = () => {
      $('#cnProgSel').innerHTML = keys.map(([k, l]) => `<button class="btn ${k === progKey ? 'on' : ''}" data-k="${k}">${l}</button>`).join(' ');
      $$('#cnProgSel button').forEach(b => b.onclick = () => { progKey = b.dataset.k; draw(); });
      const ser = S[progKey] || {}; const yrs = Object.keys(ser).map(Number).sort().filter(y => y >= Math.max(...Object.keys(ser).map(Number)) - 6);
      const cy = yrs.at(-1);
      chart('cCnProg', { type: 'line', data: { datasets: yrs.map((y, i) => ({ label: String(y), data: ser[y].map(p => ({ x: p[0], y: p[1] })),
        borderColor: y === cy ? '#c0392b' : y === cy - 1 ? '#2c6fbb' : PAL[(i + 2) % PAL.length], borderWidth: y === cy ? 2.6 : 1.2, pointRadius: y === cy ? 4 : 2, tension: .2 })) },
        options: { scales: { x: { type: 'linear', min: 0, max: 120, ticks: { callback: v => dayLabel(v) } }, y: { min: 0, max: 100, title: { display: true, text: '% of crop' } } },
          plugins: { tooltip: { callbacks: { title: it => dayLabel(it[0].parsed.x) } } } } });
      const z = D.progress.latest?.[progKey];
      $('#cnProgNote').innerHTML = z ? `${z.season}: ${fmt(z.pct, 1)}% at ${z.obs}; same date last year ${fmt(z.last_year, 1)}%, average of ${z.n_avg} earlier seasons ${fmt(z.avg5, 1)}% (interpolated between survey dates). China Cotton Association farm surveys (Xinjiang mid-month, national month-end).` : '';
    };
    if (keys.length) draw();
  }

  function estimates() {
    const E = D.estimates; if (!E) return;
    const yrs = Object.keys(E.paths).map(Number).sort().slice(-6); const cy = yrs.at(-1);
    const mx = s => { const [y, m] = s.split('-').map(Number); return m + (y - 0) * 0; };
    chart('cCnEst', { type: 'line', data: { datasets: [
      ...yrs.map((y, i) => ({ label: String(y), data: E.paths[y].filter(p => +p[0].slice(0, 4) === y && +p[0].slice(5, 7) >= 6).map(p => ({ x: mx(p[0]), y: p[1] / 1000 })),
        borderColor: y === cy ? '#c0392b' : y === cy - 1 ? '#2c6fbb' : PAL[(i + 2) % PAL.length], borderWidth: y === cy ? 2.6 : 1.2, pointRadius: 3 })),
      { label: 'CCA final', type: 'scatter', data: yrs.filter(y => E.finals?.[y] && y < cy).map(y => ({ x: 12, y: E.finals[y] / 1000 })), backgroundColor: '#333', pointRadius: 4 }] },
      options: { scales: { x: { type: 'linear', min: 6, max: 12.4, ticks: { stepSize: 1, callback: v => MON[v - 1] || '' } }, y: { title: { display: true, text: 'million t' } } } } });
  }

  function imports() {
    const I = D.imports; if (!I) return;
    const keys = [['yarn', 'Cotton yarn'], ['cotton', 'Raw cotton'], ['fibre', 'Cotton + yarn (lint eq.)']].filter(k => I[k[0]]);
    const draw = () => {
      $('#cnImpSel').innerHTML = keys.map(([k, l]) => `<button class="btn ${k === impKey ? 'on' : ''}" data-k="${k}">${l}</button>`).join(' ');
      $$('#cnImpSel button').forEach(b => b.onclick = () => { impKey = b.dataset.k; draw(); });
      const x = I[impKey]; const yrs = Object.keys(x.monthly_kt).map(Number).sort(); const cy = yrs.at(-1);
      chart('cCnImp', { type: 'line', data: { labels: MON, datasets: yrs.map((y, i) => ({ label: String(y), data: x.monthly_kt[y], spanGaps: false,
        borderColor: y === cy ? '#c0392b' : y === cy - 1 ? '#2c6fbb' : PAL[(i + 2) % PAL.length], borderWidth: y === cy ? 2.6 : 1.1, pointRadius: y === cy ? 3 : 0 })) },
        options: { scales: { y: { min: 0, title: { display: true, text: 'thousand t' } } } } });
      $('#cnImpNote').innerHTML = `Jan–${MON[x.last_month - 1]} ${x.year}: ${fmt(x.ytd_kt[x.year], 0)} kt (${pct(x.ytd_yoy_pct)} y/y; 5-yr avg ${fmt(x.avg5_kt, 0)} kt). Customs publishes quantities in 10,000 t, so single months are ±10 kt; Jan–Feb are often released together.
        ${impKey === 'yarn' ? 'Customs "cotton yarn" covers pure and blended yarn (HS 5204–5207).' : impKey === 'fibre' ? `Raw cotton plus yarn counted as lint (yarn ×${I.combined?.factor || 1.1}).` : ''}`;
      const ys = Object.keys(x.ytd_kt).map(Number).sort();
      chart('cCnYtd', { type: 'bar', data: { labels: ys, datasets: [
        { label: `Jan–${MON[x.last_month - 1]}`, data: ys.map(y => x.ytd_kt[y]), backgroundColor: ys.map(y => y === cy ? '#c0392b' : '#9fb8a5') },
        { label: 'Full year', data: ys.map(y => x.full_kt[y] ?? null), backgroundColor: '#d9d9d9' }] }, options: { scales: { y: { title: { display: true, text: 'thousand t' } } } } });
      const cb = I.combined?.by_year || {};
      $('#cnYtdNote').innerHTML = Object.keys(cb).length ? `Cotton + yarn as lint (yarn ×${I.combined.factor}), Jan–${MON[I.combined.through_month - 1]}: ${Object.keys(cb).sort().map(y => `${y} ${fmt(cb[y].total, 0)} kt`).join(' · ')}.` : '';
    };
    if (keys.length) draw();
  }

  let cumKey = 'cotton', cumBasis = 'my';
  function cumulative() {
    const C = D.imports?.cumulative; if (!C) return;
    const draw = () => {
      $('#cnCumSel').innerHTML = [['cotton', 'Raw cotton'], ['yarn', 'Cotton yarn'], ['fibre', 'Cotton + yarn']].filter(([k]) => C[k]).map(([k, l]) => `<button class="btn ${k === cumKey ? 'on' : ''}" data-k="${k}">${l}</button>`).join(' ') + ' &nbsp; ' +
        [['my', 'Marketing year Aug–Jul'], ['calendar', 'Calendar year']].map(([k, l]) => `<button class="btn ${k === cumBasis ? 'on' : ''}" data-b="${k}">${l}</button>`).join(' ');
      $$('#cnCumSel button[data-k]').forEach(b => b.onclick = () => { cumKey = b.dataset.k; draw(); });
      $$('#cnCumSel button[data-b]').forEach(b => b.onclick = () => { cumBasis = b.dataset.b; draw(); });
      const S = C[cumKey][cumBasis], keys = Object.keys(S).sort().slice(-6), cy = keys.at(-1);
      const labels = cumBasis === 'my' ? C[cumKey].my_months : MON;
      const ds = keys.map((k, i) => ({ label: k, data: S[k], spanGaps: true, borderColor: k === cy ? '#c0392b' : i === keys.length - 2 ? '#2c6fbb' : PAL[(i + 2) % PAL.length], borderWidth: k === cy ? 2.6 : 1.2, pointRadius: k === cy ? 3 : 0 }));
      const U = D.imports.usda_check?.imports;
      if (cumKey === 'cotton' && cumBasis === 'my' && U?.usda_kt) ds.push({ label: `USDA ${U.my}`, data: labels.map(() => U.usda_kt), borderColor: '#555', borderDash: [5, 4], borderWidth: 1.2, pointRadius: 0 });
      chart('cCnCum', { type: 'line', data: { labels, datasets: ds }, options: { scales: { y: { min: 0, title: { display: true, text: 'thousand t' } } } } });
      const f = D.imports.filled_from_cca || [];
      $('#cnCumNote').innerHTML = `China customs, cumulative from ${cumBasis === 'my' ? 'August (USDA and CCA marketing year for cotton)' : 'January'}. Months the bulletin skipped are interpolated.${f.length ? ` Latest month from the CCA import report (customs figures, ahead of the English bulletin): ${f.join(', ')}.` : ''}`;
    };
    draw();
  }
  function usdaCheck() {
    const U = D.imports?.usda_check; if (!U) return;
    const a = U.imports, kt = v => v == null ? '–' : fmt(v, 0);
    $('#cnUsda').innerHTML = `<table><tr><th>Marketing year</th><th>Imports by end-${a.through} (kt)</th><th>Full year, customs</th><th>USDA</th><th>Share by ${a.through}</th></tr>
      ${a.hist.slice().reverse().map(h => `<tr><td>${h.my}</td><td>${kt(h.full_kt * h.share_pct / 100)}</td><td>${kt(h.full_kt)}</td><td>${kt(h.usda_kt)}</td><td>${fmt(h.share_pct, 0)}%</td></tr>`).join('')}
      <tr><td><b>${a.my}</b></td><td><b>${kt(a.to_date_kt)}</b></td><td>pace ≈ ${kt(a.pace_implied_kt)}</td><td>${kt(a.usda_kt)}</td><td>${fmt(a.usda_pct_done, 0)}% of USDA</td></tr></table>`;
    const u = U.use || {};
    $('#cnUsdaNote').innerHTML = `USDA ${a.my}: mill use ${kt(u.usda_kt)} kt (${fmt(u.usda_kt / 217.725, 1)} m bales), production ${kt(u.usda_prod_kt)} kt, ending stocks ${kt(u.usda_end_kt)} kt. Yarn imports Aug–${a.through}: ${kt(u.yarn_to_date_kt)} kt vs ${kt(u.yarn_to_date_prev_kt)} kt a year earlier. USDA PSD (Aug–Jul, 480-lb bales converted).`;
  }

  function polyester() {
    const P = D.prices?.polyester;
    if (!P) { $('#cnPolyCard').style.display = 'none'; return; }
    const W = P.weekly;
    chart('cCnPoly', { type: 'line', data: { labels: W.date, datasets: [
      { label: 'Zhengzhou cotton CF (yuan/t)', data: W.cf, borderColor: '#c0392b', borderWidth: 1.6, pointRadius: 0, yAxisID: 'y' },
      { label: 'Polyester staple fibre PF (yuan/t)', data: W.pf, borderColor: '#2c6fbb', borderWidth: 1.6, pointRadius: 0, yAxisID: 'y' },
      { label: 'PTA (yuan/t)', data: W.ta, borderColor: '#7f8c8d', borderWidth: 1, pointRadius: 0, yAxisID: 'y', hidden: true },
      { label: 'Cotton ÷ polyester', data: W.ratio, borderColor: '#2f6b3a', borderWidth: 2, pointRadius: 0, yAxisID: 'y1' },
      { label: 'Brent ($/bbl)', data: W.brent, borderColor: '#d68910', borderDash: [4, 3], borderWidth: 1.2, pointRadius: 0, yAxisID: 'y2' }] },
      options: { scales: { x: { ticks: { callback: function (v) { return this.getLabelForValue(v).slice(0, 7); } } }, y: { title: { display: true, text: 'yuan/t' } },
        y1: { position: 'right', grid: { display: false }, title: { display: true, text: 'cotton ÷ PSF' } }, y2: { display: false } } } });
    $('#cnPolyNote').innerHTML = `Latest ${P.date}: cotton ${fmt(P.cf, 0)}, PSF ${fmt(P.pf, 0)} yuan/t (${fmt(P.pf_clb, 1)}¢/lb incl. VAT), ratio ${fmt(P.ratio, 2)} (${fmt(P.ratio_pctile, 0)}th percentile since Oct 2020, average ${fmt(P.ratio_avg, 2)}). Six-month change: Brent ${sgn(P.chg_26w.brent, 0, '%')}, PTA ${sgn(P.chg_26w.pta, 0, '%')}, PSF ${sgn(P.chg_26w.psf, 0, '%')}, cotton ${sgn(P.chg_26w.cotton, 0, '%')}. Zhengzhou front months and ICE Brent via TradingView.`;
  }

  function originDemand() {
    const O = D.imports?.origin_demand; if (!O?.rows?.length) return;
    const kt = v => v == null ? '–' : fmt(v, 0), m = MON[O.through_month - 1];
    $('#cnOrgD').innerHTML = `<table><tr><th>Country</th><th>Yarn to China Jan–${m} ${O.year} (kt)</th><th>Year earlier</th><th>Extra yarn</th><th>Extra lint (m bales)</th><th>% of its USDA imports</th><th>US share (5-yr)</th><th>≈ US cotton (m bales)</th><th>Mills spin</th></tr>
      ${O.rows.map(r => `<tr><td>${r.country}</td><td>${kt(r.yarn_ytd_kt)}</td><td>${kt(r.yarn_prev_kt)}</td><td>${sgn(r.extra_yarn_kt, 0)}</td><td>${sgn(r.extra_lint_mbales, 2)}</td><td>${r.extra_pct_of_imports != null ? sgn(r.extra_pct_of_imports, 0, '%') : '–'}</td><td>${r.us_share5_pct != null ? fmt(r.us_share5_pct, 0) + '%' : '–'}</td><td>${r.implied_us_mbales != null ? sgn(r.implied_us_mbales, 2) : '–'}</td><td class="l">${/own/.test(r.note) && !/imported/.test(r.note) ? 'own crop' : /home-grown/.test(r.note) ? 'own + imported' : 'imported'}</td></tr>`).join('')}</table>`;
    $('#cnOrgDNote').innerHTML = `Each tonne of yarn China buys is about ${D.imports.combined?.factor || 1.1} t of lint spun in the supplying country. Country split this year: ${O.share_source}; last year: ${O.share_base || 'same'}. Customs "cotton yarn" includes blends, so the lint is an upper bound. US share and commitments from the desk's cotton export-sales brief; USDA imports are the current WASDE forecast.`;
  }

  let exVat = false;
  function prices() {
    const W = D.prices?.weekly; if (!W) return;
    const draw = () => {
      $('#cnPxSel').innerHTML = `<button class="btn ${!exVat ? 'on' : ''}" data-v="0">incl. VAT</button> <button class="btn ${exVat ? 'on' : ''}" data-v="1">ex-VAT</button>`;
      $$('#cnPxSel button').forEach(b => b.onclick = () => { exVat = b.dataset.v === '1'; draw(); });
      const k = exVat ? '_xvat' : '';
      const pts = key => W.date.map((d, i) => ({ x: d, y: W[key]?.[i] ?? null })).filter(p => p.y != null);
      const tgt = W.date.map((d, i) => ({ x: d, y: W.target_clb[i] == null ? null : W.target_clb[i] / (exVat ? 1.09 : 1) })).filter(p => p.y != null);
      chart('cCnPx', { type: 'line', data: { datasets: [
        { label: 'CCIndex 3128B', data: pts('cc_clb' + k), borderColor: '#c0392b', borderWidth: 1.8, pointRadius: 0 },
        { label: 'Zhengzhou CF', data: pts('cf_clb' + k), borderColor: '#d68910', borderWidth: 1.2, pointRadius: 0 },
        { label: 'ICE cotton', data: pts('ct'), borderColor: '#2c6fbb', borderWidth: 1.4, pointRadius: 0 },
        { label: 'Cotlook A', data: pts('a'), borderColor: '#17a589', borderWidth: 1.4, pointRadius: 0 },
        { label: 'Target price', data: tgt, borderColor: '#555', borderDash: [5, 4], borderWidth: 1.2, pointRadius: 0 }] },
        options: { parsing: true, scales: { x: { type: 'category', labels: W.date, ticks: { callback: function (v) { const s = this.getLabelForValue(v); return s.slice(0, 4); }, maxTicksLimit: 10 } }, y: { title: { display: true, text: '¢/lb' } } } } });
    };
    draw();
    const lab = W.date.map((d, i) => i).filter(i => W.date[i] >= '2021-01-01');
    chart('cCnMg', { type: 'line', data: { labels: lab.map(i => W.date[i]), datasets: [
      { label: 'Import margin, 1% duty', data: lab.map(i => W.imp_margin_1pct?.[i] ?? null), borderColor: '#c0392b', borderWidth: 1.6, pointRadius: 0, spanGaps: true },
      { label: 'Import margin, sliding duty', data: lab.map(i => W.imp_margin_sliding?.[i] ?? null), borderColor: '#d68910', borderWidth: 1.2, pointRadius: 0, spanGaps: true },
      { label: 'CCIndex – target price', data: lab.map(i => W.cc_vs_target?.[i] ?? null), borderColor: '#555', borderDash: [5, 4], borderWidth: 1.2, pointRadius: 0, spanGaps: true },
      { label: 'Yarn – cotton (CY–CF)', data: lab.map(i => W.cy?.[i] != null && W.cf?.[i] != null ? W.cy[i] - W.cf[i] : null), borderColor: '#2c6fbb', borderWidth: 1.4, pointRadius: 0, spanGaps: true }] },
      options: { scales: { x: { ticks: { callback: function (v) { return this.getLabelForValue(v).slice(0, 7); } } }, y: { title: { display: true, text: 'yuan/t' } } } } });
  }

  function tables() {
    const E = D.estimates;
    const kt = v => v == null ? '–' : fmt(v, 0);
    if (E?.table) $('#cnEstTbl').innerHTML = `<table><tr><th>Season</th><th>CCA Sep survey</th><th>CCA last survey</th><th>CCA final</th><th>NBS</th><th>USDA</th></tr>
      ${E.table.slice().reverse().map(r => `<tr><td>${r.season}</td><td>${kt(r.sep)}</td><td>${kt(r.last_survey)}</td><td>${kt(r.cca_final)}</td><td>${kt(r.nbs)}</td><td>${kt(r.usda)}</td></tr>`).join('')}</table>
      ${E.projection ? `<p class="note">Projected final ${E.season}: ${kt(E.projection.kt)} kt (range ${kt(E.projection.lo_kt)}–${kt(E.projection.hi_kt)}), applying past moves from the ${MON[+E.latest.survey.slice(5) - 1]} survey to the final figure (${E.projection.n} seasons).</p>` : ''}`;
    const O = D.imports?.origins?.yarn;
    if (O) $('#cnOrg').innerHTML = `<table><tr><th>Origin</th>${O.years.map(y => `<th>${y}</th>`).join('')}</tr>${Object.keys(O.share).map(p => `<tr><td>${p}</td>${O.share[p].map(v => `<td>${fmt(v, 1)}</td>`).join('')}</tr>`).join('')}</table>`;
    const G = D.grains;
    if (G) { const ys = Object.keys(G.rows[0].ytd).map(Number).sort().slice(-6);
      $('#cnGr').innerHTML = `<table><tr><th>Jan–${MON[G.through_month - 1]}</th>${ys.map(y => `<th>${y}</th>`).join('')}<th>y/y</th><th>vs 5-yr</th></tr>${G.rows.map(r => `<tr><td>${r.name}</td>${ys.map(y => `<td>${kt(r.ytd[y])}</td>`).join('')}<td>${pct(r.yoy_pct, 0)}</td><td>${pct(r.vs_avg5_pct, 0)}</td></tr>`).join('')}</table>
        <p class="note">China customs monthly bulletin, "major import commodities" (10,000 t, rounded).</p>`; }
    const SP = (D.seed_price || []).filter(r => r.yuan_kg > 3 && r.yuan_kg < 15).sort((x, y) => x.pub < y.pub ? -1 : 1);
    if (SP.length) chart('cCnSeed', { type: 'line', data: { datasets: [{ label: 'Seed cotton, yuan/kg', data: SP.map(r => ({ x: r.pub, y: r.yuan_kg })), borderColor: '#2f6b3a', pointRadius: 2, borderWidth: 1.4 }] },
      options: { scales: { x: { type: 'category', labels: SP.map(r => r.pub), ticks: { callback: function (v) { return this.getLabelForValue(v).slice(0, 7); } } } } } });
  }
  return { mount };
})();
