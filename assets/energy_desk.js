// Energy section: one menu with four sub-desks (natural gas, WTI crude, ULSD, RBOB), each with numbered sub-tabs like
// the cotton section. Everything reads repo data written by the workflows (no API key in the browser).
// Gas panels: assets/energy_ng.js (EnergyNG); oil and product panels: assets/energy_oil.js (EnergyOil).
// Deep links: #energy/<ng|cl|ho|rb>/<tab>; old terminal links (#energy/oref etc.) map to the matching tab.
const Energy = (() => {
  let built = false, tab = 'primer', mk = 'NG';
  const P = {
    NG: { name: 'Natural gas (Henry Hub)', spec: [['Contract', 'NYMEX Henry Hub Natural Gas (NG)'], ['Size', '10,000 MMBtu'], ['Quote / tick', '$/MMBtu; $0.001 = $10'],
        ['Months', 'Every month, many years out'], ['Delivery', 'Physical, at the Sabine Pipe Line Henry Hub in Erath, Louisiana'], ['Last trade', '3 business days before the first calendar day of the contract month']],
      sd: [['Storage vs 5-yr average', 'The single most-watched number: a deficit to the 5-year average supports price, a surplus weighs. Injection season Apr–Oct, withdrawal Nov–Mar.', 'EIA weekly storage (Thu 10:30 ET)'],
        ['Dry gas production', 'Shale output (Appalachia, Permian associated gas, Haynesville) sets supply; Permian gas follows oil drilling, Haynesville follows gas prices.', 'EIA monthly, pipeline nominations, rig count'],
        ['LNG feedgas', 'The fastest-growing demand: export terminals on the Gulf Coast take gas whenever global prices (TTF, JKM) beat Henry Hub plus shipping. Outages at one terminal free up gas at home.', 'EIA LNG exports, terminal maintenance'],
        ['Weather (HDD/CDD)', 'Winter heating and summer power burn move demand by billions of cubic feet a day; forecasts 1–2 weeks out move price daily.', 'NOAA 6–10/8–14 day outlooks, gas-weighted degree days'],
        ['Power burn', 'Gas competes with coal and renewables in power; low prices push gas into more generation.', 'EIA electricity data'],
        ['Mexico exports / Canada imports', 'Pipeline exports to Mexico add steady demand; Canadian imports add supply in the Northeast and West.', 'EIA border flows']],
      links: ['Fertilizer: natural gas is the feedstock and fuel for ammonia, so it sets the floor under nitrogen fertilizer costs (corn).', 'Grain drying and farm heating use gas and propane in the fall.', 'Ethanol plants burn gas; a large share of their non-corn cost.', 'Power and food processing costs in dairy and meat plants.'],
      season: 'Withdrawals Nov–Mar (winter risk premium peaks Dec–Feb), shoulder months Apr–May and Oct–Nov, power-burn demand Jul–Aug, Atlantic hurricane season Jun–Nov (Gulf production and LNG terminals). Storage typically peaks near the start of November.' },
    CL: { name: 'WTI crude oil', spec: [['Contract', 'NYMEX Light Sweet Crude Oil (CL)'], ['Size', '1,000 barrels'], ['Quote / tick', '$/bbl; $0.01 = $10'], ['Months', 'Every month, years out'],
        ['Delivery', 'Physical, at Cushing, Oklahoma'], ['Last trade', '3 business days before the 25th of the month before the contract month (4 if the 25th is not a business day)']],
      sd: [['OPEC+ policy', 'Production quotas and voluntary cuts by Saudi Arabia and partners decide how much spare capacity sits off the market.', 'OPEC+ meetings, OPEC MOMR'],
        ['US shale output', 'Permian and Bakken drilling respond to price with a 6–9 month lag; productivity gains have kept output rising with fewer rigs.', 'Baker Hughes rigs (Fri), EIA weekly/monthly production'],
        ['US commercial and Cushing stocks', 'Weekly builds and draws vs the seasonal norm; Cushing stocks drive the WTI calendar spreads.', 'EIA Weekly Petroleum Status Report (Wed 10:30 ET)'],
        ['Refinery runs', 'Refiners are the buyers of crude; spring and fall maintenance cut demand, summer runs peak.', 'EIA refinery utilization'],
        ['Exports and global demand', 'The US exports crude to Europe and Asia; Chinese imports and global growth set the demand side.', 'EIA exports, IEA OMR'],
        ['Geopolitics and sanctions', 'Supply risk from the Middle East, Russia, Venezuela and Iran adds a risk premium that comes and goes quickly.', 'News flow, tanker tracking']],
      links: ['Diesel and gasoline follow crude, so it sets farm fuel and freight costs.', 'Ethanol and biodiesel margins (corn, soybean oil) improve when crude is high.', 'Commodity index flows: crude is the largest weight in GSCI-type indices, so index buying and selling spills into ags.', 'A weaker dollar usually lifts both crude and grains.'],
      season: 'Spring refinery maintenance (Feb–Apr), US driving season Memorial Day–Labor Day lifts runs, fall maintenance Sep–Oct, hurricane season Jun–Nov (Gulf production and refineries).' },
    HO: { name: 'ULSD (NY Harbor heating oil)', spec: [['Contract', 'NYMEX NY Harbor ULSD (HO)'], ['Size', '42,000 gallons (1,000 bbl)'], ['Quote / tick', '$/gal; $0.0001 = $4.20'], ['Months', 'Every month'],
        ['Delivery', 'Physical, ultra-low-sulfur diesel in New York Harbor'], ['Last trade', 'Last business day of the month before the contract month']],
      sd: [['Distillate stocks', 'US distillate inventories vs the 5-year range; East Coast (PADD 1) stocks matter most for the NY Harbor contract.', 'EIA weekly (Wed)'],
        ['Diesel demand', 'Trucking, rail, farming (planting and harvest) and construction; a good read on the industrial economy.', 'EIA product supplied'],
        ['Refinery output and cracks', 'The diesel crack (HO minus crude) decides how hard refiners chase distillate yield.', 'HO–CL crack, refinery utilization'],
        ['Exports', 'The Gulf Coast exports diesel to Latin America and Europe; European shortages pull US barrels.', 'EIA exports'],
        ['Renewable diesel and biodiesel', 'Policy-driven renewable diesel (soybean oil, canola, fats) displaces petroleum diesel and links HO to ZL.', 'EPA RVO, RIN prices'],
        ['Winter heating', 'Heating oil demand in the Northeast adds a winter premium.', 'Northeast weather']],
      links: ['Farm fuel: planting and harvest diesel costs follow HO.', 'Soybean oil: renewable diesel margins (HO + credits − soybean oil cost) drive crush demand.', 'Fertilizer and grain freight (barge, rail, truck) costs.'],
      season: 'Strong demand at spring planting and fall harvest, winter heating premium Dec–Feb, refinery maintenance Feb–Apr and Sep–Oct.' },
    RB: { name: 'RBOB gasoline', spec: [['Contract', 'NYMEX RBOB Gasoline (RB)'], ['Size', '42,000 gallons (1,000 bbl)'], ['Quote / tick', '$/gal; $0.0001 = $4.20'], ['Months', 'Every month'],
        ['Delivery', 'Physical, reformulated blendstock for oxygenate blending in New York Harbor'], ['Last trade', 'Last business day of the month before the contract month']],
      sd: [['Gasoline stocks', 'US motor gasoline inventories vs the seasonal norm; East Coast stocks matter most for NY Harbor.', 'EIA weekly (Wed)'],
        ['Driving demand', 'US gasoline demand peaks in summer; weekly product supplied is a noisy but watched number.', 'EIA product supplied'],
        ['Summer/winter grade', 'Summer-grade gasoline (lower vapor pressure) is costlier to make; the April contract switch lifts the curve.', 'Contract specs'],
        ['Refinery outages and hurricanes', 'Gulf Coast refinery outages tighten gasoline quickly; the gasoline crack spikes.', 'Refinery news, NHC'],
        ['Ethanol blending', 'Gasoline is sold as E10, so about 10% of the pool is ethanol; gasoline demand sets ethanol demand.', 'EIA ethanol production and stocks']],
      links: ['Corn: ethanol uses about a third of the US corn crop, and gasoline demand sets ethanol demand.', 'Ethanol margins (ethanol price vs corn and gas) decide plant run rates.', 'Consumer spending: pump prices affect food demand and inflation.'],
      season: 'Spring build-up into summer-grade gasoline (Mar–May), peak driving Jun–Aug, demand falls after Labor Day, winter grade from mid-September.' },
  };
  const REPORTS = [['EIA Weekly Petroleum Status Report', 'Wed 10:30 ET', 'Crude, Cushing, gasoline, distillate stocks, refinery runs, production, exports'],
    ['EIA Weekly Natural Gas Storage Report', 'Thu 10:30 ET', 'Working gas in storage by region vs 5-year average'],
    ['API weekly inventories', 'Tue 4:30 pm ET', 'Industry estimate a day before EIA'], ['Baker Hughes rig count', 'Fri 1:00 pm ET', 'Oil and gas rigs: drilling activity'],
    ['EIA Short-Term Energy Outlook', 'Monthly (early in the month)', 'EIA forecasts of production, demand, prices, storage'],
    ['OPEC Monthly Oil Market Report / IEA Oil Market Report', 'Monthly, mid-month', 'Global supply-demand balances and OPEC output'],
    ['CFTC Commitments of Traders', 'Fri 3:30 pm ET', 'Fund positioning as of Tuesday']];
  // one Energy menu, four sub-desks, numbered sub-tabs (cotton style). Deep links: #energy/<ng|cl|ho|rb>/<tab>.
  const DESKS = { NG: 'Natural gas', CL: 'Crude oil (WTI)', HO: 'Heating oil (ULSD)', RB: 'RBOB gasoline' };
  const TABS = {
    NG: [['primer', 'Primer'], ['storage', 'Storage'], ['sd', 'Supply, demand &amp; fair value'], ['weather', 'Weather &amp; models'], ['model', 'Storage model'],
         ['geo', 'Production, trade &amp; LNG'], ['flows', 'Futures, options &amp; COT'], ['rv', 'Curve, spreads &amp; vol'], ['seas', 'Seasonality &amp; technicals'], ['outlook', 'Outlook'], ['news', 'News &amp; calendar']],
    CL: [['primer', 'Primer'], ['stocks', 'Inventories'], ['refining', 'Refining &amp; demand'], ['sd', 'Supply, demand &amp; fair value'], ['geo', 'Production &amp; trade'],
         ['flows', 'Futures, options &amp; COT'], ['rv', 'Curve, spreads &amp; vol'], ['seas', 'Seasonality &amp; technicals'], ['outlook', 'Outlook'], ['news', 'News &amp; calendar']],
    HO: [['primer', 'Primer'], ['stocks', 'Distillate stocks'], ['refining', 'Refining, demand &amp; cracks'], ['sd', 'Supply, demand &amp; fair value'], ['geo', 'Production &amp; trade'],
         ['flows', 'Futures, options &amp; COT'], ['rv', 'Curve, spreads &amp; vol'], ['seas', 'Seasonality &amp; technicals'], ['outlook', 'Outlook'], ['news', 'News &amp; calendar']],
    RB: [['primer', 'Primer'], ['stocks', 'Gasoline stocks'], ['refining', 'Refining, demand &amp; cracks'], ['sd', 'Supply, demand &amp; fair value'], ['geo', 'Production &amp; trade'],
         ['flows', 'Futures, options &amp; COT'], ['rv', 'Curve, spreads &amp; vol'], ['seas', 'Seasonality &amp; technicals'], ['outlook', 'Outlook'], ['news', 'News &amp; calendar']] };
  // old terminal links (#energy/<tab>) land on the matching new tab
  const LEGACY = { desk: ['NG', 'outlook'], cot: ['NG', 'flows'], gstor: ['NG', 'storage'], gsd: ['NG', 'sd'], wx: ['NG', 'weather'], gmodel: ['NG', 'model'],
    ostock: ['CL', 'stocks'], oref: ['CL', 'refining'], price: ['NG', 'rv'], tech: ['NG', 'seas'], data: ['NG', 'news'],
    'e-primer': ['NG', 'primer'], 'e-sd': ['NG', 'sd'], 'e-geo': ['NG', 'geo'], 'e-charts': ['NG', 'flows'], 'e-seas': ['NG', 'seas'], 'e-news': ['NG', 'news'] };
  function shell() {
    const el = document.getElementById('energy');
    el.innerHTML = `<div class="mk-bar" id="eDesks" style="margin:10px 12px 0">${Object.entries(DESKS).map(([k, l]) => `<button data-m="${k}">${l}</button>`).join('')}</div>
      <nav class="tabs" id="eTabs"></nav><main id="eMain"><div id="eBody"></div></main>`;
    $$('#eDesks button').forEach(b => b.onclick = () => { mk = b.dataset.m; if (!TABS[mk].some(x => x[0] === tab)) tab = 'primer'; render(); });
  }
  function tabsNav() {
    $$('#eDesks button').forEach(x => x.classList.toggle('on', x.dataset.m === mk));
    $('#eTabs').innerHTML = TABS[mk].map(([k, l], i) => `<button data-t="${k}" class="${k === tab ? 'on' : ''}">${i + 1} · ${l}</button>`).join('');
    $$('#eTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; render(); });
  }
  const body = () => $('#eBody');
  const GEO_KEYS = ['crude', 'natgas', 'products'];   // EnergyGeo map keys
  const safe = (fn) => { try { const r = fn(); if (r && r.catch) r.catch(e => { body().insertAdjacentHTML('beforeend', `<div class="card"><p class="note">This panel failed to load (${String(e.message || e).slice(0, 120)}).</p></div>`); }); } catch (e) { body().insertAdjacentHTML('beforeend', `<div class="card"><p class="note">This panel failed to load (${String(e.message || e).slice(0, 120)}).</p></div>`); } };
  function primer() {
    const p = P[mk];
    $('#eBody').innerHTML = `<div class="grid g2">
      <div class="card"><h2>${p.name}: the contract</h2><div class="tbl"><table>${p.spec.map(r => `<tr><td>${r[0]}</td><td class="l">${r[1]}</td></tr>`).join('')}</table></div>
        <h3>Seasonality</h3><p>${p.season}</p>
        <h3>Links to the ag markets</h3><ul class="read">${p.links.map(x => `<li>${x}</li>`).join('')}</ul></div>
      <div class="card"><h2>What moves the price</h2><div class="tbl"><table><tr><th class="l">Driver</th><th class="l">Mechanism</th><th class="l">Watch</th></tr>
        ${p.sd.map(r => `<tr><td class="l"><b>${r[0]}</b></td><td class="l">${r[1]}</td><td class="l">${r[2]}</td></tr>`).join('')}</table></div></div></div>${Specs.slot('energy', [mk])}
      <div class="card" style="margin-top:12px"><h2>Key reports</h2><div class="tbl"><table><tr><th class="l">Report</th><th class="l">When</th><th class="l">What</th></tr>
        ${REPORTS.map(r => `<tr><td class="l">${r[0]}</td><td class="l">${r[1]}</td><td class="l">${r[2]}</td></tr>`).join('')}</table></div>
        <p class="note">Live numbers for each driver are in the other tabs of this desk. Learn more: <a href="https://www.cmegroup.com/education.html" target="_blank" rel="noopener">CME Group education (energy courses)</a> · <a href="https://www.eia.gov/energyexplained/" target="_blank" rel="noopener">EIA Energy Explained</a> · <a href="https://www.iea.org/topics" target="_blank" rel="noopener">IEA topics</a>.</p></div>`;
  }
  function flows() {
    body().innerHTML = `<div class="card"><h2>${DESKS[mk]}: price and technicals</h2><div id="eTech"></div></div>
      <div class="card" style="margin-top:12px"><h2>Positioning (CFTC)</h2><div id="eCot"></div></div>
      <div class="card" style="margin-top:12px"><h2>Options</h2><p>CME implied vols, smile, skew, open-interest walls and the Black-76 pricer for ${mk}: <a href="#options/${mk}" onclick="setTimeout(()=>document.querySelector('nav.comm button[data-c=options]').click(),0)">Options pricer ↗</a></p><div id="eOpt"></div></div>`;
    Tech.mount($('#eTech'), [mk]);
    CotDesk.mount($('#eCot'), [mk]);
    if (typeof EnergyOil !== 'undefined' && EnergyOil.options) safe(() => EnergyOil.options($('#eOpt'), mk));
  }
  let SD = null;
  async function sd() {
    if (!SD) SD = await getJSON('data/energy/sd.json').catch(() => null);
    if (!SD) { $('#eBody').innerHTML = '<p class="note">Supply & demand model not built yet.</p>'; return; }
    if (!SD.markets[mk]) { $('#eBody').innerHTML = '<p class="note">No supply &amp; demand model for this market yet.</p>'; return; }
    const M = SD.markets[mk], st = M.stocks, f = M.fair, b = M.balance;
    const n = (v, d = 1) => v == null ? '–' : (+v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
    const sg = (v, d = 1) => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${n(v, d)}</span>`;
    const pk = `<div class="mk-bar" style="margin:0 0 10px">${Object.keys(SD.markets).map(k => `<button data-m="${k}" class="${k === mk ? 'on' : ''}">${SD.markets[k].name}</button>`).join('')}</div>`;
    $('#eBody').innerHTML = `<div class="card"><h2>${M.name}: inventories, balance and fair value <span class="note">EIA data; built ${SD.generated}</span></h2><p>${M.read}</p>
      <div class="kpi-row" style="display:flex;flex-wrap:wrap;gap:18px;margin:8px 0">
        <div><div class="note">${st.name}</div><b>${n(st.value, mk === 'NG' ? 0 : 1)}</b> ${M.unit_stock}</div>
        <div><div class="note">vs 5-yr average</div><b>${sg(st.dev, mk === 'NG' ? 0 : 1)}</b> (${sg(st.dev_pct)}%)</div>
        <div><div class="note">week on week</div><b>${sg(st.wow, mk === 'NG' ? 0 : 1)}</b></div>
        ${st.days != null ? `<div><div class="note">days of supply</div><b>${n(st.days)}</b>${st.days_avg5 != null ? ` <span class="note">(5-yr ${n(st.days_avg5)})</span>` : ''}</div>` : ''}
        ${st.cushing != null ? `<div><div class="note">Cushing</div><b>${n(st.cushing)}</b> mb <span class="note">(5-yr ${n(st.cushing_avg5)})</span></div>` : ''}
        ${st.spr != null ? `<div><div class="note">SPR</div><b>${n(st.spr)}</b> mb</div>` : ''}
        ${M.price_now ? `<div><div class="note">futures (${M.price_now.date})</div><b>${M.price_now.value}</b></div>` : ''}</div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>${st.name} vs the last 5 years <span class="note">${M.unit_stock}, by week of year</span></h2><div class="chart"><canvas id="esdSea"></canvas></div>
          ${M.projection ? `<h3>Projection at the 5-year average pace</h3><div class="tbl"><table><tr><th class="l">Date</th><th>Projected (Bcf)</th><th>5-yr average</th></tr>${M.projection.filter(x => x.projected).map(x => `<tr><td class="l">${x.what}</td><td>${n(x.projected, 0)}</td><td>${n(x.avg5, 0)}</td></tr>`).join('')}</table></div>` : ''}
          ${M.storage_regions ? `<p class="note">By region (Bcf): ${Object.entries(M.storage_regions).map(([k, v]) => `${({ storEast: 'East', storMw: 'Midwest', storSc: 'South Central', storMtn: 'Mountain', storPac: 'Pacific' })[k]} ${n(v, 0)}`).join(' · ')}</p>` : ''}</div>
        <div class="card"><h2>Fair value from inventories <span class="note">${f ? f.label + ', ' + f.unit : ''}</span></h2>${f ? `<div class="chart"><canvas id="esdFv"></canvas></div>
          <div class="tbl"><table><tr><td class="l">Driver</td><td class="l">${f.driver}: now ${Object.values(f.x_now).map(v => n(v)).join(' / ')}</td></tr>
          <tr><td class="l">Fair value · actual · gap (z)</td><td class="l"><b>${n(f.fair, 2)}</b> · ${n(f.actual, 2)} · ${sg(f.gap, 2)} (${sg(f.gap_z)})</td></tr></table></div>
          ${M.fair_outright ? `<p class="note">US crude stocks alone do not explain the global crude price, so only the inventory-sensitive spread is shown.</p>` : ''}
          <h3>Price vs driver</h3><div class="chart short"><canvas id="esdSc"></canvas></div>` : '<p class="note">Not enough history yet.</p>'}</div></div>
      ${b ? `<div class="card" style="margin-top:12px"><h2>Supply &amp; demand balance <span class="note">${M.balance_unit}</span></h2><div class="tbl"><table><tr><th class="l">Line</th>${b.periods.map(p => `<th>${p.slice(0, mk === 'NG' ? 7 : 10)}</th>`).join('')}<th>${b.avg_label}</th><th>Year ago</th><th>y/y</th></tr>
        ${b.rows.map(r => `<tr><td class="l">${r.name}</td>${r.values.map(v => `<td>${n(v, mk === 'NG' ? 1 : 0)}</td>`).join('')}<td><b>${n(r.avg, mk === 'NG' ? 1 : 0)}</b></td><td>${n(r.avg_ya, mk === 'NG' ? 1 : 0)}</td><td>${r.chg_ya_pct == null ? '–' : sg(r.chg_ya_pct) + '%'}</td></tr>`).join('')}</table></div>
        <p class="note">${mk === 'CL' ? 'Production + imports − exports − refinery input should equal the stock change; the adjustment line is EIA\'s unaccounted-for crude.' : mk === 'NG' ? 'Monthly EIA Natural Gas Monthly data (two-month lag); daily pipeline data in the Energy terminal (Gas S&D) is more current.' : 'Product supplied is EIA\'s measure of demand (disappearance).'}</p></div>` : ''}`;
    const s = M.seasonal;
    chart('esdSea', { type: 'line', data: { labels: s.weeks, datasets: [
      { label: '5-yr max', data: s.max5, borderWidth: 0, pointRadius: 0, backgroundColor: 'rgba(196,138,28,.15)', fill: '+1' },
      { label: '5-yr min', data: s.min5, borderWidth: 0, pointRadius: 0, fill: false },
      { label: '5-yr avg', data: s.avg5, borderColor: '#999', borderDash: [4, 3], pointRadius: 0, borderWidth: 1.2 },
      { label: String(s.cy - 1), data: s.last, borderColor: '#2c6fbb', pointRadius: 0, borderWidth: 1.2 },
      { label: String(s.cy), data: s.this, borderColor: '#c0392b', pointRadius: 0, borderWidth: 2 }] },
      options: { plugins: { legend: { labels: { filter: i => !i.text.includes('min') } } }, scales: { x: { title: { display: true, text: 'week of year', font: { size: 10 } } } } } });
    if (f) {
      chart('esdFv', { type: 'line', data: { labels: f.series.map(x => x[0]), datasets: [
        { label: 'actual', data: f.series.map(x => x[1]), borderColor: '#24402a', pointRadius: 0, borderWidth: 1.6 },
        { label: 'inventory fair value', data: f.series.map(x => x[2]), borderColor: '#d68910', pointRadius: 0, borderWidth: 1.4, borderDash: [5, 3] }] } });
      chart('esdSc', { type: 'scatter', data: { datasets: [{ label: 'weekly (5 years)', data: f.scatter.map(p => ({ x: p[0], y: p[1] })), pointRadius: 2, backgroundColor: 'rgba(44,111,187,.45)' },
        { label: 'now', data: [{ x: Object.values(f.x_now)[0], y: f.actual }], pointRadius: 6, backgroundColor: '#c0392b' }] },
        options: { interaction: { mode: 'nearest' }, scales: { x: { title: { display: true, text: f.driver, font: { size: 10 } } }, y: { title: { display: true, text: f.unit, font: { size: 10 } } } } } });
    }
  }
  function news() {
    body().innerHTML = `<div class="grid g2"><div class="card"><h2>${DESKS[mk]}: calendar <span class="note">next 30 days, US Central time</span></h2><div id="eCal"></div></div>
      <div class="card"><h2>News</h2><div id="eNews"></div></div></div><div id="eFresh" style="margin-top:12px"></div>`;
    Intel.calendar($('#eCal'), { markets: [mk], days: 30, minImp: 1 });
    Intel.news($('#eNews'), { tags: mk === 'NG' ? ['natgas'] : mk === 'CL' ? ['crude'] : ['products', 'crude'], n: 30, chips: true });
    if (typeof EnergyOil !== 'undefined' && EnergyOil.freshness) safe(() => EnergyOil.freshness($('#eFresh')));
  }
  const missing = (n) => body().innerHTML = `<div class="card"><p class="note">${n} is being built.</p></div>`;
  const NGm = () => (typeof EnergyNG !== 'undefined' ? EnergyNG : null), OILm = () => (typeof EnergyOil !== 'undefined' ? EnergyOil : null);
  function render() {
    tabsNav();
    history.replaceState(null, '', '#energy/' + mk.toLowerCase() + '/' + tab);
    body().innerHTML = '';
    const R = {
      primer, sd: () => { sd(); if (mk === 'NG' && NGm()) setTimeout(() => safe(() => NGm().sdMonthly(body())), 0); },
      storage: () => NGm() ? safe(() => NGm().storage(body())) : missing('Storage'),
      weather: () => NGm() ? safe(() => NGm().weather(body(), mk)) : missing('Weather'),
      model: () => NGm() ? safe(() => NGm().model(body())) : missing('Storage model'),
      stocks: () => OILm() ? safe(() => OILm().stocks(body(), mk)) : missing('Inventories'),
      refining: () => OILm() ? safe(() => OILm().refining(body(), mk)) : missing('Refining'),
      geo: () => EnergyGeo.mount(body(), { NG: GEO_KEYS[1], CL: GEO_KEYS[0], HO: GEO_KEYS[2], RB: GEO_KEYS[2] }[mk]),
      flows,
      rv: () => { body().innerHTML = '<div id="eCurve"></div><div id="eRv" style="margin-top:12px"></div>';
        if (OILm() && OILm().curve) safe(() => OILm().curve($('#eCurve'), mk));
        Promise.resolve(RVView.mount($('#eRv'), mk)).then(() => $$('#eRv .card').forEach(c => { if (/Report-day playbook/.test(c.querySelector('h2')?.textContent || '')) c.remove(); })); },
      seas: () => MktStudy.mount(body(), [mk]),
      outlook, news };
    (R[tab] || primer)();
  }
  async function outlook() {
    const [S, SDx, W] = await Promise.all([getJSON('data/energy/summary.json').catch(() => null), SD ? Promise.resolve(SD) : getJSON('data/energy/sd.json').catch(() => null),
      mk === 'NG' ? getJSON('data/energy/wx/signal.json').catch(() => null) : null]);
    SD = SDx; const M = SD?.markets?.[mk], P2 = S?.prices?.[mk], V = S?.vol?.[mk];
    const pct = (v) => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${(+v).toFixed(1)}%</span>`;
    body().innerHTML = `<div class="card"><h2>${DESKS[mk]}: outlook <span class="note">${S ? 'built ' + S.generated : ''}</span></h2>
      ${P2 ? `<div class="kpi-row" style="display:flex;flex-wrap:wrap;gap:18px;margin:6px 0 10px"><div><div class="note">front month (${P2.date})</div><b>${P2.last}</b></div><div><div class="note">day</div><b>${pct(P2.d1)}</b></div><div><div class="note">week</div><b>${pct(P2.w1)}</b></div><div><div class="note">month</div><b>${pct(P2.m1)}</b></div>${V?.atm ? `<div><div class="note">ATM vol (${V.label})</div><b>${V.atm.toFixed(0)}%</b> <span class="note">RV20 ${V.rv20?.toFixed(0) ?? '–'}%, 25d RR ${V.rr25 ?? '–'}</span></div>` : ''}</div>` : ''}
      ${W ? `<h3>Weather and positioning</h3><p><b>Squeeze risk ${W.regime}.</b> ${W.action}</p><ul class="read">${W.cold_checks.filter(c => c.on).map(c => `<li>${c.text}</li>`).join('') || '<li>No cold-risk checks on.</li>'}</ul>` : ''}
      ${M ? `<h3>Inventories and fair value</h3><p>${M.read}</p>` : ''}
      <h3>Technicals and positioning</h3><div id="eOutTech"></div></div>`;
    Tech.mount($('#eOutTech'), [mk]);
  }
  function show() {
    if (!built) { shell(); built = true; }
    const h = location.hash.slice(1), m = h.match(/^energy\/(ng|cl|ho|rb)(?:\/(\w+))?/i);
    if (m) { mk = m[1].toUpperCase(); tab = TABS[mk].some(x => x[0] === m[2]) ? m[2] : 'primer'; }
    else { const lg = h.match(/^energy\/(\w+)/) || h.match(/^(e-\w+)/); if (lg && LEGACY[lg[1]]) [mk, tab] = LEGACY[lg[1]]; }
    render(); window.scrollTo(0, 0);
  }
  return { show };
})();
