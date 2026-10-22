// COT desk panel: positioning by trader group, flows, money under water, CTA trigger levels, seasonality.
// Usage: CotDesk.mount(element, ['ZC']) or several symbols for a market picker.
const CotDesk = (() => {
  const SUM = { p: null };
  const cache = {};
  const NAMES = { ZC: 'Corn', ZS: 'Soybeans', ZW: 'Chicago wheat', KE: 'KC wheat', ZM: 'Meal', ZL: 'Oil', HE: 'Lean hogs', LE: 'Live cattle', GF: 'Feeder cattle', DC: 'Class III', GDK: 'Class IV', CSC: 'Cheese', CB: 'Butter', GNF: 'NFDM', DY: 'Dry whey' };
  const GROUP = { CT: 'softs', ZC: 'grains', ZS: 'grains', ZM: 'grains', ZL: 'grains', ZW: 'grains', KE: 'grains', HE: 'livestock', LE: 'livestock', GF: 'livestock', DC: 'dairy', GDK: 'dairy', CSC: 'dairy', CB: 'dairy', GNF: 'dairy', DY: 'dairy' };
  const k = v => v == null ? '–' : Math.round(v).toLocaleString();
  const sk = v => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${Math.round(v).toLocaleString()}</span>`;
  const usd = (v, sign) => { if (v == null) return '–'; const x = Math.abs(v), s = v < 0 ? '−' : (sign ? '+' : ''); return s + '$' + (x >= 1e9 ? (x / 1e9).toFixed(2) + 'bn' : x >= 1e6 ? (x / 1e6).toFixed(0) + 'm' : (x / 1e3).toFixed(0) + 'k'); };
  const susd = v => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${usd(v, true)}</span>`;
  const ord = v => { if (v == null) return '–'; const n = Math.round(v); return n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th')); };
  const pc = (v, d = 1) => v == null ? '–' : (+v).toFixed(d) + '%';
  const px = (v, dp) => v == null ? '–' : (+v).toFixed(dp);
  const heat = v => v == null ? '' : v >= 90 ? 'background:#d8efdf' : v <= 10 ? 'background:#f8dcd8' : '';
  const chip = s => s === 1 ? '<span class="cd-chip cd-up">▲ long</span>' : s === -1 ? '<span class="cd-chip cd-dn">▼ short</span>' : '<span class="cd-chip">– flat</span>';
  const DP = { ZC: 2, ZS: 2, ZW: 2, KE: 2, ZM: 1, ZL: 2, HE: 3, LE: 3, GF: 3, DC: 2, GDK: 2, CSC: 3, CB: 3, GNF: 3, DY: 3 };

  function mount(root, syms) {
    const st = { sym: syms[0], range: 156, chartMode: 'mm', charts: {} };
    root.innerHTML = `<div class="card cotdesk"><h2>COT desk: positioning, money under water and CTA levels</h2>
      <p class="note" data-r="asof">Loading…</p>
      ${syms.length > 1 ? `<div class="tbar"><div class="grp" data-r="g-sym"><span class="lab">Market</span></div></div>` : ''}
      <div data-r="kpis" class="grid g4" style="margin:8px 0"></div>
      <div class="grid g2">
        <div><div class="tbar"><div class="grp" data-r="g-mode"><span class="lab">Chart</span></div><div class="grp" data-r="g-rng"><span class="lab">Range</span></div></div>
          <div class="chart tall"><canvas data-r="c-pos"></canvas></div></div>
        <div><h3>Trader groups</h3><div class="tbl" data-r="t-cats"></div><p class="note" data-r="conc"></p></div>
      </div>
      <h3 style="margin-top:14px">Money under water (managed money, estimate)</h3>
      <div class="grid g2"><div data-r="uw"></div><div><div class="chart"><canvas data-r="c-uw"></canvas></div></div></div>
      <div data-r="cta-wrap"><h3 style="margin-top:14px">CTA / trend-follower levels</h3>
        <div class="grid g2"><div data-r="cta"></div><div><div class="chart"><canvas data-r="c-cta"></canvas></div><p class="note">Managed-money net vs the position implied by the trend score (5-year fit). A big gap means positioning is out of line with trend: discretionary funds, or room for trend-followers to adjust.</p></div></div>
        <div class="grid g2" style="margin-top:8px"><div data-r="cta-sig"></div><div data-r="cta-scen"></div></div>
        <div data-r="trig" style="margin-top:8px"></div></div>
      <h3 style="margin-top:14px">Seasonality of managed-money net</h3>
      <div class="chart"><canvas data-r="c-seas"></canvas></div>
      <h3 style="margin-top:14px" data-r="grp-h">Group monitor</h3><div class="tbl" data-r="grp"></div>
      <p class="note">CFTC disaggregated futures and options combined, report as of Tuesday, released Friday. Positioning is secondary in these cash-settled and delivery markets: settlement is set by cash prices, so read it as information about flows and crowding, not a forecast. Under-water and CTA figures are model estimates (method notes under each table).</p></div>`;
    const R = n => root.querySelector(`[data-r="${n}"]`);
    function chips(name, items, cur, cb) { const g = R(name); if (!g) return; g.querySelectorAll('button').forEach(b => b.remove());
      items.forEach(([key, lab]) => { const b = document.createElement('button'); b.className = 'chip' + (cur === key ? ' on' : ''); b.textContent = lab; b.onclick = () => cb(key); g.appendChild(b); }); }
    function draw(id, cfg) { if (st.charts[id]) st.charts[id].destroy(); st.charts[id] = new Chart(R(id), cfg); }

    function render() {
      const D = cache[st.sym], dp = DP[st.sym], mm = D.cats.mm, u = D.usd || {};
      if (syms.length > 1) chips('g-sym', syms.map(s => [s, NAMES[s]]), st.sym, s => { st.sym = s; load(); });
      R('asof').textContent = `${D.name} · CFTC report ${D.date}${D.front ? ` · prices on ${D.front}` : ''} · open interest ${k(D.oi)} (${D.doi >= 0 ? '+' : ''}${k(D.doi)} w/w)`;
      const kpi = (l, v, s) => `<div class="kpi card" style="padding:10px"><div class="lbl">${l}</div><div class="val" style="font-size:19px">${v}</div><div class="sub">${s}</div></div>`;
      R('kpis').innerHTML = kpi('Managed money net', `${k(mm.N)} <span class="note">lots</span>`, `${usd(u.N)} · ${pc(mm.np_oi)} of OI`) +
        kpi('This week', sk(mm.dN), `${susd(u.dN)} · ${D.driver || ''} · z ${mm.z ?? '–'} · streak ${mm.streak}`) +
        kpi('Percentile 3y · 10y · all', `${ord(mm.pct.y3)} · ${ord(mm.pct.y10)} · ${ord(mm.pct.all)}`, `5y ${ord(mm.pct.y5)} · all = since ${(D.history_since || '2006').slice(0, 4)} · COT index ${mm.cot.y3 ?? '–'} (3y), ${mm.cot.y10 ?? '–'} (10y)`) +
        kpi('4 weeks', sk(mm.dN4), `${susd(u.dN4)} · longs ${k(mm.L)} (${ord(mm.pct_L)}) · shorts ${k(mm.S)} (${ord(mm.pct_S)})`);
      // chart
      chips('g-mode', [['mm', 'Managed money'], ['cats', 'All groups'], ['traders', 'Trader counts']], st.chartMode, m => { st.chartMode = m; render(); });
      chips('g-rng', [[52, '1Y'], [156, '3Y'], [260, '5Y'], [520, '10Y']], st.range, r => { st.range = r; render(); });
      const S = D.series, n = Math.min(st.range, S.date.length), sl = a => a.slice(-n), lab = sl(S.date);
      let ds;
      if (st.chartMode === 'mm') ds = [{ type: 'bar', label: 'MM long', data: sl(S.mm_l), backgroundColor: 'rgba(31,122,58,.35)', yAxisID: 'y', stack: 's' },
        { type: 'bar', label: 'MM short', data: sl(S.mm_s).map(v => v == null ? null : -v), backgroundColor: 'rgba(179,38,30,.35)', yAxisID: 'y', stack: 's' },
        { type: 'line', label: 'MM net', data: sl(S.mm_n), borderColor: '#1a1a1a', borderWidth: 2, pointRadius: 0, yAxisID: 'y' }];
      else if (st.chartMode === 'cats') ds = [['mm', '#1a1a1a'], ['pm', '#2a78d6'], ['sw', '#eb6834'], ['or', '#1baf7a'], ['nr', '#8a8984']].map(([c, col]) => ({ type: 'line', label: D.cat_names[c], data: sl(S[c + '_n']), borderColor: col, borderWidth: c === 'mm' ? 2.2 : 1.3, pointRadius: 0, yAxisID: 'y' }));
      else ds = [{ type: 'line', label: 'MM traders long', data: sl(S.mm_tl), borderColor: '#1f7a3a', pointRadius: 0, yAxisID: 'y' }, { type: 'line', label: 'MM traders short', data: sl(S.mm_ts), borderColor: '#b3261e', pointRadius: 0, yAxisID: 'y' }];
      ds.push({ type: 'line', label: 'Price (front, roll-adjusted)', data: sl(S.price), borderColor: '#6250d6', borderWidth: 1.4, borderDash: [4, 3], pointRadius: 0, yAxisID: 'y2' });
      draw('c-pos', { data: { labels: lab, datasets: ds }, options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { boxWidth: 10, font: { size: 11 } } } }, scales: { x: { stacked: true, ticks: { maxTicksLimit: 8 } }, y: { stacked: st.chartMode === 'mm', title: { display: true, text: 'lots' } }, y2: { position: 'right', grid: { display: false }, title: { display: true, text: 'price' } } } } });
      // categories table
      const C = D.cats;
      R('t-cats').innerHTML = `<table><tr><th>Group</th><th>Net</th><th>w/w</th><th>4 wk</th><th>% OI</th><th>1y</th><th>3y</th><th>5y</th><th>10y</th><th>All</th><th>COT idx 3y</th><th>z</th><th>Traders L/S</th></tr>
        ${Object.keys(C).map(c => { const x = C[c]; return `<tr><td>${D.cat_names[c]}</td><td>${k(x.N)}</td><td>${sk(x.dN)}</td><td>${sk(x.dN4)}</td><td>${pc(x.np_oi)}</td>${['y1', 'y3', 'y5', 'y10', 'all'].map(w => `<td style="${heat(x.pct[w])}">${ord(x.pct[w])}</td>`).join('')}<td>${x.cot.y3 ?? '–'}</td><td>${x.z ?? '–'}</td><td>${x.TL != null ? `${k(x.TL)} / ${k(x.TS)}` : '–'}</td></tr>`; }).join('')}</table>`;
      const cc = D.conc || {};
      R('conc').innerHTML = `Percentiles of net position vs each window (green ≥ 90th, red ≤ 10th). Concentration, net share of OI held by the largest traders: top 4 long ${pc(cc.conc_net_le_4_tdr_long_all)}, short ${pc(cc.conc_net_le_4_tdr_short_all)}; top 8 long ${pc(cc.conc_net_le_8_tdr_long_all)}, short ${pc(cc.conc_net_le_8_tdr_short_all)}.`;
      // under water
      const W = D.underwater;
      if (W && (W.long || W.short)) {
        const side = (lab, x, sign) => x ? `<tr><td>${lab}</td><td>${k(x.lots)}</td><td>${px(x.avg_entry, dp)}</td><td>${pc(x.pct_underwater, 0)}</td><td>${susd(x.pnl_usd)}</td><td>${px(x.half_underwater_at, dp)}</td></tr>` : '';
        R('uw').innerHTML = `<div class="tbl"><table><tr><th></th><th>Lots</th><th>Avg entry</th><th>Under water</th><th>Open P&amp;L</th><th>Half under water at</th></tr>${side('MM gross longs', W.long)}${side('MM gross shorts', W.short)}</table></div>
          <p>Front month ${px(W.price_now, dp)}. ${W.long ? `Longs are ${W.long.pnl_usd >= 0 ? 'in profit' : 'losing'} ${usd(Math.abs(W.long.pnl_usd))} with ${pc(W.long.pct_underwater, 0)} of lots under water` : ''}${W.short ? `; shorts are ${W.short.pnl_usd >= 0 ? 'in profit' : 'losing'} ${usd(Math.abs(W.short.pnl_usd))} with ${pc(W.short.pct_underwater, 0)} under water.` : '.'}</p>
          <div class="tbl"><table><tr><th>Price move</th><th>Price</th><th>Longs under water</th><th>Longs P&amp;L</th><th>Shorts under water</th><th>Shorts P&amp;L</th></tr>
          ${W.grid.filter((g, i) => i % 2 === 0).map(g => `<tr style="${g.move_pct === 0 ? 'font-weight:600' : ''}"><td>${g.move_pct > 0 ? '+' : ''}${g.move_pct}%</td><td>${px(g.price, dp)}</td><td>${pc(g.long_pct_underwater, 0)}</td><td>${susd(g.long_pnl_usd)}</td><td>${pc(g.short_pct_underwater, 0)}</td><td>${susd(g.short_pnl_usd)}</td></tr>`).join('')}</table></div>
          <p class="note">Method: last-in-first-out. Each week's change in managed-money gross longs (shorts) is booked at that report-day's front-month close; reductions remove the newest layers first. Starts ${W.window_weeks} weeks ago with the then-open position at the prior 13-week average price. Pain rises as the share under water climbs: forced liquidation risk for longs on a drop, short covering on a rally.</p>`;
        draw('c-uw', { type: 'bar', data: { labels: W.grid.map(g => `${g.move_pct > 0 ? '+' : ''}${g.move_pct}%`), datasets: [
          { label: 'Longs under water %', data: W.grid.map(g => g.long_pct_underwater), backgroundColor: 'rgba(179,38,30,.55)' },
          { label: 'Shorts under water %', data: W.grid.map(g => g.short_pct_underwater), backgroundColor: 'rgba(31,122,58,.55)' }] },
          options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { labels: { boxWidth: 10 } }, title: { display: true, text: 'Share of fund positions losing money if the front month moves…' } }, scales: { y: { min: 0, max: 100, title: { display: true, text: '%' } }, x: { title: { display: true, text: 'price move from today' } } } } });
      } else { R('uw').innerHTML = '<p class="note">No price history for this market yet.</p>'; if (st.charts['c-uw']) st.charts['c-uw'].destroy(); }
      // CTA
      const T = D.cta, show = T && T.r2 >= 0.3;
      R('cta-wrap').style.display = T ? '' : 'none';
      if (T) {
        const nx = T.next || {};
        R('cta').innerHTML = `<div class="grid g3" style="gap:6px">${kpi('Trend score', (T.score > 0 ? '+' : '') + T.score.toFixed(2), T.score >= 0.75 ? 'all signals long' : T.score <= -0.75 ? 'all signals short' : 'mixed signals')}
          ${kpi('MM vs trend-implied', sk(T.gap_lots), `actual ${k(T.mm_now)} vs implied ${k(T.implied_mm)}`)}${kpi('Flow per signal flip', `${k(Math.abs(T.beta_lots) / 2)} lots`, `≈ ${usd(Math.abs(T.beta_lots) / 2 * T.front_close * ({ ZC: 50, ZS: 50, ZW: 50, KE: 50, ZM: 100, ZL: 600, HE: 400, LE: 400, GF: 500, DC: 2000, GDK: 2000, CSC: 20000, CB: 200, GNF: 440, DY: 440, CT: 500, CL: 1000, NG: 10000, HO: 42000, RB: 42000 }[st.sym]))} within ~2 weeks`)}</div>
          <p><b>Next trigger up:</b> ${nx.up ? `${px(nx.up.lvl, dp)} (${nx.up.name}, ${pc(nx.up.pct)} / ${nx.up.atr?.toFixed(1)} ATR)` : '–'} · <b>down:</b> ${nx.dn ? `${px(nx.dn.lvl, dp)} (${nx.dn.name}, ${pc(nx.dn.pct)} / ${Math.abs(nx.dn.atr ?? 0).toFixed(1)} ATR)` : '–'}</p>
          ${show ? '' : `<p class="note" style="color:#7a5000">Trend explains little of fund positioning here (R² ${T.r2.toFixed(2)}): treat the CTA levels as indicative only.</p>`}
          <p class="note">Score = average sign of 20/60/120/250-day returns on the roll-adjusted front month (+1 all up, −1 all down). Fit over the last 5 years: managed-money net vs score R² ${T.r2.toFixed(2)}; 2-week flow vs 2-week score change correlation ${T.r_flow?.toFixed(2) ?? '–'}. Managed money includes discretionary funds, so this is the trend-following component, not CTA books directly.</p>`;
        R('cta-sig').innerHTML = `<h3>Momentum signals and flip levels</h3><div class="tbl"><table><tr><th>Lookback</th><th>Signal</th><th>Flips at</th><th>Distance</th><th>ATR</th><th>Est. flow if flipped</th></tr>
          ${T.signals.map(s => `<tr><td>${s.lookback} days</td><td>${chip(s.state)}</td><td>${px(s.flip_price * T.front_close / T.price_now, dp)}</td><td>${pc(s.dist_pct)}</td><td>${s.dist_atr?.toFixed(1)}</td><td>${sk(s.flow_lots_if_flipped)} <span class="note">${usd(s.flow_usd_if_flipped, true)}</span></td></tr>`).join('')}</table></div>
          <p class="note">A signal flips when price crosses where it was 20/60/120/250 sessions ago; that reference moves daily, so the level drifts. Flow = fitted 2-week managed-money response to the score change.</p>`;
        R('cta-scen').innerHTML = `<h3>Price scenarios</h3><div class="tbl"><table><tr><th>Move</th><th>Front price</th><th>Score</th><th>2-week flow</th><th>$</th><th>Trend-implied MM</th><th>Gap after</th></tr>
          ${T.scenarios.map(s => `<tr style="${s.move_pct === 0 ? 'font-weight:600' : ''}"><td>${s.move_pct > 0 ? '+' : ''}${s.move_pct}%</td><td>${px(s.price * T.front_close / T.price_now, dp)}</td><td>${s.score.toFixed(2)}</td><td>${sk(s.flow_lots)}</td><td>${susd(s.flow_usd)}</td><td>${k(s.implied_mm)}</td><td>${sk(T.mm_now + s.flow_lots - s.implied_mm)}</td></tr>`).join('')}</table></div>
          <p class="note">2-week flow = fitted response to the change in score. Gap after = managed money (after that flow) minus the level the trend score implies: a large positive gap with all signals short means longs are still exposed if the downtrend persists; the reverse for shorts in an uptrend.</p>`;
        R('trig').innerHTML = `<h3>Breakout and moving-average triggers (tradable contract ${D.front || ''})</h3><div class="tbl"><table><tr>${T.triggers.map(t => `<th>${t.name}</th>`).join('')}</tr><tr>${T.triggers.map(t => `<td>${chip(t.state)}</td>`).join('')}</tr>
          <tr>${T.triggers.map(t => `<td>${t.lvl != null ? px(t.lvl, dp) : `${px(t.dn, dp)} – ${px(t.up, dp)}`}</td>`).join('')}</tr></table></div>
          <p class="note">Breakouts: state flips on a close above the prior N-day high or below the N-day low (range shown). Averages: close vs the N-day mean. These are the levels systematic funds watch; ATR ${px(T.atr, dp)}.</p>`;
        const H = T.history;
        draw('c-cta', { data: { labels: H.date, datasets: [{ type: 'line', label: 'MM net', data: H.mm, borderColor: '#1a1a1a', borderWidth: 2, pointRadius: 0, yAxisID: 'y' },
          { type: 'line', label: 'Trend-implied', data: H.implied, borderColor: '#2a78d6', borderWidth: 1.5, borderDash: [4, 3], pointRadius: 0, yAxisID: 'y' },
          { type: 'bar', label: 'Trend score', data: H.score, backgroundColor: H.score.map(v => v >= 0 ? 'rgba(31,122,58,.25)' : 'rgba(179,38,30,.25)'), yAxisID: 'y2' }] },
          options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { labels: { boxWidth: 10 } } },
            scales: { x: { ticks: { maxTicksLimit: 8 } }, y: { title: { display: true, text: 'lots' } }, y2: { position: 'right', min: -1, max: 1, grid: { display: false } } } } });
      }
      // seasonality
      const Z = D.seasonal, yrs = Object.keys(Z.years).sort(), PAL = ['#8a8984', '#e87ba4', '#eda100', '#1baf7a', '#2a78d6'];
      draw('c-seas', { type: 'line', data: { datasets: [
        { label: '5-yr max', data: Z.band.w.map((w, i) => ({ x: w, y: Z.band.max[i] })), borderWidth: 0, pointRadius: 0, fill: false },
        { label: '5-yr range', data: Z.band.w.map((w, i) => ({ x: w, y: Z.band.min[i] })), borderWidth: 0, pointRadius: 0, backgroundColor: 'rgba(138,137,132,.18)', fill: '-1' },
        { label: '5-yr avg', data: Z.band.w.map((w, i) => ({ x: w, y: Z.band.avg[i] })), borderColor: '#8a8984', borderDash: [5, 4], borderWidth: 1.4, pointRadius: 0 },
        ...yrs.map((y, i) => ({ label: y, data: Z.years[y].map(p => ({ x: p[0], y: p[1] })), borderColor: i === yrs.length - 1 ? '#c0392b' : PAL[i % PAL.length], borderWidth: i === yrs.length - 1 ? 2.6 : 1, pointRadius: 0 }))] },
        options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { labels: { boxWidth: 10, filter: i => i.text !== '5-yr max' } } }, scales: { x: { type: 'linear', min: 1, max: 53, title: { display: true, text: 'week of year' } }, y: { title: { display: true, text: 'MM net, lots' } } } } });
      // group monitor
      const g = GROUP[st.sym], M = SUM.p?.markets || {}, list = (SUM.p?.groups?.[g] || []).filter(s => M[s]);
      R('grp-h').textContent = `Group monitor: ${g}`;
      R('grp').innerHTML = `<table><tr><th>Market</th><th>MM net</th><th>w/w</th><th>Driver</th><th>z</th><th>3y pct</th><th>10y pct</th><th>All pct</th><th>COT idx</th><th>Net $</th><th>Longs u/w</th><th>Shorts u/w</th><th>Trend</th><th>Next trigger up</th><th>Next trigger down</th></tr>
        ${list.map(s => { const x = M[s], nx = x.next || {}; return `<tr style="${s === st.sym ? 'font-weight:600' : ''}"><td>${x.name}</td><td>${k(x.N)}</td><td>${sk(x.dN)}</td><td>${x.driver || ''}</td><td>${x.z ?? '–'}</td><td style="${heat(x.pct3)}">${ord(x.pct3)}</td><td style="${heat(x.pct10)}">${ord(x.pct10)}</td><td style="${heat(x.pct_all)}">${ord(x.pct_all)}</td><td>${x.cot3 ?? '–'}</td><td>${usd(x.usdN)}</td><td>${pc(x.long_uw, 0)}</td><td>${pc(x.short_uw, 0)}</td><td>${x.cta_score == null ? '–' : (x.cta_score > 0 ? '+' : '') + x.cta_score.toFixed(2)}</td>
          <td>${nx.up ? `${px(nx.up.lvl, DP[s])} <span class="note">${pc(nx.up.pct)}</span>` : '–'}</td><td>${nx.dn ? `${px(nx.dn.lvl, DP[s])} <span class="note">${pc(nx.dn.pct)}</span>` : '–'}</td></tr>`; }).join('')}</table>`;
    }
    async function load() {
      try {
        if (!SUM.p) SUM.p = await fetch('data/cot_desk/summary.json?' + Date.now()).then(r => r.json()).catch(() => ({}));
        if (!cache[st.sym]) cache[st.sym] = await fetch(`data/cot_desk/${st.sym}.json?` + Date.now()).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
        render();
      } catch (e) { R('asof').textContent = `COT desk data for ${st.sym} is not built yet.`; }
    }
    load();
  }
  return { mount };
})();
