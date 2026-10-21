// Signals: the research library (commodity futures, trend, carry, volatility, sizing) applied to each market.
// Data: data/research/research.json (models/research.py). Deep link: #signals/<SYM>.
const Signals = (() => {
  let R = null, sym = null, built = false;
  const pc = (v, d = 1) => v == null ? '–' : sgn(v * 100, d, '%');
  const n = (v, d = 2) => v == null ? '–' : fmt(v, d);
  const nth = v => v == null ? '–' : `${v}${v % 100 >= 11 && v % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' })[v % 10] || 'th'}`;
  const dir = s => s > 0 ? '<span class="up">long</span>' : '<span class="dn">short</span>';
  const SRC = [
    ['Fama-French 1987', 'Theory of storage: the basis reflects interest, storage and convenience yield. Seasonal carry is structural in grains; in livestock the curve forecasts the cash path.'],
    ['Gorton-Rouwenhorst 2004', 'Commodity futures earned an equity-like premium with positive skew. Excess return is measured on the nearest contract that will not expire in the holding month (how the series here is built).'],
    ['Gorton-Hayashi-Rouwenhorst 2007', 'Low inventories mean high basis, high expected returns and momentum continuation. High-minus-low basis and 12-month momentum earned 10-13% a year, and the two are largely the same trade (corr 0.87). COT hedging pressure did not predict returns.'],
    ['Erb-Harvey 2006', 'Individual commodity excess returns average about zero; roll yield (curve shape) explains the cross-section. Use term structure and momentum as tactical overlays.'],
    ['Moskowitz-Ooi-Pedersen 2012', 'Time-series momentum: the sign of the 12-month excess return, each market scaled to 40% vol with an EWMA (60-day centre of mass).'],
    ['Kim-Tse-Wald 2016', 'Much of the TSMOM gain is the vol scaling itself, so compare it with vol-scaled long-only.'],
    ['Dao-Bouchaud 2016; Bhansali-Holdom 2024; Fung-Hsieh 2001', 'Trend P&L is long-horizon minus short-horizon variance, so a variance ratio above 1 favours trend. Trend following behaves like a long straddle paid for with whipsaw.'],
    ['Daniel-Moskowitz 2016', 'Momentum crashes come in rebounds after a large decline in high volatility, and the short side is hit hardest.'],
    ['Da-Gurun-Warachka 2014', 'Trends built from many small moves persist; trends built on a few jumps fade.'],
    ['Constantinides et al. 2010; Chan 2017', 'Delta-hedged option P&L is about half gamma times (IV² − RV²). IV usually exceeds realized vol, and that gap is the premium option sellers collect.'],
    ['Johnson 2017', 'The slope of the IV term structure, not its level, predicts variance returns. An inverted curve preceded gains for long variance (VIX evidence).'],
    ['Breeden-Litzenberger 1978; Jackwerth-Rubinstein 1996; Gatheral 2006', 'The second strike-derivative of call prices is the risk-neutral density. Fit the smile smoothly first, and don\'t read the wings literally. These are risk-neutral, not real-world, odds, and American exercise biases them.'],
    ['MacLean-Thorp-Ziemba 2010; Callan 2010', 'Use half Kelly or less, because errors in the mean dominate. Inverse-vol (risk parity) weights are a robust default.'],
    ['Almgren 2008; Chan 2017', 'Impact rises with the square root of size: about 0.5-1 × daily vol × √(order / daily volume).'],
    ['Pardo 2008; Chan 2017', 'Use walk-forward or out-of-sample tests, and prefer stable parameters. A Sharpe ratio that changes sign between halves of the sample is not a signal.'],
  ];
  function table() {
    const ms = Object.values(R.markets);
    const groups = [...new Set(ms.map(m => m.group))];
    return `<div class="tbl"><table class="sig-t"><thead><tr><th class="l">Market</th><th>12m excess</th><th>Trend</th><th>Lev (40% vol)</th><th>Vol pct</th><th>Var ratio 3m / 12m</th>
      <th>Carry %/yr</th><th>Carry pct (month)</th><th>Rank mom / carry</th><th>IV − RV</th><th>MM net % OI</th><th>Inventory</th><th>Trend Sharpe (vs long-only)</th><th class="l">Flags</th></tr></thead><tbody>
      ${groups.map(g => `<tr class="grp"><td class="l" colspan="14"><b>${g}</b></td></tr>` + ms.filter(m => m.group === g).map(m => {
        const vr = Object.fromEntries(m.vr), t = m.backtest.tsmom_12m, l = m.backtest.long_only_scaled;
        return `<tr data-s="${m.sym}" class="sig-row${m.sym === sym ? ' on' : ''}"><td class="l"><a href="#signals/${m.sym}">${m.name}</a> <span class="note">${m.sym}</span></td>
        <td>${pc(m.trend.r12)}</td><td>${dir(m.trend.sign)}</td><td>${n(m.trend.lev)}</td><td>${nth(m.trend.vol_pct5y)}</td>
        <td>${n(vr[63])} / ${n(vr[250])}</td><td>${pc(m.carry.now)}</td><td>${nth(m.carry.pct_month)}</td><td>${m.rank.mom ?? '–'} / ${m.rank.carry ?? '–'}</td>
        <td>${m.options ? sgn(m.options.vol_prem, 1) : '–'}</td><td>${m.positioning ? sgn(m.positioning.mm_np_oi, 1, '%') : '–'}</td>
        <td>${m.inventory ? m.inventory.state : '–'}</td><td>${t ? n(t.sharpe) : '–'} <span class="note">(${l ? n(l.sharpe) : '–'})</span></td>
        <td class="l">${m.flags.length ? `<span class="sig-flag" title="${m.flags.join('\n').replace(/"/g, '&quot;')}">${m.flags.length} ⚑</span>` : ''}</td></tr>`;
      }).join('')).join('')}</tbody></table></div>
      <p class="note">There are ${ms.length} markets; ranks run 1 = strongest. "12m excess" is the roll-adjusted return of the nearest contract not expiring in the month (Gorton-Rouwenhorst). Carry is (F1 − F2)/F1 annualized between the held and next contract. For storable markets, compare it with the same calendar month in past years. For livestock and dairy it is the market's forecast of the cash path. Variance ratio above 1: trends persist. Sharpe figures are monthly backtests since 2006-2012 with no look-ahead, before costs. Click a row for details.</p>`;
  }
  function xsCard() {
    const x = R.cross_section, row = (k, s) => s ? `<tr><td class="l">${k}</td><td>${n(s.sharpe)}</td><td>${s.ann_ret}%</td><td>${s.ann_vol}%</td><td>${s.hit}%</td><td>${n(s.sharpe_1st_half)} / ${n(s.sharpe_2nd_half)}</td><td>${s.since}</td></tr>` : '';
    return `<div class="tbl"><table><thead><tr><th class="l">Cross-section, high − low tercile (GHR 2007)</th><th>Sharpe</th><th>Ann. return</th><th>Vol</th><th>Hit</th><th>Halves</th><th>Since</th></tr></thead>
      <tbody>${row('12-month momentum', x.momentum)}${row('Carry (seasonal-adjusted for storables)', x.carry)}</tbody></table></div>
      <p class="note">These are monthly long/short backtests across the desk's ${Object.keys(R.markets).length} markets. Each leg is inverse-vol weighted. Costs are excluded.</p>`;
  }
  function detail(m) {
    const t = m.trend, c = m.carry, o = m.options, d = m.density, z = m.size, p = m.positioning, b = m.backtest;
    const bt = (k, lab) => b[k] ? `<tr><td class="l">${lab}</td><td>${n(b[k].sharpe)}</td><td>${b[k].ann_ret}%</td><td>${b[k].hit}%</td><td>${b[k].max_dd}%</td><td>${n(b[k].sharpe_1st_half)} / ${n(b[k].sharpe_2nd_half)}</td></tr>` : '';
    return `<div class="card"><h2>${m.name} <span class="note">${m.sym} · held ${m.held}, next ${m.next} · ${m.date}</span></h2>
      <p>${m.read}</p>${m.flags.length ? `<ul class="sig-flags">${m.flags.map(f => `<li>${f}</li>`).join('')}</ul>` : ''}
      <div class="sig-grid">
        <div><h3>Trend (time-series momentum)</h3><div class="tbl"><table><tbody>
          <tr><td class="l">Excess return 1m / 3m / 6m / 12m</td><td>${pc(t.r1)} ${pc(t.r3)} ${pc(t.r6)} ${pc(t.r12)}</td></tr>
          <tr><td class="l">Signal · leverage for 40% vol</td><td>${dir(t.sign)} · ${n(t.lev)}x</td></tr>
          <tr><td class="l">EWMA vol (60-day c.o.m.) · 5-yr pct</td><td>${n(t.ewma_vol, 1)}% · ${nth(t.vol_pct5y)}</td></tr>
          <tr><td class="l">Information discreteness (− = smooth)</td><td>${n(t.id)}</td></tr></tbody></table></div>
          <h3>Variance ratio σ²(τ)/τσ²(1)</h3><div class="chart" style="height:180px"><canvas id="sig-vr"></canvas></div></div>
        <div><h3>Carry and inventories</h3><div class="tbl"><table><tbody>
          <tr><td class="l">${m.held} vs ${m.next}, annualized</td><td>${pc(c.now)}</td></tr>
          <tr><td class="l">Percentile for this calendar month</td><td>${nth(c.pct_month)}</td></tr>
          ${c.storable ? `<tr><td class="l">Seasonal-adjusted (vs past same-month median)</td><td>${pc(c.adj)}</td></tr>` : `<tr><td class="l" colspan="2">Non-storable: the slope is the market's forecast of the cash path, not storage carry (Fama-French).</td></tr>`}
          <tr><td class="l">Rank on momentum / carry</td><td>${m.rank.mom ?? '–'} / ${m.rank.carry ?? '–'} of ${m.rank.n}</td></tr>
          ${m.inventory ? `<tr><td class="l">${m.inventory.measure}</td><td>${m.inventory.state}</td></tr>` : `<tr><td class="l" colspan="2">No inventory series here; carry stands in for it (GHR).</td></tr>`}</tbody></table></div>
          <h3>Carry history (%/yr, month-end)</h3><div class="chart" style="height:180px"><canvas id="sig-carry"></canvas></div></div>
        <div><h3>Backtest (monthly, before costs)</h3><div class="tbl"><table><thead><tr><th class="l">Rule</th><th>Sharpe</th><th>Ann.</th><th>Hit</th><th>Max DD*</th><th>Halves</th></tr></thead><tbody>
          ${bt('tsmom_12m', 'TSMOM 12m, 40% vol')}${bt('tsmom_12_1', 'TSMOM 12-1 (skip last month)')}${bt('long_only_scaled', 'Long-only, 40% vol (benchmark)')}${bt('carry', 'Carry sign, 40% vol')}</tbody></table></div>
          <p class="note">Correlation of the trend and carry returns: ${n(b.corr_tsmom_carry)}. They often overlap, so don't double-count them (GHR). *Drawdowns are sums of monthly % returns at 40% vol per market, so they look large. Halves are the first and second halves of the sample; a sign flip means no stable edge (Pardo).</p>
          <div class="chart" style="height:180px"><canvas id="sig-eq"></canvas></div></div>
        <div><h3>Options</h3>${o ? `<div class="tbl"><table><tbody>
          <tr><td class="l">${o.label} ATM IV · realized 20d · EWMA</td><td>${n(o.atm, 1)}% · ${n(o.rv20, 1)}% · ${n(o.ewma_rv, 1)}%</td></tr>
          <tr><td class="l">Vol premium IV − RV · variance IV² − RV²</td><td>${sgn(o.vol_prem, 1)} · ${sgn(o.var_prem, 1)}</td></tr>
          <tr><td class="l">25-delta risk reversal · IV 1-yr pct</td><td>${n(o.rr25, 1)} · ${nth(o.iv_pct1y)}</td></tr>
          <tr><td class="l">Term slope ${o.slope_pair || ''}</td><td>${o.slope == null ? '–' : sgn(o.slope, 1, ' pts')}</td></tr></tbody></table></div>` : '<p class="note">No CME option settlements yet (the nightly Mac run collects them).</p>'}
          ${d ? `<h3>Risk-neutral density, ${d.label} (${d.dte} days, F ${d.F})</h3><div class="chart" style="height:180px"><canvas id="sig-dens"></canvas></div>
          <div class="tbl"><table><thead><tr><th class="l">Move</th><th>P(down)</th><th>× lognormal</th><th>P(up)</th><th>× lognormal</th></tr></thead><tbody>
          ${d.tails.map(x => `<tr><td class="l">${x.k}σ (${x.move_pct}%)</td><td>${x.down}%</td><td>${n(x.down_ratio)}</td><td>${x.up}%</td><td>${n(x.up_ratio)}</td></tr>`).join('')}</tbody></table></div>
          <p class="note">These are risk-neutral odds from settlements (Breeden-Litzenberger). The smile is quadratic in log-moneyness, with flat wings beyond the last quoted strike. Quantiles: 5% ${d.quantiles[5]}, 50% ${d.quantiles[50]}, 95% ${d.quantiles[95]}.</p>` : ''}</div>
        <div><h3>Positioning and sizing</h3><div class="tbl"><table><tbody>
          ${p ? `<tr><td class="l">Managed money net % OI · 5-yr pct (${p.date})</td><td>${sgn(p.mm_np_oi, 1, '%')} · ${nth(Math.round(p.mm_pct5y))}</td></tr>
          <tr><td class="l">With the trend? · crowded?</td><td>${p.aligned ? 'yes' : 'no'} · ${p.crowded ? '<b>yes</b>' : 'no'}</td></tr>` : ''}
          <tr><td class="l">Contract notional</td><td>$${fmt(z.notional, 0)}</td></tr>
          <tr><td class="l">Contracts for 10% annual vol on $1M</td><td>${n(z.contracts_10pct_1m, 1)}</td></tr>
          <tr><td class="l">Inverse-vol (risk parity) weight across the desk</td><td>${n(z.invvol_weight, 1)}%</td></tr>
          <tr><td class="l">Half-Kelly upper bound on the trend strategy</td><td>${z.half_kelly_upper == null ? 'n/a (no edge)' : n(z.half_kelly_upper) + 'x'}</td></tr>
          <tr><td class="l">Avg daily volume (all months, 20d) · cost of a 1%-ADV order</td><td>${fmt(z.adv, 0)} · ~${n(z.cost_bps_1pct_adv, 1)} bp</td></tr></tbody></table></div>
          <p class="note">Kelly uses the backtest Sharpe halved, then half Kelly; it is an upper bound because errors in the mean dominate (MacLean-Thorp-Ziemba). Impact is 0.75 × daily vol × √(order/ADV) (Almgren; Chan). That calibration is for equities, and it excludes the bid-ask spread and limit days.</p></div>
      </div></div>`;
  }
  function draw(m) {
    chart('sig-vr', { type: 'line', data: { labels: m.vr.map(x => x[0]), datasets: [{ label: 'variance ratio', data: m.vr.map(x => x[1]), borderColor: PAL[0], pointRadius: 2 },
      { label: 'random walk = 1', data: m.vr.map(() => 1), borderColor: '#aaa', borderDash: [4, 3], pointRadius: 0 }] },
      options: { scales: { x: { title: { display: true, text: 'horizon (trading days)', font: { size: 10 } } } } } });
    chart('sig-carry', { type: 'line', data: { labels: m.carry.hist.map(x => x[0].slice(0, 7)), datasets: [{ label: `${m.sym} carry %/yr`, data: m.carry.hist.map(x => x[1]), borderColor: PAL[2], pointRadius: 0, borderWidth: 1.4 }] } });
    const e = m.equity, labs = e.tsmom_12m.map(x => x[0]);
    const al = (s) => { const mp = Object.fromEntries(s.map(x => [x[0], x[1]])); return labs.map(l => mp[l] ?? null); };
    chart('sig-eq', { type: 'line', data: { labels: labs, datasets: [{ label: 'TSMOM 12m', data: al(e.tsmom_12m), borderColor: PAL[0], pointRadius: 0, borderWidth: 1.4 },
      { label: 'long-only scaled', data: al(e.long_only_scaled), borderColor: '#999', pointRadius: 0, borderWidth: 1.2 },
      { label: 'carry', data: al(e.carry), borderColor: PAL[3], pointRadius: 0, borderWidth: 1.2 }] }, options: { scales: { y: { title: { display: true, text: 'cumulative %', font: { size: 10 } } } } } });
    if (m.density) chart('sig-dens', { type: 'line', data: { labels: m.density.curve.map(x => x[0]), datasets: [
      { label: 'options-implied', data: m.density.curve.map(x => x[1]), borderColor: PAL[1], pointRadius: 0, borderWidth: 1.6 },
      { label: 'lognormal at ATM vol', data: m.density.curve.map(x => x[2]), borderColor: '#999', borderDash: [4, 3], pointRadius: 0 }] },
      options: { scales: { y: { display: false } } } });
  }
  function render() {
    const el = document.getElementById('signals');
    el.innerHTML = `<main><div class="card"><h2>Research signals <span class="note">${R.generated}</span></h2>
      <p class="note">The commodity-futures, trend, volatility and sizing research in the library, computed for every market on the desk: trend, carry, inventories, options, positioning and sizing. Each item names its source paper. Backtests here are research checks, not trade recommendations.</p>
      ${table()}${xsCard()}</div><div id="sig-detail"></div>
      <div class="card"><h2>What each measure is based on</h2><div class="tbl"><table><tbody>${SRC.map(s => `<tr><td class="l" style="white-space:nowrap"><b>${s[0]}</b></td><td class="l">${s[1]}</td></tr>`).join('')}</tbody></table></div></div></main>`;
    $$('#signals .sig-row').forEach(r => r.onclick = ev => { ev.preventDefault(); pick(r.dataset.s); });
    pick(sym);
  }
  function pick(s) {
    sym = s;
    $$('#signals .sig-row').forEach(r => r.classList.toggle('on', r.dataset.s === s));
    const m = R.markets[s];
    $('#sig-detail').innerHTML = detail(m);
    history.replaceState(null, '', '#signals/' + s);
    try { draw(m); } catch (e) { console.warn('signals charts', e); }
  }
  async function show() {
    const hs = (location.hash.split('/')[1] || '').toUpperCase();
    if (!built) { R = await getJSON('data/research/research.json').catch(() => null); built = true; }
    if (!R) { document.getElementById('signals').innerHTML = '<main><div class="card"><p class="note">Research signals not built yet.</p></div></main>'; return; }
    sym = R.markets[hs] ? hs : sym && R.markets[sym] ? sym : Object.keys(R.markets)[0];
    render();
  }
  return { show };
})();
