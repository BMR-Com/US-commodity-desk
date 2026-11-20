// Metals section: one menu with six sub-desks (gold, silver, copper, aluminum, platinum, palladium), numbered sub-tabs like Energy and Cotton.
// Data: data/metals/metals.json (models/metals.py), data/metals/status.json + release_calendar.json (pipelines/metals_status.py),
// and the shared desk files (technicals, COT desk, seasonality, spreads, specs, news, calendar). Built by its own workflow
// (metals.yml), so a failure there cannot affect the rest of the desk. Deep links: #metals/<gc|si|hg|ali|pl|pa>/<tab>.
const Metals = (() => {
  let built = false, mk = 'GC', tab = 'outlook', D = null, ST = null, CAL = null;
  const KEY = { GC: 'gold', SI: 'silver', HG: 'copper', ALI: 'aluminum', PL: 'platinum', PA: 'palladium' };
  const DESKS = { GC: 'Gold', SI: 'Silver', HG: 'Copper', ALI: 'Aluminum', PL: 'Platinum', PA: 'Palladium' };
  const COT = { GC: 'GC', SI: 'SI', HG: 'HG', ALI: 'AUP', PL: 'PL', PA: 'PA' };
  const PREC = k => ['GC', 'SI', 'PL', 'PA'].includes(k);   // precious metals: curve carry vs T-bills gives an implied lease rate
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
    PL: { spec: [['Contract', 'NYMEX Platinum (PL)'], ['Size / tick', '50 troy oz; $0.10/oz = $5 per lot'], ['Active months', 'Jan, Apr, Jul, Oct (the next three calendar months also list)'],
        ['First notice / last trade', 'As COMEX gold: first notice on the last business day of the month before delivery (longs out before first position day); last trade third-last business day of the delivery month'],
        ['Delivery', 'A 50-oz plate or ingot, at least 99.95% pure, made by an exchange-approved refiner, on warrant in a NYMEX-approved vault. Longs receive a warrant, not metal in hand'],
        ['Options', 'Monthly options on the futures (thin next to gold)'],
        ['Other markets', 'London/Zurich OTC market (LPPM; LBMA Platinum Price set twice a day; spot and forwards for loco London/Zurich metal), Japan (Osaka Exchange platinum futures in yen per gram; Japanese investors buy bars on dips), China (Shanghai Gold Exchange spot; Guangzhou Futures Exchange platinum futures since late 2024). Price gaps between New York, London and Shanghai show where metal is being pulled']],
      drivers: [['Mine supply concentration', 'South Africa (Bushveld) mines about 70% of the world\'s platinum, Zimbabwe about 9%, Russia about 12% and North America the rest. Output has gone sideways for a decade: power cuts, deep and ageing shafts, processing outages and shaft closures when the PGM basket price is low. Supply responds to price only over years.', 'WPIC/JM supply, South African mining output (Stats SA), producer results'],
        ['Autocatalyst demand and the EV mix', 'About a third of demand is catalytic converters, above all diesel cars and heavy trucks. Hybrids carry more PGM per vehicle than plain combustion cars; battery-electric cars carry none. A slower EV roll-out and more hybrids support demand; tighter emissions rules (Euro 7, China 6b, US 2027 truck rules) raise loadings.', 'Light-vehicle production, EV/hybrid share, WPIC automotive demand'],
        ['Platinum-for-palladium substitution', 'Gasoline catalysts can swap palladium for platinum. Automakers did this heavily when palladium traded far above platinum (2019-2022); the switch is slow (re-certification) and reverses only if platinum becomes the dearer metal.', 'Platinum/palladium ratio, WPIC substitution estimates'],
        ['Jewellery and China', 'Jewellery is about a quarter of demand, led by China (falling), India and Japan; it is price-sensitive. China also drives industrial use (glass, chemicals) and investment bars. China imports, the Shanghai premium over London and Guangzhou futures show the pull.', 'WPIC jewellery, China imports, Shanghai premium'],
        ['Industrial and hydrogen', 'Chemical catalysts (paraxylene, silicones), glass fibre and LCD glass, petroleum refining, medical, and hydrogen (PEM electrolysers and fuel cells). Lumpy: capacity build-outs in China swing it.', 'WPIC industrial demand'],
        ['Investment, ETFs and above-ground stocks', 'Bar and coin buying (Japan, China, US), ETF flows and exchange stocks swing the balance. WPIC expresses above-ground stocks as months of demand cover; a falling cover after years of deficits means less free metal to absorb shocks.', 'PPLT and other ETF holdings, NYMEX stocks, WPIC above-ground stocks'],
        ['Lease rates and the forward curve', 'Precious metals normally trade in carry (forward above spot by about the interest rate). When free metal is scarce, lenders demand a lease rate, the forward discount narrows or flips to backwardation, and New York trades a premium to London. In 2025 US tariff risk pulled metal into NYMEX vaults and lease rates spiked.', 'Implied lease rate from the curve, NYMEX stocks, EFP (New York vs London)']],
      cot: 'Managed money drives short-term moves and swings from net short to large net long within months; platinum\'s open interest is small, so fund flows move price hard. Producers/merchants include refiners, fabricators and miners hedging; swap dealers carry the banks\' OTC and ETF-related books. Read managed money against its own 3-year range.',
      season: 'Weak seasonal pattern. Chinese buying ahead of Lunar New Year and Japanese bar buying on dips have given some support in Dec-Feb; South African mining outages (power, safety stoppages) are not seasonal. Seasonals matter far less than supply news and fund flows.',
      links: ['Palladium: the two share mines (one ore body), autocatalysts and substitution, so read them together through the platinum/palladium ratio.', 'Gold: platinum trades as a precious metal on dollar and real-rate moves; the platinum/gold ratio is on the Prices & curve tab.', 'Diesel and heavy-truck markets (see Energy) link to platinum autocatalyst demand.', 'South African rand: a weaker rand lifts producers\' local-currency margins and slows closures.'] },
    PA: { spec: [['Contract', 'NYMEX Palladium (PA)'], ['Size / tick', '100 troy oz; $0.50/oz = $50 per lot'], ['Active months', 'Mar, Jun, Sep, Dec (the next three calendar months also list)'],
        ['First notice / last trade', 'As platinum and gold: first notice on the last business day of the month before delivery; last trade third-last business day of the delivery month'],
        ['Delivery', 'A 100-oz plate or ingot, at least 99.95% pure, from an exchange-approved refiner, on warrant in a NYMEX-approved vault'], ['Options', 'Monthly options on the futures (very thin)'],
        ['Other markets', 'London/Zurich OTC (LPPM; LBMA Palladium Price twice a day). Russian refiners lost London good-delivery status in 2022, so Russian metal moves mostly to China and other Asian buyers. Guangzhou Futures Exchange lists palladium futures (since late 2024); Osaka lists palladium too']],
      drivers: [['Russia and South Africa', 'Russia (Nornickel) mines about 45% of the world\'s palladium and South Africa about 35%, with North America (Stillwater, cut back in 2024) and Zimbabwe the rest. Sanctions, trade cases and tariff risk on Russian metal (a US anti-dumping case on Russian palladium was opened in 2025) can split the market by origin.', 'JM supply by region, Nornickel guidance, trade-case rulings'],
        ['Autocatalyst demand (about 80% of use)', 'Palladium is the main metal in gasoline-car and hybrid catalysts. Battery-electric cars use none, so EV share (above all in China) erodes demand year after year; hybrids and stricter emission rules slow the decline.', 'Light-vehicle production, EV/hybrid share, JM autocatalyst demand'],
        ['Substitution and thrifting', 'Expensive palladium pushed automakers to swap in platinum and use less metal per catalyst; that demand does not come back quickly even when palladium cheapens.', 'Platinum/palladium ratio'],
        ['Recycling', 'Recovery from scrapped catalysts is about a third of supply and rising as older gasoline cars are scrapped; collection slows when prices are low or scrap-car supply dips.', 'JM secondary supply'],
        ['Industrial and investment', 'Electronics, dental, chemical catalysts. Investment is small; ETF holdings (PALL) are modest, so flows matter less than in platinum.', 'PALL holdings, JM investment demand'],
        ['Lease rates and the curve', 'In 2019-2021 palladium ran a deep deficit with backwardation and very high lease rates; a market moving into surplus usually returns to carry. The curve and NYMEX stocks show how tight free metal is.', 'Implied lease rate from the curve, NYMEX stocks']],
      cot: 'Palladium open interest is small and managed money has been net short for long stretches since 2022, so short-covering rallies can be violent. Producers/merchants (refiners, fabricators) hedge; swap dealers carry OTC books. Read managed money against its own range rather than the absolute level.',
      season: 'No reliable seasonal: price follows auto production, Russian supply news and substitution. Chinese restocking before Lunar New Year has occasionally given a Dec-Jan lift.',
      links: ['Platinum: shared mines and the substitution trade (platinum/palladium ratio).', 'Car production and the EV share link palladium to industrial and energy-transition markets.', 'Russia sanctions and trade policy (see News).'] },
  };
  const REPORTS = [['CFTC Commitments of Traders', 'Fri 3:30 pm ET', 'Positions as of Tuesday (gold, silver, copper, aluminum Midwest premium, platinum, palladium)'],
    ['COMEX / NYMEX warehouse stocks', 'Daily, evening', 'Registered (deliverable) and eligible metal in exchange warehouses and vaults'],
    ['LME official prices and stocks', 'Daily, London', 'Cash, 3-month, warehouse stocks, cancelled warrants'],
    ['ETF holdings (GLD, IAU, SLV)', 'Daily', 'Metal held by the large US ETFs'],
    ['World Gold Council Gold Demand Trends', 'Quarterly (~5 weeks after quarter end)', 'Jewellery, technology, bar/coin, ETFs, central banks, supply'],
    ['ICSG monthly press release', 'Monthly (3rd–4th week)', 'World copper mine/refined production, usage, balance'],
    ['IAI primary aluminium production', 'Monthly (~20th)', 'Output by region incl. China'],
    ['Silver Institute World Silver Survey', 'Annual (April), interim (November)', 'Silver supply, demand, deficit'],
    ['WPIC Platinum Quarterly', 'Quarterly (early Mar, mid-May, early Sep, mid-Nov)', 'Platinum balance by year and quarter (research by Metals Focus), above-ground stocks'],
    ['Johnson Matthey PGM market report', 'Annual (mid-May)', 'Platinum and palladium supply, recycling, demand, balance'],
    ['PPLT / PALL quarterly filings', 'About 5-6 weeks after quarter end', 'Ounces held by the abrdn platinum and palladium ETFs'],
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
    const extra = { GC: goldDrivers, SI: silverRatio, HG: copperArb, ALI: aluminumPrem, PL: pgmRatios, PA: pgmRatios }[mk];
    body().innerHTML = `<div class="grid g4">
        ${kpi(`${DESKS[mk]} · ${esc(p.contract)}`, `${fmt(p.last, dp)}`, `${p.unit} · ${p.date} · ${sgn(p.chg_1w, 1, '%')} wk · ${sgn(p.chg_1m, 1, '%')} mo`)}
        ${kpi('Year to date', sgn(p.chg_ytd, 1, '%'), `52-wk range ${fmt(p.lo52, dp)}–${fmt(p.hi52, dp)}`)}
        ${sp[0] ? kpi('Front spread', `${sgn(sp[0].spread, dp)}`, `${esc(sp[0].pair)} · ${fmt(sp[0].ann_pct, 2)}% a year carry`) : ''}
        ${sp[0] && sp[0].lease_pct != null && PREC(mk) ? kpi('Implied lease rate', `${fmt(sp[0].lease_pct, 2)}%`, `T-bill ${fmt(D.rate, 2)}% minus the carry the spread pays`) : ''}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Forward curve <span class="note">${p.unit}, last close of each listed contract</span></h2><div class="chart short"><canvas id="mtCurve"></canvas></div>
          <div class="tbl"><table><tr><th class="l">Spread</th><th>Later − earlier</th><th>Carry, % a year</th>${PREC(mk) ? '<th>Implied lease rate</th>' : ''}</tr>
          ${sp.map(s => `<tr><td class="l">${esc(s.pair)}</td><td>${sgn(s.spread, dp)}</td><td>${fmt(s.ann_pct, 2)}%</td>${PREC(mk) ? `<td>${fmt(s.lease_pct, 2)}%</td>` : ''}</tr>`).join('')}</table></div>
          <p class="note">${PREC(mk) ? 'Precious metals normally sit in full carry (later months higher by about the interest rate). Carry below the T-bill rate means an implied lease rate above zero: metal is tight to borrow. Backwardation is rare and a strong squeeze signal.' : 'Base metals swing between contango (ample stocks) and backwardation (nearby metal tight). Compare with the LME cash–3-month spread on the Supply & demand tab.'}</p></div>
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

  function pgmRatios(m) {
    const r = m.ratio_pd, g = m.ratio_gold, gl = mk === 'PL' ? 'Platinum/gold' : 'Palladium/gold';
    $('#mtExtra').innerHTML = `<div class="grid g2" style="margin-top:12px">
      <div class="card"><h2>Platinum/palladium ratio <span class="note">platinum price ÷ palladium price, weekly, 10 years</span></h2>${r ? `<div class="chart"><canvas id="mtPtPd"></canvas></div>
        <p class="note">${fmt(r.last, 2)} on ${r.asof} (${r.pct10 == null ? '–' : r.pct10 + 'th'} percentile of 10 years; median ${fmt(r.med10, 2)}; ${sgn(r.chg_1m, 2)} in a month, ${sgn(r.chg_1y, 2)} in a year). Below 1 palladium is the dearer metal, which pushes automakers to substitute platinum into gasoline catalysts; well above 1 the incentive fades. NYMEX front months.</p>` : '<p class="note">Needs platinum and palladium prices.</p>'}</div>
      <div class="card"><h2>${gl} ratio <span class="note">weekly, 10 years</span></h2>${g ? `<div class="chart"><canvas id="mtPgmAu"></canvas></div>
        <p class="note">${fmt(g.last, 3)} on ${g.asof} (${g.pct10 == null ? '–' : g.pct10 + 'th'} percentile of 10 years; median ${fmt(g.med10, 3)}; ${sgn(g.chg_1y, 3)} in a year). NYMEX ${DESKS[mk].toLowerCase()} and COMEX gold front months.</p>` : '<p class="note">Needs gold prices.</p>'}</div></div>`;
    if (r) chart('mtPtPd', { type: 'line', data: { labels: r.weekly.date, datasets: [ln(r.weekly.v, 'Pt/Pd', PAL[4]), ln(r.weekly.v.map(() => 1), 'Parity', '#999', { borderDash: [4, 3] })] } });
    if (g) chart('mtPgmAu', { type: 'line', data: { labels: g.weekly.date, datasets: [ln(g.weekly.v, gl, PAL[3]), ln(g.weekly.v.map(() => g.med10), '10-yr median', '#999', { borderDash: [4, 3] })] } });
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
    ({ GC: sdGold, SI: sdSilver, HG: sdCopper, ALI: sdAluminum, PL: sdPgm, PA: sdPgm }[mk])(m);
  }
  function sdGold(m) {
    const w = m.wgc, e = m.etf;
    body().innerHTML = `${w ? `<div class="card"><h2>Gold demand, ${esc(w.quarter)} <span class="note">tonnes; ${esc(w.source)}, published ${esc(w.published)}</span></h2>
        <div class="tbl"><table><tr><th class="l">Line</th><th>${esc(w.quarter)}</th><th>y/y (WGC)</th>${w.quarters.slice(0, -1).slice(-4).map(q => `<th>${esc(q)}</th>`).join('')}</tr>
        ${w.table.map(r => `<tr><td class="l">${r.line}</td><td><b>${fmt(r.now, 0)}</b></td><td>${sgn(r.yoy_pct, 0, '%')}</td>${r.hist.slice(0, -1).slice(-4).map(v => `<td>${fmt(v, 0)}</td>`).join('')}</tr>`).join('')}</table></div>
        ${w.quarters.length > 1 ? '<div class="chart short"><canvas id="mtWgc"></canvas></div>' : ''}
        <p class="note">${esc(w.summary)} <a href="${w.url}" target="_blank" rel="noopener">Report</a>. The desk reads the public summary of each quarterly report (the full Goldhub tables need a login and its data service is closed to automated access), so earlier quarters keep the figures first published; WGC's later revisions are not captured.</p></div>` : none('World Gold Council data')}
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Gold ETF holdings: SPDR GLD <span class="note">tonnes, weekly</span></h2>${e ? `<div class="chart short"><canvas id="mtEtf"></canvas></div>
          <p class="note">GLD ${fmt(e.gld.tonnes, 1)} t on ${e.gld.asof}: ${sgn(e.gld.chg_1w, 1)} t in a week, ${sgn(e.gld.chg_1m, 1)} t in a month, ${sgn(e.gld.chg_ytd, 0)} t this year (${e.gld.pct5y == null ? '–' : e.gld.pct5y + 'th'} percentile of 5 years).
          ${e.iau ? ` iShares IAU ${fmt(e.iau.tonnes, 1)} t on ${e.iau.asof} (${sgn(e.iau.chg_1m, 1)} t in a month; iShares shows only the current figure, so history builds from when the desk started).` : ''} Sources: SPDR Gold Shares archive; iShares product page.</p>` : '<p class="note">ETF data not built yet.</p>'}</div>
        <div class="card"><h2>Central banks</h2>${w ? (() => { const cb = w.table.find(r => r.key === 'central_banks'); return cb ? `<p>Central banks bought <b>${fmt(cb.now, 0)} t</b> in ${esc(w.quarter)} (${sgn(cb.yoy_pct, 0, '%')} vs a year ago, World Gold Council).</p><p class="note">Since 2022 central banks have bought around 1,000 t a year, about a fifth of demand; WGC's estimate includes unreported buying, so it runs above IMF-reported reserve changes.</p>` : '<p class="note">Not in the latest summary.</p>'; })() : '<p class="note">No WGC data yet.</p>'}</div></div>
      ${usgsCard(m.usgs)}`;
    if (w && w.quarters.length > 1) {
      const sel = w.table.filter(r => ['jewellery', 'technology', 'bar_coin', 'etfs', 'central_banks'].includes(r.key));
      chart('mtWgc', { type: 'bar', data: { labels: w.quarters, datasets: sel.map((r, i) => ({ label: r.line, data: r.hist, backgroundColor: PAL[i] })) } });
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

  function revTable(rv, unit) {
    return `<div class="tbl"><table><tr><th class="l">Line</th><th class="l">Year</th><th>Now</th><th>Before</th><th>Revision</th></tr>
      ${rv.map(r => `<tr><td class="l">${esc(r.line)}</td><td class="l">${esc(String(r.period).replace(/f$/, ' (forecast)'))}</td><td>${fmt(r.now, 0)}</td><td>${fmt(r.before, 0)}</td><td><b>${sgn(r.chg, 0)}</b></td></tr>`).join('')}</table></div><p class="note">${unit}</p>`;
  }
  function sdPgm(m) {
    const W = m.wpic, J = m.jm, E = m.etf, metal = DESKS[mk].toLowerCase();
    const bal = W && W.rows.find(r => r.line === 'Balance'), ags = W && W.rows.find(r => r.line === 'Above Ground Stocks');
    const wcols = W ? W.columns : [], lab = c => String(c).replace(/f$/, 'f');
    body().innerHTML = `${W ? `<div class="grid g4">${wcols.slice(-3).map(c => kpi(`WPIC balance ${lab(c)}`, `${sgn(bal && bal[c], 0)} koz`, (bal && bal[c] < 0 ? 'deficit' : 'surplus') + (ags && ags[c] != null ? ` · above-ground stocks ${fmt(ags[c], 0)} koz` : ''))).join('')}
        ${kpi('Latest Platinum Quarterly', esc(W.release), W.next_release ? `next release ${esc(W.next_release)}` : esc(W.fetched || ''))}</div>
      <div class="card" style="margin-top:12px"><h2>World platinum balance (WPIC) <span class="note">thousand oz; ${esc(W.release)}; f = forecast</span></h2>
        <div class="tbl"><table><tr><th class="l">Line</th>${wcols.map(c => `<th>${esc(lab(c))}</th>`).join('')}${W.quarters.map(q => `<th>${esc(q)}</th>`).join('')}</tr>
        ${W.rows.map(r => `<tr><td class="l">${/: /.test(r.line) ? '&nbsp;&nbsp;' + esc(r.line.split(': ')[1]) : `<b>${esc(r.line)}</b>`}</td>${wcols.concat(W.quarters).map(c => `<td>${r[c] == null ? '' : /Balance|Investment|Change/.test(r.line) ? sgn(r[c], 0) : fmt(r[c], 0)}</td>`).join('')}</tr>`).join('')}</table></div>
        <h3>Revisions vs the previous release${W.prev_release ? ` (${esc(W.prev_release)})` : ''}</h3>
        ${W.revisions && W.revisions.length ? revTable(W.revisions, 'Thousand oz. A deficit revised deeper, or demand revised up, is the change that matters more than the level: agencies differ widely on levels.') : `<p class="note">${W.prev_release ? 'No line changed by more than 0.5 koz.' : 'The desk stores every release from the first one it read; revisions to the same years show from the next release.'}</p>`}
        <h3>What WPIC says</h3><ul class="read">${(W.points || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <p class="note">Positive balance = surplus. ${esc(W.source)}. <a href="${W.report}" target="_blank" rel="noopener">Report</a> · <a href="${W.url}" target="_blank" rel="noopener">Tables</a>.</p></div>` : mk === 'PL' ? none('WPIC data') : ''}
      ${J ? `<div class="card" style="margin-top:12px"><h2>${DESKS[mk]} supply and demand (Johnson Matthey) <span class="note">thousand oz; ${esc(J.edition)} edition; latest year is JM's forecast</span></h2>
        <div class="tbl"><table><tr><th class="l">Line</th>${J.years.map(y => `<th>${y}</th>`).join('')}</tr>
        ${J.rows.map(r => `<tr><td class="l">${/^Total|Movements/.test(r.line) ? `<b>${esc(r.line === 'Movements in stocks' ? 'Balance (movements in stocks)' : r.line)}</b>` : esc(r.line)}</td>${J.years.map(y => `<td>${r[y] == null ? '' : /Movements|Investment/.test(r.line) ? sgn(r[y], 0) : fmt(r[y], 0)}</td>`).join('')}</tr>`).join('')}</table></div>
        <h3>Revisions vs the ${esc(J.prev_edition || 'previous')} edition</h3>
        ${J.revisions && J.revisions.length ? revTable(J.revisions, 'Thousand oz; same years in both editions.') : '<p class="note">Revisions show once two editions are stored.</p>'}
        <p class="note">Balance = supply minus demand (negative = deficit). ${esc(J.source)}. ${J.report ? `<a href="${J.report}" target="_blank" rel="noopener">Report</a> · ` : ''}<a href="${J.url}" target="_blank" rel="noopener">Data</a>. Annual (May).${mk === 'PA' ? ' WPIC covers platinum only, so Johnson Matthey is the free public palladium balance.' : ''}</p></div>` : none('Johnson Matthey data')}
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>${E ? esc(E.fund) : (mk === 'PL' ? 'PPLT' : 'PALL')} ounces held <span class="note">thousand oz, quarter ends</span></h2>${E ? `<div class="chart short"><canvas id="mtPgmEtf"></canvas></div>
          <p class="note">${fmt(E.koz, 0)} koz on ${E.asof} (${sgn(E.chg_q_pct, 1, '%')} on the quarter${E.chg_y_pct != null ? `, ${sgn(E.chg_y_pct, 1, '%')} on the year` : ''}; filed ${esc(E.filed)}). ${esc(E.source)}. The fund's own page shows a daily figure only in the browser, so the desk uses the quarterly filings.</p>` : '<p class="note">Not built yet.</p>'}</div>
        ${comexCard(m.comex_stocks, metal).replace('COMEX ' + metal, 'NYMEX ' + metal)}</div>
      <div class="card" style="margin-top:12px"><h2>Not on this desk (no free automated source)</h2><p class="note">London lease rates and LBMA ${metal} prices (licensed data; the desk shows the lease rate implied by the NYMEX curve instead), Swiss and UK customs flows, Chinese import premiums, Osaka and Guangzhou futures, ${mk === 'PA' ? 'Nornickel production guidance (company reports), ' : 'South African mining output by company (quarterly results), '}and WPIC's ${mk === 'PA' ? 'platinum-only coverage (no palladium quarterly).' : 'full report text (PDF): the desk reads the tables and the public key points.'}</p></div>
      ${usgsCard(m.usgs)}`;
    if (E) chart('mtPgmEtf', { type: 'bar', data: { labels: E.series.date, datasets: [{ label: E.fund + ' (koz)', data: E.series.v, backgroundColor: PAL[mk === 'PL' ? 2 : 5] }] }, options: { plugins: { legend: { display: false } } } });
    if (m.comex_stocks) chart('mtCx', { type: 'line', data: { labels: m.comex_stocks.series.date, datasets: [ln(m.comex_stocks.series.v, 'NYMEX stocks', PAL[1])] }, options: { plugins: { legend: { display: false } } } });
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
        <li><b>COMEX and NYMEX warehouse stocks</b> (incl. platinum and palladium): cmegroup.com blocks GitHub's servers; the desk's Mac collector downloads the daily reports.</li>
        <li><b>Daily PPLT/PALL holdings</b>: the fund pages render their figures only in a browser; the desk reads the ounces from the trusts' quarterly SEC filings.</li>
        <li><b>London platinum/palladium lease rates and LBMA prices</b>: licensed data; the desk shows the lease rate implied by the NYMEX curve.</li>
        <li><b>LME positions (COTR), SHFE stocks, Chinese premiums, treatment charges, Platts/Fastmarkets premiums</b>: no free automated source (paid, or blocked).</li>
        <li><b>World Gold Council full data tables and revisions</b>: the tables need a Goldhub login and its data service disallows automated access, so the desk parses the public summary of each quarterly report.</li>
        <li><b>Silver Institute survey tables</b> are a PDF: the desk stores the key numbers from the public page.</li>
        <li><b>Free implied volatility for COMEX options</b>: not published; the options pricer uses realized volatility.</li></ul></div>`;
  }

  async function show() {
    if (!built) { shell(); built = true; }
    if (!D) D = await getJSON('data/metals/metals.json').catch(() => null);
    const m = location.hash.match(/^#metals\/(gc|si|hg|ali|pl|pa)(?:\/(\w+))?/i);
    if (m) { mk = m[1].toUpperCase(); if (TABS.some(t => t[0] === m[2])) tab = m[2]; }
    render(); window.scrollTo(0, 0);
  }
  return { show };
})();
