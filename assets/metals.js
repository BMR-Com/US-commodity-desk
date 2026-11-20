// Metals section: one menu with four sub-desks (gold, silver, copper, aluminum), numbered sub-tabs like Energy and Cotton.
// Data: data/metals/metals.json (models/metals.py), data/metals/status.json + release_calendar.json (pipelines/metals_status.py),
// and the shared desk files (technicals, COT desk, seasonality, spreads, specs, news, calendar). Built by its own workflow
// (metals.yml), so a failure there cannot affect the rest of the desk. Deep links: #metals/<gc|si|hg|ali>/<tab>.
const Metals = (() => {
  let built = false, mk = 'GC', tab = 'outlook', D = null, ST = null, CAL = null;
  const KEY = { GC: 'gold', SI: 'silver', HG: 'copper', ALI: 'aluminum' };
  const DESKS = { GC: 'Gold', SI: 'Silver', HG: 'Copper', ALI: 'Aluminum' };
  const COT = { GC: 'GC', SI: 'SI', HG: 'HG', ALI: 'AUP' };
  const TABS = [['primer', 'Primer'], ['px', 'Prices &amp; curve'], ['flows', 'Futures &amp; COT'], ['sd', 'Supply &amp; demand'], ['seas', 'Seasonality &amp; technicals'],
    ['outlook', 'Outlook'], ['news', 'News &amp; calendar'], ['status', 'Data status']];
  const esc = x => String(x == null ? '' : x).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const tr = (a, b) => `<tr><td class="l"><b>${a}</b></td><td class="l">${b}</td></tr>`;
  const kpi = (l, v, s2) => `<div class="card kpi"><div class="lbl">${l}</div><div class="val">${v}</div><div class="sub">${s2}</div></div>`;
  const pill = s => `<span class="${s > 0 ? 'up' : s < 0 ? 'dn' : ''}">${s > 0 ? 'supportive' : s < 0 ? 'weighing' : 'neutral'}</span>`;
  const ln = (data, label, color, extra = {}) => ({ label, data, borderColor: color, borderWidth: 1.6, pointRadius: 0, spanGaps: true, ...extra });
  const body = () => $('#mtBody');
  const none = what => `<div class="card"><p class="note">${what} not built yet: it appears after the metals workflow's next run.</p></div>`;

  // ───────── primers (own words; trader-focused) ─────────
  const P = {
    GC: { spec: [['Contract', 'COMEX Gold (GC); micro gold (MGC, 10 oz)'], ['Size / tick', '100 troy oz; $0.10/oz = $10 per lot'], ['Active months', 'Feb, Apr, Jun, Aug, Oct, Dec (nearby months also list)'],
        ['First notice / last trade', 'First notice: last business day of the month before delivery (longs must be out the day before first position day). Last trade: third-last business day of the delivery month'],
        ['Delivery', 'A 100-oz bar (or three 1-kg bars), 995 fine, on warrant in a COMEX-approved New York-area vault. Shorts choose when in the delivery month to deliver; longs take a warrant, not a bar in hand'],
        ['Options', 'Monthly options expire on the 4th-last business day of the month before the contract month; weeklies too']],
      drivers: [['Real interest rates', 'Gold pays no yield, so the opportunity cost of holding it is the real (inflation-adjusted) rate. Falling 10-year TIPS yields have been the most reliable tailwind; the link loosened from 2022 as central banks bought regardless of rates.', 'US 10-yr TIPS yield (Treasury), Fed path'],
        ['US dollar', 'Gold is priced in dollars: a weaker dollar makes it cheaper for everyone else and usually lifts the dollar price.', 'Dollar index (DXY)'],
        ['Central-bank buying', 'Since 2022 central banks (China, Poland, Turkey, India, others) have bought about 1,000 t a year, roughly a fifth of demand, to diversify reserves away from the dollar. Price-insensitive, so it puts a floor under dips.', 'WGC Gold Demand Trends (quarterly), IMF reserves'],
        ['ETF flows', 'Western investors move in and out through ETFs (GLD, IAU and peers). Inflows follow falling real rates and risk-off moves; big outflows mark tops.', 'GLD/IAU holdings (daily), WGC monthly ETF flows'],
        ['Jewellery and bar/coin (India, China)', 'Jewellery is the largest single use but it is price-sensitive: high prices cut tonnage and bring in recycling. Indian demand peaks with weddings and Diwali/Akshaya Tritiya; Chinese with Lunar New Year. Local premiums or discounts show how hard physical buyers are pulling.', 'WGC, India import duty, Shanghai premium'],
        ['Mine supply and recycling', 'Mine output (about 3,600 t a year) barely responds to price in the short run; recycling (about 1,300 t) does, and caps rallies.', 'WGC supply, USGS']],
      cot: 'Managed money holds the speculative long; swap dealers are mostly the banks on the other side of OTC and ETF-related flows; producers/merchants (miners, refiners, bullion banks hedging inventory) are structurally short. In gold, funds trend-follow: their net length tracks price momentum and real-rate moves, so a crowded long after a run-up is liquidation risk rather than a signal on its own.',
      season: 'Indian festival and wedding buying (Sep–Nov, Apr–May), Chinese Lunar New Year stocking (Dec–Jan) and January fund re-allocation have historically made Dec–Feb the firmest stretch; summer (Jun–Jul) is often soft. Seasonals are weak next to rates and the dollar.',
      links: ['Rates and the dollar link gold to every macro market on the desk (see Markets & macro).', 'Silver follows gold with higher beta; copper/gold ratio tracks growth and bond yields.', 'A falling dollar that lifts gold usually supports grain and oilseed export demand too.'] },
    SI: { spec: [['Contract', 'COMEX Silver (SI); 1,000-oz (SIL) and micro'], ['Size / tick', '5,000 troy oz; $0.005/oz = $25 per lot'], ['Active months', 'Mar, May, Jul, Sep, Dec'],
        ['First notice / last trade', 'As gold: first notice on the last business day of the month before delivery; last trade third-last business day of the delivery month'],
        ['Delivery', '1,000- or 1,100-oz bars, 999 fine, on warrant in a COMEX-approved vault'], ['Options', 'Monthly options expire on the 4th-last business day of the month before the contract month']],
      drivers: [['Gold', 'Silver trades as high-beta gold: most days, gold, real rates and the dollar explain the move.', 'Gold price, gold/silver ratio'],
        ['Industrial demand (about half of use)', 'Electronics, brazing, and above all solar panels (photovoltaic paste). Solar use rose from about 100 Moz in 2020 to near 200 Moz; thrifting (using less silver per cell) is the offset to watch.', 'Silver Institute, solar installations, copper and industrial metals'],
        ['Mine supply', 'Most silver is a by-product of lead/zinc, copper and gold mines, so output does not respond to the silver price. Mexico, China, Peru lead.', 'Silver Institute, USGS'],
        ['Investment and ETFs', 'Bar/coin buying (India especially) and ETF flows (SLV) swing the balance; the market has run deficits since 2021 and London vault stocks have been drawn down.', 'SLV holdings, LBMA vault data'],
        ['Gold/silver ratio', 'Ounces of silver per ounce of gold. A high ratio (silver cheap) has tended to mean-revert when industry is strong; it spikes in recessions.', 'Ratio vs its 10-year range']],
      cot: 'Managed money swings much harder in silver than in gold relative to open interest, and silver has a long history of crowded fund positions being squeezed. Swap dealers and producer/merchant shorts (miners, bullion banks) take the other side. Read managed money against its own 3-year range, not the absolute level.',
      season: 'Tends to follow gold\'s seasonal (firm Dec–Feb, soft summer), with extra swings from Indian buying when prices dip.',
      links: ['Copper and industrial metals: silver\'s industrial half follows the same cycle.', 'Solar build-out (China especially) is the main structural demand story.'] },
    HG: { spec: [['Contract', 'COMEX Copper (HG); micro copper (MHG, 2,500 lb, cash-settled)'], ['Size / tick', '25,000 lb; $0.0005/lb = $12.50 per lot'], ['Months', 'Every month; liquidity in Mar, May, Jul, Sep, Dec'],
        ['First notice / last trade', 'First notice on the last business day of the month before delivery; last trade third-last business day of the delivery month'],
        ['Delivery', 'Grade 1 copper cathode on warrant in a COMEX-approved US warehouse (tariff status matters: COMEX metal sits in the US)'], ['Other exchanges', 'LME (the world benchmark, $/t, daily prompt dates), Shanghai (SHFE, yuan, VAT-inclusive)']],
      drivers: [['China demand', 'China uses over half the world\'s refined copper: grid investment, property (falling), electric vehicles and air-conditioning. Chinese import premiums (Yangshan) and SHFE stocks show the pull.', 'ICSG balance, China imports, SHFE stocks'],
        ['Mine supply and disruptions', 'Mine supply is concentrated (Chile, Peru, DR Congo, China, Indonesia) and disruption-prone: strikes, mud rushes, grade decline, permits. A tight mine market shows up first in concentrate.', 'ICSG mine production, company news'],
        ['Treatment charges (TC/RCs)', 'What miners pay smelters to process concentrate. Very low or negative TCs mean concentrate is scarce (bullish for copper, bad for smelters); smelters then cut runs.', 'Annual benchmark (Antofagasta–China smelters), spot TCs'],
        ['Exchange stocks', 'Visible stocks at the LME, COMEX and SHFE are the market\'s scorecard. Big draws with LME backwardation mean nearby metal is tight.', 'LME/COMEX/SHFE stocks (daily/weekly)'],
        ['COMEX–LME arbitrage and US tariffs', 'US tariff risk on copper pulls metal into COMEX warehouses and puts COMEX at a premium to the LME; the premium collapses when tariff risk is resolved. The arb also decides where stocks build.', 'COMEX minus LME spread'],
        ['Macro', 'Dr. Copper: global growth, the dollar and China\'s credit cycle. Funds use copper to express growth views.', 'PMIs, dollar, China credit']],
      cot: 'Managed money is the swing factor and follows trend and Chinese macro; producer/merchant shorts are fabricators and miners hedging. In 2025–26 positioning also reflected the US tariff trade (COMEX vs LME), so compare the COT with the arbitrage before reading it as a pure growth bet.',
      season: 'Chinese demand is strongest from March to May after Lunar New Year (stocks draw) and weak in the July–August heat; LME/SHFE stocks usually build in Jan–Feb. Prices have tended to firm in Q1 and soften into mid-year.',
      links: ['Copper/gold ratio moves with bond yields and growth expectations.', 'Energy transition demand (grids, EVs) links copper to power and gas.', 'Chile and Peru weather (El Niño rains) can disrupt mines and ports.'] },
    ALI: { spec: [['Contracts', 'COMEX Aluminum (ALI, 25 t, physically delivered, thinly traded) and COMEX Aluminum Midwest premium (AUP, cash-settled to Platts)'],
        ['Size / tick', 'ALI: 25 t, $0.25/t = $6.25. AUP: 25 t (55,116 lb), quoted in $/lb'], ['Months', 'Every month'],
        ['First notice / last trade', 'ALI: as gold and copper (first notice end of the prior month, last trade third-last business day). AUP: settles to the monthly average of the Platts US Midwest premium on the last business day of the month'],
        ['Benchmark', 'The world price is the LME 3-month aluminium. US buyers pay LME + Midwest premium (freight, duty/tariff, financing); the premium is where US-specific tightness shows'],
        ['Why AUP for positioning', 'CFTC publishes COMEX aluminum (ALI) positions only in weeks with enough traders; the Midwest premium (AUP) has a continuous weekly report, so the desk uses it for COT']],
      drivers: [['Energy cost', 'Smelting takes about 14–15 MWh of power per tonne, so power is roughly a third or more of cost. Power-price spikes (Europe 2022) close smelters; cheap hydro/coal power keeps them running.', 'Power and coal prices, smelter restarts/curtailments'],
        ['China capacity cap', 'China makes about 60% of the world\'s primary aluminium and has capped capacity near 45 Mt/yr. With output near the cap, world supply growth has to come from elsewhere (Indonesia, India, Middle East).', 'IAI monthly production (China vs rest)'],
        ['US Midwest premium and tariffs', 'US Section 232 tariffs on aluminum feed straight into the Midwest premium: the US imports about 80% of its primary metal (Canada mainly), so the duty is paid by the US buyer.', 'AUP futures, Canadian exports'],
        ['Alumina and bauxite', 'Alumina (from bauxite) is the main raw material; Guinea bauxite export disruptions and alumina refinery outages have driven sharp cost spikes.', 'USGS, alumina prices'],
        ['Exchange stocks and LME spreads', 'LME stocks and the cash–3-month spread show nearby tightness; warrant cancellations signal metal leaving.', 'LME stocks (daily)'],
        ['Demand', 'Transport (lightweighting, EVs), packaging, construction, power cables. China\'s semis exports are the swing.', 'China exports, PMIs']],
      cot: 'AUP positions are mostly physical-market hedgers (producers, traders, consumers) with a modest managed-money share; fund length in the premium usually reflects a tariff view. The outright aluminum price is set at the LME, whose own Commitments of Traders report is not freely downloadable.',
      season: 'Chinese output dips in winter heating-season curbs in some years; demand builds in spring. The Midwest premium is driven by trade policy more than seasons.',
      links: ['Energy: aluminum is "solid electricity"; gas and power prices set the marginal smelter cost.', 'Copper/aluminum substitution in cables and air-conditioning when copper is expensive.'] },
  };
  const REPORTS = [['CFTC Commitments of Traders', 'Fri 3:30 pm ET', 'Positions as of Tuesday (gold, silver, copper, aluminum Midwest premium)'],
    ['COMEX warehouse stocks', 'Daily, evening', 'Registered (deliverable) and eligible metal in COMEX warehouses'],
    ['LME official prices and stocks', 'Daily, London', 'Cash, 3-month, warehouse stocks, cancelled warrants'],
    ['ETF holdings (GLD, IAU, SLV)', 'Daily', 'Metal held by the large US ETFs'],
    ['World Gold Council Gold Demand Trends', 'Quarterly (~5 weeks after quarter end)', 'Jewellery, technology, bar/coin, ETFs, central banks, supply'],
    ['ICSG monthly press release', 'Monthly (3rd–4th week)', 'World copper mine/refined production, usage, balance'],
    ['IAI primary aluminium production', 'Monthly (~20th)', 'Output by region incl. China'],
    ['Silver Institute World Silver Survey', 'Annual (April), interim (November)', 'Silver supply, demand, deficit'],
    ['USGS Mineral Commodity Summaries', 'Annual (late January)', 'World mine production and reserves by country; US statistics'],
    ['US CPI, jobs, FOMC', 'Monthly / 8 meetings a year', 'Real rates and the dollar (see Markets & macro)']];

  function shell() {
    $('#metals').innerHTML = `<div class="mk-bar" id="mtDesks" style="margin:10px 12px 0">${Object.entries(DESKS).map(([k, l]) => `<button data-m="${k}">${l}</button>`).join('')}</div>
      <nav class="tabs" id="mtTabs"></nav><main><div id="mtBody"></div></main>`;
    $$('#mtDesks button').forEach(b => b.onclick = () => { mk = b.dataset.m; render(); });
  }
  function nav() {
    $$('#mtDesks button').forEach(x => x.classList.toggle('on', x.dataset.m === mk));
    $('#mtTabs').innerHTML = TABS.map(([k, l], i) => `<button data-t="${k}" class="${k === tab ? 'on' : ''}">${i + 1} · ${l}</button>`).join('');
    $$('#mtTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; render(); });
  }
  const safe = fn => { try { const r = fn(); if (r && r.catch) r.catch(e => fail(e)); } catch (e) { fail(e); } };
  const fail = e => { console.error(e); body().insertAdjacentHTML('beforeend', `<div class="card"><p class="note">This panel failed to load (${esc(String(e.message || e).slice(0, 120))}).</p></div>`); };
  const M = () => D && D.metals && D.metals[KEY[mk]];

  function render() {
    nav();
    history.replaceState(null, '', '#metals/' + mk.toLowerCase() + '/' + tab);
    body().innerHTML = '';
    ({ primer, px, flows, sd, outlook, news, status, seas: () => MktStudy.mount(body(), [mk]) }[tab] || outlook)();
  }

  // ───────── 1 · Primer ─────────
  function primer() {
    const p = P[mk];
    body().innerHTML = `<div class="grid g2">
      <div class="card"><h2>${DESKS[mk]}: the contract</h2><div class="tbl"><table>${p.spec.map(r => tr(r[0], r[1])).join('')}</table></div>
        <h3>Seasonality</h3><p>${p.season}</p><h3>Links to other markets</h3><ul class="read">${p.links.map(x => `<li>${x}</li>`).join('')}</ul></div>
      <div class="card"><h2>What moves the price</h2><div class="tbl"><table><tr><th class="l">Driver</th><th class="l">Mechanism</th><th class="l">Watch</th></tr>
        ${p.drivers.map(r => `<tr><td class="l"><b>${r[0]}</b></td><td class="l">${r[1]}</td><td class="l">${r[2]}</td></tr>`).join('')}</table></div>
        <h3>How the COT categories behave in ${DESKS[mk].toLowerCase()}</h3><p>${p.cot}</p></div></div>
      ${Specs.slot('metals', mk === 'ALI' ? ['ALI', 'AUP'] : [mk])}
      <div class="card" style="margin-top:12px"><h2>Key reports</h2><div class="tbl"><table><tr><th class="l">Report</th><th class="l">When</th><th class="l">What</th></tr>
        ${REPORTS.map(r => `<tr><td class="l">${r[0]}</td><td class="l">${r[1]}</td><td class="l">${r[2]}</td></tr>`).join('')}</table></div>
        <p class="note">Live numbers for each driver are on the other tabs of this desk. Release times and the date of every input are on the Data status tab.</p></div>`;
  }

  // ───────── 2 · Prices & curve ─────────
  function px() {
    const m = M();
    if (!m || !m.price) { body().innerHTML = none('Price data'); return; }
    const p = m.price, dp = p.dp, sp = p.spreads || [];
    const extra = { GC: goldDrivers, SI: silverRatio, HG: copperArb, ALI: aluminumPrem }[mk];
    body().innerHTML = `<div class="grid g4">
        ${kpi(`${DESKS[mk]} · ${esc(p.contract)}`, `${fmt(p.last, dp)}`, `${p.unit} · ${p.date} · ${sgn(p.chg_1w, 1, '%')} wk · ${sgn(p.chg_1m, 1, '%')} mo`)}
        ${kpi('Year to date', sgn(p.chg_ytd, 1, '%'), `52-wk range ${fmt(p.lo52, dp)}–${fmt(p.hi52, dp)}`)}
        ${sp[0] ? kpi('Front spread', `${sgn(sp[0].spread, dp)}`, `${esc(sp[0].pair)} · ${fmt(sp[0].ann_pct, 2)}% a year carry`) : ''}
        ${sp[0] && sp[0].lease_pct != null && (mk === 'GC' || mk === 'SI') ? kpi('Implied lease rate', `${fmt(sp[0].lease_pct, 2)}%`, `T-bill ${fmt(D.rate, 2)}% minus the carry the spread pays`) : ''}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Forward curve <span class="note">${p.unit}, last close of each listed contract</span></h2><div class="chart short"><canvas id="mtCurve"></canvas></div>
          <div class="tbl"><table><tr><th class="l">Spread</th><th>Later − earlier</th><th>Carry, % a year</th>${mk === 'GC' || mk === 'SI' ? '<th>Implied lease rate</th>' : ''}</tr>
          ${sp.map(s => `<tr><td class="l">${esc(s.pair)}</td><td>${sgn(s.spread, dp)}</td><td>${fmt(s.ann_pct, 2)}%</td>${mk === 'GC' || mk === 'SI' ? `<td>${fmt(s.lease_pct, 2)}%</td>` : ''}</tr>`).join('')}</table></div>
          <p class="note">${mk === 'GC' || mk === 'SI' ? 'Precious metals normally sit in full carry (later months higher by about the interest rate). Carry below the T-bill rate means an implied lease rate above zero: metal is tight to borrow. Backwardation is rare and a strong squeeze signal.' : 'Base metals swing between contango (ample stocks) and backwardation (nearby metal tight). Compare with the LME cash–3-month spread on the Supply & demand tab.'}</p></div>
        <div class="card"><h2>${DESKS[mk]} front month, weekly <span class="note">${p.unit}, continuous (rolls not adjusted)</span></h2><div class="chart short"><canvas id="mtLong"></canvas></div></div>
      </div><div id="mtExtra"></div><div id="mtRv" style="margin-top:12px"></div>`;
    chart('mtCurve', { type: 'line', data: { labels: p.curve.map(c => c.label), datasets: [ln(p.curve.map(c => c.last), DESKS[mk], PAL[0], { pointRadius: 3 })] }, options: { plugins: { legend: { display: false } } } });
    chart('mtLong', { type: 'line', data: { labels: p.weekly.date, datasets: [ln(p.weekly.v, DESKS[mk], PAL[2])] }, options: { plugins: { legend: { display: false } } } });
    if (extra) safe(() => extra(m));
    if (typeof RVView !== 'undefined') safe(() => Promise.resolve(RVView.mount($('#mtRv'), mk)).then(() => $$('#mtRv .card').forEach(c => { if (/Report-day playbook/.test(c.querySelector('h2')?.textContent || '')) c.remove(); })));
  }
  function goldDrivers(m) {
    const r = (m.drivers || {}).real10, d = (m.drivers || {}).dxy, f = m.fit;
    $('#mtExtra').innerHTML = `<div class="grid g2" style="margin-top:12px">
      <div class="card"><h2>Gold vs the 10-year real yield <span class="note">weekly, 5 years; real yield axis inverted</span></h2>${r ? `<div class="chart"><canvas id="mtReal"></canvas></div>
        <p class="note">10-yr TIPS yield ${fmt(r.last, 2)}% on ${r.asof} (${sgn(r.chg_1m, 2)} pts in a month). Dollar index ${d ? `${fmt(d.last, 2)} on ${d.asof} (${sgn(d.chg_1m_pct, 1, '%')} in a month)` : '–'}. Sources: US Treasury real yield curve; Yahoo (DXY).</p>` : '<p class="note">Real-yield data not built yet.</p>'}</div>
      <div class="card"><h2>Driver fit <span class="note">context only</span></h2>${f ? `<div class="chart"><canvas id="mtFit"></canvas></div>
        <p class="note">Fit $${fmt(f.fair, 0)} vs the market (${sgn(f.gap_pct, 0, '%')} from it) as of ${f.asof}; R² ${f.r2}, typical miss ±${fmt(f.se_pct, 0)}%. Variables used: ${f.variables.join('; ')}; ${f.window}. Since 2022 central-bank buying has kept gold well above what rates alone imply, so a gap here is not a trade signal.</p>` : '<p class="note">Needs real-yield and dollar history.</p>'}</div></div>`;
    if (r) { const gw = m.price.weekly, map = Object.fromEntries(gw.date.map((x, i) => [x, gw.v[i]]));
      chart('mtReal', { type: 'line', data: { labels: r.weekly.date, datasets: [ln(r.weekly.date.map(x => map[x] ?? null), 'Gold ($/oz)', PAL[3]), ln(r.weekly.v, '10-yr real yield (%)', PAL[2], { yAxisID: 'y1' })] },
        options: { scales: { y1: { position: 'right', reverse: true, grid: { display: false } } } } }); }
    if (f) chart('mtFit', { type: 'line', data: { labels: f.hist.date, datasets: [ln(f.hist.actual, 'Gold', PAL[3]), ln(f.hist.fit, 'Fit', '#999', { borderDash: [4, 3] })] } });
  }
  function silverRatio(m) {
    const r = m.ratio;
    $('#mtExtra').innerHTML = `<div class="card" style="margin-top:12px"><h2>Gold/silver ratio <span class="note">ounces of silver per ounce of gold, weekly, 10 years</span></h2>${r ? `<div class="chart"><canvas id="mtRatio"></canvas></div>
      <p class="note">${fmt(r.last, 1)} on ${r.asof} (${r.pct10 == null ? '–' : r.pct10 + 'th'} percentile of 10 years; median ${fmt(r.med10, 1)}; ${sgn(r.chg_1m, 1)} in a month). High = silver cheap to gold. COMEX front months.</p>` : '<p class="note">Needs gold and silver prices.</p>'}</div>`;
    if (r) chart('mtRatio', { type: 'line', data: { labels: r.weekly.date, datasets: [ln(r.weekly.v, 'Gold/silver', PAL[4]), ln(r.weekly.v.map(() => r.med10), '10-yr median', '#999', { borderDash: [4, 3] })] } });
  }
  function copperArb(m) {
    const a = m.arb, L = m.lme;
    $('#mtExtra').innerHTML = `<div class="grid g2" style="margin-top:12px">
      <div class="card"><h2>COMEX minus LME copper <span class="note">$/t</span></h2>${a ? `<div class="chart"><canvas id="mtArb"></canvas></div>
        <p class="note">${sgn(a.usd_t, 0)} $/t (${sgn(a.pct, 1, '%')}) on ${a.asof}; ${sgn(a.chg_1m, 0)} $/t in a month. ${a.note} A wide COMEX premium pulls metal into US warehouses (tariff trade); it collapses when the tariff question is settled.</p>` : '<p class="note">Needs LME prices (westmetall.com) and COMEX copper.</p>'}</div>
      <div class="card"><h2>LME copper: cash and 3-month <span class="note">$/t</span></h2>${L ? `<div class="chart"><canvas id="mtLme"></canvas></div>
        <p class="note">Cash ${fmt(L.cash, 0)}, 3-month ${fmt(L.m3, 0)}, cash–3M ${sgn(L.cash_3m, 0)} on ${L.asof}. ${L.source}.</p>` : '<p class="note">LME data not built yet.</p>'}</div></div>`;
    if (a) chart('mtArb', { type: 'line', data: { labels: a.series.date, datasets: [ln(a.series.v, 'COMEX − LME 3M', PAL[1], { fill: 'origin', backgroundColor: 'rgba(192,57,43,.08)' })] }, options: { plugins: { legend: { display: false } } } });
    if (L) chart('mtLme', { type: 'line', data: { labels: L.series.date, datasets: [ln(L.series.cash, 'Cash', PAL[0]), ln(L.series.m3, '3-month', PAL[2])] } });
  }
  function aluminumPrem(m) {
    const w = m.midwest, L = m.lme;
    $('#mtExtra').innerHTML = `<div class="grid g2" style="margin-top:12px">
      <div class="card"><h2>US Midwest premium (COMEX AUP) <span class="note">$/lb, weekly</span></h2>${w ? `<div class="chart"><canvas id="mtMw"></canvas></div>
        <p class="note">${esc(w.contract)} ${fmt(w.last, 4)} $/lb (≈ $${fmt(w.usd_t, 0)}/t) on ${w.date}; ${sgn(w.chg_1m, 1, '%')} in a month, ${w.pct5 == null ? '–' : w.pct5 + 'th'} percentile of 5 years. US buyers pay LME + this premium; tariffs on imports show up here.</p>` : '<p class="note">Midwest premium prices not built yet.</p>'}</div>
      <div class="card"><h2>LME aluminium: cash and 3-month <span class="note">$/t</span></h2>${L ? `<div class="chart"><canvas id="mtLmeAl"></canvas></div>
        <p class="note">Cash ${fmt(L.cash, 0)}, 3-month ${fmt(L.m3, 0)}, cash–3M ${sgn(L.cash_3m, 0)} on ${L.asof}; COMEX ALI front ${fmt(m.price.last, 0)} $/t. ${L.source}.</p>` : '<p class="note">LME data not built yet.</p>'}</div></div>`;
    if (w) chart('mtMw', { type: 'line', data: { labels: w.weekly.date, datasets: [ln(w.weekly.v, 'Midwest premium', PAL[5])] }, options: { plugins: { legend: { display: false } } } });
    if (L) chart('mtLmeAl', { type: 'line', data: { labels: L.series.date, datasets: [ln(L.series.cash, 'Cash', PAL[0]), ln(L.series.m3, '3-month', PAL[2])] } });
  }

  // ───────── 3 · Futures & COT ─────────
  function flows() {
    const cs = COT[mk];
    body().innerHTML = `<div class="card"><h2>${DESKS[mk]}: price and technicals</h2><div id="mtTech"></div></div>
      <div class="card" style="margin-top:12px"><h2>Positioning (CFTC) ${mk === 'ALI' ? '<span class="note">aluminum Midwest premium (AUP)</span>' : ''}</h2>
        ${mk === 'ALI' ? '<p class="note">The CFTC reports COMEX aluminum (ALI) only in weeks with enough traders (it has been missing for months at a time), so positioning here is the COMEX aluminum Midwest premium contract, which has a continuous weekly report. Its open interest is mostly physical hedgers; the LME, where the outright price is set, publishes its own positions report that is not freely downloadable.</p>' : ''}
        <div id="mtCot"></div></div>
      <div class="card" style="margin-top:12px"><h2>Options</h2><p>CME publishes no free implied volatility for COMEX metals options. The <a href="#options/${mk}" id="mtOpt">options pricer</a> prices ${mk === 'ALI' ? 'gold, silver and copper' : DESKS[mk].toLowerCase()} options off realized volatility (editable).</p></div>`;
    Tech.mount($('#mtTech'), mk === 'ALI' ? ['ALI', 'AUP'] : [mk]);
    CotDesk.mount($('#mtCot'), [cs]);
    const o = $('#mtOpt'); if (o) o.onclick = e => { e.preventDefault(); history.pushState(null, '', '#options/' + (mk === 'ALI' ? 'HG' : mk)); $('nav.comm button[data-c="options"]').click(); };
  }

  // ───────── 4 · Supply & demand ─────────
  function usgsCard(u) {
    if (!u || !u.items) return '';
    return Object.entries(u.items).map(([c, x]) => `<div class="card" style="margin-top:12px"><h2>${c}: world ${esc(x.what.toLowerCase())} <span class="note">${esc(u.edition)}; ${esc(x.unit)}</span></h2>
      <div class="tbl"><table><tr><th class="l">Country</th><th>${x.prev_year || ''}</th><th>${x.year}</th><th>Change</th></tr>
      ${x.top.map(r => `<tr><td class="l">${esc(r.country)}</td><td>${fmt(r.before, 0)}</td><td>${fmt(r.now, 0)}</td><td>${r.before ? sgn(100 * (r.now / r.before - 1), 1, '%') : '–'}</td></tr>`).join('')}
      <tr><td class="l"><b>World</b></td><td>${fmt(x.world_prev, 0)}</td><td><b>${fmt(x.world, 0)}</b></td><td>${x.world_prev ? sgn(100 * (x.world / x.world_prev - 1), 1, '%') : '–'}</td></tr></table></div>
      <p class="note">${x.year} figures are USGS estimates; revised in next year's edition.${x.reserves_world ? ` World reserves ${fmt(x.reserves_world, 0)} ${esc(x.reserves_unit)}.` : ''} Annual (late January).</p>
      ${x.us && x.us.length ? `<details><summary class="note">United States salient statistics</summary><div class="tbl"><table><tr><th class="l">Line</th>${x.us[0].years.map(y => `<th>${y}</th>`).join('')}</tr>
        ${x.us.map(l => `<tr><td class="l">${esc(l.line)} <span class="note">${esc(l.unit)}</span></td>${l.values.map(v => `<td>${fmt(v, v != null && Math.abs(v) < 100 ? 1 : 0)}</td>`).join('')}</tr>`).join('')}</table></div></details>` : ''}</div>`).join('');
  }
  function lmeStocksCard(L, metal) {
    if (!L) return `<div class="card" style="margin-top:12px"><p class="note">LME ${metal} data not built yet.</p></div>`;
    return `<div class="card" style="margin-top:12px"><h2>LME ${metal} stocks <span class="note">tonnes, daily</span></h2><div class="chart short"><canvas id="mtLmeSt"></canvas></div>
      <p class="note">${fmt(L.stock, 0)} t on ${L.asof}: ${sgn(L.stock_chg_1w, 0)} t in a week, ${sgn(L.stock_chg_1m, 0)} t in a month; ${L.stock_pct5 == null ? '–' : L.stock_pct5 + 'th'} percentile of 5 years. Cash–3M ${sgn(L.cash_3m, 0)} $/t (${L.cash_3m_pct5 == null ? '–' : L.cash_3m_pct5 + 'th'} percentile). ${L.source}.</p></div>`;
  }
  function comexCard(c, metal) {
    return `<div class="card" style="margin-top:12px"><h2>COMEX ${metal} warehouse stocks</h2>${c ? `<div class="chart short"><canvas id="mtCx"></canvas></div><p class="note">${fmt(c.total, 0)} on ${c.asof} (${sgn(c.chg_1w, 0)} in a week, ${sgn(c.chg_1m, 0)} in a month)${c.registered != null ? `; registered (deliverable) ${fmt(c.registered, 0)}` : ''}. CME daily stock report.</p>`
      : '<p class="note">Not collected yet. CME blocks GitHub\'s servers, so the daily COMEX stock reports are downloaded by the desk\'s Mac collector (local/mac_collector.py) and parsed here on the next metals run.</p>'}</div>`;
  }
  function sd() {
    const m = M();
    if (!m) { body().innerHTML = none('Supply and demand'); return; }
    ({ GC: sdGold, SI: sdSilver, HG: sdCopper, ALI: sdAluminum }[mk])(m);
  }
  function sdGold(m) {
    const w = m.wgc, e = m.etf;
    body().innerHTML = `${w ? `<div class="card"><h2>Gold supply and demand, ${esc(w.quarter)} <span class="note">tonnes; ${esc(w.source)}; fetched ${w.asof}</span></h2>
        <div class="tbl"><table><tr><th class="l">Line</th><th>${esc(w.quarter)}</th><th>Year ago</th><th>y/y</th><th>Last 4 quarters avg</th></tr>
        ${w.table.map(r => `<tr><td class="l">${r.line}</td><td><b>${fmt(r.now, 0)}</b></td><td>${fmt(r.yago, 0)}</td><td>${sgn(r.yoy, 0)}</td><td>${fmt(r.avg4, 0)}</td></tr>`).join('')}</table></div>
        <div class="chart short"><canvas id="mtWgc"></canvas></div>
        <h3>Revisions</h3>${w.revisions && w.revisions.length ? `<div class="tbl"><table><tr><th class="l">Line</th><th class="l">Quarter</th><th>Now</th><th>Before</th><th>Change</th></tr>
          ${w.revisions.map(r => `<tr><td class="l">${r.line}</td><td class="l">${esc(r.quarter)}</td><td>${fmt(r.now, 0)}</td><td>${fmt(r.before, 0)}</td><td>${sgn(r.chg, 0)}</td></tr>`).join('')}</table></div><p class="note">Changes since the WGC data stored on ${w.prev_snapshot}.</p>`
          : `<p class="note">The desk keeps every WGC release from ${w.asof}; revisions to earlier quarters show here after the next quarterly update.</p>`}</div>` : none('World Gold Council data')}
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Gold ETF holdings: SPDR GLD <span class="note">tonnes, weekly</span></h2>${e ? `<div class="chart short"><canvas id="mtEtf"></canvas></div>
          <p class="note">GLD ${fmt(e.gld.tonnes, 1)} t on ${e.gld.asof}: ${sgn(e.gld.chg_1w, 1)} t in a week, ${sgn(e.gld.chg_1m, 1)} t in a month, ${sgn(e.gld.chg_ytd, 0)} t this year (${e.gld.pct5y == null ? '–' : e.gld.pct5y + 'th'} percentile of 5 years).
          ${e.iau ? ` iShares IAU ${fmt(e.iau.tonnes, 1)} t on ${e.iau.asof} (${sgn(e.iau.chg_1m, 1)} t in a month; daily history kept from ${e.iau.n_days > 1 ? 'when the desk started' : 'today'}).` : ''} Sources: SPDR Gold Shares archive; iShares product page.</p>` : '<p class="note">ETF data not built yet.</p>'}</div>
        <div class="card"><h2>Central banks</h2>${w ? (() => { const cb = w.table.find(r => r.line === 'Central banks'); return cb ? `<p>Central banks bought <b>${fmt(cb.now, 0)} t</b> in ${esc(w.quarter)} (${sgn(cb.yoy, 0)} t vs a year ago; ${fmt(cb.avg4, 0)} t a quarter on average over the last four).</p><div class="chart short"><canvas id="mtCb"></canvas></div><p class="note">World Gold Council estimates, which include unreported buying; IMF-reported reserve changes are a subset.</p>` : ''; })() : '<p class="note">No WGC data yet.</p>'}</div></div>
      ${usgsCard(m.usgs)}`;
    if (w) {
      const sel = w.table.filter(r => ['Jewellery', 'Technology', 'Bar and coin', 'Gold ETFs', 'Central banks'].includes(r.line));
      chart('mtWgc', { type: 'bar', data: { labels: w.quarters, datasets: sel.map((r, i) => ({ label: r.line, data: r.hist, backgroundColor: PAL[i] })) }, options: { scales: { x: { stacked: true }, y: { stacked: true } } } });
      const cb = w.table.find(r => r.line === 'Central banks'); if (cb && $('#mtCb')) chart('mtCb', { type: 'bar', data: { labels: w.quarters, datasets: [{ label: 'Central banks (t)', data: cb.hist, backgroundColor: PAL[3] }] }, options: { plugins: { legend: { display: false } } } });
    }
    if (e) chart('mtEtf', { type: 'line', data: { labels: e.gld.weekly.date, datasets: [ln(e.gld.weekly.v, 'GLD (t)', PAL[3])] }, options: { plugins: { legend: { display: false } } } });
  }
  function sdSilver(m) {
    const s = m.survey, e = m.etf;
    body().innerHTML = `<div class="grid g2"><div class="card"><h2>Silver Institute: supply and demand <span class="note">${esc(s ? s.survey || '' : '')}</span></h2>${s ? `<ul class="read">${s.points.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <p class="note">Key numbers as published on the Silver Institute's supply-and-demand page (prepared with Metals Focus); checked daily, stored when they change${s.history && s.history.length ? `; previous version from ${s.history.at(-1).fetched}` : ''}. <a href="${s.url}" target="_blank" rel="noopener">Source</a>. The full survey tables are a PDF and are not parsed.</p>` : '<p class="note">Not built yet.</p>'}</div>
      <div class="card"><h2>iShares SLV holdings <span class="note">million oz</span></h2>${e ? `${e.n_days > 5 ? '<div class="chart short"><canvas id="mtSlv"></canvas></div>' : ''}<p class="note">${fmt(e.moz, 1)} Moz (${fmt(e.tonnes, 0)} t) on ${e.asof}; ${sgn(e.chg_1w, 1)} Moz in a week, ${sgn(e.chg_1m, 1)} Moz in a month. iShares publishes only the current figure, so the desk stores one snapshot a day (history from when collection started).</p>` : '<p class="note">Not built yet.</p>'}</div></div>
      ${usgsCard(m.usgs)}`;
    if (e && e.n_days > 5) chart('mtSlv', { type: 'line', data: { labels: e.series.date, datasets: [ln(e.series.v, 'SLV (Moz)', PAL[6])] }, options: { plugins: { legend: { display: false } } } });
  }
  function sdCopper(m) {
    const ic = m.icsg, L = m.lme;
    const lab = { mine: 'Mine production', mine_util: 'Mine capacity use (%)', refined_primary: 'Refined, primary', refined_secondary: 'Refined, secondary (scrap)', refined: 'Refined production', refinery_util: 'Refinery capacity use (%)',
      usage: 'Refined usage', stocks: 'Refined stocks, end of period', stock_change: 'Stock change', balance: 'Refined balance (production − usage)', balance_sa: 'Balance, seasonally adjusted', balance_bonded: 'Balance adjusted for China bonded stocks' };
    body().innerHTML = `${ic ? `<div class="card"><h2>World refined copper balance (ICSG) <span class="note">thousand t; data to ${esc(ic.data_month)}; issued ${esc(ic.issued)}</span></h2>
        <div class="tbl"><table><tr><th class="l"></th>${(ic.columns || []).map(c => `<th>${esc(c)}</th>`).join('')}</tr>
        ${Object.entries(ic.table || {}).map(([k, r]) => `<tr><td class="l">${lab[k] || k}</td>${(ic.columns || []).map(c => `<td>${r[c] == null ? '' : /balance|change/.test(k) ? sgn(r[c], 0) : fmt(r[c], /util/.test(k) ? 1 : 0)}</td>`).join('')}</tr>`).join('')}</table></div>
        <h3>Revisions vs the previous release${ic.prev_issued ? ` (${esc(ic.prev_issued)})` : ''}</h3>${ic.revisions && ic.revisions.length ? `<div class="tbl"><table><tr><th class="l">Line</th><th class="l">Period</th><th>Now</th><th>Before</th><th>Change</th></tr>
          ${ic.revisions.map(r => `<tr><td class="l">${lab[r.line] || r.line}</td><td class="l">${esc(r.period)}</td><td>${fmt(r.now, 0)}</td><td>${fmt(r.before, 0)}</td><td>${sgn(r.chg, 0)}</td></tr>`).join('')}</table></div>`
          : '<p class="note">The desk stores every ICSG release from the first one it read; revisions to the same periods show here after the next monthly release.</p>'}
        <h3>What the release says</h3><ul class="read">${(ic.points || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <p class="note">Positive balance = surplus. <a href="${ic.url}" target="_blank" rel="noopener">ICSG press release</a>. The full bulletin is paid; the press release is free.</p></div>` : none('ICSG data')}
      ${lmeStocksCard(L, 'copper')}${comexCard(m.comex_stocks, 'copper')}
      <div class="card" style="margin-top:12px"><h2>Not on this desk (no free automated source)</h2><p class="note">Shanghai Futures Exchange weekly copper stocks (the exchange site does not serve its data files to GitHub's servers), Chinese Yangshan import premium and spot treatment charges (paid price reporters), and the LME positions report. These matter: check them through a broker or the press when the balance or the arbitrage moves.</p></div>
      ${usgsCard(m.usgs)}`;
    if (L) chart('mtLmeSt', { type: 'line', data: { labels: L.series.date, datasets: [ln(L.series.stock, 'LME stocks (t)', PAL[2], { fill: 'origin', backgroundColor: 'rgba(44,111,187,.08)' })] }, options: { plugins: { legend: { display: false } } } });
    if (m.comex_stocks) chart('mtCx', { type: 'line', data: { labels: m.comex_stocks.series.date, datasets: [ln(m.comex_stocks.series.v, 'COMEX stocks', PAL[1])] }, options: { plugins: { legend: { display: false } } } });
  }
  function sdAluminum(m) {
    const I = m.iai, L = m.lme;
    body().innerHTML = `${I ? `<div class="grid g4">${kpi('World primary output', `${fmt(I.world, 0)} kt`, `${esc(I.month)} · ${fmt(I.world_daily, 1)} kt/day · ${sgn(I.world_yoy_pct, 1, '%')} y/y`)}
        ${kpi('China (estimated)', `${fmt(I.china, 0)} kt`, `${sgn(I.china_yoy_pct, 1, '%')} y/y`)}${kpi('Outside China', `${fmt(I.world - I.china, 0)} kt`, `${sgn(I.exchina_yoy_pct, 1, '%')} y/y`)}${kpi('Year to date', sgn(I.ytd_yoy_pct, 1, '%'), 'vs same months last year')}</div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>Primary aluminium production (IAI) <span class="note">thousand t a month</span></h2><div class="chart"><canvas id="mtIai"></canvas></div>
        <p class="note">${esc(I.source)}; monthly, about the 20th. ${I.revisions && I.revisions.length ? `Revisions vs the ${esc(I.prev_release_month)} release: ${I.revisions.map(r => `${r.month} ${sgn(r.chg, 0)} kt`).join(', ')}.` : 'The desk stores what each release says about the last 13 months; revisions show from the next release.'}</p></div>
        <div class="card"><h2>By region, ${esc(I.month)} <span class="note">kt</span></h2><div class="tbl"><table>${Object.entries(I.regions).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<tr><td class="l">${esc(k)}</td><td>${fmt(v, 0)}</td><td>${fmt(100 * v / I.world, 1)}%</td></tr>`).join('')}</table></div>
        <p class="note">China's output runs close to its ~45 Mt/yr capacity cap, so growth elsewhere (Gulf, India, Indonesia) sets world supply growth.</p></div></div>` : none('IAI data')}
      ${lmeStocksCard(L, 'aluminium')}${comexCard(m.comex_stocks, 'aluminum')}
      ${usgsCard(m.usgs)}`;
    if (I) chart('mtIai', { type: 'line', data: { labels: I.series.month, datasets: [ln(I.series.world, 'World', PAL[0]), ...(I.series.china ? [ln(I.series.china, 'China (estimated)', PAL[1])] : [])] } });
    if (L) chart('mtLmeSt', { type: 'line', data: { labels: L.series.date, datasets: [ln(L.series.stock, 'LME stocks (t)', PAL[2], { fill: 'origin', backgroundColor: 'rgba(44,111,187,.08)' })] }, options: { plugins: { legend: { display: false } } } });
    if (m.comex_stocks) chart('mtCx', { type: 'line', data: { labels: m.comex_stocks.series.date, datasets: [ln(m.comex_stocks.series.v, 'COMEX stocks', PAL[1])] }, options: { plugins: { legend: { display: false } } } });
  }

  // ───────── 6 · Outlook ─────────
  function outlook() {
    const m = M();
    body().innerHTML = `${m && !m.error ? `<div class="card"><h2>${DESKS[mk]} brief · ${esc(m.view)} <span class="note">built ${esc(D.generated)}</span></h2>
        ${m.brief.map(b => `<p><b>${esc(b.h)}.</b> ${esc(b.t)}</p>`).join('')}</div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>What drives the read</h2><div class="tbl"><table><thead><tr><th class="l">Factor</th><th class="l">Reading</th><th class="l">Effect</th></tr></thead><tbody>
        ${m.factors.map(x => `<tr><td class="l">${esc(x.name)}</td><td class="l">${esc(x.txt)}</td><td class="l">${pill(x.s)}</td></tr>`).join('')}</tbody></table></div>
        <p class="note">Each factor reads +1, 0 or −1 and the view is their average (${m.score == null ? '–' : (m.score > 0 ? '+' : '') + m.score}). Rule-based context from public data, not a tested trading signal. The same read feeds the ${DESKS[mk]} tile on the Overview tab.</p></div>
        <div class="card"><h2>Seasonal windows due</h2><div id="mtSz"></div></div></div>` : none('The metals model')}
      <div class="card" style="margin-top:12px"><h2>Technicals and positioning</h2><div id="mtOTech"></div></div>`;
    Tech.mount($('#mtOTech'), [mk]);
    if ($('#mtSz')) MktStudy.upcoming($('#mtSz'), [mk], () => { tab = 'seas'; render(); });
  }

  // ───────── 7 · News & calendar ─────────
  function news() {
    body().innerHTML = `<div class="grid g2"><div class="card"><h2>${DESKS[mk]}: calendar <span class="note">next 30 days, US Central time</span></h2><div id="mtCal"></div></div>
      <div class="card"><h2>News <span class="note">price- and production-relevant headlines: Reuters, Bloomberg, WSJ and other tier-1 outlets, exchanges and industry bodies</span></h2><div id="mtNews"></div></div></div>`;
    Intel.calendar($('#mtCal'), { markets: [mk], days: 30, minImp: 1 });
    Intel.news($('#mtNews'), { tags: [KEY[mk]], n: 30, chips: true });
  }

  // ───────── 8 · Data status ─────────
  async function status() {
    if (!ST) [ST, CAL] = await Promise.all([getJSON('data/metals/status.json').catch(() => null), getJSON('data/metals/release_calendar.json').catch(() => null)]);
    if (!ST) { body().innerHTML = none('Data status'); return; }
    const chip = r => r.state === 'ok' ? '<b class="up">OK</b>' : r.state === 'needs Mac' ? '<b>NEEDS MAC</b>' : r.state === 'late' ? '<b class="dn">LATE</b>' : '<b class="dn">MISSING</b>';
    const bad = ST.sources.filter(r => r.state === 'late' || r.state === 'missing'), grp = [...new Set(ST.sources.map(r => r.group))];
    body().innerHTML = `<div class="card"><h2>Metals data status <span class="note">checked ${esc(ST.generated)}</span></h2>
      <p class="read">${bad.length ? `<b class="dn">${bad.length} of ${ST.sources.length} sources are late or missing:</b> ${bad.map(r => esc(r.source)).join('; ')}. Numbers built on them may be out of date.` : `<b class="up">All automatic sources are current.</b>`}</p>
      <div class="tbl"><table><tr><th class="l">Source</th><th>Latest data</th><th>Age</th><th class="l">Cadence</th><th>Late after</th><th>Status</th><th class="l">Feed</th><th class="l">Used in</th></tr>
      ${grp.map(g => `<tr><td class="l" colspan="8"><b>${esc(g)}</b></td></tr>` + ST.sources.filter(r => r.group === g).map(r => `<tr style="${r.state === 'late' || r.state === 'missing' ? 'background:rgba(192,57,43,.08)' : ''}"><td class="l">${esc(r.source)}</td><td class="n">${r.latest || '–'}</td><td class="n">${r.age == null ? '–' : r.age + ' ' + (r.age_unit === 'days' ? 'd' : 'bd')}</td><td class="l">${esc(r.cadence)}</td><td class="n">${r.limit} ${r.age_unit === 'days' ? 'd' : 'bd'}</td><td>${chip(r)}</td><td class="l note">${r.manual ? 'Mac collector' : 'automatic'}</td><td class="l note">${esc(r.used_in)}</td></tr>`).join('')).join('')}</table></div>
      <p class="note">Age in business days (bd) for daily sources, calendar days (d) for the rest; monthly and quarterly sources are dated by the period they cover. A catch-up job runs every night and next morning: it reruns the metals workflow when an automatic source is late or a run failed, and turns red if that does not fix it.</p></div>
      ${CAL ? `<div class="grid g2" style="margin-top:12px"><div class="card"><h2>Release timing</h2><div class="tbl"><table><tr><th class="l">Report</th><th class="l">Published</th><th class="l">Desk update</th></tr>
        ${CAL.timing.map(t => `<tr><td class="l">${esc(t.report)}</td><td class="l">${esc(t.when)}</td><td class="l">${esc(t.desk)}</td></tr>`).join('')}</table></div></div>
        <div class="card"><h2>Next releases</h2><div class="tbl"><table><tr><th class="l">Date</th><th class="l">Report</th></tr>
        ${CAL.upcoming.filter(u => !/Commitments/.test(u.event)).slice(0, 14).map(u => `<tr><td class="l">${u.date}</td><td class="l">${u.link ? `<a href="${u.link}" target="_blank" rel="noopener">${esc(u.event)}</a>` : esc(u.event)}${u.estimated ? ' <span class="note">(estimated)</span>' : ''}</td></tr>`).join('')}</table></div>
        <p class="note">Plus the CFTC report every Friday at 3:30 pm ET.</p></div></div>` : ''}
      <div class="card" style="margin-top:12px"><h2>What could not be automated</h2><ul class="read">
        <li><b>COMEX warehouse stocks</b>: cmegroup.com blocks GitHub's servers; the desk's Mac collector downloads the daily reports.</li>
        <li><b>LME positions (COTR), SHFE stocks, Chinese premiums, treatment charges, Platts/Fastmarkets premiums</b>: no free automated source (paid, or blocked).</li>
        <li><b>World Gold Council full data tables</b> need a Goldhub login; the desk uses the public chart data (world totals by category).</li>
        <li><b>Silver Institute survey tables</b> are a PDF: the desk stores the key numbers from the public page.</li>
        <li><b>Free implied volatility for COMEX options</b>: not published; the options pricer uses realized volatility.</li></ul></div>`;
  }

  async function show() {
    if (!built) { shell(); built = true; }
    if (!D) D = await getJSON('data/metals/metals.json').catch(() => null);
    const m = location.hash.match(/^#metals\/(gc|si|hg|ali)(?:\/(\w+))?/i);
    if (m) { mk = m[1].toUpperCase(); if (TABS.some(t => t[0] === m[2])) tab = m[2]; }
    render(); window.scrollTo(0, 0);
  }
  return { show };
})();
