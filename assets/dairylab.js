// Dairy primer: convergence, persistence and trading lab (data/dairy/derived/dairy_lab.json + dairy_arb.json).
const DairyLab = (() => {
  let LB = null, AR = null, done = false;
  const n = (v, d = 2) => v == null ? '–' : (+v).toFixed(d);
  const sg = (v, d = 2) => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${(+v).toFixed(d)}</span>`;
  const usd = v => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v < 0 ? '-' : ''}$${Math.abs(Math.round(v)).toLocaleString()}</span>`;
  const T = (head, rows, cls = 'bt-t') => `<div class="tbl"><table class="${cls}"><tr>${head.map((h, i) => `<th class="${i < 2 ? 'l' : ''}">${h}</th>`).join('')}</tr>${rows.join('')}</table></div>`;
  async function mount(el) {
    if (!el) return;
    if (!done) { [LB, AR] = await Promise.all([getJSON('data/dairy/derived/dairy_lab.json').catch(() => null), getJSON('data/dairy/derived/dairy_arb.json').catch(() => null)]); done = true; }
    if (!LB) { el.innerHTML = ''; return; }
    const M = LB.models, nm = s => LB.specs[s]?.name || s;
    const S = LB.strategies, desk = LB.desk_book || {}, D0 = desk['Convergence (spot gap) + trend, all six'];
    const best = (sym, model, h) => S.find(r => r.sym === sym && r.model === model && r.h_max === h && r.hurdle === 1);
    const conv = ['CB', 'DY', 'CSC', 'DC', 'GDK', 'GNF'].map(s => best(s, 'spot_gap', 2)).filter(Boolean);
    const trend = ['GDK', 'GNF', 'CB', 'DC', 'CSC', 'DY'].map(s => best(s, 'fut_momentum', 5)).filter(Boolean);
    const pers = LB.persistence;
    const arbB = AR?.gap_trades?.find(t => t.sym === 'CB' && t.signal === 'Spot-based nowcast' && t.threshold_x_cost === 1 && t.window === 'All');
    const fund = LB.fundamentals.filter(r => r.model === 'fundamentals only' && r.horizon_m === 3);
    const top = [
      `<b>Prices checked.</b> Futures are daily CME settlements on exchange trade dates (TradingView stamps evening-open sessions a day early; corrected, and 93-100% of closes now match CME's own settlement files). Cash is the CME daily spot (2018 on, from USDA Dairy Market News) and the weekly NDPSR survey (2012 on). Every test below is walk-forward: models only use data that existed on the decision day.`,
      `<b>Cash prices are persistent; futures much less.</b> Month-to-month changes in the announced price have autocorrelation ${pers.map(p => `${p.name} ${p.monthly_ac1}`).join(', ')} (averaging alone gives about 0.25). Weekly futures returns: ${pers.map(p => `${p.name} ${p.futures_weekly_ac1}`).join(', ')}. The market prices most of the persistence, but not all of it: a 4-week futures trend still pays in Class IV, nonfat and butter.`,
      `<b>Convergence edge (cash arbitrage).</b> The settlement is decided by CME spot trading from mid-previous-month to mid-month. Holding the nearest two months in the direction of the gap between a spot-based nowcast and the futures price paid in ${conv.filter(r => (r.sharpe_2020_26 ?? 0) > 0.8).map(r => `${r.name} (Sharpe ${n(r.sharpe_2020_26)} in 2020-26; ${n(r.sharpe_2020_23)} in 2020-23, ${n(r.sharpe_2024_26)} in 2024-26)`).join(', ') || 'butter and whey'}. Class III, cheese and Class IV are priced efficiently on this measure.${arbB ? ` Held to settlement, the butter gap trade made $${arbB.avg_usd.toLocaleString()} per contract after costs over ${arbB.months} months, right ${arbB.hit}% of the time.` : ''}`,
      `<b>Trend edge (persistence).</b> 4-week futures momentum on contracts up to 5 months out: ${trend.filter(r => (r.sharpe ?? 0) > 0.5).map(r => `${r.name} Sharpe ${n(r.sharpe_2014_19)} in 2014-19 and ${n(r.sharpe_2020_26)} in 2020-26`).join('; ')}. Positive in both halves, which a lucky backtest rarely is.`,
      `<b>What does not work.</b> Predicting from the lagging NDPSR alone, regressions on supply and demand (ERS stocks vs normal, production, exports and domestic use forecast the next 3 months worse than "no change": out-of-sample R² ${fund.map(r => `${r.name} ${r.r2_oos}%`).join(', ')}), and trading the Wednesday release. Fundamentals explain the level of prices over a year, not the next few weeks that futures have not already priced.`,
      D0 ? `<b>Desk book.</b> Both sleeves on all six contracts, one lot per signal, no per-contract picking: Sharpe ${D0.sharpe_one_lot} over 2020-26 (2020-23 ${D0.sharpe_2020_23}, 2024-26 ${D0.sharpe_2024_26}), about $${D0.ann_usd_one_lot.toLocaleString()} a year, worst drawdown $${Math.abs(D0.maxdd_usd_one_lot).toLocaleString()}. Convergence and trend are nearly uncorrelated (${D0.corr_conv_trend}).` : ''
    ].filter(Boolean);
    // live
    const liveAll = (LB.live || []).filter(r => r.h <= 5);
    const live = liveAll.filter(r => r.sig_convergence || r.sig_trend);
    const sig = v => v > 0 ? '<b class="up">LONG</b>' : v < 0 ? '<b class="dn">SHORT</b>' : '<span class="note">flat</span>';
    const liveRows = rows => T(['Contract', 'Month', 'Futures', 'Cash (NDPSR 4 wk)', 'Spot nowcast gap %', 'Cost %', 'Convergence (≤2 mo)', '4-wk futures trend %', 'Trend (≤5 mo)'],
      rows.map(r => `<tr><td class="l"><b>${r.name}</b></td><td class="l">${r.month}</td><td>${r.futures}</td><td>${n(r.cash, 3)}</td><td>${sg(r.spot_gap_pct)}</td><td>${n(r.cost_pct)}</td><td>${r.h <= 2 ? sig(r.sig_convergence) : '<span class="note">–</span>'}</td><td>${sg(r.fmom_pct)}</td><td>${sig(r.sig_trend)}</td></tr>`));
    const liveT = (live.length ? liveRows(live) : '<p class="note">No contract clears the cost hurdle today.</p>') + `<details><summary>All ${liveAll.length} open contract months</summary>${liveRows(liveAll)}</details>`;
    const stT = rows => T(['Contract', 'Signal', 'Months out', 'Hurdle', 'Sharpe', '2014-19', '2020-23', '2024-26', '$ / year (one lot per month)', 'Worst drawdown', 'Avg positions', 'Cost $ / year'],
      rows.map(r => `<tr><td class="l"><b>${r.name}</b></td><td class="l">${M[r.model] || r.model}</td><td>≤${r.h_max}</td><td>${r.hurdle}x</td><td><b>${sg(r.sharpe)}</b></td><td>${sg(r.sharpe_2014_19)}</td><td>${sg(r.sharpe_2020_23)}</td><td>${sg(r.sharpe_2024_26)}</td><td>${usd(r.ann_usd)}</td><td>${usd(r.maxdd_usd)}</td><td>${r.avg_positions}</td><td>${usd(r.cost_ann_usd)}</td></tr>`));
    const robust = S.filter(r => (r.sharpe_2020_23 ?? -9) > 0.3 && (r.sharpe_2024_26 ?? -9) > 0.3).sort((a, b) => Math.min(b.sharpe_2020_23, b.sharpe_2024_26) - Math.min(a.sharpe_2020_23, a.sharpe_2024_26));
    const ev = LB.evaluation.filter(r => r.horizon === 'all' && r.period === '2020+');
    const evT = T(['Contract', 'Model', 'Obs', 'Months', 'Error %', 'R² vs futures %', 'Direction right %', 't (by month)'],
      ev.map(r => `<tr><td class="l">${nm(r.sym)}</td><td class="l">${M[r.model]}</td><td>${r.n}</td><td>${r.months}</td><td>${n(r.rmse_pct)}</td><td>${sg(r.r2_oos, 1)}</td><td>${n(r.hit, 1)}</td><td>${sg(r.t)}</td></tr>`));
    const fT = T(['Contract', 'Model', 'Horizon (months)', 'Forecasts', 'R² out of sample %', 'Direction right %', 'Correlation'],
      LB.fundamentals.filter(r => r.r2_oos != null).map(r => `<tr><td class="l">${r.name}</td><td class="l">${r.model}</td><td>${r.horizon_m}</td><td>${r.n}</td><td>${sg(r.r2_oos, 1)}</td><td>${n(r.hit, 1)}</td><td>${n(r.corr)}</td></tr>`));
    const pT = T(['Contract', '', 'Monthly price: lag-1 autocorr.', 'Lag 2', 'Months moving the same way %', 'Weekly NDPSR lag-1', '4-week blocks lag-1', 'Weekly futures lag-1'],
      pers.map(p => `<tr><td class="l"><b>${p.name}</b></td><td></td><td>${n(p.monthly_ac1)}</td><td>${n(p.monthly_ac2)}</td><td>${p.months_same_direction}</td><td>${n(p.weekly_ac1)}</td><td>${n(p.weekly_ac4)}</td><td>${n(p.futures_weekly_ac1)}</td></tr>`));
    const acc = AR?.accuracy || [];
    el.innerHTML = `<div class="card" style="margin-top:12px"><h2>Convergence, persistence and a trading book <span class="note">${LB.generated} · walk-forward since 2013 · details in Backtest → Dairy deep dive</span></h2>
        <ul class="read">${top.map(x => `<li>${x}</li>`).join('')}</ul></div>
      <div class="card" style="margin-top:12px"><h2>Today's signals <span class="note">decision day ${LB.live_date}; convergence uses contracts up to 2 months out, trend up to 5; a signal needs the gap or trend to beat the round-trip cost</span></h2>${liveT}
        <p class="note">Research signals, not advice. Sizes in the backtest are one contract per signal; dairy futures are thin, so real fills beyond a few lots will be worse than settlement prices.</p></div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>Desk book: cumulative $ (one lot per signal) <span class="note">2020 on</span></h2><div class="chart" style="height:260px"><canvas id="dlEq"></canvas></div>
          ${T(['Book', '', 'Sharpe', '2020-23', '2024-26', '$ / year', 'Worst drawdown', 'Risk-weighted Sharpe'], Object.entries(desk).map(([k, v]) => `<tr><td class="l" colspan="2">${k}</td><td><b>${sg(v.sharpe_one_lot)}</b></td><td>${sg(v.sharpe_2020_23)}</td><td>${sg(v.sharpe_2024_26)}</td><td>${usd(v.ann_usd_one_lot)}</td><td>${usd(v.maxdd_usd_one_lot)}</td><td>${sg(v.sharpe_risk_weighted)}</td></tr>`))}
          ${D0 ? `<details><summary>By year ($, one lot per signal)</summary>${T(['Year', '', '$'], Object.entries(D0.by_year).map(([y, v]) => `<tr><td class="l">${y}</td><td></td><td>${usd(v)}</td></tr>`))}</details>` : ''}</div>
        <div class="card"><h2>Strategies that held up in both 2020-23 and 2024-26 <span class="note">Sharpe above 0.3 in each</span></h2>${stT(robust.slice(0, 10))}
          <details><summary>All ${S.length} strategy runs</summary>${stT([...S].sort((a, b) => (b.sharpe ?? -9) - (a.sharpe ?? -9)))}</details></div></div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>How close each estimate gets to settlement <select id="dlSel">${Object.keys(LB.specs).map(k => `<option value="${k}">${nm(k)}</option>`).join('')}</select></h2><div class="chart" style="height:260px"><canvas id="dlAcc"></canvas></div>
          <p class="note">Average miss vs the final announced price by stage of the contract (2018 on). The futures price beats a pure nowcast for most contracts at most stages; butter is the exception, which is why the convergence trade works there.</p></div>
        <div class="card"><h2>Is there persistence?</h2>${pT}<p class="note">Autocorrelation of log price changes. Positive = moves tend to continue. An average of a random walk has 0.25 mechanically, so monthly settlement prices above that carry real persistence; weekly futures returns near zero mean the market has already priced it.</p></div></div>
      <div class="card" style="margin-top:12px"><h2>Model scorecard <span class="note">forecasting y = log(final settlement / futures price), 2020 on, all horizons</span></h2>
        <p class="note">R² vs futures above zero means the model beats the futures price as a forecast of where the contract settles. Few models manage that; the trading results come from the sign of the forecast being right more often than not, net of costs.</p>
        <details><summary>All models and contracts</summary>${evT}</details>
        <details><summary>Supply and demand: forecasting the next 1 and 3 months of announced prices (ERS stocks, production, exports, domestic use)</summary>${fT}</details></div>`;
    const draw = s => {
      const a = acc.filter(x => x.sym === s);
      if (a.length) chart('dlAcc', { type: 'bar', data: { labels: a.map(x => x.phase.replace(/^\d\. /, '')), datasets: [
        { label: 'futures', data: a.map(x => x.mae_futures), backgroundColor: PAL[0] }, { label: 'spot nowcast', data: a.map(x => x.mae_nowcast), backgroundColor: PAL[1] },
        { label: 'last NDPSR print', data: a.map(x => x.mae_naive), backgroundColor: '#bbb' }] }, options: { scales: { x: { ticks: { font: { size: 9 }, maxRotation: 40 } } } } });
    };
    $('#dlSel').onchange = e => draw(e.target.value); $('#dlSel').value = 'CB'; draw('CB');
    if (D0) chart('dlEq', { type: 'line', data: { labels: D0.equity.map(e => e[0].slice(0, 7)), datasets: Object.entries(desk).map(([k, v], i) => ({ label: k, data: v.equity.map(e => e[1]), borderColor: PAL[i % PAL.length], pointRadius: 0, borderWidth: i ? 1.1 : 2 })) },
      options: { scales: { y: { title: { display: true, text: '$ cumulative', font: { size: 10 } } } } } });
  }
  return { mount };
})();
