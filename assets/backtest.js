// Backtest tab: trend, COT, carry, fundamental, seasonal and combined rules tested on every market (data/backtest/lab.json,
// models/backtest_lab.py). Deep link: #backtest/<SYM>.
const Backtest = (() => {
  let L = null, EQ = null, BK = null, sym = 'ZC', key = null, bkey = null, built = false, sub = 'bt-baskets';
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
    el.innerHTML = `<nav class="tabs" id="btTabs"><button data-t="bt-baskets">Baskets (portfolios across commodities)</button><button data-t="bt-rules">Single-market rules</button><button data-t="bt-dairy">Dairy deep dive</button></nav><div id="btBody"></div>`;
    $$('#btTabs button').forEach(b => b.onclick = () => { sub = b.dataset.t; history.replaceState(null, '', '#' + sub); paint(); });
    paint();
  }
  function paint() {
    $$('#btTabs button').forEach(b => b.classList.toggle('on', b.dataset.t === sub));
    if (sub === 'bt-baskets') return baskets();
    if (sub === 'bt-dairy') return dairy();
    rules();
  }
  function bstat(x, k) { return x[k] ? x[k].sharpe : null; }
  function baskets() {
    const el = $('#btBody');
    if (!BK) { el.innerHTML = '<main><p class="note">Basket backtests not built yet.</p></main>'; return; }
    const S = BK.strategies;
    if (!bkey) bkey = S[0].key;
    const groups = [...new Set(S.map(s => s.group))];
    el.innerHTML = `<main><div class="card"><h2>Basket strategies <span class="note">${BK.generated} · ${BK.markets.length} markets · weekly rebalance · ${BK.target_vol * 100}% vol target · ${BK.cost_bp} bp per unit traded</span></h2>
      <p>Each basket goes long and short several commodities at once, the way commodity quant funds trade: every position is risk-weighted (equal volatility per market) and the whole basket is scaled to 10% annual volatility from its own past volatility. Signals use Friday information and trade from the next day's close. Split: 2008-2018 (in-sample) and 2019 on (out-of-sample).</p>
      <h3>What the tests say</h3><ul class="read">${BK.learnings.map(x => `<li>${x}</li>`).join('')}</ul>
      <p class="note">Calmar = annual return / max drawdown (higher = more return per unit of pain). Drawdowns are sums of weekly % returns at 10% volatility. Gross Sharpe is before costs: fast signals (1-2 weeks) trade a lot, so costs decide whether they work.</p></div>
      <div class="card" style="margin-top:12px"><h2>All baskets <span class="note">click a row for its equity curve and today's positions</span></h2>
      <div class="tbl"><table class="bt-t"><tr><th class="l">Strategy</th><th class="l">Type</th><th>Sharpe</th><th>2008-18</th><th>2019+</th><th>Gross Sharpe</th><th>Ann. %</th><th>Max DD %</th><th>Calmar</th><th>Hit % (weeks)</th><th>Worst week %</th><th>Longest DD (wk)</th><th>Avg long / short</th><th>Cost % p.a.</th></tr>
      ${S.map(x => `<tr class="bt-row${x.key === bkey ? ' on' : ''}" data-b="${x.key}"><td class="l">${x.name}<br><span class="note">${x.lit}</span></td><td class="l note">${x.group}</td><td><b>${sg(x.sharpe)}</b></td><td>${sg(bstat(x, 'is'))}</td><td>${sg(bstat(x, 'oos'))}</td><td>${sg(x.sharpe_gross)}</td>
        <td>${sg(x.ann, 1)}</td><td>${n(x.maxdd, 0)}</td><td>${n(x.calmar)}</td><td>${n(x.hit, 0)}</td><td>${n(x.worst_week, 1)}</td><td>${x.longest_dd_weeks ?? '–'}</td><td>${x.n_long ?? '–'} / ${x.n_short ?? '–'}</td><td>${n(x.cost_pa, 1)}</td></tr>`).join('')}</table></div></div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2 id="bkT"></h2><div class="chart" style="height:280px"><canvas id="bkEq"></canvas></div></div>
        <div class="card"><h2>Positions in the latest week <span class="note" id="bkD"></span></h2><div id="bkBook"></div></div></div></main>`;
    $$('#btBody .bt-row').forEach(r => r.onclick = () => { bkey = r.dataset.b; baskets(); });
    const x = S.find(s => s.key === bkey), lo = S.find(s => s.key === 'long_only');
    $('#bkT').textContent = x.name;
    const lab = x.equity.map(e => e[0]), lm = Object.fromEntries((lo?.equity || []).map(e => [e[0], e[1]]));
    chart('bkEq', { type: 'line', data: { labels: lab, datasets: [{ label: x.name.slice(0, 60), data: x.equity.map(e => e[1]), borderColor: PAL[0], pointRadius: 0, borderWidth: 1.6 },
      ...(x.key !== 'long_only' ? [{ label: 'equal-risk long only', data: lab.map(l => lm[l] ?? null), borderColor: '#999', pointRadius: 0, borderWidth: 1.1 }] : [])] },
      options: { scales: { y: { title: { display: true, text: 'cumulative % at 10% vol', font: { size: 10 } } } } } });
    $('#bkD').textContent = x.book_date ? `(signals of ${x.book_date})` : '';
    $('#bkBook').innerHTML = x.members ? `<p>Members: ${x.members.map(k => S.find(s => s.key === k)?.name || k).join('; ')}</p>` : x.book && x.book.length ?
      `<div class="tbl"><table><tr><th class="l">Market</th><th>Weight (risk units)</th><th class="l">Side</th></tr>${x.book.map(b => `<tr><td class="l">${b.market}</td><td>${sg(b.weight, 2)}</td><td class="l">${b.weight > 0 ? 'long' : 'short'}</td></tr>`).join('')}</table></div>
      <p class="note">Weights are in leverage units after volatility targeting; research positions, not advice.</p>` : '<p class="note">Flat this week.</p>';
  }
  function dairy() {
    const el = $('#btBody');
    if (!BK || !BK.dairy) { el.innerHTML = '<main><p class="note">Not built yet.</p></main>'; return; }
    const d = BK.dairy, b = d.basket || {};
    el.innerHTML = `<main><div class="card"><h2>Why trend rules work in dairy futures</h2>
      <p><b>The mechanism.</b> CME Class III and IV milk, cheese, butter, nonfat dry milk and dry whey futures are cash-settled to USDA's monthly announced prices, which are averages of four or five weekly NDPSR survey prices (and, for Class III/IV, formulas built on those product prices). Once a month is under way, part of its settlement price is already known, and the weekly survey prices themselves move in steps that follow the CME spot cheese, butter and powder markets with a lag. So futures prices inherit slow, persistent moves: when a contract starts rising it tends to keep rising for several weeks, and breakout or moving-average rules ride that.</p>
      <p><b>The evidence.</b> Weekly returns of the roll-adjusted series since 2012 have positive autocorrelation in dairy (Class IV ${d.markets.find(m => m.sym === 'GDK')?.ac1}, cheese ${d.markets.find(m => m.sym === 'CSC')?.ac1}, nonfat ${d.markets.find(m => m.sym === 'GNF')?.ac1}, Class III ${d.markets.find(m => m.sym === 'DC')?.ac1}) against a median of ${d.other_median_ac1} for the other markets, where returns are close to random week to week. The dairy trend basket (20-day breakouts in all six, equal risk) has Sharpe <b>${n(b.sharpe)}</b> (2008-18 ${n(d.basket_is?.sharpe)}, 2019+ ${n(d.basket_oos?.sharpe)}), max drawdown ${n(b.maxdd, 1)}% and a weekly hit rate of ${n(b.hit, 0)}% at 10% volatility.</p>
      <p><b>The catch.</b> These markets are thin: average daily volume (all months) is roughly ${d.markets.map(m => `${m.market} ${m.adv ? m.adv.toLocaleString() : '–'}`).join(', ')} contracts, versus hundreds of thousands in corn or crude. Bid-ask spreads are wide and a fund could only run small size; the backtest uses closing settlements, so real fills would be worse (the 4x-cost column shows the edge mostly survives higher costs, but not slippage from moving the market). Class III milk, the most liquid, has the weakest out-of-sample result. Butter, Class IV and nonfat carry the edge.</p></div>
      <div class="card" style="margin-top:12px"><h2>By contract</h2><div class="tbl"><table class="bt-t"><tr><th class="l">Contract</th><th>Data from</th><th>Weekly autocorr.</th><th>Avg daily volume</th><th>Notional ($)</th><th class="l">20-day breakout now</th><th class="l">Best rules (Sharpe · 2019+ · hit % · max DD % · trades · Sharpe at 4x cost)</th></tr>
      ${d.markets.map(m => `<tr><td class="l"><b>${m.market}</b></td><td>${m.since}</td><td>${n(m.ac1)}</td><td>${m.adv ? m.adv.toLocaleString() : '–'}</td><td>${m.notional ? m.notional.toLocaleString() : '–'}</td><td class="l">${m.now}</td>
        <td class="l">${m.best.map(x => `${x.strategy}: ${n(x.sharpe)} · ${n(x.oos)} · ${n(x.hit, 0)} · ${n(x.maxdd, 0)} · ${x.trades} · ${n(x.cost4)}`).join('<br>')}</td></tr>`).join('')}</table></div></div>
      <div class="card" style="margin-top:12px"><h2>Persistence by market <span class="note">lag-1 autocorrelation of weekly returns, 2012 on</span></h2><div class="chart" style="height:300px"><canvas id="dyAc"></canvas></div></div></main>`;
    chart('dyAc', { type: 'bar', data: { labels: d.autocorr.map(a => a.market), datasets: [{ label: 'weekly return autocorrelation', data: d.autocorr.map(a => a.ac1), backgroundColor: d.autocorr.map(a => a.group === 'Dairy' ? '#d68910' : '#9bb7d9') }] },
      options: { plugins: { legend: { display: false } }, scales: { x: { ticks: { autoSkip: false, maxRotation: 70, font: { size: 9 } } } } } });
  }
  function rules() {
    const el = $('#btBody');
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
    $$('#btBody .card .bt-row').forEach(r => r.onclick = () => { if (r.dataset.s) { sym = r.dataset.s; key = r.dataset.k; market(); document.getElementById('btMkt').scrollIntoView({ behavior: 'smooth' }); } });
    market();
  }
  async function show() {
    const hs = (location.hash.split('/')[1] || '').toUpperCase();
    if (!built) { [L, BK] = await Promise.all([getJSON('data/backtest/lab.json').catch(() => null), getJSON('data/backtest/baskets.json').catch(() => null)]); built = true; }
    const h = location.hash.slice(1); if (/^bt-(baskets|rules|dairy)$/.test(h)) sub = h; else if (hs) sub = 'bt-rules';
    if (!L) { document.getElementById('backtest').innerHTML = '<main><div class="card"><p class="note">Backtests not built yet.</p></div></main>'; return; }
    if (L.per_market[hs]) sym = hs;
    render();
    if (!location.hash.startsWith('#backtest') && !location.hash.startsWith('#bt-')) history.replaceState(null, '', '#backtest');
  }
  return { show };
})();
