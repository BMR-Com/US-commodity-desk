// Cotton section: built from the BMR-Com cotton repos (WASDE analytics, export sales, crop progress, on-call, COT)
// plus the desk's own COT desk, technicals, news and calendar.
const Cotton = (() => {
  let built = false, tab = 'ct-primer';
  const ORG = location.hostname === 'bmr-com.github.io' ? '' : 'https://bmr-com.github.io';   // sibling Pages sites (same origin when live)
  const SITE = { wasde: ORG + '/wasde-analytics/', esr: ORG + '/usd-export-sales-email/', crop: ORG + '/cotton-crop-progress/', oncall: ORG + '/cotton-on-call/',
    cot: ORG + '/cftc-cot-full/', opts: ORG + '/softs--options-/' };
  const TABS = [['ct-primer', 'Primer'], ['ct-geo', "Where it's grown, trade &amp; weather"], ['ct-wasde', 'WASDE'], ['ct-esr', 'Export sales'], ['ct-crop', 'Crop progress'], ['ct-ams', 'AMS market review'], ['ct-china', 'China'], ['ct-india', 'India'], ['ct-aus', 'Australia'], ['ct-loan', 'Loan'], ['ct-certs', 'Certs &amp; quality premiums'], ['ct-oncall', 'On-call'], ['ct-basis', 'Basis &amp; ideas'],
    ['ct-flows', 'Futures, options &amp; COT'], ['ct-rv', 'Spreads &amp; vol'], ['ct-outlook', 'Outlook'], ['ct-seas', 'Seasonality &amp; technicals']];
  function shell() {
    $('#cotton').innerHTML = `<nav class="tabs" id="ctTabs">${TABS.map(([k, l], i) => `<button data-t="${k}" class="${k === tab ? 'on' : ''}">${i + 1} · ${l}</button>`).join('')}</nav><main><div id="ctBody"></div></main>`;
    $$('#ctTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; $$('#ctTabs button').forEach(x => x.classList.toggle('on', x === b)); render(); });
  }
  function show() {
    if (!built) { shell(); built = true; }
    const h = location.hash.slice(1); if (TABS.some(t => t[0] === h)) { tab = h; $$('#ctTabs button').forEach(x => x.classList.toggle('on', x.dataset.t === tab)); }
    render();
  }
  const body = () => $('#ctBody');
  const src = (u, l) => `<a href="${u}" target="_blank" rel="noopener">${l} ↗</a>`;
  function render() {
    history.replaceState(null, '', '#' + tab);
    ({ 'ct-primer': primer, 'ct-geo': () => Geo.mount(body(), 'cotton'),
      'ct-aus': () => { try { typeof AusCotton !== 'undefined' ? AusCotton.mount(body()) : body().innerHTML = '<div class="card"><p class="note">Australia module not loaded.</p></div>'; } catch (e) { body().innerHTML = '<div class="card"><p class="note">Australia tab failed to load.</p></div>'; } }, 'ct-wasde': wasde, 'ct-esr': esr, 'ct-crop': cropTab,
      'ct-china': () => { try { typeof ChinaCotton !== 'undefined' ? ChinaCotton.mount(body()) : body().innerHTML = '<div class="card"><p class="note">China module not loaded.</p></div>'; } catch (e) { body().innerHTML = '<div class="card"><p class="note">China tab failed to load.</p></div>'; } }, 'ct-india': () => { try { typeof IndiaCotton !== 'undefined' ? IndiaCotton.mount(body()) : body().innerHTML = '<div class="card"><p class="note">India module not loaded.</p></div>'; } catch (e) { body().innerHTML = '<div class="card"><p class="note">India tab failed to load.</p></div>'; } }, 'ct-loan': () => { try { typeof CottonLoan !== 'undefined' ? CottonLoan.mount(body()) : body().innerHTML = '<div class="card"><p class="note">Loan module not loaded.</p></div>'; } catch (e) { body().innerHTML = '<div class="card"><p class="note">Loan tab failed to load.</p></div>'; } },
      'ct-oncall': () => frame(SITE.oncall, 'Cotton on-call', 'CFTC weekly cotton on-call: unfixed call sales and purchases by contract month, mill fixation pace and what it means for futures.'),
      'ct-basis': () => frame(SITE.crop + 'basis.html', 'Spot basis &amp; trade ideas', 'USDA spot cotton (41-4-34) minus nearby futures: seasonal pattern, current reading, what followed, and the rule-based trade ideas.'),
      'ct-ams': () => { try { AmsReview.mount(body()); } catch (e) { body().innerHTML = '<div class="card"><p class="note">AMS review failed to load.</p></div>'; } }, 'ct-flows': flows, 'ct-rv': () => RVView.mount(body(), 'CT'), 'ct-outlook': outlook, 'ct-certs': certs, 'ct-seas': () => MktStudy.mount(body(), ['CT']) })[tab]();
  }
  function primer() {
    body().innerHTML = Specs.slot('cotton') + `<div class="grid g2">
      <div class="card"><h2>ICE Cotton No. 2 (CT)</h2><div class="tbl"><table>
        <tr><td>Size</td><td class="l">50,000 lb net weight (~100 running bales)</td></tr><tr><td>Quote / tick</td><td class="l">¢/lb; 0.01¢ = $5</td></tr>
        <tr><td>Months that matter</td><td class="l">Mar, May, Jul (old crop) and Dec (new crop). October trades but is thin and is ignored here.</td></tr>
        <tr><td>Delivery</td><td class="l">Physical, by certificated warehouse receipt at Galveston, Houston, Dallas/Ft Worth, Memphis, Greenville/Spartanburg; base grade Strict Low Middling 1-1/16"</td></tr>
        <tr><td>First notice / last trade</td><td class="l">First notice 5 business days before the delivery month; last trade 17 business days before month end</td></tr></table></div>
        <h3>Calendar</h3><p>US planting Apr–Jun, bolls set Jul–Aug, harvest Sep–Dec. Marketing year Aug–Jul. Texas (≈40% of US area) decides abandonment through dryland West Texas rainfall; FSA failed acres in October understate the final number.</p></div>
      <div class="card"><h2>What moves cotton</h2><div class="tbl"><table><tr><th class="l">Driver</th><th class="l">Mechanism</th><th class="l">Where on this desk</th></tr>
        <tr><td class="l">US crop</td><td class="l">Planted area × (1 − abandonment) × yield; Texas drought sets abandonment.</td><td class="l">Crop progress, WASDE</td></tr>
        <tr><td class="l">Export demand</td><td class="l">~80% of the US crop is exported; the US competes with Brazil, Australia and Africa. India exports only when supply is well above use; China does not export.</td><td class="l">Export sales</td></tr>
        <tr><td class="l">Mill fixation</td><td class="l">Unfixed on-call sales are mills' short futures exposure: they must buy futures to fix, which supports the old-crop months into first notice.</td><td class="l">On-call</td></tr>
        <tr><td class="l">Spec positioning</td><td class="l">Managed money swings are large relative to open interest; crowded shorts fuel short-covering rallies.</td><td class="l">Futures, options &amp; COT</td></tr>
        <tr><td class="l">World balance</td><td class="l">World ex-China stocks/use sets the value of US cotton against polyester and other origins.</td><td class="l">WASDE</td></tr></table></div>
        <h3>Full dashboards</h3><p class="note">${src(SITE.wasde, 'WASDE analytics')} · ${src(SITE.esr, 'Export sales')} · ${src(SITE.crop, 'Crop progress')} · ${src(SITE.oncall, 'On-call')} · ${src(SITE.cot, 'COT desk')} · ${src(SITE.opts, 'Softs options')}</p></div></div>
      <div class="card" style="margin-top:12px"><h2>Delivery: points, quality differentials, age and storage penalties</h2>
        <p>Cotton No. 2 delivers US-grown cotton held as electronic warehouse receipts in ICE-licensed warehouses. Each bale is classed by USDA; the invoice is the notice price plus or minus the quality differentials for each bale, less penalties for cotton that has sat certificated for months.</p>
        <div class="grid g2"><div class="tbl"><table>
          <tr><td class="l"><b>Delivery points</b></td><td class="l">Galveston, Houston and Dallas/Fort Worth (Texas), Memphis (Tennessee), Greenville/Spartanburg (South Carolina), each including warehouses within 15 miles. Savannah, Georgia is added from the October 2028 expiry. The contract sets no location premium or discount between points: the difference is in each warehouse's storage and load-out tariff (Texas ports carry the highest storage caps).</td></tr>
          <tr><td class="l"><b>Basis quality</b></td><td class="l">Strict Low Middling, 1-1/16 inch staple, leaf 4, micronaire 3.5–4.9, strength 25 g/tex or more, colours 11–51 white and 12–32 light spotted. 92–108 bales of 400–650 lb, 50,000 lb net ±1%.</td></tr>
          <tr><td class="l"><b>Quality differentials</b></td><td class="l">Premiums and discounts for grade, leaf and staple are the average of USDA AMS commercial spot quotations on the sixth business day before delivery. 1-1/32 inch staple delivers at twice the quoted 1-1/16 discount. Each bale's points are netted on the invoice.</td></tr>
          <tr><td class="l"><b>Year of growth</b></td><td class="l">No penalty if delivered by 31 December of the year after the crop year; 2¢/lb in the following calendar year and another 2¢/lb for each year after.</td></tr>
          <tr><td class="l"><b>Weight date allowance</b></td><td class="l">½ lb per bale per month from the month after weighing (shrinkage), on top of the age penalty.</td></tr>
          <tr><td class="l"><b>Storage and fees</b></td><td class="l">The deliverer pays storage up to the delivery day (each warehouse's tariff, capped per delivery point); load-out, inspection ($2/bale) and certificate fees per the ICE tariff schedule.</td></tr>
          <tr><td class="l"><b>Timing</b></td><td class="l">First notice 5 business days before the first delivery day; last trading day 17 business days before month end; last notice 12 business days before month end.</td></tr></table></div>
        <div><h3>Aged cotton penalty (months certificated)</h3><div class="tbl"><table><tr><th class="l">Month after original certification</th><th class="l">Penalty, lb per bale</th></tr>
          <tr><td class="l">1–3</td><td class="l">none</td></tr><tr><td class="l">4–10</td><td class="l">3 in month 4, +3 each month (21 in month 10)</td></tr>
          <tr><td class="l">11–16</td><td class="l">25 in month 11, +4 each month (45 in month 16)</td></tr><tr><td class="l">17–22</td><td class="l">50 in month 17, +5 each month (75 in month 22)</td></tr>
          <tr><td class="l">23 on</td><td class="l">81 in month 23, +6 each month (no cap)</td></tr></table></div>
          <div class="grid g2"><label>Months certificated<br><input id="ctAge" type="number" value="10" min="0"></label><label>Price, ¢/lb<br><input id="ctPx" type="number" value="70" step="1"></label>
            <label>Average bale weight, lb<br><input id="ctBw" type="number" value="500" step="10"></label><label>Months since weighing<br><input id="ctWd" type="number" value="10" min="0"></label></div>
          <div id="ctAgeOut" style="margin-top:8px"></div></div></div>
        <div class="tbl" style="margin-top:8px"><table>
          <tr><td class="l"><b>Why it matters</b></td><td class="l">The penalty is taken as pounds off each bale, so in price terms it is (penalty lb ÷ bale weight) × the price, and it grows faster the longer cotton sits. Old certificated stock therefore delivers at a discount and tends to be tendered first, which weighs on the spot month; a fresh certification wave (new-crop cotton, strong basis elsewhere) is cheaper to deliver and can pressure the front spread too. High certificated stocks with an ageing profile are a bearish structure signal; low and fresh ones support the inverse.</td></tr>
          <tr><td class="l"><b>On-call link</b></td><td class="l">Mills fix on-call purchases against the front months; if they leave fixing late into notice period, they compete with longs who want to avoid delivery. See the On-call tab for unfixed sales by month.</td></tr></table></div>
        <p class="note">From the ICE Cotton No. 2 Deliverer's &amp; Receiver's Guide, contract specifications and tariff schedule. Penalties and tariffs change; check the current ICE documents before acting.</p></div>`;
    const kpi = (lab, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${lab}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
    const ct = () => {
      const m = Math.max(0, +$('#ctAge').value || 0), px = +$('#ctPx').value || 0, bw = +$('#ctBw').value || 500, wd = Math.max(0, +$('#ctWd').value || 0);
      let lb = 0;
      if (m >= 4 && m <= 10) lb = 3 * (m - 3); else if (m >= 11 && m <= 16) lb = 25 + 4 * (m - 11); else if (m >= 17 && m <= 22) lb = 50 + 5 * (m - 17); else if (m >= 23) lb = 81 + 6 * (m - 23);
      const wlb = 0.5 * wd, pen = lb / bw * px, wpen = wlb / bw * px;
      $('#ctAgeOut').innerHTML = `<div class="grid g4">${kpi('Age penalty', fmt(lb, 0) + ' lb/bale', `month ${m} of certification`)}${kpi('In price', fmt(pen, 2) + '¢/lb', `${fmt(100 * lb / bw, 1)}% of value at ${fmt(px, 0)}¢`)}
        ${kpi('Weight allowance', fmt(wlb, 1) + ' lb/bale', fmt(wpen, 2) + '¢/lb')}${kpi('Total', fmt(pen + wpen, 2) + '¢/lb', `≈ $${fmt((pen + wpen) * 500, 0)} per contract (50,000 lb)`)}</div>`;
    };
    ['#ctAge', '#ctPx', '#ctBw', '#ctWd'].forEach(id => $(id).addEventListener('input', ct)); ct();
  }
  async function wasde() {
    body().innerHTML = '<div class="card"><p class="note">Loading WASDE analysis…</p></div>';
    const idx = await getJSON('data/grains/derived/wasde_brief/index.json').catch(() => null);
    if (!idx) { body().innerHTML = '<div class="card"><p class="note">WASDE analysis not built yet.</p></div>'; return; }
    WasdeView.mount(body(), { base: 'data/grains/derived/wasde_brief/', index: idx, key: 'cotton' });
    body().insertAdjacentHTML('beforeend', `<p class="note">Cotton brief, factor read and month-history from ${src(SITE.wasde, 'BMR-Com WASDE analytics')} (crop ratings, Texas drought, export sales, Brazil, on-call, COT); balance sheets and revision paths built here.</p>`);
  }
  async function esr() {
    body().innerHTML = '<div class="card"><p class="note">Loading export sales…</p></div>';
    // two sources: the separate cotton export-sales repo and the desk's own Thursday run; show whichever has the later week
    const [X, OWN] = await Promise.all([fetch(SITE.esr + 'data/brief.json?t=' + Date.now()).then(r => r.json()).catch(() => null),
      getJSON('data/grains/derived/esr_brief.json').catch(() => null)]);
    const own = OWN && OWN.commodities.find(c => c.key === 'cotton');
    const wk = d => (d?.commodities || []).map(c => c.week || '').sort().pop() || '';
    const useOwn = own && (!X || (own.week || '') >= wk(X));   // same week: the desk's brief has the fuller destination and Brazil analysis
    const D = useOwn ? { generated: OWN.generated, commodities: [own] } : X;
    if (!D) { body().innerHTML = `<div class="card"><p class="note">Could not load the cotton export sales brief. Open ${src(SITE.esr, 'the export sales page')}.</p></div>`; return; }
    ESR.mount(body(), D, { name: 'Cotton' });
    // China yarn note: text only, from the China module; if it is missing or stale nothing else on this page changes
    try { const N = await getJSON('data/china/esr_note.json').catch(() => null);
      if (N?.items?.length) body().insertAdjacentHTML('beforeend', `<div class="card" style="margin-top:12px"><h2>China's yarn imports and demand in its suppliers (as of ${N.asof})</h2><p>${N.text}</p><ul>${N.items.map(x => `<li>${x}</li>`).join('')}</ul><p class="note">${N.caveat} Built ${N.generated}; see Cotton → China.</p></div>`);
    } catch (e) { /* ignore */ }
    body().insertAdjacentHTML('beforeend', `<p class="note" style="margin:4px 2px">${useOwn ? `Desk's own Thursday export-sales run (upland + Pima, USDA FAS), week ending ${own.week} · ${OWN.generated}${X ? ` · the ${src(SITE.esr, 'cotton export sales page')} has week ending ${wk(X) || '?'}` : ''}` : `From ${src(SITE.esr, 'BMR-Com US cotton export sales')} (upland + Pima, USDA FAS) · ${D.generated}`}.</p>`);
  }
  // Crop progress tab: BMR-Com crop projection card (output of the cotton-crop-progress repo) above the live dashboard
  function cropTab() {
    frame(SITE.crop, 'Cotton crop progress', 'NASS crop progress and condition, crop projection, ginning and classing pace, grades and tenderability, FSA acreage.');
    const host = document.createElement('div');
    host.className = 'card'; host.style.marginBottom = '8px';
    host.innerHTML = '<p class="note">Loading the crop projection…</p>';
    body().insertBefore(host, body().children[1] || null);
    fetch(SITE.crop + 'data/crop_projection.json?' + Date.now()).then(r => r.ok ? r.json() : Promise.reject(r.status)).then(P => {
      const f = x => x.toFixed(2), pc = x => Math.round(x * 100) + '%';
      const u = P.us_upland, a = P.us_all, t = P.texas, U = P.usda || {};
      const row = (lab, x, us) => `<tr><td class="l">${lab}</td><td class="n"><b>${f(x.central)}</b></td><td class="n">${f(x.lo68)}–${f(x.hi68)}</td><td class="n">${f(x.lo95)}–${f(x.hi95)}</td><td class="n">${f(x.lo99)}–${f(x.hi99)}</td><td class="n">${us != null ? f(us) : '–'}</td></tr>`;
      host.innerHTML = `<h2>BMR-Com crop projection <span class="note">as of ${P.asof} · ${P.unit}</span></h2>
        <div class="tbl"><table><tr><th class="l"></th><th>Projection</th><th>68%</th><th>95%</th><th>99%</th><th>USDA ${U.report || ''}</th></tr>
        ${row('US all cotton', a, U.us_all)}${row('US upland', u, U.us_upland)}${row('Texas upland', t, U.tx)}</table></div>
        ${(P.states || []).length ? `<details style="margin:8px 0"><summary>By state (upland)</summary><div class="tbl"><table><tr><th class="l">State</th><th>Projection</th><th>68%</th><th>95%</th><th>99%</th><th>USDA</th></tr>
          ${P.states.map(x => row(x.name, x, x.usda)).join('')}</table></div></details>` : ''}
        ${P.conditional ? (() => { const C = P.conditional, ha = C.tx_harvested_acres, yd = C.tx_yield; return `<p><b>Conditional view</b> (Texas built as harvested acres × yield): abandonment ${pc(C.tx_abandonment.central)} of ${f(C.tx_planted_acres || 0)}m planted leaves ${ha ? f(ha.central) : '–'}m harvested acres (95% ${ha ? f(ha.lo95) + '–' + f(ha.hi95) : '–'}m); at USDA's ${yd ? yd.central : '–'} lb (95% ${yd ? yd.lo95 + '–' + yd.hi95 : '–'}) Texas is ${f(C.texas.central)}m (95% ${f(C.texas.lo95)}–${f(C.texas.hi95)}m). US upland ${f(C.us_upland.central)}m (95% ${f(C.us_upland.lo95)}–${f(C.us_upland.hi95)}m), all cotton ${f(C.us_all.central)}m.${C.analog ? ` Past seasons with similar Texas ratings ended at ${pc(C.analog.min)}–${pc(C.analog.max)} abandonment.` : ''}</p>`; })() : ''}
        <p>Texas final abandonment projected at <b>${pc(t.abandonment.central)}</b> (95% ${pc(t.abandonment.lo95)}–${pc(t.abandonment.hi95)}) against ${pc(U.tx_abandonment || 0)} in USDA's numbers.</p>
        ${P.texas_regions ? `<p>${P.texas_regions}</p>` : ''}${(P.notes || []).map(n => `<p class="note">${n}</p>`).join('')}
        <p class="note">Inputs through: ${Object.entries(P.inputs_through || {}).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · ')}. Built from ${(P.variables || []).length} public USDA data sets; see the ${src(SITE.crop, 'crop progress page')}.</p>`;
    }).catch(() => { host.innerHTML = '<p class="note">Crop projection not available yet.</p>'; });
  }
  function frame(u, title, what) {
    body().innerHTML = `<div class="card" style="margin-bottom:8px"><h2 style="display:inline">${title}</h2> <span class="note">${what} Live view of the ${src(u, 'full dashboard')}.</span></div>
      <iframe class="ctframe" src="${u}" title="${title}" loading="lazy" referrerpolicy="no-referrer" sandbox="allow-scripts allow-same-origin allow-popups"></iframe>`;
  }
  function flows() {
    body().innerHTML = `<div id="ctCot"></div><div class="card" style="margin-top:12px"><h2>Options and index traders</h2>
      <p class="note">Options flow, vol surface and skew: ${src(SITE.opts, 'softs options terminal')}. Index-trader (CIT) positions and the full COT read: ${src(SITE.cot, 'COT positioning desk')}.</p></div>`;
    CotDesk.mount($('#ctCot'), ['CT']);
  }
  // Certs & quality premiums. The ICE grid is public USDA data (data/cotton/ice_diffs.json). ICE certificated-stock files
  // are read in the viewer's browser only (file picker, kept in this browser's localStorage) and never stored in the repo.
  async function certs() {
    const D = await getJSON('data/cotton/ice_diffs.json').catch(() => null);
    const kp = (lab, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${lab}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
    const sg = (v, d = 0) => v == null || isNaN(v) ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(v), d);
    const LS = { get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} }, del: k => { try { localStorage.removeItem(k); } catch (e) {} } };
    const gk = (c, l, st) => `${c}|${['1', '2'].includes(String(l)) ? '1 & 2' : l}|${String(st).replace('+', '')}`;
    const pts = (G, c, l, st) => G ? G[gk(c, l, st)] : undefined;
    if (!D) { body().innerHTML = '<div class="card"><p class="note">The quality-premium grid loads after the first cotton-diffs data run.</p></div>'; return; }
    const G = D.grid, P1 = D.prev['1m']?.grid, P1y = D.prev['1y']?.grid;
    const rows = []; D.colors.forEach(c => D.leaves.forEach(l => { if (D.staples.some(st => G[`${c}|${l}|${st}`] != null)) rows.push([c, l]); }));
    const strn = D.strength[0];
    body().innerHTML = `<div class="grid g4">
        ${kp('Grid date', D.date, 'USDA spot quotations, ICE tenderable differences')}
        ${kp('31-3-36', sg(pts(G, '31', '3', '36')) + ' pts', `${sg(pts(G, '31', '3', '36') - pts(P1, '31', '3', '36'))} on the month, ${sg(pts(G, '31', '3', '36') - pts(P1y, '31', '3', '36'))} on the year`)}
        ${kp('21-2-37', sg(pts(G, '21', '2', '37')) + ' pts', `${sg(pts(G, '21', '2', '37') - pts(P1, '21', '2', '37'))} on the month`)}
        ${kp('Strength ' + (strn?.range || ''), sg(strn?.points) + ' pts', 'GPT 25.0–25.9; below 25 not deliverable')}</div>
      <div class="card" style="margin-top:12px"><h2>ICE Cotton No. 2 premiums and discounts <span class="note">points (100 = 1¢/lb) against 41-4-34</span></h2>
        <div class="seg" style="display:flex;gap:6px;margin:0 0 8px"><label class="note">Show <select id="ctGridMode"><option value="lvl">level</option><option value="m">change, 1 month</option><option value="y">change, 1 year</option></select></label></div>
        <div class="tbl" id="ctGrid"></div>
        <p class="note">Each delivered bale is invoiced at the notice price plus or minus these differences for its color, leaf and staple (plus the strength discount if GPT is 25.0–25.9). They are the average of the designated spot markets' quoted differences, set on the sixth business day before delivery. Leaf 1 and 2 share one value; staple 37 covers 37 and longer.</p></div>
      <div class="card" style="margin-top:12px"><h2>Premium history, key qualities</h2><div style="position:relative;height:260px"><canvas id="ctDiffH"></canvas></div></div>
      <div class="card" style="margin-top:12px"><h2>Certs on board <span class="note">ICE Report Center files (Certified Stock Reports – Cotton)</span></h2>
        <p class="note">Shows the latest ICE files stored on the desk (data/cotton/ice). To look at a newer file before it is added, pick it below: it is read in this browser and replaces the stored one until you choose "Forget loaded files".</p>
        <div class="grid g3"><label>Certified stock (by delivery point)<br><input type="file" id="ctFStock" accept=".csv,text/csv"></label><label>Stock by warehouse<br><input type="file" id="ctFWh" accept=".csv,text/csv"></label><label>Strength (GPT) by delivery point<br><input type="file" id="ctFStr" accept=".csv,text/csv"></label><label>Year of growth<br><input type="file" id="ctFYog" accept=".csv,text/csv"></label><label>Grade / staple (ICE updates the full detail on Mondays)<br><input type="file" id="ctFGrade" accept=".csv,text/csv"></label></div>
        <p class="note" style="margin-top:6px"><a href="#" id="ctFClear">Forget loaded files (back to the stored ones)</a></p>
        <div id="ctCertOut" style="margin-top:10px"></div></div>`;
    const drawGrid = mode => {
      const ref = mode === 'm' ? P1 : mode === 'y' ? P1y : null;
      const cellv = (c, l, st) => { const v = G[`${c}|${l}|${st}`]; if (v == null) return null; return ref ? (ref[`${c}|${l}|${st}`] == null ? null : v - ref[`${c}|${l}|${st}`]) : v; };
      const bg = v => v == null ? '' : `background:${v >= 0 ? `rgba(47,107,58,${Math.min(0.55, Math.abs(v) / (ref ? 300 : 800))})` : `rgba(192,57,43,${Math.min(0.55, Math.abs(v) / (ref ? 300 : 800))})`}`;
      $('#ctGrid').innerHTML = `<table><tr><th class="l">Color</th><th class="l">Leaf</th>${D.staples.map(st => `<th>${st}${st === '37' ? '+' : ''}</th>`).join('')}</tr>${rows.map(([c, l]) => `<tr><td class="l">${c}</td><td class="l">${l}</td>${D.staples.map(st => { const v = cellv(c, l, st); return `<td class="n" style="${bg(v)}">${v == null ? '' : sg(v)}</td>`; }).join('')}</tr>`).join('')}</table>`;
    };
    drawGrid('lvl'); $('#ctGridMode').onchange = e => drawGrid(e.target.value);
    const H = D.history, ks = Object.keys(H), lab = H[ks[0]].dates;
    chart('ctDiffH', { type: 'line', data: { labels: lab, datasets: ks.map((k, i) => ({ label: k, data: lab.map(d => { const j = H[k].dates.indexOf(d); return j < 0 ? null : H[k].points[j]; }), borderColor: ['#7f8c8d', '#2c6fbb', '#2f6b3a', '#7d3c98', '#d68910', '#c0392b', '#16a085', '#34495e'][i % 8], pointRadius: 0, borderWidth: 1.4, spanGaps: true })) },
      options: { scales: { y: { title: { display: true, text: 'points vs 41-4-34' } } } } });

    // ----- private ICE files -----
    let WM = null;
    try { const [csv, rules] = await Promise.all([fetch('data/cotton/warehouse_map.csv').then(r => r.text()), getJSON('data/cotton/warehouse_map_rules.json')]);
      const L = csv.trim().split(/\r?\n/).map(l => { const o = []; let c = '', q = false; for (const ch of l) { if (ch === '"') q = !q; else if (ch === ',' && !q) { o.push(c); c = ''; } else c += ch; } o.push(c); return o; });
      const hd = L[0]; WM = { rows: L.slice(1).map(r => Object.fromEntries(hd.map((k, i) => [k, r[i] || '']))), rules: rules.owner_rules }; } catch (e) { WM = null; }
    const REPO = {};
    try { const Lt = await getJSON('data/cotton/ice/latest.json');
      try { REPO.ewr = await getJSON('data/cotton/ewr/latest.json'); } catch (e) {}
      try { REPO.cfr = await getJSON('data/cotton/cfr_compare.json'); } catch (e) {}
      try { REPO.cal = await getJSON('data/specs/calendar.json'); } catch (e) {}
      try { const L2 = await getJSON('data/cotton/ice/latest.json'); REPO.whHist = await Promise.all((L2.warehouse_history || []).map(async x => { const t = await fetch(x.path).then(r => r.text()); const R = t.trim().split(/\r?\n/).map(l => l.split(',')), h = R[0].map(v => v.toLowerCase()), j = h.findIndex(v => /receipt|bales|stock/.test(v)); return { date: x.date, total: R.slice(1).reduce((a, r) => a + (+r[r.length - 1] || 0), 0) }; })); } catch (e) { REPO.whHist = []; }
      try { REPO.tariffTxt = await fetch('data/cotton/ref/ice_tariffs_2026-27.csv').then(r => r.ok ? r.text() : null); } catch (e) {}
      try { const T = await getJSON('data/technicals/CT.json'); REPO.px = Object.fromEntries((T.series || []).map(x => [x.ticker, { label: x.label, close: x.bars[x.bars.length - 1][4], date: x.bars[x.bars.length - 1][0] }])); } catch (e) {}
      await Promise.all([['ctIceStock', 'stock'], ['ctIceGrade', 'grade'], ['ctIceWh', 'warehouse'], ['ctIceWhPrev', 'warehouse_prev'], ['ctIceStr', 'strength'], ['ctIceYog', 'year_of_growth']].map(async ([k, f]) => { if (Lt[f]) { REPO[k] = await fetch(Lt[f]).then(r => r.ok ? r.text() : null); REPO[k + 'Date'] = Lt[f + '_date']; } })); } catch (e) {}
    const got = k => LS.get(k) ?? REPO[k] ?? null;
    const parseCSV = t => t.trim().split(/\r?\n/).map(line => { const out = []; let cur = '', q = false; for (const ch of line) { if (ch === '"') q = !q; else if (ch === ',' && !q) { out.push(cur); cur = ''; } else cur += ch; } out.push(cur); return out.map(x => x.trim()); });
    // Stop December, hold, redeliver against March: what it costs, against the Mar/Dec spread (ICE Cotton No. 2 rules)
    const CF = { st: LS.get('ctCarrySt') != null ? +LS.get('ctCarrySt') : null, ir: +(LS.get('ctCarryIr') || 5.0), bw: 500 };
    // storage rate weighted by the certs each warehouse holds (ICE 2026/27 tariff sheet, cents per bale per month)
    const stWeighted = () => { const tt = REPO.tariffTxt, wh = got('ctIceWh'); if (!tt || !wh) return null; const T = parseCSV(tt), th = T[0], iC = th.indexOf('code'), iS = th.indexOf('storage_c_per_bale_month');
      const rate = Object.fromEntries(T.slice(1).map(r => [r[iC], +r[iS]])), R = parseCSV(wh), h = R[0].map(x => x.toLowerCase()), jC = h.findIndex(x => /number|code/.test(x)), jB = h.findIndex(x => /receipt|bales|stock/.test(x));
      let n = 0, v = 0; R.slice(1).forEach(r => { const b = +r[jB] || 0, c = rate[r[jC]]; if (b && c) { n += b; v += b * c; } }); return n ? v / n / 100 : null; };
    // Delivery pair: the spot (front) contract still open and the next one it rolls into (October is skipped).
    const MON = { F: 1, G: 2, H: 3, J: 4, K: 5, M: 6, N: 7, Q: 8, U: 9, V: 10, X: 11, Z: 12 }, MN = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const ym = c => ({ y: +c.slice(3), m: MON[c[2]] }), mdiff = (a, b) => (b.y - a.y) * 12 + (b.m - a.m), clab = c => { const q = ym(c); return MN[q.m] + ' ' + String(q.y).slice(2); };
    function pair() {
      const C = ((((REPO.cal || {}).markets || {}).CT || {}).contracts || []).filter(x => !/^CTV/.test(x.contract)), today = new Date().toISOString().slice(0, 10), px = REPO.px || {};
      const i = C.findIndex(x => x.ltd >= today); if (i < 0 || !C[i + 1]) return null;
      const f = C[i].contract, n = C[i + 1].contract; if (!px[f] || !px[n]) return null;
      return { f, n, fl: clab(f), nl: clab(n), months: mdiff(ym(f), ym(n)), F: px[f], N: px[n], fq: ym(f), nq: ym(n) };
    }
    // ICE over-age allowance, lb/bale, by months after the month of original certification
    const ageSched = m => m < 4 ? 0 : m <= 10 ? 3 * (m - 3) : m <= 16 ? 21 + 4 * (m - 10) : m <= 22 ? 45 + 5 * (m - 16) : 75 + 6 * (m - 22);
    // certification-month cohorts from the weekly warehouse reports: increases are new certs (dated to the week before the
    // report), decreases come out of the oldest cohort first
    function cohorts() {
      const H = (REPO.whHist || []).slice().sort((a, b) => a.date < b.date ? -1 : 1), co = []; let prev = 0;
      H.forEach(x => { const d = new Date(x.date); d.setDate(d.getDate() - 7); const q = { y: d.getFullYear(), m: d.getMonth() + 1 };
        if (x.total > prev) co.push({ q, n: x.total - prev }); else { let out = prev - x.total; for (const c of co) { const t = Math.min(c.n, out); c.n -= t; out -= t; if (!out) break; } }
        prev = x.total; });
      return co.filter(c => c.n > 0);
    }
    function carry(premPts, S) {
      const P = pair(); if (!P) return '';
      const sw = stWeighted(), st = CF.st != null ? CF.st : (sw || 5.0);
      const months = P.months, dec = P.F.close, mar = P.N.close, spread = mar - dec, inv = dec + premPts / 100, invN = mar + premPts / 100;
      const storage = st * months / CF.bw * 100, interest = inv * CF.ir / 100 * months / 12;
      const co = cohorts(), T = co.reduce((a, c) => a + c.n, 0) || 1;
      const ageF = co.reduce((a, c) => a + c.n * ageSched(mdiff(c.q, P.fq)), 0) / T, ageN = co.reduce((a, c) => a + c.n * ageSched(mdiff(c.q, P.nq)), 0) / T;
      const ageLb = ageN - ageF, agePen = ageLb / CF.bw * invN;                  // the receiver is allowed age at the front delivery, allows age at the next
      const wda = 0.5 * months / CF.bw * invN;
      const yogPen = (crop, yr) => Math.max(0, 2 * (yr - crop - 1));
      const YG = S.yogCrops || [], YT = YG.reduce((a, x) => a + x.n, 0) || 1;
      const yog = YG.reduce((a, x) => a + x.n * (yogPen(x.y, P.nq.y) - yogPen(x.y, P.fq.y)), 0) / YT;
      const yogShare = YG.filter(x => yogPen(x.y, P.nq.y) > yogPen(x.y, P.fq.y)).reduce((a, x) => a + x.n, 0) / YT;
      const coTxt = co.map(c => `${MN[c.q.m]} ${fmt(c.n / T * 100, 0)}%`).join(', ');
      const tot = storage + interest + agePen + wda + yog, gap = spread - tot;
      EC.c = { P, z: P.F, h: P.N, dec, mar, spread, st, sw, storage, interest, agePen, ageLb, coTxt, wda, yog, yogShare, tot, gap, inv, months };
      return '';
    }
    // Take December delivery, decertify and ship: the receiver pays storage until the bales load out (about two months
    // in season) and pays the ICE premium, against buying the same qualities in the spot market (AMS spot quotations).
    const MKT = { Galveston: 'East Texas - South Texas', Houston: 'East Texas - South Texas', Dallas: 'West Texas - Kansas - Oklahoma', Memphis: 'North Delta', Greenville: 'Southeast' };
    const DC = { m: +(LS.get('ctDecM') || 2) };
    function decert(premPts, S) {
      const PP = pair(), z = PP && PP.F, h = PP && PP.N, B = D.basis, MG = (D.markets || {}).grids; if (!z || !B || !MG || !S.cells || !S.dp) return '';
      const mk = (c, l, st) => `${c === '11' || c === '21' ? '11 & 21' : c === '12' || c === '22' ? '12 & 22' : c === '13' || c === '23' ? '13 & 23' : c}|${l === '1' || l === '2' ? '1 & 2' : l}|${String(st).replace('+', '')}`;
      const dps = Object.entries(S.dp).filter(([, v]) => v.n), T = dps.reduce((a, [, v]) => a + v.n, 0); if (!T) return '';
      const N = S.cells.reduce((a, x) => a + x.n, 0); let miss = 0;
      const rows = dps.map(([dp, v]) => { const m = MKT[dp] || 'US Average', g = MG[m] || {}, b = (B.markets[m] || B.markets['US Average'] || {});
        let pts = 0; S.cells.forEach(x => { const q = g[mk(x.c, x.l, x.s)]; if (q == null) { miss += x.n * v.n / T; pts += x.n * x.p; } else pts += x.n * q; });
        const diff = pts / (N || 1), adj = b.basis_month && h && new RegExp('^' + PP.nl.slice(0, 3), 'i').test(b.basis_month) ? (h.close - z.close) * 100 : 0, basis = (b.basis_41_4_34 || 0) + adj;
        return { dp, m, n: v.n, w: v.n / T, diff, basis, val: basis + diff, bm: b.basis_month }; });
      const val = rows.reduce((a, r) => a + r.w * r.val, 0), over = (premPts - val) / 100;
      const stw = (typeof stWeighted === 'function' && stWeighted()) || 5.0, st = CF.st != null ? CF.st : stw, inv = z.close + premPts / 100;
      const storage = st * DC.m / CF.bw * 100, fin = inv * CF.ir / 100 * DC.m / 12, tot = over + storage + fin;
      EC.d = { rows, val, over, storage, fin, tot, st, inv, B, miss, carry: storage + fin };
      return '';
    }
    // one table: premium/discount kept separate from the carry (storage + financing), for the two things a long can do with December certs
    const EC = {};
    function econ(premPts) {
      const c = EC.c, d = EC.d; if (!c) return '';
      const f = v => v == null || isNaN(v) ? '–' : v.toFixed(2), P = premPts / 100;
      const carryR = c.storage + c.interest, pen = c.agePen + c.wda + c.yog, needR = carryR + pen, gapR = c.spread - needR;
      const carryD = d ? d.carry : null;
      const row = (lab, a, b, note) => `<tr><td class="l">${lab}</td><td class="n">${a}</td><td class="n">${b}</td><td class="l note">${note || ''}</td></tr>`;
      return `<h3 style="margin-top:14px">What ${c.P.fl} delivery costs a long <span class="note">futures ${c.z.date}: ${c.P.fl} ${c.dec.toFixed(2)}, ${c.P.nl} ${c.mar.toFixed(2)}; ICE grid ${D.date}</span></h3>
        <div class="grid g4" style="margin:6px 0"><label>Storage, $/bale/month <input id="ctCSt" type="number" step="0.05" value="${c.st.toFixed(2)}" style="width:75px"></label><label>Financing, %/yr <input id="ctCIr" type="number" step="0.25" value="${CF.ir}" style="width:70px"></label><label>Months to load-out (decert) <input id="ctDecMo" type="number" step="0.5" min="0" value="${DC.m}" style="width:60px"></label><span class="note">${CF.st != null ? 'your storage rate' : c.sw ? 'storage: ICE 2026/27 tariffs weighted by where the certs sit' : 'assumed storage rate'}</span></div>
        <div class="tbl"><table><tr><th class="l">¢/lb</th><th>Hold, redeliver in ${c.P.nl} (${c.months} mo)</th><th>Decertify and ship (${DC.m} mo)</th><th class="l">Basis</th></tr>
        <tr><td class="l" colspan="4"><b>Carry</b></td></tr>
        ${row('Storage', f(c.storage), d ? f(d.storage) : '–', `$${c.st.toFixed(2)}/bale/month ÷ ${CF.bw} lb`)}
        ${row('Financing', f(c.interest), d ? f(d.fin) : '–', `${CF.ir}% a year on the ${c.inv.toFixed(2)}¢ invoice`)}
        ${row('Over-age allowance', f(c.agePen), '–', `${c.ageLb.toFixed(1)} lb/bale more at a ${c.P.nl} delivery than at ${c.P.fl} (certified: ${c.coTxt || 'n/a'}); ICE schedule from the 4th month after certification`)}
        ${row('Weight-date allowance', f(c.wda), '–', `½ lb/bale for each of the ${c.months} extra months`)}
        ${row('Year of growth', f(c.yog), '–', c.yog ? `2¢/lb more on the ${fmt(c.yogShare * 100, 1)}% of bales whose penalty steps up between the two deliveries` : 'no step-up between the two deliveries')}
        ${row('<b>Breakeven carry</b>', `<b>${f(needR)}</b> <span class="note">${c.P.nl} over ${c.P.fl}</span>`, `<b>${d ? f(carryD) : '–'}</b> <span class="note">to load-out</span>`, `Redeliver: what ${c.P.nl} has to pay over ${c.P.fl}. Decert: the cost of holding the bales until they leave the warehouse`)}
        ${row('Market now', `${f(c.spread)} <span class="note">${c.P.nl} − ${c.P.fl}</span>`, `${f(c.spread)} <span class="note">carry the market pays</span>`, `Decert: taking ${c.P.fl.slice(0, 3)} cotton instead of rolling to ${c.P.nl.slice(0, 3)} buys it ${f(c.spread)}¢ cheaper`)}
        ${row('<b>Carry earned less carry cost</b>', `<b class="${gapR < 0 ? 'dn' : 'up'}">${sg(gapR, 2)}</b>`, d ? `<b class="${c.spread - carryD < 0 ? 'dn' : 'up'}">${sg(c.spread - carryD, 2)}</b>` : '–', `redeliver: if the ICE grid premium in ${c.P.nl.slice(0, 3)} is the same as today`)}
        <tr><td class="l" colspan="4"><b>Premium / discount</b> <span class="note">kept separate: the receiver pays it now; what comes back is unknown</span></td></tr>
        ${row('ICE premium paid on the certs', sg(P, 2), sg(P, 2), `grade, staple and strength of the certs on board, ${sg(premPts)} pts at the ${D.date} grid`)}
        ${row('Same qualities in the physical market', '–', d ? sg(d.val / 100, 2) : '–', d ? `AMS Texas spot quotes vs ${c.P.fl.slice(0, 3)} (${d.B.date})` : '')}
        ${row('Premium paid over the physical market', '–', d ? sg(P - d.val / 100, 2) : '–', '')}
        <tr><td class="l" colspan="4"><b>Net</b></td></tr>
        ${row('<b>Net advantage (+) / disadvantage (−)</b>', `<b class="${gapR < 0 ? 'dn' : 'up'}">${sg(gapR, 2)}</b>`, d ? `<b class="${(c.spread - carryD) - (P - d.val / 100) < 0 ? 'dn' : 'up'}">${sg((c.spread - carryD) - (P - d.val / 100), 2)}</b>` : '–', 'decert: carry earned less carry cost, less the premium paid over the physical market')}
        ${row('<b>Breakeven</b>', `<b>${f(needR)}</b> <span class="note">${c.P.nl.slice(0, 3)} − ${c.P.fl.slice(0, 3)} needed, or ${sg(P - gapR, 2)} on the ${c.P.nl.slice(0, 3)} grid</span>`, d ? `<b>${f(carryD + P - d.val / 100)}</b> <span class="note">${c.P.nl.slice(0, 3)} − ${c.P.fl.slice(0, 3)} needed, or physical ${sg(P + carryD - c.spread, 2)} over ${c.P.nl.slice(0, 3)}</span>` : '–', 'decert: the spread has to cover carry to load-out plus the premium paid over the physical market')}
        </table></div>
        <p class="note">Rules: ICE Cotton No. 2 (deliverer pays storage up to delivery and load-out to car/truck; receiver pays storage after; over-age allowance from the 4th month after the month of certification; ½ lb/bale/month weight-date allowance; 2¢/lb year-of-growth penalty from 1 January on older crop).${d ? ` For reference, AMS spot quotations on ${d.B.date} put the same qualities at ${sg(d.val)} pts vs ${c.P.fl} in the Texas markets (base 41-4-34 ${sg(d.rows.reduce((a, r) => a + r.w * r.basis, 0))} pts, quality differences ${sg(d.rows.reduce((a, r) => a + r.w * r.diff, 0))} pts); what a buyer actually pays for high grades can differ.` : ''}</p>`;
    }
    // Plain-language read of the delivery numbers, regenerated from the same inputs
    function brief(premPts) {
      const c = EC.c, d = EC.d, C = REPO.cfr; if (!c) return '';
      const f = v => v.toFixed(2), P = premPts / 100, fl = c.P.fl, nl = c.P.nl, f3 = fl.slice(0, 3), n3 = nl.slice(0, 3);
      const needR = c.storage + c.interest + c.agePen + c.wda + c.yog, gapR = c.spread - needR, payR = gapR >= 0;
      const carryD = d ? d.carry : null, needD = d ? P + carryD : null, spotD = d ? d.val / 100 : null, payD = d ? spotD >= needD : false;
      const best = C && C.rows && C.rows.length ? C.rows.slice().sort((a, b) => b.basis - a.basis)[0] : null;
      const cfrGap = best ? [C.cert_basis[0] - best.basis, C.cert_basis[1] - best.basis] : null;
      const payD2 = d ? ((c.spread - carryD) - (P - spotD)) >= 0 : false; const verdict = payR || payD2 ? `<b class="up">Taking ${f3} delivery can pay</b>` : `<b class="dn">Taking ${f3} delivery does not pay at today's prices</b>`;
      const li = [];
      li.push(`<b>Redeliver against ${n3}.</b> Holding the certs ${c.months} months costs <b>${f(needR)}¢</b>: storage and financing ${f(c.storage + c.interest)}¢ plus delivery penalties ${f(c.agePen + c.wda + c.yog)}¢. ${n3} is ${f(c.spread)}¢ over ${f3}, ${payR ? `<b>${f(gapR)}¢ more than full carry</b>, so stopping and redelivering earns money` : `<b>${f(-gapR)}¢ short of full carry</b>`}. It makes sense once ${nl}/${fl} reaches <b>${f(needR)}¢</b> (${f3} at or below ${f(c.mar - needR)} with ${n3} at ${f(c.mar)}), or if the ${n3} ICE grid pays at least ${sg(P * 100 - gapR * 100)} pts on these qualities against ${sg(premPts)} today.`);
      const netD = d ? (c.spread - carryD) - (P - spotD) : null;
      if (d) li.push(`<b>Decertify and sell.</b> Taking ${f3} cotton instead of rolling to ${n3} buys it ${f(c.spread)}¢ cheaper, against ${f(carryD)}¢ of storage and financing for ${DC.m} months to load-out: <b>${sg(c.spread - carryD, 2)}¢ net carry</b>. But the ICE premium on the certs (${sg(P, 2)}¢) is ${f(P - spotD)}¢ more than the physical market pays for the same grades (${sg(spotD, 2)}¢), so the effective ${netD >= 0 ? 'advantage' : 'cost'} is <b>${f(Math.abs(netD))}¢</b>. It makes sense once ${n3}/${f3} reaches <b>${f(carryD + P - spotD)}¢</b>, or the physical basis for these grades reaches ${sg(P + carryD - c.spread, 2)}¢ over ${n3}.`);
      const adjC = d ? Math.round((c.spread - carryD) * 100) : 0;
      if (best) li.push(`<b>Export.</b> Priced CFR Far East, and allowing for the net carry, the delivered certs come to ${sg(C.cert_basis[0] - adjC)} to ${sg(C.cert_basis[1] - adjC)} pts over Dec (quotes of ${C.asof}), against ${sg(best.basis)} for ${best.origin}, the highest high-grade quote: ${fmt(cfrGap[0] - adjC, 0)}–${fmt(cfrGap[1] - adjC, 0)} pts too dear.`);
      li.push(payR || payD2 ? `<b>For the spread:</b> with at least one route paying, longs can stop certs, which supports ${f3} against ${n3}.` : `<b>For the spread:</b> no route pays, so longs roll rather than stop. Certs stay with the deliverers, which keeps ${f3} under pressure against ${n3} until the spread widens toward ${f(needR)}¢.`);
      return `<div class="card" style="margin:0 0 12px;border-left:4px solid var(--accent, #2f6db3)"><h3 style="margin-top:0">${verdict}</h3><ul style="margin:0;padding-left:18px">${li.map(x => `<li style="margin:4px 0">${x}</li>`).join('')}</ul>
        <p class="note" style="margin-bottom:0">Prices ${c.z.date}; ICE grid ${D.date}; certs ${got('ctIceWhDate') || got('ctIceGradeDate') || ''}. Updates with each certs upload, the daily grid and prices.</p></div>`;
    }
    // Final output only: certs taken on December delivery, priced CFR Far East, against other origins' quotes (all vs December)
    function cfrOut() {
      const C0 = REPO.cfr; if (!C0) return '';
      const adj = EC.c && EC.d ? Math.round((EC.c.spread - EC.d.carry) * 100) : 0, C = { ...C0, cert_basis: C0.cert_basis.map(v => v - adj), rows: C0.rows.map(r => ({ ...r, gap: r.gap.map(g => g - adj) })) };
      return `<h3 style="margin-top:14px">December certs vs other origins, CFR Far East <span class="note">basis in points over December futures (${C.dec.toFixed(2)}), quotes of ${C.asof}</span></h3>
        <div class="tbl"><table><tr><th class="l">CFR Far East, Nov/Dec shipment</th><th>Basis vs Dec</th><th>Certs over it</th></tr>
        <tr><td class="l"><b>Certs taken on December delivery, priced CFR</b></td><td class="n"><b>+${fmt(C.cert_basis[0], 0)} to +${fmt(C.cert_basis[1], 0)}</b></td><td></td></tr>
        ${C.rows.map(r => `<tr><td class="l">${r.origin}</td><td class="n">+${fmt(r.basis, 0)}</td><td class="n ${r.gap[0] > 0 ? 'dn' : 'up'}">+${fmt(r.gap[0], 0)} to +${fmt(r.gap[1], 0)}</td></tr>`).join('')}</table></div>
        <p class="note">${adj ? `Certs include the carry the spread pays over the cost of holding to load-out (${sg(adj)} pts). ` : ''}A positive gap means certs taken on delivery would have to be offered above that origin's quote.</p>`;
    }
    const analyse = () => {
      const st = got('ctIceStock'), gr = got('ctIceGrade'), O = $('#ctCertOut'); if (!O) return;
      let html = '', stTot = 0; const SUM = {};
      // delivery points come from the warehouse file whenever it is newer than the delivery-point stock file
      const whT = got('ctIceWh'), whD = got('ctIceWhDate') || '', stD = got('ctIceStockDate') || '';
      const whDP = t => { if (!t || !WM) return null; const R = parseCSV(t), h = R[0].map(x => x.toLowerCase()), iC = h.findIndex(x => /number|code/.test(x)), iB = h.findIndex(x => /receipt|bales|stock/.test(x)), iN = h.findIndex(x => x === 'warehouse');
        const byCode = Object.fromEntries(WM.rows.filter(r => r.code).map(r => [r.code, r])), o = {};
        R.slice(1).filter(r => r[iN]).forEach(r => { const m = byCode[r[iC]] || {}, d = m.delivery_point || '?'; const x = o[d] = o[d] || { n: 0, cap: 0 }; x.n += +r[iB] || 0; x.cap += +m.capacity_bales || 0; }); return o; };
      const DPn = whD > stD ? whDP(whT) : null; SUM.dp = DPn || whDP(whT);
      if (DPn) {
        const P = whDP(got('ctIceWhPrev')) || {}, pd = got('ctIceWhPrevDate') || '', ks = Object.keys(DPn).filter(k => DPn[k].n || (P[k] || {}).n).sort((a, b) => DPn[b].n - DPn[a].n);
        const T = Object.values(DPn).reduce((a, x) => a + x.n, 0), TP = Object.values(P).reduce((a, x) => a + x.n, 0), C = Object.values(DPn).reduce((a, x) => a + x.cap, 0); stTot = T;
        html += `<div class="grid g4">${kp('Certificated stock', fmt(T, 0) + ' bales', 'ICE stock by warehouse, ' + whD)}${kp('Change', pd ? sg(T - TP) + ' bales' : '–', pd ? 'vs ' + pd : '')}${kp('Share of licensed capacity', fmt(T / (C || 1) * 100, 1) + '%', fmt(C, 0) + ' bales licensed')}${kp('Delivery points holding', ks.filter(k => DPn[k].n).length, '')}</div>
          <div class="tbl" style="margin-top:8px"><table><tr><th class="l">Delivery point</th><th>Bales</th>${pd ? `<th>${pd}</th><th>Change</th>` : ''}<th>Licensed capacity</th><th>% full</th></tr>
          ${ks.map(k => `<tr><td class="l">${k}</td><td class="n">${fmt(DPn[k].n, 0)}</td>${pd ? `<td class="n">${fmt((P[k] || {}).n || 0, 0)}</td><td class="n">${sg(DPn[k].n - ((P[k] || {}).n || 0))}</td>` : ''}<td class="n">${fmt(DPn[k].cap, 0)}</td><td class="n">${fmt(DPn[k].n / (DPn[k].cap || 1) * 100, 1)}%</td></tr>`).join('')}</table></div>
          <p class="note">Delivery points are taken from each warehouse's location (ICE 2026/27 licensed-warehouse list), because the warehouse report (${whD}) is newer than the delivery-point stock file${stD ? ' (' + stD + ')' : ''}.</p>`;
      } else if (st) {
        const R = parseCSV(st), h = R[0], rr = R.slice(1).filter(r => r[0]);
        const iCur = h.findIndex(x => /^Current Stock/i.test(x)), iNew = h.findIndex(x => /^New Certs/i.test(x)), iDec = h.findIndex(x => /^Decerts/i.test(x)), iPrev = h.findIndex(x => /^Stock/i.test(x));
        const tot = i => rr.reduce((a, r) => a + (+r[i] || 0), 0); stTot = tot(iCur);
        html += `<div class="grid g4">${kp('Certificated stock', fmt(tot(iCur), 0) + ' bales', h[iCur].replace('Current Stock - ', ''))}${kp('New certs', fmt(tot(iNew), 0), h[iNew].replace('New Certs - ', ''))}${kp('Decerts', fmt(tot(iDec), 0), '')}${kp('Change', sg(tot(iCur) - tot(iPrev)) + ' bales', 'vs ' + h[iPrev].replace('Stock - ', ''))}</div>
          <div class="tbl" style="margin-top:8px"><table><tr>${h.map((x, i) => `<th class="${i ? '' : 'l'}">${x}</th>`).join('')}</tr>${rr.map(r => `<tr>${r.map((x, i) => `<td class="${i ? 'n' : 'l'}">${i ? fmt(+x, 0) : x}</td>`).join('')}</tr>`).join('')}</table></div>`;
      }
      let strAdj = null;
      const sr = got('ctIceStr');
      if (sr) {
        const R = parseCSV(sr), h = R[0], rr = R.slice(1).filter(r => r[0] && !/^totals?:?$/i.test(r[0]));
        const cols = h.map((x, i) => [x, i]).filter(([x], i) => i > 0 && !/total/i.test(x));
        const tc = cols.map(([, i]) => rr.reduce((a, r) => a + (+String(r[i]).replace(/,/g, '') || 0), 0)), T = tc.reduce((a, b) => a + b, 0);
        const lowI = cols.findIndex(([x]) => /^25/.test(x)), low = lowI >= 0 ? tc[lowI] : 0, disc = D.strength[0]?.points || 0;
        strAdj = { share: T ? low / T : 0, disc, low, T }; SUM.str = strAdj;
        html += `<h3 style="margin-top:14px">Strength of the certs on board <span class="note">ICE GPT report ${got('ctIceStrDate') || ''}: ${fmt(T, 0)} bales</span></h3>
          <div class="tbl"><table><tr><th class="l">GPT (g/tex)</th>${cols.map(([x]) => `<th>${x.replace(' AND ABOVE', '+')}</th>`).join('')}<th>Total</th></tr>
          ${rr.filter(r => cols.some(([, i]) => +String(r[i]).replace(/,/g, ''))).map(r => `<tr><td class="l">${r[0]}</td>${cols.map(([, i]) => `<td class="n">${fmt(+String(r[i]).replace(/,/g, '') || 0, 0)}</td>`).join('')}<td class="n">${fmt(cols.reduce((a, [, i]) => a + (+String(r[i]).replace(/,/g, '') || 0), 0), 0)}</td></tr>`).join('')}
          <tr><td class="l">Share</td>${tc.map(v => `<td class="n">${fmt(v / T * 100, 1)}%</td>`).join('')}<td class="n">100%</td></tr></table></div>
          <p class="note">${low ? `${fmt(low, 0)} bales (${fmt(low / T * 100, 1)}%) are in 25.0–25.9 and take the ${sg(disc)}-point strength discount; the average premium below includes it.` : `No bales in 25.0–25.9, so no strength discount applies to the certs on board.`} ${fmt((tc.at(-1) || 0) / T * 100, 0)}% test 30 g/tex or stronger.</p>`;
      }
      if (gr) {
        const R = parseCSV(gr), h = R[0], sc = h.map((x, i) => [x.trim(), i]).filter(([x]) => /^(staple\s*)?3\d\+?$/i.test(x)).map(([x, i]) => [x.replace(/staple\s*/i, ''), i]);
        const iCo = h.findIndex(x => /^color/i.test(x)), iLf = h.findIndex(x => /^leaf/i.test(x)), iRd = h.findIndex(x => /date/i.test(x));
        if (iRd >= 0 && R[1]) LS.get('ctIceGrade') || (REPO.ctIceGradeDate = REPO.ctIceGradeDate || R[1][iRd]);
        const cells = [];
        R.slice(1).forEach(r => { const c = r[iCo], l = r[iLf]; if (!/^\d+$/.test(c) || !/^\d+$/.test(l)) return; sc.forEach(([s, i]) => { const n = +String(r[i]).replace(/,/g, '') || 0; if (n) cells.push({ c, l, s: s.replace('+', ''), n, p: pts(G, c, l, s) }); }); });
        const n = cells.reduce((a, x) => a + x.n, 0), priced = cells.filter(x => x.p != null), np = priced.reduce((a, x) => a + x.n, 0);
        const w0 = priced.reduce((a, x) => a + x.n * x.p, 0) / (np || 1), w = w0 + (strAdj ? strAdj.share * strAdj.disc : 0); SUM.grade = w0; SUM.gradeN = n; SUM.gradeDate = got('ctIceGradeDate'); SUM.cells = priced;
        const by = k => { const m = {}; priced.forEach(x => { (m[x[k]] = m[x[k]] || { n: 0, v: 0 }); m[x[k]].n += x.n; m[x[k]].v += x.n * x.p; }); return Object.entries(m).sort(); };
        const cheap = [...priced].sort((a, b) => a.p - b.p).slice(0, 5);
        const mkt = $('#ctPx')?.value;
        html += `<h3 style="margin-top:14px">Quality of the certs on board <span class="note">weekly grade/staple report ${got('ctIceGradeDate') || ''}: ${fmt(n, 0)} bales${stTot ? ` (${fmt(n / stTot * 100, 0)}% of the ${fmt(stTot, 0)} bales in the latest stock file)` : ''}${np < n ? `, ${fmt(n - np, 0)} without a grid value` : ''}</span></h3>
          <div class="grid g4">${kp('Average premium', sg(w) + ' pts', `${sg(w / 100, 2)}¢/lb against 41-4-34 at the ${D.date} grid`)}${kp('Per lot', '$' + fmt(w / 100 * 500, 0), '50,000 lb contract')}
            ${kp('Cheapest to deliver', `${cheap[0]?.c}-${cheap[0]?.l}-${cheap[0]?.s}`, `${sg(cheap[0]?.p)} pts, ${fmt(cheap[0]?.n, 0)} bales`)}${kp('Base-grade cotton on board', fmt(priced.filter(x => x.p <= 0).reduce((a, x) => a + x.n, 0), 0) + ' bales', 'at or below 41-4-34 value')}</div>
          <div class="grid g2" style="margin-top:8px"><div class="tbl"><table><tr><th class="l">Staple</th><th>Bales</th><th>Share</th><th>Avg pts</th></tr>${by('s').map(([k, v]) => `<tr><td class="l">${k}${k === '37' ? '+' : ''}</td><td class="n">${fmt(v.n, 0)}</td><td class="n">${fmt(v.n / np * 100, 1)}%</td><td class="n">${sg(v.v / v.n)}</td></tr>`).join('')}</table></div>
            <div class="tbl"><table><tr><th class="l">Color</th><th>Bales</th><th>Share</th><th>Avg pts</th></tr>${by('c').map(([k, v]) => `<tr><td class="l">${k}</td><td class="n">${fmt(v.n, 0)}</td><td class="n">${fmt(v.n / np * 100, 1)}%</td><td class="n">${sg(v.v / v.n)}</td></tr>`).join('')}</table></div></div>
          <div class="tbl" style="margin-top:8px"><table><tr><th class="l">Cheapest qualities on board</th><th>Bales</th><th>Points</th><th>¢/lb</th></tr>${cheap.map(x => `<tr><td class="l">${x.c}-${x.l}-${x.s}</td><td class="n">${fmt(x.n, 0)}</td><td class="n">${sg(x.p)}</td><td class="n">${sg(x.p / 100, 2)}</td></tr>`).join('')}</table></div>
          <p class="note">Values each bale in the file at today's grid${strAdj ? `, with the strength discount applied to the share of bales in 25.0–25.9 (${fmt(strAdj.share * 100, 1)}%)` : ' (no strength report loaded, so no strength discount applied)'}; micronaire is not in the files. ICE shows each bale at its invoicing staple: under the Smith-Doxey provisions a bale's staple for exchange delivery is set by the USDA "dig" measurement and can differ from its USDA class staple, so these premiums are what the bale actually invoices at. A deliverer picks the cheapest qualities first, so the low end of this table sets the value of the spot month; a pile priced well above base means receivers pay the notice price plus that premium, and only new certification of lower grades would cheapen it.${st ? ' The stock file is daily; ICE refreshes the full grade/staple detail on Mondays, so between Mondays the quality mix lags new certs and decerts.' : ''}</p>`;
      }
      const yg = got('ctIceYog');
      if (yg) {
        const R = parseCSV(yg), h = R[0].map(x => x.toLowerCase()), iP = h.findIndex(x => /delivery/.test(x)), iY = h.findIndex(x => /crop|year/.test(x)), iB = h.findIndex(x => /receipt|bales/.test(x));
        const Y = R.slice(1).filter(r => /^\d{4}$/.test(r[iY])).map(r => ({ dp: r[iP].replace(/,\s*[A-Z]{2}$/, ''), y: +r[iY], n: +String(r[iB]).replace(/,/g, '') || 0 }));
        const T = Y.reduce((a, x) => a + x.n, 0), yrs = [...new Set(Y.map(x => x.y))].sort(), dps = [...new Set(Y.map(x => x.dp))];
        const now = new Date(), cy = now.getFullYear();
        const pen = (crop, dy) => dy <= crop + 1 ? 0 : 2 * (dy - crop - 1);        // ¢/lb: free through 31 Dec of the year after the crop year
        const months = [['Dec ' + String(cy).slice(2), cy], ['Mar ' + String(cy + 1).slice(2), cy + 1], ['Dec ' + String(cy + 1).slice(2), cy + 1], ['Mar ' + String(cy + 2).slice(2), cy + 2]];
        const avgPen = dy => Y.reduce((a, x) => a + x.n * pen(x.y, dy), 0) / (T || 1); SUM.yog = months.slice(0, 2).map(([l, dy]) => [l, -avgPen(dy) * 100]); SUM.yogOld = Y.filter(x => pen(x.y, cy + 1) > 0).reduce((a, x) => a + x.n, 0); SUM.yogT = T; SUM.yogCrops = Y;
        html += `<h3 style="margin-top:14px">Year of growth <span class="note">ICE report ${got('ctIceYogDate') || ''}: ${fmt(T, 0)} bales</span></h3>
          <div class="grid g2"><div class="tbl"><table><tr><th class="l">Crop year</th>${dps.map(d => `<th>${d}</th>`).join('')}<th>Total</th><th>Share</th></tr>
            ${yrs.map(y => { const t = Y.filter(x => x.y === y).reduce((a, x) => a + x.n, 0); return `<tr><td class="l">${y}</td>${dps.map(d => `<td class="n">${fmt(Y.filter(x => x.y === y && x.dp === d).reduce((a, x) => a + x.n, 0), 0)}</td>`).join('')}<td class="n">${fmt(t, 0)}</td><td class="n">${fmt(t / T * 100, 1)}%</td></tr>`; }).join('')}</table></div>
          <div class="tbl"><table><tr><th class="l">If delivered against</th>${yrs.map(y => `<th>${y} crop</th>`).join('')}<th>Avg on board</th></tr>
            ${months.map(([l, dy]) => `<tr><td class="l">${l}</td>${yrs.map(y => `<td class="n">${pen(y, dy) ? '−' + fmt(pen(y, dy), 0) + '¢' : '0'}</td>`).join('')}<td class="n">${avgPen(dy) ? '−' + fmt(avgPen(dy), 2) + '¢' : '0'}</td></tr>`).join('')}</table></div></div>
          <p class="note">Year-of-growth discount: none if delivered by 31 December of the year after the crop year, then 2¢/lb, plus 2¢/lb for each further year. Older-crop certs on board are free to deliver against December but lose 2¢/lb from the March contract, so they tend to be tendered in December or decertified and sold before year end.</p>`;
      }
      const wh = got('ctIceWh');
      if (wh && WM) {
        const R = parseCSV(wh), h = R[0].map(x => x.toLowerCase()), iC = h.findIndex(x => /number|code/.test(x)), iN = h.findIndex(x => x === 'warehouse'), iB = h.findIndex(x => /receipt|bales|stock/.test(x)), iD = h.findIndex(x => /date/.test(x));
        const byCode = Object.fromEntries(WM.rows.filter(r => r.code).map(r => [r.code, r])), norm = t => t.toLowerCase().replace(/[^a-z0-9]/g, '');
        const byName = Object.fromEntries(WM.rows.map(r => [norm(r.warehouse), r]));
        const rule = t => { for (const [re, m] of WM.rules) if (new RegExp(re, 'i').test(t)) return m; return null; };
        const W = R.slice(1).filter(r => r[iN]).map(r => { const code = r[iC], nm = r[iN], n = +r[iB] || 0, hit = byCode[code] || byName[norm(nm)];
          return { code, nm, n, merchant: hit?.merchant || rule(nm) || 'Unmapped', dp: hit?.delivery_point || '?', how: byCode[code] ? 'code' : hit ? 'name' : rule(nm) ? 'owner rule' : '–' }; });
        const tot = W.reduce((a, x) => a + x.n, 0), rd = R[1]?.[iD] || got('ctIceWhDate') || '';
        const dps = [...new Set(W.filter(x => x.n).map(x => x.dp))].sort();
        const M = {}; W.forEach(x => { const o = M[x.merchant] = M[x.merchant] || { n: 0, dp: {}, w: 0 }; o.n += x.n; o.dp[x.dp] = (o.dp[x.dp] || 0) + x.n; if (x.n) o.w++; });
        const ms = Object.entries(M).filter(([, v]) => v.n).sort((a, b) => b[1].n - a[1].n);
        html += `<h3 style="margin-top:14px">Certs by merchant <span class="note">ICE stock by warehouse, ${rd}: ${fmt(tot, 0)} bales; warehouse → merchant mapping from data/cotton/warehouse_map.csv</span></h3>
          <div class="tbl"><table><tr><th class="l">Merchant</th><th>Bales</th><th>Share</th>${dps.map(d => `<th>${d}</th>`).join('')}<th>Warehouses holding</th></tr>
          ${ms.map(([k, v]) => `<tr><td class="l"><b>${k}</b></td><td class="n">${fmt(v.n, 0)}</td><td class="n">${fmt(v.n / tot * 100, 1)}%</td>${dps.map(d => `<td class="n">${v.dp[d] ? fmt(v.dp[d], 0) : ''}</td>`).join('')}<td class="n">${v.w}</td></tr>`).join('')}
          <tr><td class="l">Total</td><td class="n">${fmt(tot, 0)}</td><td class="n">100%</td>${dps.map(d => `<td class="n">${fmt(W.filter(x => x.dp === d).reduce((a, x) => a + x.n, 0), 0)}</td>`).join('')}<td class="n">${W.filter(x => x.n).length}</td></tr></table></div>
          <p class="note">Ownership changes: some licensed warehouses have changed hands since ICE's 2026/27 licence list; they are shown as "Ownership change" and not attributed to a merchant.</p>
          <details style="margin-top:6px"><summary class="note">By warehouse (${W.length} listed, ${W.filter(x => x.n).length} holding certs)</summary><div class="tbl"><table><tr><th class="l">Code</th><th class="l">Warehouse</th><th class="l">Delivery point</th><th class="l">Merchant</th><th>Bales</th><th class="l">Matched by</th></tr>
          ${[...W].sort((a, b) => b.n - a.n).map(x => `<tr><td class="l">${x.code}</td><td class="l">${x.nm}</td><td class="l">${x.dp}</td><td class="l">${x.merchant}</td><td class="n">${x.n ? fmt(x.n, 0) : ''}</td><td class="l">${x.how}</td></tr>`).join('')}</table></div></details>
          ${stTot && Math.abs(stTot - tot) > 100 ? `<p class="note">The warehouse report (${rd}) totals ${fmt(tot, 0)} bales against ${fmt(stTot, 0)} in the latest delivery-point file; the two are from different dates, so certification in between is not yet assigned to merchants.</p>` : ''}`;
      }
      if (SUM.grade != null) {
        const sp = SUM.str ? SUM.str.share * SUM.str.disc : 0, y = SUM.yog || [['Dec', 0], ['Mar', 0]];
        const net = v => SUM.grade + sp + v, row = (lab, v, note) => `<tr><td class="l">${lab}</td>${y.map(([, yv]) => `<td class="n">${sg(v === 'yog' ? yv : v === 'net' ? net(yv) : v)}${v === 'net' ? '' : ''}</td>`).join('')}<td class="l note">${note}</td></tr>`;
        html = `<h3>Premiums and discounts on the certs on board <span class="note">points vs 41-4-34 (100 = 1¢/lb); weekly reports ${SUM.gradeDate || ''}, grid ${D.date}</span></h3>
          <div class="tbl"><table><tr><th class="l">Component</th>${y.map(([l]) => `<th>If delivered ${l}</th>`).join('')}<th class="l">Basis</th></tr>
          ${row('Grade and staple', SUM.grade, `average of ${fmt(SUM.gradeN, 0)} bales at the USDA grid (invoicing staple)`)}
          ${row('Strength', sp, SUM.str ? (SUM.str.low ? `${fmt(SUM.str.low, 0)} bales in 25.0–25.9 at ${sg(SUM.str.disc)} pts` : 'no bales in 25.0–25.9') : 'no strength report loaded')}
          ${row('Year of growth', 'yog', SUM.yog ? `${fmt(SUM.yogOld, 0)} of ${fmt(SUM.yogT, 0)} bales are older crop: free in December, 2¢/lb discount from March` : 'no year-of-growth report loaded')}
          <tr><td class="l"><b>Net average premium</b></td>${y.map(([, yv]) => `<td class="n"><b>${sg(net(yv))} pts</b><br><span class="note">${sg(net(yv) / 100, 2)}¢/lb · $${fmt(net(yv) * 5, 0)}/lot</span></td>`).join('')}<td class="l note">what a receiver pays over the notice price, on average</td></tr></table></div>` + (carry(net(y[0][1]), SUM), decert(net(y[0][1]), SUM), econ(net(y[0][1]))) + cfrOut() + html;
        html = brief(net(y[0][1])) + html;
      }
      const E = REPO.ewr;
      if (E && E.states) {
        const T = E.states.find(x => x.state === 'TOTAL') || {}, TX = E.states.find(x => x.state === 'TX') || {}, Y = E.issued_same_date || { years: [], rows: [] };
        const yt = Y.years.map((y, i) => [y, Y.rows.reduce((a, r) => a + (r[i + 1] || 0), 0)]), txr = Y.rows.find(r => r[0] === 'TX') || [];
        html += `<h3 style="margin-top:14px">Warehouse receipts (EWR) <span class="note">EWR Inc. receipt statistics, ${E.asof}; daily, ahead of the ICE reports</span></h3>
          <div class="grid g4">${kp('Tenderable certificated (open)', fmt(E.tenderable_cert, 0) + ' bales', 'EWR count of open certificated receipts')}${kp('Under shipping order', fmt(T.shipping_order, 0), fmt(T.shipping_order / (T.total_open || 1) * 100, 1) + '% of open receipts; Texas ' + fmt(TX.shipping_order, 0))}${kp('Held by CCC (loan)', fmt(T.ccc, 0), fmt(T.ccc / (T.open_cur || 1) * 100, 1) + '% of open ' + E.crop_year + ' crop')}${kp('Open older crops', fmt(T.open_prev + T.open_prev2 + T.open_older, 0), fmt(T.open_prev, 0) + ' of them ' + (E.crop_year - 1) + ' crop')}</div>
          <div class="tbl" style="margin-top:8px"><table><tr><th class="l">Receipts issued by this date</th>${yt.map(([y]) => `<th>${y}</th>`).join('')}</tr>
          <tr><td class="l">United States</td>${yt.map(([, v]) => `<td class="n">${fmt(v, 0)}</td>`).join('')}</tr>
          <tr><td class="l">Texas</td>${Y.years.map((y, i) => `<td class="n">${fmt(txr[i + 1] || 0, 0)}</td>`).join('')}</tr></table></div>
          <p class="note">Receipts issued so far: ${fmt(E.new_issued_total, 0)} new ${E.crop_year}-crop receipts, ${fmt(E.new_issued_total / (E.crop_est || 1) * 100, 1)}% of the USDA crop estimate of ${fmt(E.crop_est, 0)}. Receipts under shipping order are bales sold and called for shipment, a lead indicator of what can physically ship in the coming weeks. History builds from daily snapshots kept in data/cotton/ewr/history.csv.</p>`;
      }
      O.innerHTML = html || '<p class="note">No files loaded in this browser yet.</p>';
      const bindC = (id, k, key) => { const el = $('#' + id); if (el) el.onchange = () => { CF[k] = +el.value || 0; LS.set(key, String(CF[k])); analyse(); }; }; { const el = $('#ctDecMo'); if (el) el.onchange = () => { DC.m = Math.max(0, +el.value || 0); LS.set('ctDecM', String(DC.m)); analyse(); }; } { const el = $('#ctCSt'); if (el) el.onchange = () => { if (el.value === '') { CF.st = null; LS.del('ctCarrySt'); } else { CF.st = +el.value; LS.set('ctCarrySt', String(CF.st)); } analyse(); }; } bindC('ctCIr', 'ir', 'ctCarryIr');
    };
    const hook = (id, key) => { const el = $('#' + id); if (el) el.onchange = e => { const f = e.target.files[0]; if (!f) return; const rd = new FileReader(); rd.onload = () => { LS.set(key, rd.result); const m = f.name.match(/(\d{4}-\d{2}-\d{2})/); LS.set(key + 'Date', m ? m[1] : f.name); analyse(); }; rd.readAsText(f); }; };
    hook('ctFStock', 'ctIceStock'); hook('ctFGrade', 'ctIceGrade'); hook('ctFWh', 'ctIceWh'); hook('ctFStr', 'ctIceStr'); hook('ctFYog', 'ctIceYog');
    $('#ctFClear').onclick = e => { e.preventDefault(); ['ctIceStock', 'ctIceGrade', 'ctIceWh', 'ctIceStr', 'ctIceYog'].forEach(k => { LS.del(k); LS.del(k + 'Date'); }); analyse(); };
    analyse();
  }

  async function outlook() {
    body().innerHTML = `<div id="ctOb" style="margin-bottom:12px"></div><div id="ctBal" style="margin-bottom:12px"></div><div id="ctPx" style="margin-bottom:12px"></div><div id="ctTech"></div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>WASDE outlook factors</h2><div id="ctFac"><p class="note">Loading…</p></div></div>
      <div class="card"><h2>Next events</h2><div id="ctCal"></div></div></div>
      <div id="ctSzUp" style="margin-top:12px"></div>
      <div class="card" style="margin-top:12px"><h2>Cotton headlines</h2><div id="ctNews"></div></div>`;
    OutlookBrief.mount($('#ctOb'), 'cotton'); BalanceSheet.mount($('#ctBal'), 'cotton'); if (typeof PriceOutlook !== 'undefined') PriceOutlook.mount($('#ctPx'));
    Tech.mount($('#ctTech'), ['CT']);
    MktStudy.upcoming($('#ctSzUp'), ['CT'], () => $('#ctTabs button[data-t="ct-seas"]').click());
    Intel.calendar($('#ctCal'), { markets: ['CT'], days: 30, minImp: 2 });
    Intel.news($('#ctNews'), { tags: ['cotton'], n: 20, chips: false });
    const idx = await getJSON('data/grains/derived/wasde_brief/index.json').catch(() => null);
    const R = idx && await getJSON('data/grains/derived/wasde_brief/' + idx.reports[0].report + '.json').catch(() => null);
    const C = R?.commodities?.cotton;
    $('#ctFac').innerHTML = C ? `<p>${R.label} report, ${C.my}: <b>${C.outlook}</b> (score ${C.score > 0 ? '+' : ''}${C.score}).</p><div class="tbl"><table>${(C.factors || []).map(f => `<tr><td class="l"><b>${f.factor}</b></td><td>${f.tilt}</td><td class="l sv-w">${String(f.text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')}</td></tr>`).join('')}</table></div>` : '<p class="note">Not available.</p>';
  }
  return { show };
})();
