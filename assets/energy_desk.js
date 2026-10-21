// Energy section: sub-tabs around the energy terminal (energy.html, in a frame): primers, production / trade / LNG
// maps, price charts and technicals, COT, news and calendar. Deep links: #energy (terminal), #e-primer, #e-geo,
// #e-charts, #e-news, #energy/<terminal tab>.
const Energy = (() => {
  let built = false, tab = 'e-term', mk = 'NG';
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
  function shell() {
    const el = document.getElementById('energy');
    el.innerHTML = `<nav class="tabs" id="eTabs"><button data-t="e-term" class="on">Energy terminal</button><button data-t="e-primer">Primer</button>
      <button data-t="e-geo">Production, trade &amp; LNG</button><button data-t="e-charts">Price charts, technicals &amp; COT</button><button data-t="e-news">News &amp; calendar</button></nav>
      <div id="eTerm"><iframe id="energy-frame" title="Energy terminal" style="display:block;width:100%;height:calc(100vh - 130px);min-height:640px;border:0;background:#0b111b"></iframe></div>
      <main id="eMain" style="display:none"><div id="eBody"></div></main>`;
    $$('#eTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; render(); });
  }
  function picker(cb) {
    return `<div class="mk-bar" style="margin:0 0 10px">${Object.keys(P).map(k => `<button data-m="${k}" class="${k === mk ? 'on' : ''}">${P[k].name}</button>`).join('')}</div>`;
  }
  function wirePicker(fn) { $$('#eBody [data-m]').forEach(b => b.onclick = () => { mk = b.dataset.m; fn(); }); }
  function primer() {
    const p = P[mk];
    $('#eBody').innerHTML = picker() + `<div class="grid g2">
      <div class="card"><h2>${p.name}: the contract</h2><div class="tbl"><table>${p.spec.map(r => `<tr><td>${r[0]}</td><td class="l">${r[1]}</td></tr>`).join('')}</table></div>
        <h3>Seasonality</h3><p>${p.season}</p>
        <h3>Links to the ag markets</h3><ul class="read">${p.links.map(x => `<li>${x}</li>`).join('')}</ul></div>
      <div class="card"><h2>What moves the price</h2><div class="tbl"><table><tr><th class="l">Driver</th><th class="l">Mechanism</th><th class="l">Watch</th></tr>
        ${p.sd.map(r => `<tr><td class="l"><b>${r[0]}</b></td><td class="l">${r[1]}</td><td class="l">${r[2]}</td></tr>`).join('')}</table></div></div></div>
      <div class="card" style="margin-top:12px"><h2>Key reports</h2><div class="tbl"><table><tr><th class="l">Report</th><th class="l">When</th><th class="l">What</th></tr>
        ${REPORTS.map(r => `<tr><td class="l">${r[0]}</td><td class="l">${r[1]}</td><td class="l">${r[2]}</td></tr>`).join('')}</table></div>
        <p class="note">Live numbers for each driver are in the Energy terminal tabs (Gas storage, Gas S&amp;D, Weather, Oil stocks, Refining &amp; cracks) and in Production, trade &amp; LNG. Learn more: <a href="https://www.cmegroup.com/education.html" target="_blank" rel="noopener">CME Group education (energy courses)</a> · <a href="https://www.eia.gov/energyexplained/" target="_blank" rel="noopener">EIA Energy Explained</a> · <a href="https://www.iea.org/topics" target="_blank" rel="noopener">IEA topics</a>.</p></div>`;
    wirePicker(primer);
  }
  function charts() {
    $('#eBody').innerHTML = `<div class="card"><h2>Price charts and technicals</h2><div id="eTech"></div></div><div class="card" style="margin-top:12px"><h2>COT positioning</h2><div id="eCot"></div></div>`;
    Tech.mount($('#eTech'), ['NG', 'CL', 'HO', 'RB']);
    CotDesk.mount($('#eCot'), ['NG', 'CL', 'HO', 'RB']);
  }
  function news() {
    $('#eBody').innerHTML = `<div class="grid g2"><div class="card"><h2>Energy calendar <span class="note">next 30 days, US Central time</span></h2><div id="eCal"></div></div>
      <div class="card"><h2>Energy news</h2><div id="eNews"></div></div></div>`;
    Intel.calendar($('#eCal'), { markets: ['NG', 'CL', 'HO', 'RB'], days: 30, minImp: 1 });
    Intel.news($('#eNews'), { tags: ['natgas', 'crude', 'products'], n: 30, chips: true });
  }
  function render() {
    $$('#eTabs button').forEach(x => x.classList.toggle('on', x.dataset.t === tab));
    const term = tab === 'e-term';
    $('#eTerm').style.display = term ? '' : 'none'; $('#eMain').style.display = term ? 'none' : '';
    if (term) {
      const f = $('#energy-frame'), t = (location.hash.match(/^#energy\/(\w+)/) || [])[1];
      if (!f.src) f.src = 'energy.html' + (t ? '#' + t : '');
      if (!location.hash.startsWith('#energy')) history.replaceState(null, '', '#energy');
      return;
    }
    history.replaceState(null, '', '#' + tab);
    ({ 'e-primer': primer, 'e-geo': () => EnergyGeo.mount($('#eBody')), 'e-charts': charts, 'e-news': news })[tab]();
  }
  function show() {
    if (!built) { shell(); built = true; }
    const h = location.hash.slice(1);
    if (/^e-(primer|geo|charts|news)$/.test(h)) tab = h; else if (h.startsWith('energy')) tab = 'e-term';
    render(); window.scrollTo(0, 0);
  }
  return { show };
})();
