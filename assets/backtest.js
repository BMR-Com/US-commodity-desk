// Backtest tab: trend, COT, carry, fundamental, seasonal and combined rules tested on every market (data/backtest/lab.json,
// models/backtest_lab.py). Deep link: #backtest/<SYM>.
const Backtest = (() => {
  let L = null, EQ = null, sym = 'ZC', key = null, built = false;
  const n = (v, d = 2) => v == null ? '–' : (+v).toFixed(d);
  const sg = (v, d = 2) => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${(+v).toFixed(d)}</span>`;
  const tbl = (head, rows, cls = '') => `<div class="tbl"><table class="${cls}"><tr>${head.map((h, i) => `<th class="${i < 2 ? 'l' : ''}">${h}</th>`).join('')}</tr>${rows.join('')}</table></div>`;
  const rank = (rows, title) => `<h3>${title}</h3>` + tbl(['Market', 'Strategy', 'Sharpe', 'Out of sample', 'In sample', 'Ann. %', 'Hit %', 'Max DD %', 'Trades'],
    rows.map(r => `<tr class="bt-row" data-s="${r.market}" data-k="${r.key}"><td class="l"><b>${r.name_m}</b></td><td class="l">${r.strategy}</td><td>${sg(r.sharpe)}</td><td>${sg(r.oos_sharpe)}</td><td>${sg(r.is_sharpe)}</td><td>${sg(r.ann, 1)}</td><td>${n(r.hit, 0)}</td><td>${n(r.maxdd, 0)}</td><td>${r.trades}</td></tr>`));
  function market() {
    const rows = L.results.filter(r => r.market === sym).sort((a, b) => (b.enough - a.enough) || (b.sharpe - a.sharpe));
    const lo = rows.find(r => r.key === 'long_only');
    if (!key || !rows.some(r => r.key === key)) key = rows[0]?.key;
    const pm = L.per_market[sym] || {};
    $('#btMkt').innerHTML = `<div class="mk-bar" style="margin:0 0 10px;flex-wrap:wrap">${Object.entries(L.per_market).map(([k, v]) => `<button data-m="${k}" class="${k === sym ? 'on' : ''}" title="${v.group}">${v.name}</button>`).join('')}</div>
      <p>${pm.read || ''}</p><p class="note">Data ${L.coverage[sym]?.from} to ${L.coverage[sym]?.to}; ${L.coverage[sym]?.source}. Long-only rules (covering, low producer longs, fundamentals long) should be compared with the long-only benchmark (Sharpe ${lo ? lo.sharpe : '–'}).</p>
      <div class="chart" style="height:260px"><canvas id="btEq"></canvas></div>
      ${tbl(['Strategy', 'Family', 'Sharpe', 'OOS (2019+)', 'IS (to 2018)', 'Ann. %', 'Vol %', 'Hit %', 'Max DD %', 'Trades', 'In market %', 'Sharpe at 4x cost', 'Event: fwd 4 wk %', 'fwd 13 wk %', 'Spec Δ 4 wk (% OI)'],
        rows.map(r => `<tr class="bt-row${r.key === key ? ' on' : ''}" data-k="${r.key}"><td class="l">${r.strategy}${r.robust ? ' ✓' : ''}${r.enough ? '' : ' <span class="note">(too few trades)</span>'}</td><td class="l note">${r.family}</td><td><b>${sg(r.sharpe)}</b></td><td>${sg(r.oos_sharpe)}</td><td>${sg(r.is_sharpe)}</td>
          <td>${sg(r.ann, 1)}</td><td>${n(r.vol, 1)}</td><td>${n(r.hit, 0)}</td><td>${n(r.maxdd, 0)}</td><td>${r.trades}</td><td>${n(r.exposure, 0)}</td><td>${sg(r.sharpe_4x_cost)}</td>
          <td>${r.fwd4 == null ? '' : sg(r.fwd4) + ` <span class="note">(${r.events} ev, ${r.fwd4_hit}% right)</span>`}</td><td>${r.fwd13 == null ? '' : sg(r.fwd13)}</td><td>${r.spec_d4 == null ? '' : sg(r.spec_d4, 1)}</td></tr>`), 'bt-t')}
      <p class="note">✓ = positive Sharpe in both halves (to 2018 and 2019 on) with at least 10 trades. Rules with too few trades are listed last. Click a row for its equity curve.</p>`;
    $$('#btMkt [data-m]').forEach(b => b.onclick = () => { sym = b.dataset.m; key = null; market(); history.replaceState(null, '', '#backtest/' + sym); });
    $$('#btMkt .bt-row').forEach(r => r.onclick = () => { key = r.dataset.k; market(); });
    drawEq();
  }
  async function drawEq() {
    if (!EQ) EQ = await getJSON('data/backtest/equity.json').catch(() => ({}));
    const a = EQ[`${sym}|${key}`] || [], b = EQ[`${sym}|long_only`] || [];
    const lab = a.map(x => x[0]), mb = Object.fromEntries(b.map(x => [x[0], x[1]]));
    const nm = L.results.find(r => r.market === sym && r.key === key)?.strategy || key;
    chart('btEq', { type: 'line', data: { labels: lab, datasets: [{ label: nm.slice(0, 70), data: a.map(x => x[1]), borderColor: PAL[0], pointRadius: 0, borderWidth: 1.6 },
      { label: 'long only', data: lab.map(l => mb[l] ?? null), borderColor: '#999', pointRadius: 0, borderWidth: 1.1 }] },
      options: { scales: { y: { title: { display: true, text: 'cumulative % at 10% vol', font: { size: 10 } } } } } });
  }
  function render() {
    const el = document.getElementById('backtest');
    el.innerHTML = `<main>
      <div class="card"><h2>Backtest lab <span class="note">${L.generated} · ${L.n_tests} rule × market tests · 2007–${L.generated.slice(0, 4)}</span></h2>
        <p>Every rule is traded on every market with the same discipline: signals use only information known on Friday (CFTC positions come out Friday afternoon), positions start at the next trading day's close and are rebalanced weekly; each strategy is scaled to ${L.target_vol * 100}% annual volatility per market with ${L.cost_bp} bp cost per unit traded; results are split into in-sample (to 2018) and out-of-sample (2019 on). Prices are roll-adjusted contract series, so roll gaps do not create fake returns.</p>
        <p class="note"><b>Read with care:</b> with ${L.n_tests} tests the best Sharpe that pure luck would produce is about <b>${L.noise_sharpe}</b>. A rule that beats that, is positive in both halves and works across many markets is evidence; a single strong market is not. Fundamentals use USDA PSD final stocks/use (later revisions are known in hindsight), so those results are optimistic. Max drawdown is the sum of weekly % returns at 10% vol (it can exceed 100% over 19 years).</p>
        <h3>What the tests say</h3><ul class="read">${L.learnings.map(x => `<li>${x}</li>`).join('')}</ul></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>By family</h2>${tbl(['Family', '', 'Tests', 'Median Sharpe', '% positive', '% robust (both halves)', 'Median OOS'], L.families.map(f => `<tr><td class="l"><b>${f.family}</b></td><td></td><td>${f.tests}</td><td>${sg(f.median_sharpe)}</td><td>${f.pos_share}%</td><td>${f.robust_share}%</td><td>${sg(f.median_oos)}</td></tr>`))}</div>
        <div class="card"><h2>How specs respond to signals <span class="note">median across markets</span></h2>${tbl(['Event', '', 'Events', 'Price 4 wk %', 'Price 13 wk %', 'Spec Δ 4 wk (% OI)', 'Spec Δ 8 wk', 'Specs bought'],
          (L.spec_response || []).map(r => `<tr><td class="l" colspan="2">${r.strategy}</td><td>${r.events}</td><td>${sg(r.fwd4)}</td><td>${sg(r.fwd13)}</td><td>${sg(r.spec_d4, 1)}</td><td>${sg(r.spec_d8, 1)}</td><td>${n(r.spec_buy_share, 0)}%</td></tr>`))}
          <p class="note">Price columns are in the trade's direction (short rules: a positive number means price fell). Spec Δ = change in managed-money net position as % of open interest after the event (normal 4-week drift ≈ 0).</p></div></div>
      <div class="card" style="margin-top:12px"><h2>Each rule across all markets</h2>${tbl(['Strategy', 'Family', 'Markets', 'Median Sharpe', '% positive', '% robust', 'Median OOS', 'Median hit %', 'Median max DD %'],
        L.strategies.map(s => `<tr><td class="l">${s.strategy}</td><td class="l note">${s.family}</td><td>${s.markets}</td><td><b>${sg(s.median_sharpe)}</b></td><td>${s.pos_share}%</td><td>${s.robust_share}%</td><td>${sg(s.median_oos)}</td><td>${n(s.median_hit, 0)}</td><td>${n(s.median_dd, 0)}</td></tr>`))}</div>
      <div class="card" style="margin-top:12px"><h2>Top 10 and bottom 10 <span class="note">by full-period Sharpe; rules in the market at least 10% of the time</span></h2>
        ${rank(L.top, 'Best 10')}${rank(L.top_oos, 'Best 10 that also held up out of sample (ranked by 2019+ Sharpe)')}${rank(L.bottom, 'Worst 10')}</div>
      <div class="card" style="margin-top:12px"><h2>By market</h2><div id="btMkt"></div></div></main>`;
    $$('#backtest .card .bt-row').forEach(r => r.onclick = () => { if (r.dataset.s) { sym = r.dataset.s; key = r.dataset.k; market(); document.getElementById('btMkt').scrollIntoView({ behavior: 'smooth' }); } });
    market();
  }
  async function show() {
    const hs = (location.hash.split('/')[1] || '').toUpperCase();
    if (!built) { L = await getJSON('data/backtest/lab.json').catch(() => null); built = true; }
    if (!L) { document.getElementById('backtest').innerHTML = '<main><div class="card"><p class="note">Backtests not built yet.</p></div></main>'; return; }
    if (L.per_market[hs]) sym = hs;
    render();
    if (!location.hash.startsWith('#backtest')) history.replaceState(null, '', '#backtest');
  }
  return { show };
})();
