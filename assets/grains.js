// Grains & oilseeds section: corn, soybeans, soybean meal, soybean oil, Chicago wheat, KC wheat.
const G = 'data/grains/derived/';
const GC = {
  corn: { sym: 'ZC', name: 'Corn', wasde: 'corn', unit: '¢/bu', qty: 'mil bu', spec: [
      ['Contract', 'CBOT Corn (ZC)'], ['Size', '5,000 bushels'], ['Quote / tick', '¢/bu; ¼¢ = $12.50'], ['Months', 'Mar, May, Jul, Sep, Dec'],
      ['Delivery', 'Physical, by shipping certificate at Illinois River and Chicago/Burns Harbor stations; No. 2 yellow at par'],
      ['Last trade', 'Business day before the 15th of the contract month']],
    calendar: 'Planting Apr–May, pollination (silking) July, harvest Sep–Nov. Marketing year Sep–Aug. Key USDA dates: Prospective Plantings (end-Mar), Acreage and June 1 Stocks (end-Jun), first survey yield (Aug Crop Production), final (Jan).',
    lines: [
      ['Acreage', 'Set in spring by the new-crop corn/soy price ratio and input costs. 1 million acres ≈ 180 mil bu at trend yield.', 'Prospective Plantings, Acreage, FSA'],
      ['Yield', 'The biggest swing factor: July pollination weather decides it. 1 bu/acre on ~90 mil harvested acres ≈ 90 mil bu.', 'Crop condition (weekly), Aug–Nov Crop Production'],
      ['Feed & residual', 'Largest use (~35–40%); tied to animal numbers and price. Residual soaks up measurement error, revealed by quarterly stocks.', 'Grain Stocks (quarterly), cattle on feed, hogs & pigs'],
      ['Ethanol', '~35% of use; driven by gasoline demand, blending policy and the ethanol crush margin.', 'EIA weekly ethanol output'],
      ['Exports', 'Competes with Brazil (safrinha crop ships Jul–Jan), Argentina and Ukraine. Mexico, Japan, China, Colombia, Korea are buyers.', 'Weekly export sales, inspections, flash sales'],
      ['Ending stocks / use', 'The price-setting ratio. The desk fit on WASDE history shows price falling sharply as stocks-to-use rises.', 'WASDE (monthly)']],
    links: ['<b>Soybeans:</b> the two compete for acres; the new-crop soy/corn price ratio (~2.3–2.5) decides the split.',
      '<b>Livestock and dairy:</b> corn is the main feed cost for cattle, hogs and dairy; cheap corn widens feeding margins and supports herd expansion.',
      '<b>Energy:</b> one bushel yields ~2.9 gallons of ethanol plus ~16 lb DDGS; gasoline demand and RFS/E15 policy move corn grind.',
      '<b>Wheat:</b> wheat is fed to livestock when it trades near corn, capping the wheat–corn spread.',
      '<b>Brazil and the dollar:</b> Brazil’s second crop is now the main export rival; BRL weakness makes Brazilian corn cheaper.'] },
  soybeans: { sym: 'ZS', name: 'Soybeans', wasde: 'soybeans', unit: '¢/bu', qty: 'mil bu', crush: true, spec: [
      ['Contract', 'CBOT Soybeans (ZS)'], ['Size', '5,000 bushels'], ['Quote / tick', '¢/bu; ¼¢ = $12.50'], ['Months', 'Jan, Mar, May, Jul, Aug, Sep, Nov'],
      ['Delivery', 'Physical, by shipping certificate at Illinois River and Chicago stations; No. 2 yellow at par'],
      ['Last trade', 'Business day before the 15th of the contract month']],
    calendar: 'Planting May–Jun, pod setting August (the yield month), harvest Sep–Nov. Marketing year Sep–Aug. South America plants Sep–Dec and harvests Jan–May, so US prices trade Brazilian weather in the northern winter.',
    lines: [
      ['Acreage', 'Competes with corn; soy needs less nitrogen, so high fertilizer costs favor soybeans.', 'Prospective Plantings, Acreage'],
      ['Yield', 'August rain decides pod fill. 1 bu/acre on ~85 mil acres ≈ 85 mil bu, large against ~300–400 mil bu ending stocks.', 'Crop condition, Crop Production'],
      ['Crush', 'Driven by the board crush margin and by soybean oil demand for renewable diesel; new crush plants have lifted capacity.', 'NOPA monthly crush, Fats & Oils'],
      ['Exports', 'China is the key buyer; Brazil now supplies most Chinese demand from Feb–Aug. US export season is Sep–Jan.', 'Export sales, flash sales to China/unknown'],
      ['South America', 'Brazil and Argentina production sets world supply and the US export window.', 'WASDE world tables, CONAB'],
      ['Ending stocks / use', 'US stocks matter less for price than in corn; world and Brazil balances dominate.', 'WASDE']],
    links: ['<b>Crush:</b> one bushel (60 lb) yields ~11 lb oil and ~44 lb meal; beans trade against the value of their products.',
      '<b>Biofuels:</b> renewable diesel and biodiesel use ~half of US soybean oil; RVO volumes and 45Z credits drive oil and crush.',
      '<b>Corn:</b> acreage competition and shared weather.', '<b>China and Brazil:</b> Chinese buying and the BRL set US export competitiveness.'] },
  meal: { sym: 'ZM', name: 'Soybean meal', wasde: 'meal', unit: '$/short ton', qty: 'thou short tons', crush: true, spec: [
      ['Contract', 'CBOT Soybean Meal (ZM)'], ['Size', '100 short tons'], ['Quote / tick', '$/short ton; 10¢ = $10'], ['Months', 'Jan, Mar, May, Jul, Aug, Sep, Oct, Dec'],
      ['Delivery', 'Physical, by shipping certificate issued by processors in the delivery territory (48% protein)'],
      ['Last trade', 'Business day before the 15th of the contract month']],
    calendar: 'Produced year-round by crushers; output follows the crush rate, not a harvest.',
    lines: [['Crush rate', 'Meal is the by-product when oil drives crush: strong oil demand pushes meal supply up and price down.', 'NOPA crush'],
      ['Feed demand', 'Poultry and hogs are the main users; animal numbers and feed rations set domestic use.', 'Cattle on feed, hogs & pigs, broiler placements'],
      ['Exports', 'Competes with Argentina (largest exporter); Argentine crush strikes or drought tighten the world market.', 'Export sales, WASDE world']],
    links: ['<b>Soybean oil:</b> oil share of crush value rises with biofuel demand, making meal the residual product.', '<b>Livestock:</b> the protein half of the feed ration (corn is the energy half).'] },
  oil: { sym: 'ZL', name: 'Soybean oil', wasde: 'oil', unit: '¢/lb', qty: 'mil lb', crush: true, spec: [
      ['Contract', 'CBOT Soybean Oil (ZL)'], ['Size', '60,000 lb'], ['Quote / tick', '¢/lb; 0.01¢ = $6'], ['Months', 'Jan, Mar, May, Jul, Aug, Sep, Oct, Dec'],
      ['Delivery', 'Physical, by warehouse receipt for crude degummed oil at approved tanks'],
      ['Last trade', 'Business day before the 15th of the contract month']],
    calendar: 'Produced year-round; demand is policy-driven (biofuel mandates) and seasonal in food use.',
    lines: [['Biofuel use', 'Renewable diesel and biodiesel; driven by RFS volumes (RVO), RIN prices, LCFS and the 45Z credit.', 'EIA feedstock data, EPA RVO'],
      ['Crush supply', 'More crush means more oil; new plants add supply.', 'NOPA crush, oil stocks'],
      ['Competing fats', 'Canola, palm, used cooking oil and tallow compete as biofuel feedstock; import policy matters.', 'Census trade, palm oil prices']],
    links: ['<b>Energy:</b> trades with diesel/heating oil plus credit values.', '<b>Palm oil:</b> the world vegetable-oil benchmark.', '<b>Meal:</b> the other side of the crush.'] },
  wheat: { sym: 'ZW', name: 'Chicago wheat', wasde: 'wheat', unit: '¢/bu', qty: 'mil bu', spec: [
      ['Contract', 'CBOT Chicago SRW Wheat (ZW)'], ['Size', '5,000 bushels'], ['Quote / tick', '¢/bu; ¼¢ = $12.50'], ['Months', 'Mar, May, Jul, Sep, Dec'],
      ['Delivery', 'Physical, by shipping certificate (Chicago, Toledo, Ohio River, Mississippi River); variable storage rate adjusts carry'],
      ['Last trade', 'Business day before the 15th of the contract month']],
    calendar: 'Winter wheat planted Sep–Nov, harvested Jun–Jul; spring wheat planted Apr–May, harvested Aug. Marketing year Jun–May. World supply from Russia, EU, Australia, Canada, Argentina, Ukraine sets price.',
    lines: [['World production', 'Black Sea (Russia, Ukraine) and EU crops set export prices; the US is a residual supplier.', 'WASDE world, IGC'],
      ['US winter wheat condition', 'Plains drought (HRW) and soft red winter disease/quality.', 'Crop condition, drought monitor'],
      ['Exports', 'Competitiveness vs Russian FOB prices; dollar strength hurts.', 'Export sales, inspections'],
      ['Feed use', 'Wheat feeding when it trades near corn.', 'WASDE feed & residual']],
    links: ['<b>Corn:</b> feed substitution caps the wheat–corn spread.', '<b>Geopolitics:</b> Black Sea export corridors and Russian export quotas/taxes.', '<b>KC wheat:</b> HRW vs SRW spread reflects class balances and protein.'] },
  kc: { sym: 'KE', name: 'KC HRW wheat', wasde: 'wheat', unit: '¢/bu', qty: 'mil bu', spec: [
      ['Contract', 'CBOT KC Hard Red Winter Wheat (KE)'], ['Size', '5,000 bushels'], ['Quote / tick', '¢/bu; ¼¢ = $12.50'], ['Months', 'Mar, May, Jul, Sep, Dec'],
      ['Delivery', 'Physical, by shipping certificate in the Kansas City / Hutchinson / Salina / Wichita territory'],
      ['Last trade', 'Business day before the 15th of the contract month']],
    calendar: 'Southern Plains crop: planted Sep–Oct, dormant over winter, harvested Jun–Jul. Spring moisture in Kansas/Oklahoma/Texas decides yield.',
    lines: [['Plains weather', 'Drought in KS/OK/TX is the main supply risk; abandonment rises in dry years.', 'Crop condition, drought monitor'],
      ['Protein', 'Bread-wheat class; protein premiums widen KC over Chicago in short-protein years.', 'Harvest quality surveys'],
      ['Exports', 'Competes with Russian and Canadian bread wheat.', 'Export sales by class']],
    links: ['<b>Chicago wheat:</b> the KC–Chicago spread is the main relative-value trade.', '<b>Corn:</b> feed substitution.'] },
};

const Grains = (() => {
  let built = false, com = 'corn', tab = 'g-primer', W, F, COND, EXP, TESTS;
  const el = s => document.querySelector('#grains ' + s);
  function shell() {
    $('#grains').innerHTML = `
      <nav class="tabs" id="gCom" style="background:#f0f6f1">${Object.entries(GC).map(([k, v]) => `<button data-com="${k}" class="${k === com ? 'on' : ''}">${v.name}</button>`).join('')}</nav>
      <nav class="tabs" id="gTabs">
        <button data-t="g-primer" class="on">1 · Primer</button><button data-t="g-sd">2 · Supply &amp; demand</button>
        <button data-t="g-flows">3 · Futures, options &amp; COT</button><button data-t="g-outlook">4 · Outlook</button></nav>
      <main><div id="gBody"></div></main>`;
    $$('#gCom button').forEach(b => b.onclick = () => { com = b.dataset.com; $$('#gCom button').forEach(x => x.classList.toggle('on', x === b)); render(); });
    $$('#gTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; $$('#gTabs button').forEach(x => x.classList.toggle('on', x === b)); render(); });
  }
  async function load() {
    [W, F, COND, EXP, TESTS] = await Promise.all([getJSON(G + 'wasde.json'), getJSON(G + 'flows.json').catch(() => null),
      getJSON(G + 'condition.json').catch(() => null), getJSON(G + 'exports.json').catch(() => null), getJSON(G + 'tests.json').catch(() => null)]);
  }
  function fromHash() {
    const h = location.hash.slice(1).split('/');
    if (h[0] === 'g') { if (GC[h[1]]) com = h[1]; if (['g-primer', 'g-sd', 'g-flows', 'g-outlook'].includes(h[2])) tab = h[2]; }
    $$('#gCom button').forEach(x => x.classList.toggle('on', x.dataset.com === com)); $$('#gTabs button').forEach(x => x.classList.toggle('on', x.dataset.t === tab));
  }
  async function show() {
    if (!built) { shell(); await load(); built = true; }
    fromHash(); render();
  }
  window.addEventListener('hashchange', () => { if (built && location.hash.startsWith('#g/') && location.hash !== `#g/${com}/${tab}`) { fromHash(); render(); } });
  function render() {
    history.replaceState(null, '', `#g/${com}/${tab}`);
    const c = GC[com];
    ({ 'g-primer': primer, 'g-sd': sd, 'g-flows': flows, 'g-outlook': outlook })[tab](c);
  }
  const us = c => { const b = W.commodities[c.wasde].us; const my = Object.keys(b).sort(); return { b, my, cur: my.at(-1), prev: my.at(-2) }; };

  // ── PRIMER ──
  function primer(c) {
    const u = us(c), it = u.b[u.cur].items, su = W.commodities[c.wasde].stocks_use_vs_price;
    el('#gBody').innerHTML = `
      <div class="grid g2">
        <div class="card"><h2>${c.name}: the contract</h2><div class="tbl"><table>${c.spec.map(([a, b]) => `<tr><td>${a}</td><td class="l">${b}</td></tr>`).join('')}</table></div>
          <h3>Convergence</h3><p>Unlike the dairy and lean hog contracts, grain futures are physically delivered. In the delivery period the futures converge to the cash value of grain at the delivery points. Interior cash prices trade at a basis to futures that reflects freight, storage and local supply. A strong (narrow) basis signals tight nearby supply; wide carry spreads signal plentiful stocks.</p>
          <h3>Crop calendar</h3><p>${c.calendar}</p></div>
        <div class="card"><h2>How each supply-and-demand line moves price</h2><div class="tbl"><table><tr><th class="l">Line</th><th class="l">Mechanism</th><th class="l">Watch</th></tr>
          ${c.lines.map(l => `<tr><td class="l">${l[0]}</td><td class="l">${l[1]}</td><td class="l">${l[2]}</td></tr>`).join('')}</table></div>
          <h3>Linkages</h3><ul class="read">${c.links.map(x => `<li>${x}</li>`).join('')}</ul></div>
      </div>
      <div class="card" style="margin-top:12px" id="gWhatIf"></div>
      ${c.crush ? '<div class="card" style="margin-top:12px" id="gCrush"></div>' : ''}`;
    whatIf(c, it, su, u.cur);
    if (c.crush) crushCalc();
  }
  function whatIf(c, it, su, my) {
    const v = k => it[k]?.value;
    const has = v('production') != null && v('end_stocks') != null && v('use') != null;
    if (!has) { el('#gWhatIf').innerHTML = '<p class="note">Balance what-if not available for this commodity.</p>'; return; }
    const area = v('area_harvested'), yld = v('yield');
    el('#gWhatIf').innerHTML = `<h2>Balance sheet what-if: ${my} (start: WASDE ${W.commodities[c.wasde].us[my].report})</h2>
      <div class="grid g2"><div>
        ${area && yld ? `<div class="slider"><label>Yield (bu/ac)</label><input type="range" id="wYield" min="${(yld * .85).toFixed(1)}" max="${(yld * 1.1).toFixed(1)}" step="0.1" value="${yld}"><output id="oYield"></output></div>
        <div class="slider"><label>Harvested (mil ac)</label><input type="range" id="wArea" min="${(area * .92).toFixed(1)}" max="${(area * 1.06).toFixed(1)}" step="0.1" value="${area}"><output id="oArea"></output></div>` : ''}
        <div class="slider"><label>Exports (${c.qty})</label><input type="range" id="wExp" min="${(v('exports') * .75).toFixed(0)}" max="${(v('exports') * 1.2).toFixed(0)}" step="${v('exports') > 1000 ? 5 : 1}" value="${v('exports')}"><output id="oExp"></output></div>
        <div class="slider"><label>Domestic use (${c.qty})</label><input type="range" id="wDom" min="${(v('domestic') * .93).toFixed(0)}" max="${(v('domestic') * 1.07).toFixed(0)}" step="${v('domestic') > 1000 ? 5 : 1}" value="${v('domestic')}"><output id="oDom"></output></div>
        <p class="note">Production = harvested area × yield. Ending stocks = beginning stocks + production + imports − domestic use − exports. Implied price uses the desk's fit of season-average farm price on stocks-to-use across past WASDE marketing years${su ? ` (elasticity ${su.fit.elasticity}, R² ${su.fit.r2})` : ''}; treat it as a direction-and-size guide, not a forecast.</p>
      </div><div><div class="bigout"><div><div class="note">Ending stocks</div><div class="v" id="oEnd"></div></div><div><div class="note">Stocks/use</div><div class="v" id="oSU"></div></div><div><div class="note">Implied farm price</div><div class="v" id="oPx"></div></div></div>
        <div class="chart short"><canvas id="cSU"></canvas></div></div></div>`;
    const calc = () => {
      const y = +($('#wYield')?.value ?? 0), a = +($('#wArea')?.value ?? 0), ex = +$('#wExp').value, dom = +$('#wDom').value;
      const prod = area && yld ? y * a : v('production');
      const end = v('beg_stocks') + prod + (v('imports') || 0) - dom - ex, use = dom + ex;
      const s = 100 * end / use, px = su ? Math.exp(su.fit.intercept + su.fit.elasticity * Math.log(Math.max(s, .5))) : null;
      if ($('#oYield')) { $('#oYield').textContent = y.toFixed(1); $('#oArea').textContent = a.toFixed(1); }
      $('#oExp').textContent = fmt(ex, 0); $('#oDom').textContent = fmt(dom, 0);
      $('#oEnd').innerHTML = `${fmt(end, 0)} <span class="note">(${sgn(end - v('end_stocks'), 0)})</span>`;
      $('#oSU').textContent = s.toFixed(1) + '%';
      $('#oPx').innerHTML = px ? `$${px.toFixed(2)} <span class="note">vs WASDE $${fmt(v('price'))}</span>` : '–';
      if (su) chart('cSU', { type: 'scatter', data: { datasets: [
        { label: 'past marketing years', data: su.stocks_use_pct.map((x, i) => ({ x, y: su.price[i], m: su.my[i] })), backgroundColor: 'rgba(120,120,120,.5)' },
        { label: 'what-if', data: [{ x: s, y: px, m: 'what-if' }], backgroundColor: '#c0392b', pointRadius: 6 }] },
        options: { interaction: { mode: 'nearest', intersect: true }, plugins: { tooltip: { callbacks: { label: q => `${q.raw.m}: ${q.raw.x.toFixed(1)}% , $${q.raw.y?.toFixed(2)}` } } },
          scales: { x: { title: { display: true, text: 'stocks/use %' } }, y: { title: { display: true, text: '$/unit' } } } } });
    };
    $$('#gWhatIf input').forEach(i => i.oninput = calc); calc();
  }
  function crushCalc() {
    const cv = F?.curves || {}, last = s => { const d = cv[s]; if (!d) return null; const k = Object.keys(d).sort().at(-1); return d[k].settle[0]; };
    const zs = last('ZS') ?? 1050, zm = last('ZM') ?? 310, zl = last('ZL') ?? 50;
    el('#gCrush').innerHTML = `<h2>Board crush calculator</h2><div class="grid g2"><div>
      <div class="slider"><label>Soybeans ¢/bu</label><input type="range" id="kS" min="800" max="1600" step="0.25" value="${zs}"><output id="okS"></output></div>
      <div class="slider"><label>Meal $/st</label><input type="range" id="kM" min="200" max="500" step="0.1" value="${zm}"><output id="okM"></output></div>
      <div class="slider"><label>Oil ¢/lb</label><input type="range" id="kO" min="30" max="90" step="0.01" value="${zl}"><output id="okO"></output></div>
      <p class="note">Board crush ($/bu) = meal × 0.022 + oil × 0.11 − beans. A bushel yields ~44 lb meal (0.022 short tons) and ~11 lb oil. Oil share = oil value ÷ product value; above ~45–50% oil is driving crush and meal is the residual. Starts at the front-month CME settlements.</p></div>
      <div><div class="bigout"><div><div class="note">Board crush</div><div class="v" id="okC"></div></div><div><div class="note">Oil share</div><div class="v" id="okSh"></div></div></div></div></div>`;
    const calc = () => { const s = +$('#kS').value, m = +$('#kM').value, o = +$('#kO').value;
      $('#okS').textContent = s.toFixed(2); $('#okM').textContent = m.toFixed(1); $('#okO').textContent = o.toFixed(2);
      const mv = m * 0.022, ov = o * 0.11; $('#okC').textContent = '$' + (mv + ov - s / 100).toFixed(2) + '/bu'; $('#okSh').textContent = (100 * ov / (mv + ov)).toFixed(1) + '%'; };
    $$('#gCrush input').forEach(i => i.oninput = calc); calc();
  }

  // ── S&D ──
  function sd(c) {
    const u = us(c), mys = u.my.slice(-2);
    const rows = [['area_planted', 'Area planted (mil ac)', 1], ['area_harvested', 'Area harvested (mil ac)', 1], ['yield', 'Yield', 1], ['beg_stocks', 'Beginning stocks', 0],
      ['production', 'Production', 0], ['imports', 'Imports', 0], ['supply', 'Total supply', 0], ['feed_residual', 'Feed & residual', 0], ['fsi', 'Food, seed & industrial', 0],
      ['ethanol', 'Ethanol', 0], ['crush', 'Crush', 0], ['biofuel', 'Biofuel', 0], ['domestic', 'Domestic total', 0], ['exports', 'Exports', 0], ['use', 'Total use', 0],
      ['end_stocks', 'Ending stocks', 0], ['price', 'Avg farm price', 2]];
    const cell = (my, k, d) => { const x = u.b[my]?.items[k]; return x ? `<td>${fmt(x.value, d)}</td><td>${sgn(x.change, d)}</td>` : '<td>–</td><td></td>'; };
    const su = my => { const i = u.b[my].items; return i.end_stocks && i.use ? (100 * i.end_stocks.value / i.use.value).toFixed(1) + '%' : '–'; };
    const world = W.commodities[c.wasde].world;
    el('#gBody').innerHTML = `
      <div class="grid g2">
        <div class="card"><h2>US balance (WASDE ${u.b[u.cur].report}, ${c.qty})</h2><div class="tbl"><table>
          <tr><th></th>${mys.map(m => `<th>${m}</th><th>chg</th>`).join('')}</tr>
          ${rows.filter(r => mys.some(m => u.b[m]?.items[r[0]])).map(([k, l, d]) => `<tr><td>${l}</td>${mys.map(m => cell(m, k, d)).join('')}</tr>`).join('')}
          <tr><td>Stocks/use</td>${mys.map(m => `<td>${su(m)}</td><td></td>`).join('')}</tr></table></div>
          <p class="note">Change = this month's WASDE vs last month's. Read the revisions, not the levels.</p></div>
        <div class="card"><h2>Revision path</h2><div class="ctrls"><select id="gRevItem">${rows.filter(r => u.b[u.cur].items[r[0]]).map(([k, l]) => `<option value="${k}" ${k === 'end_stocks' ? 'selected' : ''}>${l} ${u.cur}</option>`).join('')}</select></div>
          <div class="chart"><canvas id="cGRev"></canvas></div>
          <div id="gRevStats" class="note"></div></div>
      </div>
      ${world ? `<div class="card" style="margin-top:12px"><h2>World: key countries (latest two marketing years)</h2><div class="tbl"><table id="tWorld"></table></div><p class="note">USDA estimates, million metric tons. Change vs last month's WASDE.</p></div>` : ''}
      <div class="grid g2" style="margin-top:12px">
        <div class="card" id="gCond"><h2>Crop condition and yield model</h2><p class="note">Loading…</p></div>
        <div class="card" id="gExp"><h2>Export pace</h2><p class="note">Loading…</p></div>
      </div>
      <div class="card" style="margin-top:12px"><h2>Stocks-to-use vs season-average farm price</h2><div class="chart"><canvas id="cGSU"></canvas></div><p class="note" id="gSUnote"></p></div>`;
    const drawRev = () => { const k = $('#gRevItem').value, x = u.b[u.cur].items[k];
      chart('cGRev', { type: 'line', data: { labels: x.history.map(h => h[0].replace(/(\w{3})\w* (\d{4})/, '$1 $2')), datasets: [{ label: `${k} ${u.cur}`, data: x.history.map(h => h[1]), borderColor: PAL[0], stepped: true, pointRadius: 3 }] } });
      const rs = W.commodities[c.wasde].revisions?.[k];
      $('#gRevStats').innerHTML = rs ? `First-to-final WASDE revision for ${k.replace('_', ' ')}: average ${fmt(rs.mean_abs_pct, 1)}% in absolute terms over ${rs.my.length} completed years (${rs.my.map((m, i) => `${m} ${sgn(rs.pct[i], 1, '%')}`).slice(-6).join(', ')}).` : ''; };
    $('#gRevItem').onchange = drawRev; drawRev();
    if (world) {
      const cs = Object.keys(world), attrs = [['production', 'Production'], ['exports', 'Exports'], ['imports', 'Imports'], ['end_stocks', 'Ending stocks']];
      $('#tWorld').innerHTML = `<tr><th>Country</th>${attrs.map(a => `<th>${a[1]}</th><th>chg</th>`).join('')}</tr>` + cs.map(cn => { const b = world[cn]; const my = Object.keys(b).sort().at(-1); const it = b[my].items;
        return `<tr><td>${cn} ${my}</td>${attrs.map(([k]) => it[k] ? `<td>${fmt(it[k].value, 1)}</td><td>${sgn(it[k].change, 1)}</td>` : '<td>–</td><td></td>').join('')}</tr>`; }).join('');
    }
    const s = W.commodities[c.wasde].stocks_use_vs_price;
    if (s) { const cur = u.b[u.cur].items; const cx = cur.end_stocks && cur.use ? 100 * cur.end_stocks.value / cur.use.value : null;
      chart('cGSU', { type: 'scatter', data: { datasets: [{ label: 'completed marketing years', data: s.stocks_use_pct.map((x, i) => ({ x, y: s.price[i], m: s.my[i] })), backgroundColor: 'rgba(47,107,58,.6)', pointRadius: 4 },
        ...(cx ? [{ label: `${u.cur} projection`, data: [{ x: cx, y: cur.price?.value, m: u.cur }], backgroundColor: '#c0392b', pointRadius: 7 }] : [])] },
        options: { interaction: { mode: 'nearest', intersect: true }, plugins: { tooltip: { callbacks: { label: q => `${q.raw.m}: ${q.raw.x.toFixed(1)}%, $${q.raw.y}` } } },
          scales: { x: { title: { display: true, text: 'ending stocks / total use %' } }, y: { title: { display: true, text: 'season-average farm price' } } } } });
      $('#gSUnote').textContent = `Log-log fit over WASDE final estimates: elasticity ${s.fit.elasticity}, R² ${s.fit.r2}. ${s.fit.r2 < 0.3 ? 'Weak: US stocks alone do not set this price (world balances, crush economics or policy dominate).' : 'US stocks-to-use explains a large share of price differences across years.'}`; }
    condCard(c); expCard(c);
  }
  function condCard(c) {
    const box = el('#gCond'), d = COND?.[c.wasde];
    if (!d) { box.innerHTML = '<h2>Crop condition and yield model</h2><p class="note">Crop condition history is still downloading from NASS in batches; this panel fills in automatically when it lands.</p>'; return; }
    box.innerHTML = `<h2>Crop condition: good/excellent % (national)</h2><div class="chart"><canvas id="cCond"></canvas></div>
      <div id="gYield"></div>`;
    const ds = Object.keys(d.ge).sort().slice(-6).map((y, i, a) => ({ label: y, data: d.ge[y].map(p => ({ x: p[0], y: p[1] })), borderColor: i === a.length - 1 ? '#c0392b' : PAL[(i + 2) % PAL.length], borderWidth: i === a.length - 1 ? 2.5 : 1.2, pointRadius: 0 }));
    chart('cCond', { type: 'line', data: { datasets: ds }, options: { scales: { x: { type: 'linear', title: { display: true, text: 'week of year' } }, y: { title: { display: true, text: 'G/E %' } } } } });
    const m = d.model;
    if (m) $('#gYield').innerHTML = `<h3>Condition-based yield model</h3><p>${m.year} yield estimate from condition in week ${m.week}: <b>${fmt(m.estimate, 1)} bu/ac</b> vs USDA ${fmt(m.usda, 1)} (trend ${fmt(m.trend, 1)}).</p>
      <p class="note">Backtest (leave-one-year-out, ${m.test.n} years): mean abs error ${fmt(m.test.mae_model, 2)} bu/ac vs ${fmt(m.test.mae_trend, 2)} for trend alone${m.test.mae_usda_same_date != null ? `; on the ${m.test.n_usda} years with a USDA yield forecast at the same date, model ${fmt(m.test.mae_model_same_years, 2)} vs USDA ${fmt(m.test.mae_usda_same_date, 2)}` : ''}. Direction vs trend right ${fmt(100 * m.test.hit_direction, 0)}% of years.</p>`;
    const sw = c.wasde === 'wheat' ? COND?.spring_wheat?.model : null;
    if (sw) $('#gYield').innerHTML += `<h3>Spring wheat (HRS)</h3><p>${sw.year} estimate from condition in week ${sw.week}: <b>${fmt(sw.estimate, 1)} bu/ac</b> vs USDA ${fmt(sw.usda, 1)} (trend ${fmt(sw.trend, 1)}).</p>
      <p class="note">Backtest (${sw.test.n} years): mean abs error ${fmt(sw.test.mae_model, 2)} vs ${fmt(sw.test.mae_trend, 2)} for trend alone; direction right ${fmt(100 * sw.test.hit_direction, 0)}%.</p>`;
    if (c.wasde === 'wheat') $('#gYield').insertAdjacentHTML('afterbegin', '<p class="note">Winter wheat; negative weeks are the previous autumn\'s ratings (crop year).</p>');
  }
  function expCard(c) {
    const box = el('#gExp'), d = EXP?.[c.wasde];
    if (!d) { box.innerHTML = '<h2>Export pace</h2><p class="note">Export inspections and sales history are still downloading; this panel fills in when they land.</p>'; return; }
    box.innerHTML = `<h2>Export inspections pace (${d.my}, ${d.unit})</h2><div class="chart"><canvas id="cExpPace"></canvas></div><div id="gExpTxt"></div>`;
    chart('cExpPace', { type: 'line', data: { labels: d.weeks, datasets: [
      { label: `${d.my} cumulative`, data: d.cur, borderColor: '#c0392b', borderWidth: 2.4, pointRadius: 0 },
      { label: 'prior year', data: d.prev, borderColor: '#2c6fbb', pointRadius: 0 },
      { label: 'pace needed for USDA', data: d.needed, borderColor: '#999', borderDash: [4, 3], pointRadius: 0 }] } });
    $('#gExpTxt').innerHTML = `<p>Week ${d.week}: ${fmt(d.cum, 0)} shipped, ${fmt(d.pct_of_usda, 1)}% of USDA's ${fmt(d.usda, 0)} vs ${fmt(d.avg_pct, 1)}% on average by this week. Pace-implied exports <b>${fmt(d.implied, 0)}</b> (${sgn(d.implied - d.usda, 0)} vs USDA).</p>
      ${d.test ? `<p class="note">Backtest: the pace-implied figure has missed final exports by ${fmt(d.test.mae_pct, 1)}% on average at this point of the season vs ${fmt(d.test.mae_usda_pct, 1)}% for USDA's same-month forecast; it called the direction of USDA's next export revision ${fmt(100 * d.test.revision_hit, 0)}% of the time (n=${d.test.n}).</p>` : ''}`;
  }

  // ── FLOWS ──
  function flows(c) {
    if (!F || !F.cot?.[c.sym]) { el('#gBody').innerHTML = '<div class="card"><p class="note">Grain futures, options and COT data are still downloading; this tab fills in after the next data run.</p></div>'; return; }
    const syms = Object.keys(F.cot);
    el('#gBody').innerHTML = `<div class="card"><h2>Managed money across grains &amp; oilseeds</h2><div class="tbl"><table id="tGCot"></table></div>
        <p class="note">CFTC Disaggregated COT, futures and options combined. Percentiles vs all history and the last 3 years.</p></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h3>Price (continuous front month, ${c.unit})</h3><div class="chart"><canvas id="cGPx"></canvas></div></div>
        <div class="card"><h3>Managed money vs producer/merchant net</h3><div class="chart"><canvas id="cGCot"></canvas></div></div>
        <div class="card"><h3 id="gCurveT">Forward curve</h3><div class="chart"><canvas id="cGCurve"></canvas></div><p class="note" id="gCarry"></p></div>
        <div class="card"><h3 id="gOiT">Open interest by month</h3><div class="chart"><canvas id="cGOi"></canvas></div></div>
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Relative value</h2><div class="ctrls"><select id="gRv"></select></div><div class="chart"><canvas id="cGRv"></canvas></div><p class="note" id="gRvNote"></p></div>
        <div class="card"><h2>Seasonality (front month, % vs that year's average)</h2><div class="chart"><canvas id="cGSeas"></canvas></div><p class="note" id="gSeasNote"></p></div>
      </div>
      <div class="card" style="margin-top:12px"><h2>Options open interest by strike</h2><div class="ctrls" id="gOptM"></div><div class="chart tall"><canvas id="cGOpt"></canvas></div></div>`;
    const name = s => Object.values(GC).find(x => x.sym === s)?.name || s;
    $('#tGCot').innerHTML = `<tr><th>Contract</th><th>Report</th><th>Open int.</th><th>MM net</th><th>w/w</th><th>% OI</th><th>Pctl all</th><th>Pctl 3y</th><th>Prod/merch</th><th>Swap</th></tr>` +
      syms.map(s => { const x = F.cot[s].summary; return `<tr><td>${name(s)}</td><td>${x.date}</td><td>${fmt(x.oi, 0)}</td><td>${sgn(x.mm_net, 0)}</td><td>${sgn(x.mm_net_wow, 0)}</td><td>${fmt(x.mm_net_pct_oi, 1)}%</td><td>${fmt(x.mm_net_percentile_all, 0)}</td><td>${fmt(x.mm_net_percentile_3y, 0)}</td><td>${sgn(x.pm_net, 0)}</td><td>${sgn(x.sw_net, 0)}</td></tr>`; }).join('');
    const px = F.prices[c.sym];
    if (px) chart('cGPx', { type: 'line', data: { labels: px.date.slice(-750), datasets: [{ label: c.name, data: px.c1.slice(-750), borderColor: PAL[0], pointRadius: 0, borderWidth: 1.4 }] } });
    const s = F.cot[c.sym].series, n = 260;
    chart('cGCot', { type: 'line', data: { labels: s.date.slice(-n), datasets: [
      { label: 'Managed money net', data: s.mm_net.slice(-n), borderColor: PAL[1], pointRadius: 0, borderWidth: 2 },
      { label: 'Producer/merchant net', data: s.pm_net.slice(-n), borderColor: PAL[2], pointRadius: 0 },
      { label: 'Swap dealer net', data: s.sw_net.slice(-n), borderColor: '#999', pointRadius: 0 }] } });
    const cv = F.curves[c.sym];
    if (cv) { const days = Object.keys(cv).sort(), d1 = days.at(-1), d0 = days.length > 1 ? days[0] : null;
      $('#gCurveT').textContent = `Forward curve · ${d1}${d0 ? ' vs ' + d0 : ''}`;
      chart('cGCurve', { type: 'line', data: { labels: cv[d1].month, datasets: [{ label: d1, data: cv[d1].settle, borderColor: PAL[0], pointRadius: 2, borderWidth: 2 },
        ...(d0 ? [{ label: d0, data: cv[d1].month.map(m => { const i = cv[d0].month.indexOf(m); return i < 0 ? null : cv[d0].settle[i]; }), borderColor: '#aaa', borderDash: [4, 3], pointRadius: 0 }] : [])] } });
      const a = cv[d1].settle; if (a.length > 1) $('#gCarry').textContent = `First spread ${cv[d1].month[0]}/${cv[d1].month[1]}: ${(a[1] - a[0]).toFixed(2)} (${a[1] > a[0] ? 'carry: nearby supply ample' : 'inverse: nearby supply tight'}).`; }
    const oi = F.oi[c.sym];
    if (oi) { $('#gOiT').textContent = `Open interest by month · ${oi.date}`;
      chart('cGOi', { type: 'bar', data: { labels: oi.month, datasets: [{ label: 'Open interest', data: oi.oi, backgroundColor: 'rgba(47,107,58,.55)', yAxisID: 'y' },
        { label: 'Change', data: oi.oi_change, backgroundColor: oi.oi_change.map(v => v >= 0 ? '#1f7a3a' : '#b3261e'), yAxisID: 'y1' }] },
        options: { scales: { y1: { position: 'right', grid: { display: false } } } } }); }
    const rv = F.rv;
    if (rv) { const lab = { soy_corn_ratio: 'Soybean / corn price ratio', wheat_minus_corn: 'Chicago wheat − corn (¢/bu)', kc_minus_chicago: 'KC − Chicago wheat (¢/bu)', board_crush: 'Board crush ($/bu)', oil_share: 'Oil share of crush value (%)' };
      const note = { soy_corn_ratio: 'Above ~2.4 favors soybean acres, below ~2.2 favors corn (new-crop Nov/Dec matters most in Feb–Mar).', wheat_minus_corn: 'Near zero, wheat gets fed to livestock instead of corn.', kc_minus_chicago: 'Protein and class balance: KC over Chicago in short-protein years.', board_crush: 'Processor margin; strong crush supports bean demand.', oil_share: 'Above ~45–50% oil is leading the crush and meal is the by-product.' };
      const keys = Object.keys(lab).filter(k => rv[k]); $('#gRv').innerHTML = keys.map(k => `<option value="${k}">${lab[k]}</option>`).join('');
      const draw = () => { const k = $('#gRv').value; chart('cGRv', { type: 'line', data: { labels: rv.date, datasets: [{ label: lab[k], data: rv[k], borderColor: PAL[0], pointRadius: 0, borderWidth: 1.3 }] } }); $('#gRvNote').textContent = note[k]; };
      $('#gRv').onchange = draw; draw(); }
    const se = F.seasonality?.[c.sym];
    if (se) { chart('cGSeas', { type: 'line', data: { labels: se.month.map(m => MON[m - 1]), datasets: [
      { label: 'upper quartile', data: se.q75, borderWidth: 0, backgroundColor: 'rgba(47,107,58,.12)', fill: '+1', pointRadius: 0 },
      { label: '_lower', data: se.q25, borderWidth: 0, pointRadius: 0 },
      { label: `${se.years}-yr average`, data: se.mean, borderColor: '#999', borderDash: [4, 3], pointRadius: 0 },
      { label: `${se.current_year} (vs prior-year avg)`, data: se.current, borderColor: '#c0392b', borderWidth: 2.2, pointRadius: 2 }] }, options: { plugins: { legend: legendNoMin } } });
      $('#gSeasNote').textContent = 'Monthly average of the continuous front month as % deviation from each year’s mean; shaded band = middle 50% of years. Roll effects between contract months are included.'; }
    const o = F.options?.[c.sym];
    if (o) { const ms = Object.keys(o.months); let om = ms[0];
      const draw = () => { $('#gOptM').innerHTML = ms.map(m => `<button class="btn ${m === om ? 'on' : ''}" data-m="${m}">${m}</button>`).join(' ') + ` <span class="note">${o.date} · put/call OI ${o.months[om].put_call_oi ?? '–'}</span>`;
        $$('#gOptM button').forEach(b => b.onclick = () => { om = b.dataset.m; draw(); });
        const x = o.months[om];
        chart('cGOpt', { type: 'bar', data: { labels: x.strike, datasets: [{ label: 'Call OI', data: x.call_oi, backgroundColor: 'rgba(31,122,58,.7)' }, { label: 'Put OI', data: x.put_oi.map(v => -v), backgroundColor: 'rgba(179,38,30,.7)' }] },
          options: { indexAxis: 'y', scales: { x: { ticks: { callback: v => Math.abs(v) } }, y: { ticks: { autoSkip: true, maxTicksLimit: 30 } } }, plugins: { tooltip: { callbacks: { label: q => `${q.dataset.label}: ${Math.abs(q.raw)}` } } } } }); };
      draw(); }
  }

  // ── OUTLOOK ──
  function outlook(c) {
    const u = us(c), it = u.b[u.cur].items, L = [];
    const ch = (k, d = 0) => it[k] ? `${fmt(it[k].value, d)} (${sgn(it[k].change, d)})` : '–';
    L.push(`<b>WASDE ${u.b[u.cur].report}, ${u.cur}:</b> production ${ch('production')}, exports ${ch('exports')}, ending stocks ${ch('end_stocks')}${it.end_stocks && it.use ? `, stocks/use ${(100 * it.end_stocks.value / it.use.value).toFixed(1)}%` : ''}, farm price ${ch('price', 2)}.`);
    const s = W.commodities[c.wasde].stocks_use_vs_price;
    if (s && it.end_stocks && it.use && it.price && s.fit.r2 >= 0.3) { const su = 100 * it.end_stocks.value / it.use.value, fair = Math.exp(s.fit.intercept + s.fit.elasticity * Math.log(su));
      L.push(`<b>Stocks/use model:</b> ${su.toFixed(1)}% stocks/use maps to about $${fair.toFixed(2)} on the historical fit vs USDA's $${fmt(it.price.value, 2)} season-average forecast.`); }
    const rv = Object.entries(it).filter(([k, x]) => x.change && Math.abs(x.change) > 0 && ['production', 'yield', 'exports', 'end_stocks', 'feed_residual', 'ethanol', 'crush'].includes(k));
    if (rv.length) L.push(`<b>This month's revisions:</b> ${rv.map(([k, x]) => `${k.replace('_', ' ')} ${sgn(x.change, k === 'yield' ? 1 : 0)}`).join(', ')}.`);
    const d = COND?.[c.wasde]?.model; if (d) L.push(`<b>Condition yield model:</b> ${fmt(d.estimate, 1)} bu/ac vs USDA ${fmt(d.usda, 1)} (${sgn(d.estimate - d.usda, 1)}).`);
    const e = EXP?.[c.wasde]; if (e) L.push(`<b>Export pace:</b> week ${e.week}, ${fmt(e.pct_of_usda, 1)}% of USDA shipped vs ${fmt(e.avg_pct, 1)}% normally; inspections imply ${fmt(e.implied, 0)} vs USDA ${fmt(e.usda, 0)} (${sgn(e.implied - e.usda, 0)})${e.test ? `, typical miss at this stage ±${fmt(e.test.mae_pct, 0)}%. Pace ahead/behind USDA has called the direction of USDA's next export revision ${fmt(100 * e.test.revision_hit, 0)}% of the time` : ''}.`);
    const x = F?.cot?.[c.sym]?.summary; if (x) L.push(`<b>Positioning (secondary):</b> managed money ${x.mm_net >= 0 ? 'net long' : 'net short'} ${fmt(Math.abs(x.mm_net), 0)} (${fmt(x.mm_net_percentile_3y, 0)} pctl of 3y).`);
    const cv = F?.curves?.[c.sym]; if (cv) { const k = Object.keys(cv).sort().at(-1), a = cv[k].settle; if (a.length > 1) L.push(`<b>Curve:</b> front spread ${(a[1] - a[0]).toFixed(2)} ${a[1] > a[0] ? '(carry)' : '(inverse)'}; front ${fmt(a[0], 2)} ${c.unit}.`); }
    const t = TESTS?.[c.wasde];
    el('#gBody').innerHTML = `<div class="grid g2"><div class="card"><h2>${c.name} desk readout</h2><ul class="read">${L.map(l => `<li>${l}</li>`).join('')}</ul>
      <p class="note">Built from tabs 2 and 3 each time the data update; what the numbers say, not a trade recommendation.</p></div>
      <div class="card"><h2>What the models have been tested to do</h2><div id="gTests">${t ? t.html : '<p class="note">Backtests run once the crop condition, export and contract histories finish downloading.</p>'}</div></div></div>`;
  }
  return { show };
})();
