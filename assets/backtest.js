// Backtest tab: trend, COT, carry, fundamental, seasonal and combined rules tested on every market (data/backtest/lab.json,
// models/backtest_lab.py). Deep link: #backtest/<SYM>.
const Backtest = (() => {
  let L = null, EQ = null, BK = null, TL = null, tsym = 'ZC', sym = 'ZC', key = null, bkey = null, built = false, sub = 'bt-baskets';
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
    el.innerHTML = `<nav class="tabs" id="btTabs"><button data-t="bt-baskets">Baskets (portfolios across commodities)</button><button data-t="bt-rules">Single-market rules</button><button data-t="bt-tech">Technical patterns</button><button data-t="bt-regime">2020-23 vs 2024-25</button><button data-t="bt-dairy">Dairy deep dive</button></nav><div id="btBody"></div>`;
    el.insertAdjacentHTML('afterbegin', topFindings());
    $$('#btTabs button').forEach(b => b.onclick = () => { sub = b.dataset.t; history.replaceState(null, '', '#' + sub); paint(); });
    paint();
  }
  function paint() {
    $$('#btTabs button').forEach(b => b.classList.toggle('on', b.dataset.t === sub));
    if (sub === 'bt-baskets') return baskets();
    if (sub === 'bt-dairy') return dairy();
    if (sub === 'bt-tech') return tech();
    if (sub === 'bt-regime') return regime();
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

  // the few results worth acting on, from all three labs, always shown above the sub-tabs
  function topFindings() {
    const li = [];
    if (BK) {
      const b = BK.strategies.filter(x => x.key !== 'long_only' && (x.oos?.sharpe ?? 0) > 0 && (x.is?.sharpe ?? 0) > 0).sort((a, c) => c.sharpe - a.sharpe).slice(0, 4);
      li.push(`<li><b>Best baskets</b> (positive in 2008-18 and 2019+): ${b.map(x => `${x.name} <b>${n(x.sharpe)}</b> <span class="note">(2019+ ${n(x.oos.sharpe)}, max DD ${n(x.maxdd, 0)}%)</span>`).join('; ')}.</li>`);
    }
    if (TL) {
      const p = TL.pooled.filter(r => r.markets >= 12).slice(0, 3);
      li.push(`<li><b>Best technical patterns across markets</b>: ${p.map(r => `${r.rule} (${r.side}, ${r.hold}d) median Sharpe <b>${n(r.sharpe)}</b>, win ${n(r.win, 0)}%, positive in ${r.pos_share}% of markets`).join('; ')}.</li>`);
      const t = TL.top.slice(0, 4);
      li.push(`<li><b>Best single-market patterns</b> (robust in both halves): ${t.map(r => `${r.name_m} ${r.rule} (${r.side}, ${r.hold}d) <b>${n(r.sharpe)}</b>, win ${n(r.win, 0)}%`).join('; ')}.</li>`);
      const fm = TL.families.filter(f => f.side === 'long').sort((a, c) => c.sharpe - a.sharpe);
      li.push(`<li><b>By family (long side, median Sharpe)</b>: ${fm.map(f => `${f.family} ${sg(f.sharpe)}`).join(' · ')}. Breakouts and trend-following crossovers beat oversold / mean-reversion buys, which lose after costs in most markets.</li>`);
      const r = (TL.recovery.pooled || []).find(x => x.k == 5);
      if (r) li.push(`<li><b>Price 5% below the 9-day MA</b>: it "recovers" to the 9-day MA in ${n(r.recovered_pct, 0)}% of cases within 20 days, but mostly because the average falls to meet price; it regains the signal day's 9-day MA level only ${n(r.orig_pct, 0)}% of the time and the 10-day return is ${sg(r.r10)}% - no edge on its own.</li>`);
    }
    if (BK && BK.strategies[0].r_oos !== undefined) {
      const ok = BK.strategies.filter(x => x.key !== 'long_only' && x.r_is && x.r_oos && x.r_is.sharpe > 0 && x.r_oos.sharpe > 0).sort((a, c) => Math.min(c.r_is.sharpe, c.r_oos.sharpe) - Math.min(a.r_is.sharpe, a.r_oos.sharpe)).slice(0, 3);
      li.push(`<li><b>Recent regime (fit 2020-23, test 2024-25)</b>: ${ok.map(x => `${x.name} ${n(x.r_is.sharpe)} → <b>${n(x.r_oos.sharpe)}</b>`).join('; ')}. Single-market breakouts and MACD/EMA trend entries stopped working in 2024-25 while short-term mean reversion inside a trend improved; diversified trend baskets kept working. See the 2020-23 vs 2024-25 sub-tab.</li>`);
    }
    if (L) li.push(`<li><b>COT on its own</b> has no reliable timing edge; trend (20-55 day breakouts, moving-average crosses) is the only family that works broadly, and dairy is the strongest trending group.</li>`);
    return `<main style="padding-bottom:0"><div class="card"><h2>Top findings <span class="note">best results from every test on this tab; details in the sub-tabs below</span></h2><ul class="read">${li.join('')}</ul></div></main>`;
  }
  function tech() {
    const el = $('#btBody');
    if (!TL) { el.innerHTML = '<main><p class="note">Technical pattern tests not built yet.</p></main>'; return; }
    const pt = (rows) => tbl(['Market', 'Pattern', 'Side', 'Hold (days)', 'Trades', 'Win %', 'Avg %', 'Edge vs any day %', 'Profit factor', 'Avg worst dip %', 'Sharpe', '2007-18', '2019+', 'Max DD %'],
      rows.map(r => `<tr><td class="l"><b>${r.name_m}</b></td><td class="l">${r.rule}</td><td>${r.side}</td><td>${r.hold}</td><td>${r.n}</td><td>${n(r.win, 0)}</td><td>${sg(r.avg)}</td><td>${sg(r.edge)}</td><td>${n(r.pf)}</td><td>${n(r.mae, 1)}</td><td><b>${sg(r.sharpe)}</b></td><td>${sg(r.is_sharpe)}</td><td>${sg(r.oos_sharpe)}</td><td>${n(r.maxdd, 0)}</td></tr>`), 'bt-t');
    const pool = (rows) => tbl(['Pattern', 'Family', 'Side', 'Hold', 'Markets', 'Trades', 'Median win %', 'Median edge %', 'Median avg worst dip %', 'Median Sharpe', '% markets positive', '% robust', 'Median 2019+'],
      rows.map(r => `<tr><td class="l">${r.rule}</td><td class="l note">${r.family}</td><td>${r.side}</td><td>${r.hold}</td><td>${r.markets}</td><td>${r.trades}</td><td>${n(r.win, 0)}</td><td>${sg(r.edge)}</td><td>${n(r.mae, 1)}</td><td><b>${sg(r.sharpe)}</b></td><td>${r.pos_share}%</td><td>${r.robust}%</td><td>${sg(r.oos)}</td></tr>`), 'bt-t');
    const P = TL.pooled.filter(r => r.markets >= 12);
    const rec = TL.recovery.pooled, pb = TL.pullback.pooled;
    const mk = Object.keys(TL.per_market);
    if (!TL.per_market[tsym]) tsym = mk[0];
    el.innerHTML = `<main>
      <div class="card"><h2>Technical patterns <span class="note">${TL.generated} · ${TL.n_tests} pattern × market × holding-period tests · daily, 2007 on</span></h2>
        <p>Classic chart setups on the daily roll-adjusted price of every desk market: RSI(14) and RSI(2) oversold / overbought, % below or above the 9-day average, Bollinger re-entry, runs of down days, stochastic, pullbacks to the 9/20/50-day average in a trend, MACD and moving-average crosses, 20/55-day breakouts and RSI / MACD divergences, each long and short and with or without a 200-day trend filter. Signal at a day's close, entry at the next close, exit after 5, 10 or 20 days; no overlapping trades; 5 bp cost per side.</p>
        <p class="note"><b>Edge vs any day</b> = average trade return minus the average return of holding any day for the same length in the same direction (markets drift, so a win rate alone flatters long rules). <b>Avg worst dip</b> = average maximum drawdown inside a trade. Sharpe is per market at 10% volatility. With ${TL.n_tests} tests, a t-stat near ${TL.noise_t} is what the luckiest test shows by chance: trust patterns that work in many markets and in both 2007-18 and 2019+.</p>
        <h3>What the tests say (best first)</h3><ul class="read">${TL.learnings.slice(0, 4).map(x => `<li>${x}</li>`).join('')}</ul>
        <details><summary>All ${TL.learnings.length} findings (weakest patterns, families, 9-day MA recovery, dip buying)</summary><ul class="read">${TL.learnings.slice(4).map(x => `<li>${x}</li>`).join('')}</ul></details></div>
      <div class="card" style="margin-top:12px"><h2>Best patterns across markets <span class="note">median over the markets tested; patterns tested in 12+ markets</span></h2>${pool(P.slice(0, 12))}
        <details><summary>All ${P.length} pooled patterns (best to worst)</summary>${pool(P)}</details></div>
      <div class="card" style="margin-top:12px"><h2>Best single-market patterns <span class="note">20+ trades, positive in both halves</span></h2>${pt(TL.top)}
        <details><summary>Highest win rate (robust, 30+ trades)</summary>${pt(TL.best_win)}</details>
        <details><summary>Lowest drawdown with Sharpe above 0.3</summary>${pt(TL.low_dd)}</details>
        <details><summary>Worst 10</summary>${pt(TL.worst)}</details></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>After a close X% below the 9-day MA <span class="note">all markets, next 20 days</span></h2>${tbl(['Below 9-day by', '', 'Cases', 'Touches 9-day MA %', 'Median days', 'Regains signal-day MA level %', 'Avg dip first %', 'Worst dip %', '5d %', '10d %', '20d %', 'Up after 10d %'],
          rec.map(r => `<tr><td class="l"><b>${r.k}%</b></td><td></td><td>${r.events}</td><td>${n(r.recovered_pct, 0)}</td><td>${n(r.days_median, 0)}</td><td>${n(r.orig_pct, 0)}</td><td>${n(r.mae_avg, 1)}</td><td>${n(r.mae_worst, 0)}</td><td>${sg(r.r5)}</td><td>${sg(r.r10)}</td><td>${sg(r.r20)}</td><td>${n(r.win10, 0)}</td></tr>`))}
          <p class="note">"Touches" counts any close at or above the moving 9-day average, which falls toward price, so it is almost always true; "regains signal-day level" asks whether price gets back to where the average was. 10% cases are rare (mostly energy and hogs) and dominated by a few crash rebounds.</p>
          <details><summary>By market</summary>${tbl(['Market', '', 'Below by', 'Cases', 'Regains level %', 'Avg dip %', '10d %', 'Up after 10d %'], Object.entries(TL.recovery.by_market).flatMap(([m, v]) => Object.entries(v).map(([k, r]) => `<tr><td class="l">${m}</td><td></td><td>${k}%</td><td>${r.events}</td><td>${n(r.orig_pct, 0)}</td><td>${n(r.mae_avg, 1)}</td><td>${sg(r.r10)}</td><td>${n(r.win10, 0)}</td></tr>`)))}</details></div>
        <div class="card"><h2>Buying the dip in an uptrend <span class="note">50-day above a rising 200-day; first close at or below the average</span></h2>${tbl(['Dip to', '', 'Cases', 'New 20-day high within 20d %', 'Closed below 50-day %', 'Avg dip %', '10d %', '20d %', 'Up after 20d %'],
          pb.map(r => `<tr><td class="l"><b>${r.k}-day MA</b></td><td></td><td>${r.events}</td><td>${n(r.new_high_pct, 0)}</td><td>${n(r.broke50_pct, 0)}</td><td>${n(r.mae_avg, 1)}</td><td>${sg(r.r10)}</td><td>${sg(r.r20)}</td><td>${n(r.win20, 0)}</td></tr>`))}
          <details><summary>By market</summary>${tbl(['Market', '', 'Dip to', 'Cases', 'New high %', 'Avg dip %', '20d %', 'Up %'], Object.entries(TL.pullback.by_market).flatMap(([m, v]) => Object.entries(v).map(([k, r]) => `<tr><td class="l">${m}</td><td></td><td>${k}-day</td><td>${r.events}</td><td>${n(r.new_high_pct, 0)}</td><td>${n(r.mae_avg, 1)}</td><td>${sg(r.r20)}</td><td>${n(r.win20, 0)}</td></tr>`)))}</details></div></div>
      <div class="card" style="margin-top:12px"><h2>By market <select id="tlSel">${mk.map(k => `<option value="${k}"${k === tsym ? ' selected' : ''}>${TL.per_market[k].name}</option>`).join('')}</select></h2><div id="tlMkt"></div></div>
      <div class="card" style="margin-top:12px"><h2>By family</h2>${tbl(['Family', 'Side', 'Tests', 'Median Sharpe', 'Median win %', 'Median edge %', '% positive', '% robust'], TL.families.map(f => `<tr><td class="l"><b>${f.family}</b></td><td class="l">${f.side}</td><td>${f.tests}</td><td>${sg(f.sharpe)}</td><td>${n(f.win, 0)}</td><td>${sg(f.edge)}</td><td>${f.pos}%</td><td>${f.robust}%</td></tr>`))}</div></main>`;
    const pm = () => { const x = TL.per_market[tsym]; $('#tlMkt').innerHTML = `<h3>Best (robust)</h3>${x.best.length ? pt(x.best) : '<p class="note">No pattern was positive in both halves with 20+ trades.</p>'}<h3>Worst</h3>${pt(x.worst)}`; };
    $('#tlSel').onchange = e => { tsym = e.target.value; pm(); };
    pm();
  }

  // recent regime: 2020-2023 as the fitting window, 2024-2025 as the test, 2026 so far; short-term (about a week) and long-term (several weeks) separately
  function regime() {
    const el = $('#btBody');
    const R = TL && TL.regime;
    const sh = (x) => x ? sg(x.sharpe) : '–';
    const mn = (a, b) => (a == null || b == null) ? -9 : Math.min(a, b);
    const HZ = [['Short-term (about a week)', 'st', 'Short-term: positions that last about a week'], ['Long-term', 'lt', 'Long-term: positions held for several weeks']];
    const isH = (h, k) => (h || '').startsWith(k === 'st' ? 'Short' : 'Long');
    let html = `<main><div class="card"><h2>Recent regime check <span class="note">fit window 2020-2023 · test window 2024-2025 · 2026 so far</span></h2>
      <p>Markets may have changed after 2019 (COVID, the 2021-22 inflation spike, then falling grain prices and record cattle). Here every test is re-scored on two recent windows: <b>2020-2023</b> (the period a trader would have chosen a strategy on) and <b>2024-2025</b> (the test), with 2026 so far shown as a live check. Strategies are split by how long a position lasts: <b>short-term</b> (about one week) and <b>long-term</b> (several weeks). Ranking is by the weaker of the two windows, so a strategy only ranks high if it worked in both.</p>
      <p class="note">Two years is short: a single market's 2024-25 result rests on 5-30 trades, so treat single-market rows as leads. Pooled results across 20 markets and diversified baskets are much more reliable. Sharpe at 10% volatility, after costs.</p>
      ${R ? `<h3>What the tests say</h3><ul class="read">${R.learnings.slice(0, 4).map(x => `<li>${x}</li>`).join('')}</ul><details><summary>More</summary><ul class="read">${R.learnings.slice(4).map(x => `<li>${x}</li>`).join('')}</ul></details>` : ''}</div>`;
    if (BK) {
      const bt = (rows) => tbl(['Basket', 'Avg hold (wk)', 'Full', '2008-18', '2020-23', '2024-25', '2026', 'Max DD 2024-25 %', 'Worked in both'], rows.map(x => `<tr><td class="l">${x.name}</td><td>${n(x.hold_wk, 1)}</td><td>${sg(x.sharpe)}</td><td>${sh(x.is)}</td><td><b>${sh(x.r_is)}</b></td><td><b>${sh(x.r_oos)}</b></td><td>${sh(x.live)}</td><td>${x.r_oos ? n(x.r_oos.maxdd, 0) : '–'}</td><td>${x.r_is && x.r_oos && x.r_is.sharpe > 0 && x.r_oos.sharpe > 0 ? '✓' : ''}</td></tr>`), 'bt-t');
      const S = BK.strategies.filter(x => x.key !== 'long_only').sort((a, c) => mn(c.r_is?.sharpe, c.r_oos?.sharpe) - mn(a.r_is?.sharpe, a.r_oos?.sharpe));
      const lo = BK.strategies.find(x => x.key === 'long_only');
      html += `<div class="card" style="margin-top:12px"><h2>Baskets across commodities <span class="note">benchmark equal-risk long-only: 2020-23 ${sh(lo?.r_is)}, 2024-25 ${sh(lo?.r_oos)}</span></h2>
        ${HZ.map(([h, k, t]) => { const rr = S.filter(x => isH(x.horizon, k)); return rr.length ? `<h3>${t}</h3>${bt(rr.slice(0, 8))}${rr.length > 8 ? `<details><summary>All ${rr.length}</summary>${bt(rr.slice(8))}</details>` : ''}` : ''; }).join('')}
        <h3>Blends</h3>${bt(S.filter(x => x.group === 'Blend'))}
        <p class="note">"Recent blend" picks the sleeves with Sharpe above 0.3 in 2020-2023 only, so its 2024-25 column is a fair test. Avg hold = 2 × gross position / weekly turnover.</p></div>`;
    }
    if (L && L.results[0].r_oos_sharpe !== undefined) {
      const ok = L.results.filter(r => r.enough && r.family !== 'Benchmark');
      const rt = (rows) => tbl(['Market', 'Rule', 'Avg hold (wk)', 'Full', '2007-18', '2020-23', '2024-25', '2026', 'Ann. % 2024-25'], rows.map(r => `<tr class="bt-row" data-s="${r.market}" data-k="${r.key}"><td class="l"><b>${r.name_m}</b></td><td class="l">${r.strategy}</td><td>${n(r.hold_wk, 1)}</td><td>${sg(r.sharpe)}</td><td>${sg(r.is_sharpe)}</td><td><b>${sg(r.r_is_sharpe)}</b></td><td><b>${sg(r.r_oos_sharpe)}</b></td><td>${sg(r.live_sharpe)}</td><td>${sg(r.r_oos_ann, 1)}</td></tr>`), 'bt-t');
      const fams = [...new Set(ok.map(r => r.family))];
      const med = (a) => { a = a.filter(v => v != null).sort((x, y) => x - y); return a.length ? a[Math.floor(a.length / 2)] : null; };
      html += `<div class="card" style="margin-top:12px"><h2>Single-market weekly rules (trend, carry, COT, fundamentals)</h2>
        ${HZ.map(([h, k, t]) => { const rr = ok.filter(r => isH(r.horizon, k) && r.r_is_sharpe > 0 && r.r_oos_sharpe > 0).sort((a, c) => mn(c.r_is_sharpe, c.r_oos_sharpe) - mn(a.r_is_sharpe, a.r_oos_sharpe)); const all = ok.filter(r => isH(r.horizon, k));
          return `<h3>${t} · <span class="note">${rr.length} of ${all.length} rule-market pairs positive in both windows</span></h3>${rr.length ? rt(rr.slice(0, 10)) : '<p class="note">None.</p>'}${rr.length > 10 ? `<details><summary>All ${rr.length}</summary>${rt(rr.slice(10))}</details>` : ''}`; }).join('')}
        <details><summary>By family (median Sharpe)</summary>${tbl(['Family', 'Horizon', 'Pairs', 'Full', '2007-18', '2020-23', '2024-25', '2026'], fams.flatMap(f => HZ.map(([h, k]) => { const rr = ok.filter(r => r.family === f && isH(r.horizon, k)); return rr.length ? `<tr><td class="l">${f}</td><td class="l">${k === 'st' ? 'short-term' : 'long-term'}</td><td>${rr.length}</td><td>${sg(med(rr.map(r => r.sharpe)))}</td><td>${sg(med(rr.map(r => r.is_sharpe)))}</td><td>${sg(med(rr.map(r => r.r_is_sharpe)))}</td><td>${sg(med(rr.map(r => r.r_oos_sharpe)))}</td><td>${sg(med(rr.map(r => r.live_sharpe)))}</td></tr>` : ''; })))}</details></div>`;
    }
    if (R) {
      const pt = (rows) => tbl(['Pattern', 'Side', 'Hold (days)', 'Markets', '2020-23', '2024-25', '2026', 'Trades 2024-25', 'Win % 2024-25', 'Avg % 2024-25', '% markets up 2024-25', 'Full period'], rows.map(r => `<tr><td class="l">${r.rule}${r.both ? ' ✓' : ''}</td><td>${r.side}</td><td>${r.hold}</td><td>${r.markets}</td><td><b>${sg(r.r_is)}</b></td><td><b>${sg(r.r_oos)}</b></td><td>${sg(r.live)}</td><td>${r.oos_n}</td><td>${n(r.oos_win, 0)}</td><td>${sg(r.oos_avg)}</td><td>${r.oos_pos ?? '–'}%</td><td>${sg(r.full)}</td></tr>`), 'bt-t');
      const st = (rows) => tbl(['Market', 'Pattern', 'Side', 'Hold', '2020-23', '2024-25', '2026', 'Trades (20-23 / 24-25)', 'Win % 2024-25', 'Avg % 2024-25', 'Full period'], rows.map(r => `<tr><td class="l"><b>${r.name_m}</b></td><td class="l">${r.rule}</td><td>${r.side}</td><td>${r.hold}</td><td><b>${sg(r.r_is_sharpe)}</b></td><td><b>${sg(r.r_oos_sharpe)}</b></td><td>${sg(r.live_sharpe)}</td><td>${r.r_is_n} / ${r.r_oos_n}</td><td>${n(r.r_oos_win, 0)}</td><td>${sg(r.r_oos_avg)}</td><td>${sg(r.sharpe)}</td></tr>`), 'bt-t');
      html += `<div class="card" style="margin-top:12px"><h2>Technical patterns (daily)</h2>
        ${HZ.map(([h, k, t]) => `<h3>${t} · <span class="note">${k === 'st' ? '5-day holds' : '10, 20 and 40-day holds'} · ${R['n_both_' + k]} of ${R['n_' + k]} pooled patterns positive in both windows (✓)</span></h3>
          <p class="note">Across markets (median of 12-20 markets):</p>${pt(R['pooled_' + k].slice(0, 8))}
          <details><summary>Best single markets</summary>${st(R['single_' + k])}</details>
          <details><summary>Worked over 2007-2026 but failed in 2024-25</summary>${pt(R['flipped_' + k])}</details>
          <details><summary>Worst in 2024-25</summary>${pt(R['pooled_' + k + '_worst'])}</details>`).join('')}
        <details><summary>By family</summary>${tbl(['Family', 'Horizon', 'Tests', 'Full', '2007-18', '2020-23', '2024-25', '2026'], R.families.map(f => `<tr><td class="l">${f.family}</td><td class="l">${f.horizon}</td><td>${f.tests}</td><td>${sg(f.full)}</td><td>${sg(f.early)}</td><td>${sg(f.r_is)}</td><td>${sg(f.r_oos)}</td><td>${sg(f.live)}</td></tr>`))}</details></div>`;
    }
    el.innerHTML = html + '</main>';
    $$('#btBody .bt-row').forEach(r => r.onclick = () => { if (r.dataset.s) { sym = r.dataset.s; key = r.dataset.k; sub = 'bt-rules'; history.replaceState(null, '', '#bt-rules'); paint(); setTimeout(() => document.getElementById('btMkt')?.scrollIntoView({ behavior: 'smooth' }), 50); } });
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
    if (!built) { [L, BK] = await Promise.all([getJSON('data/backtest/lab.json').catch(() => null), getJSON('data/backtest/baskets.json').catch(() => null)]); TL = await getJSON('data/backtest/tech.json').catch(() => null); built = true; }
    const h = location.hash.slice(1); if (/^bt-(baskets|rules|dairy|tech|regime)$/.test(h)) sub = h; else if (hs) sub = 'bt-rules';
    if (!L) { document.getElementById('backtest').innerHTML = '<main><div class="card"><p class="note">Backtests not built yet.</p></div></main>'; return; }
    if (L.per_market[hs]) sym = hs;
    render();
    if (!location.hash.startsWith('#backtest') && !location.hash.startsWith('#bt-')) history.replaceState(null, '', '#backtest');
  }
  return { show };
})();
