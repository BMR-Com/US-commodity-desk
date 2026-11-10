// Palm oil section. Data: data/palm/palm.json (models/palm.py), built by its own workflow so a failure there
// cannot affect the rest of the desk.
const Palm = (() => {
  let D = null, built = false, tab = 'po-outlook';
  const md = s => String(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  const kpi = (l, v, s2) => `<div class="card kpi"><div class="lbl">${l}</div><div class="val">${v}</div><div class="sub">${s2}</div></div>`;
  const mt = (v, d = 2) => v == null ? '–' : fmt(v / 1e6, d);
  const kt = v => v == null ? '–' : fmt(v / 1e3, 0);
  const lbl = m => { const [y, mm] = m.split('-').map(Number); return `${MON[mm - 1]} ${String(y).slice(2)}`; };
  const pill = s => `<span class="${s > 0 ? 'up' : s < 0 ? 'dn' : ''}">${s > 0 ? 'supportive' : s < 0 ? 'weighing' : 'neutral'}</span>`;

  function shell() {
    $('#palm').innerHTML = `<nav class="tabs" id="poTabs"><button data-t="po-outlook" class="on">1 · Outlook</button><button data-t="po-sd">2 · Supply &amp; demand</button>
      <button data-t="po-px">3 · Prices, spreads &amp; positioning</button><button data-t="po-primer">4 · Primer</button></nav><main><div id="poBody"></div></main>`;
    $$('#poTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; $$('#poTabs button').forEach(x => x.classList.toggle('on', x === b)); render(); });
  }
  async function show() {
    if (!built) { shell(); D = await getJSON('data/palm/palm.json').catch(() => null); built = true; }
    const h = location.hash.slice(1); if (/^po-/.test(h)) { tab = h; $$('#poTabs button').forEach(x => x.classList.toggle('on', x.dataset.t === tab)); }
    render();
  }
  const body = html => { $('#poBody').innerHTML = html; };
  function render() {
    history.replaceState(null, '', '#' + tab);
    if (!D && tab !== 'po-primer') return body('<div class="card"><p class="note">Palm oil data not built yet.</p></div>');
    ({ 'po-outlook': outlook, 'po-sd': sd, 'po-px': px, 'po-primer': primer }[tab] || outlook)();
  }

  function outlook() {
    const K = D.kpi, P = D.prices || {}, f = P.fcpo, pr = D.projection, sp = P.soy_palm;
    body(`<div class="card"><h2>Palm oil brief · ${D.view}</h2>
        ${D.brief.map(b => `<p><b>${b.h}.</b> ${md(b.t)}</p>`).join('')}
        <p class="note">Updated ${D.generated}; Malaysian data through ${D.asof_label}${D.prelim ? ' (preliminary)' : ''}. Next MPOB report about ${D.calendar.next_mpob}. ${D.calendar.note}</p></div>
      <div class="grid g4" style="margin-top:12px">
        ${kpi('Malaysian stocks', `${mt(K.stocks)} mt`, `${D.asof_label} · ${sgn(K.stocks_mom, 1, '%')} m/m · ${sgn(K.stocks_vs5, 0, '%')} vs 5-yr avg`)}
        ${kpi('CPO production', `${mt(K.prod)} mt`, `${sgn(K.prod_mom, 1, '%')} m/m`)}
        ${kpi('Exports', `${mt(K.exports)} mt`, `${sgn(K.exports_mom, 1, '%')} m/m`)}
        ${f ? kpi('Bursa FCPO', `RM${fmt(f.last, 0)}`, `US$${fmt(f.usd, 0)}/t · ${sgn(f.chg_1w, 1, '%')} wk · ${sgn(f.chg_1m, 1, '%')} mo`) : ''}
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>What drives the read</h2><div class="tbl"><table><thead><tr><th class="l">Factor</th><th class="l">Reading</th><th class="l">Effect</th></tr></thead><tbody>
          ${D.factors.map(x => `<tr><td class="l">${x.name}</td><td class="l">${x.txt}</td><td class="l">${pill(x.s)}</td></tr>`).join('')}</tbody></table></div>
          <p class="note">Each factor scores +1, 0 or −1; the view is their sum (${sgn(D.score, 0)}). Rule-based context, not a tested trading signal.</p></div>
        <div class="card"><h2>Stocks: next month's projection</h2>${pr ? `<div class="tbl"><table><thead><tr><th class="l">${lbl(pr.month)}</th><th>Low stocks</th><th>Base</th><th>High stocks</th></tr></thead><tbody>
          <tr><td class="l">Closing stocks (mt)</td><td>${mt(Math.min(pr.bull, pr.bear))}</td><td><b>${mt(pr.base)}</b></td><td>${mt(Math.max(pr.bull, pr.bear))}</td></tr>
          <tr><td class="l">Production (mt)</td><td colspan="3">${mt(pr.prod)} — usual change into the month ${sgn(pr.prod_mom.med * 100, 0, '%')} (${sgn(pr.prod_mom.lo * 100, 0, '%')} to ${sgn(pr.prod_mom.hi * 100, 0, '%')})</td></tr>
          <tr><td class="l">Exports (mt)</td><td colspan="3">${mt(pr.exports)} — usual change ${sgn(pr.exp_mom.med * 100, 0, '%')} (${sgn(pr.exp_mom.lo * 100, 0, '%')} to ${sgn(pr.exp_mom.hi * 100, 0, '%')})</td></tr>
          <tr><td class="l">Imports / domestic use (mt)</td><td colspan="3">${mt(pr.imports)} / ${mt(pr.dom)}</td></tr></tbody></table></div>
          <p class="note">Opening stocks plus production and imports, less exports and domestic use, with production and exports moved by their usual month-on-month change (last 10 years).
          ${D.backtest ? `Since ${D.backtest.since.slice(0, 4)} it called the direction of the stock change ${D.backtest.dir_hit}% of the time; on the level it missed by ${D.backtest.mae_pct}% on average vs ${D.backtest.mae_naive_pct}% for "no change", so use it for direction only.` : ''}</p>` : '<p class="note">Not enough history.</p>'}</div>
      </div>`);
  }

  function sd() {
    const S = D.series, T = D.table, W = D.world;
    const cols = ['open', 'prod', 'imports', 'exports', 'dom', 'stocks'];
    body(`<div class="grid g2">
        <div class="card"><h2>Malaysian palm oil stocks (million t)</h2><div class="chart"><canvas id="cPoSt"></canvas></div><p class="note">MPOB month-end stocks of crude and processed palm oil. Shaded: range of the previous five years.</p></div>
        <div class="card"><h2>Crude palm oil production (million t)</h2><div class="chart"><canvas id="cPoPr"></canvas></div><p class="note">Output bottoms in January–February and peaks in August–October.</p></div>
        <div class="card"><h2>Exports (million t)</h2><div class="chart"><canvas id="cPoEx"></canvas></div><p class="note">Palm oil exports (crude and processed), MPOB.</p></div>
        <div class="card"><h2>Stocks ÷ monthly use</h2><div class="chart"><canvas id="cPoSu"></canvas></div><p class="note">Month-end stocks divided by the three-month average of exports plus domestic use: months of use in store.
          ${D.kpi.su != null ? `Now ${fmt(D.kpi.su, 2)}${D.kpi.su_pct != null ? `, ${D.kpi.su_pct}th percentile of the last 10 years` : ''}.` : ''}</p></div>
      </div>
      <div class="card" style="margin-top:12px"><h2>Malaysia: monthly balance (thousand t)</h2><div class="tbl"><table><thead><tr><th class="l">Month</th><th>Opening</th><th>Production</th><th>Imports</th><th>Exports</th><th>Domestic use</th><th>Closing</th><th>Months of use</th></tr></thead><tbody>
        ${T.map(r => `<tr><td class="l">${lbl(r.m)}${r.flag === 'p' ? ' (p)' : ''}</td>${cols.map(c => `<td>${kt(r[c])}</td>`).join('')}<td>${r.su == null ? '–' : fmt(r.su, 2)}</td></tr>`).join('')}</tbody></table></div>
        <p class="note">Source: Malaysian Palm Oil Board monthly statistics. Domestic use is the residual (opening + production + imports − exports − closing), so it also absorbs revisions. (p) preliminary.</p></div>
      ${W ? `<div class="card" style="margin-top:12px"><h2>World palm oil balance (USDA, ${W.unit})</h2><div class="ctrls" id="poWSel"></div><div class="tbl"><table id="poWTab"></table></div>
        <p class="note">USDA PSD, marketing years. Industrial use is mostly biodiesel.${W.revisions && W.revisions.rows.length ? ` Changes in ${W.my} since the ${W.revisions.from} data: ${W.revisions.rows.slice(0, 8).map(x => `${x.country} ${x.attr} ${x.chg > 0 ? '+' : ''}${fmt(x.chg, 2)}`).join('; ')}.` : ' Each month\'s figures are stored, so revisions will show here from the next USDA update.'}
        ${W.vegoil_su ? ` Stocks/use of the five main vegetable oils together: ${W.vegoil_su.slice(-4).map(x => `${x.my} ${fmt(x.su, 1)}%`).join(', ')}.` : ''}</p></div>` : ''}`);
    const L = [...MON];
    const seas = (id, s) => chart(id, { type: 'line', data: { labels: L, datasets: seasonalDatasets(seasonal(s.month, s.vals)) }, options: { plugins: { legend: legendNoMin } } });
    seas('cPoSt', S.stocks); seas('cPoPr', S.prod); seas('cPoEx', S.exports); seas('cPoSu', S.su);
    if (W) {
      let cur = 0;
      const draw = () => {
        const R = W.regions[cur].rows, A = [['prod', 'Production'], ['imports', 'Imports'], ['exports', 'Exports'], ['use', 'Domestic use'], ['industrial', '  of which industrial'], ['end', 'Ending stocks'], ['su', 'Stocks/use %']];
        $('#poWTab').innerHTML = `<thead><tr><th class="l">${W.regions[cur].name}</th>${R.map(r => `<th>${r.my}</th>`).join('')}<th>y/y</th></tr></thead><tbody>` +
          A.map(([k, n]) => `<tr><td class="l">${n}</td>${R.map(r => `<td>${r[k] == null ? '–' : fmt(r[k], k === 'su' ? 1 : 2)}</td>`).join('')}<td>${R.length > 1 && R.at(-1)[k] != null && R.at(-2)[k] != null ? sgn(R.at(-1)[k] - R.at(-2)[k], k === 'su' ? 1 : 2) : '–'}</td></tr>`).join('') + '</tbody>';
        $('#poWSel').innerHTML = W.regions.map((r, i) => `<button class="chip ${i === cur ? 'on' : ''}" data-i="${i}">${r.name}</button>`).join('');
        $$('#poWSel button').forEach(b => b.onclick = () => { cur = +b.dataset.i; draw(); });
      };
      draw();
    }
  }

  function px() {
    const P = D.prices, C = D.cot;
    if (!P) return body('<div class="card"><p class="note">Price data not built yet.</p></div>');
    const w = P.weekly, row = (n, o, u, d = 0) => o ? `<tr><td class="l">${n}</td><td>${fmt(o.last, d)}${u}</td><td>${o.chg_1m == null ? '–' : sgn(o.chg_1m, d)}</td><td>${fmt(o.med5y, d)}</td><td>${o.pct5y == null ? '–' : o.pct5y}</td><td class="l">${o.date}</td></tr>` : '';
    body(`<div class="grid g2">
        <div class="card"><h2>Palm oil and soybean oil (US$/t)</h2><div class="chart"><canvas id="cPoPx"></canvas></div><p class="note">Bursa FCPO front month converted at USD/MYR; CBOT soybean oil front month (¢/lb × 22.0462). Weekly, last five years.</p></div>
        <div class="card"><h2>Soybean oil minus palm oil (US$/t)</h2><div class="chart"><canvas id="cPoSp"></canvas></div><p class="note">Futures against futures, not delivered prices. A wide palm discount pulls demand to palm in price-sensitive markets; a narrow one or a premium sends buyers to soybean and sunflower oil.</p></div>
        <div class="card"><h2>Palm oil minus gasoil (CME POGO, US$/t)</h2><div class="chart"><canvas id="cPoPg"></canvas></div><p class="note">Below zero palm is cheaper than gasoil and discretionary biodiesel blending pays; above it blending depends on mandates and subsidies.</p></div>
        <div class="card"><h2>Price vs soybean oil and stocks</h2>${P.fit ? `<div class="chart"><canvas id="cPoFit"></canvas></div><p class="note">Monthly palm price fitted on soybean oil and Malaysian stocks vs their seasonal norm (${P.fit.since} on, R² ${P.fit.r2}, typical miss ±${fmt(P.fit.se_pct, 0)}%).
          Now: fit US$${fmt(P.fit.fair_usd, 0)}/t, market ${sgn(P.fit.gap_pct, 0, '%')} from it. In-sample fit; context only.</p>` : '<p class="note">Not enough history.</p>'}</div>
      </div>
      <div class="card" style="margin-top:12px"><h2>Levels</h2><div class="tbl"><table><thead><tr><th class="l"></th><th>Last</th><th>1-month change</th><th>5-yr median</th><th>5-yr percentile</th><th class="l">Date</th></tr></thead><tbody>
        ${P.fcpo ? `<tr><td class="l">Bursa FCPO front month (RM/t)</td><td>${fmt(P.fcpo.last, 0)}</td><td>${sgn(P.fcpo.chg_1m, 1, '%')}</td><td>–</td><td>${P.fcpo.pct5y ?? '–'}</td><td class="l">${P.fcpo.date}</td></tr>
        <tr><td class="l">FCPO: 50-day / 200-day average, RSI</td><td colspan="5" class="l">${fmt(P.fcpo.ma50, 0)} / ${fmt(P.fcpo.ma200, 0)}; RSI ${fmt(P.fcpo.rsi, 0)}; 52-week range ${fmt(P.fcpo.lo52, 0)}–${fmt(P.fcpo.hi52, 0)}</td></tr>` : ''}
        ${row('CME USD Malaysian CPO front (US$/t)', P.cme, '')}${row('CBOT soybean oil (US$/t)', P.soyoil_usd, '')}${row('Soybean oil − palm (US$/t)', P.soy_palm, '')}${row('Palm − gasoil, CME POGO (US$/t)', P.pogo, '')}${row('USD/MYR', P.usdmyr, '', 3)}${row('Brent (US$/bbl)', P.brent, '', 2)}
      </tbody></table></div><p class="note">Daily closes from TradingView (delayed). Front-month series roll, so long-run changes include roll gaps.</p></div>
      ${C ? `<div class="card" style="margin-top:12px"><h2>CME palm oil: open interest and positions (CFTC)</h2><div class="chart"><canvas id="cPoCot"></canvas></div>
        <p class="note">CME USD Malaysian Crude Palm Oil Calendar futures and options, ${C.date}: open interest ${fmt(C.oi, 0)}; producers/merchants net ${sgn(C.pm, 0)}, swap dealers ${sgn(C.sw, 0)}, managed money ${sgn(C.mm, 0)}.
        A cash-settled contract used mainly by commercial hedgers; Bursa Malaysia does not publish a comparable positions report.</p></div>` : ''}`);
    const lab = w.date.map(d => d.slice(0, 7));
    const ln = (data, label, color, extra = {}) => ({ label, data, borderColor: color, borderWidth: 1.6, pointRadius: 0, spanGaps: true, ...extra });
    chart('cPoPx', { type: 'line', data: { labels: lab, datasets: [ln(w.fcpo_usd, 'Palm oil (FCPO)', PAL[0]), ln(w.zl_usd, 'Soybean oil (CBOT)', PAL[3])] } });
    chart('cPoSp', { type: 'line', data: { labels: lab, datasets: [ln(w.soy_palm, 'Soybean oil − palm', PAL[2], { fill: 'origin', backgroundColor: 'rgba(44,111,187,.10)' })] } });
    chart('cPoPg', { type: 'line', data: { labels: lab, datasets: [ln(w.pogo, 'Palm − gasoil', PAL[4], { fill: 'origin', backgroundColor: 'rgba(125,60,152,.10)' })] } });
    if (P.fit) chart('cPoFit', { type: 'line', data: { labels: P.fit.hist.month, datasets: [ln(P.fit.hist.actual, 'Palm oil, monthly average (US$/t)', PAL[0]), ln(P.fit.hist.fit, 'Fit', '#999', { borderDash: [4, 3] })] } });
    if (C) chart('cPoCot', { type: 'line', data: { labels: C.hist.date.map(d => d.slice(0, 7)), datasets: [ln(C.hist.oi, 'Open interest', '#999', { yAxisID: 'y1' }), ln(C.hist.mm, 'Managed money net', PAL[1]), ln(C.hist.pm, 'Producers/merchants net', PAL[0])] },
      options: { scales: { y1: { position: 'right', grid: { display: false }, ticks: { font: { size: 10 } } } } } });
  }

  function primer() {
    const tr = (a, b) => `<tr><td>${a}</td><td class="l">${b}</td></tr>`;
    body(`<div class="grid g2">
      <div class="card"><h2>Bursa Malaysia crude palm oil futures (FCPO)</h2><div class="tbl"><table>
        ${tr('Role', 'The world benchmark. Priced in ringgit; the third month is the reference contract')}
        ${tr('Size / tick', '25 tonnes; RM1 per tonne = RM25 per lot')}
        ${tr('Months', 'Spot month and the next 11 months, then alternate months out to 36 months')}
        ${tr('Daily limit', '10% from the previous settlement, widening to 15% after a cooling-off period (not in the spot month)')}
        ${tr('Hours (Kuala Lumpur)', '10:30–12:30 and 14:30–18:00, plus a night session 21:00–23:30 Monday to Thursday')}
        ${tr('Last trading day', 'Noon on the 15th of the delivery month')}
        ${tr('Delivery', 'Physical, into approved port tank installations at Port Klang, Penang/Butterworth or Pasir Gudang, at the seller\'s choice; tender from the 1st to the 20th of the spot month')}
        ${tr('Quality', 'Free fatty acids up to 4% delivered in; moisture and impurities up to 0.25%; DOBI at least 2.5')}</table></div>
        <p class="note">Specifications from broker and exchange-member summaries; check Bursa Malaysia Derivatives for current terms.</p></div>
      <div class="card"><h2>CME USD Malaysian Crude Palm Oil Calendar futures (CPO)</h2><div class="tbl"><table>
        ${tr('Role', 'A US-dollar, cash-settled way to hold the Bursa price without ringgit or delivery')}
        ${tr('Size / tick', '25 tonnes; US$0.25 per tonne = US$6.25 per lot')}
        ${tr('Settlement', 'Cash. The final price is the average, over the contract month, of the daily settlement of Bursa\'s third forward-month FCPO, converted to dollars at the Kuala Lumpur USD/MYR reference rate')}
        ${tr('Last trading day', 'Last business day of the contract month')}
        ${tr('Price limits', 'None on the CME contract (the Bursa contract underneath has 10%)')}
        ${tr('Related CME products', 'Palm oil minus low-sulphur gasoil spread futures (POGO); bullet futures settling to the third-month FCPO on the 15th; average-price options')}
        ${tr('Vs soybean oil', 'No listed palm–soybean oil spread: it is traded as CBOT soybean oil against CPO. One soybean oil lot is 60,000 lb (27.2 t), close to one 25 t palm lot')}</table></div>
        <p class="note">Because the contract settles to a monthly average of the <i>third-month</i> Bursa price, the CME December contract tracks Bursa's February contract through December. Source: CME Rulebook chapters 204, 204E, 204F.</p></div>
      <div class="card"><h2>Who produces, who buys</h2>
        <p>Indonesia (about 45 million t) and Malaysia (about 20 million t) grow more than four-fifths of the world's palm oil and ship a similar share of exports. India is the largest importer (8–9 million t), then China, Pakistan, the EU and Bangladesh.</p>
        <p>Malaysia exports most of what it produces, so its monthly stocks are the market's scorecard. Indonesia uses a growing share at home: its biodiesel mandate (B40 in 2026) takes about a third of its output, so Indonesian export supply depends on policy as much as on the crop.</p>
        <h3>The year</h3><p>Yields follow rainfall with a lag and a strong seasonal cycle: Malaysian output is lowest in January–February and highest in August–October. Stocks usually build from July to October or November and draw from November to February. Demand has its own calendar: India stocks up before Diwali and China before Lunar New Year; cold weather makes palm oil solidify and cuts its use in northern markets in winter.</p></div>
      <div class="card"><h2>What moves price</h2><div class="tbl"><table>
        ${tr('Malaysian stocks', 'Stocks high against the seasonal norm weigh on price; the monthly change against expectations moves it on report day')}
        ${tr('Exports during the month', 'Cargo surveyors publish Malaysian shipments for days 1–10, 1–15, 1–20, 1–25 and the full month; each count resets the stock estimate')}
        ${tr('Soybean oil', 'The closest substitute. Palm normally sells at a discount; when the discount narrows or turns to a premium, India and others switch away')}
        ${tr('Gasoil and crude', 'When palm is cheaper than gasoil, blending it into diesel pays without subsidy, which puts a floor under price')}
        ${tr('Indonesian policy', 'Biodiesel mandates (B40, B50 proposed), the monthly export duty and levy set from a reference price, and occasional export restrictions')}
        ${tr('Import duties', 'India adjusts duties on crude and refined edible oils often; the gap between them decides whether it buys crude palm or refined olein')}
        ${tr('Ringgit', 'A weaker ringgit lifts the ringgit price for the same dollar value')}
        ${tr('Weather', 'El Niño dryness cuts yields 6–12 months later; floods in the north-east monsoon (November–January) disrupt harvesting')}</table></div></div>
      <div class="card"><h2>Report calendar</h2><div class="tbl"><table>
        ${tr('Around the 10th', 'MPOB supply and demand for the previous month (production, exports, imports, stocks)')}
        ${tr('10th, 15th, 20th, 25th, month-end', 'Cargo surveyor export estimates for Malaysia (ITS, AmSpec)')}
        ${tr('Mid-month', 'Malaysia\'s export duty for the next month; India\'s vegetable oil imports for the previous month (Solvent Extractors\' Association)')}
        ${tr('Month-end', 'Indonesia\'s reference price, export duty and levy for the next month')}
        ${tr('6–8 weeks later', 'Indonesia\'s industry data on production, exports and stocks (GAPKI)')}
        ${tr('Monthly, WASDE day', 'USDA world oilseed and vegetable oil balances')}</table></div></div>
      <div class="card"><h2>How the balance on this desk is built</h2>
        <p><b>Malaysia, monthly.</b> Opening stocks + production + imports − exports − domestic use = closing stocks. MPOB publishes all but domestic use, which is the residual. Stocks divided by monthly use gives months of cover.</p>
        <p><b>Next month.</b> Production and exports are moved by their usual month-on-month change for the calendar month. This gives the direction of the stock change about two times in three, but not the level; during the month, surveyor export counts and industry production estimates matter more.</p>
        <p><b>World, yearly.</b> USDA balances by country show where supply and use are changing: Indonesian biodiesel use, Indian and Chinese imports, and the stocks-to-use ratio of palm oil and of all vegetable oils together.</p>
        <p><b>Price.</b> Palm is compared with soybean oil and with gasoil, and against a simple fit on soybean oil and Malaysian stocks.</p></div>
    </div>`);
  }
  return { show };
})();
