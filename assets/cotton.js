// Cotton section: built from the BMR-Com cotton repos (WASDE analytics, export sales, crop progress, on-call, COT)
// plus the desk's own COT desk, technicals, news and calendar.
const Cotton = (() => {
  let built = false, tab = 'ct-primer';
  const ORG = location.hostname === 'bmr-com.github.io' ? '' : 'https://bmr-com.github.io';   // sibling Pages sites (same origin when live)
  const SITE = { wasde: ORG + '/wasde-analytics/', esr: ORG + '/usd-export-sales-email/', crop: ORG + '/cotton-crop-progress/', oncall: ORG + '/cotton-on-call/',
    cot: ORG + '/cftc-cot-full/', opts: ORG + '/softs--options-/' };
  const TABS = [['ct-primer', 'Primer'], ['ct-wasde', 'WASDE'], ['ct-esr', 'Export sales'], ['ct-crop', 'Crop progress'], ['ct-oncall', 'On-call'],
    ['ct-flows', 'Futures, options &amp; COT'], ['ct-rv', 'Spreads &amp; vol'], ['ct-outlook', 'Outlook']];
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
    ({ 'ct-primer': primer, 'ct-wasde': wasde, 'ct-esr': esr, 'ct-crop': () => frame(SITE.crop, 'Cotton crop progress', 'NASS crop progress and condition, crop predicted from ratings and drought, ginning and classing pace, grades and tenderability, FSA acreage.'),
      'ct-oncall': () => frame(SITE.oncall, 'Cotton on-call', 'CFTC weekly cotton on-call: unfixed call sales and purchases by contract month, mill fixation pace and what it means for futures.'),
      'ct-flows': flows, 'ct-rv': () => RVView.mount(body(), 'CT'), 'ct-outlook': outlook })[tab]();
  }
  function primer() {
    body().innerHTML = `<div class="grid g2">
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
        <h3>Full dashboards</h3><p class="note">${src(SITE.wasde, 'WASDE analytics')} · ${src(SITE.esr, 'Export sales')} · ${src(SITE.crop, 'Crop progress')} · ${src(SITE.oncall, 'On-call')} · ${src(SITE.cot, 'COT desk')} · ${src(SITE.opts, 'Softs options')}</p></div></div>`;
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
    const D = await fetch(SITE.esr + 'data/brief.json?t=' + Date.now()).then(r => r.json()).catch(() => null);
    if (!D) { body().innerHTML = `<div class="card"><p class="note">Could not load the cotton export sales brief. Open ${src(SITE.esr, 'the export sales page')}.</p></div>`; return; }
    ESR.mount(body(), D, { name: 'Cotton' });
    body().insertAdjacentHTML('beforeend', `<p class="note" style="margin:4px 2px">From ${src(SITE.esr, 'BMR-Com US cotton export sales')} (upland + Pima, USDA FAS) · ${D.generated}.</p>`);
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
  async function outlook() {
    body().innerHTML = `<div id="ctTech"></div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>WASDE outlook factors</h2><div id="ctFac"><p class="note">Loading…</p></div></div>
      <div class="card"><h2>Next events</h2><div id="ctCal"></div></div></div>
      <div class="card" style="margin-top:12px"><h2>Cotton headlines</h2><div id="ctNews"></div></div>`;
    Tech.mount($('#ctTech'), ['CT']);
    Intel.calendar($('#ctCal'), { markets: ['CT'], days: 30, minImp: 2 });
    Intel.news($('#ctNews'), { tags: ['cotton'], n: 20, chips: false });
    const idx = await getJSON('data/grains/derived/wasde_brief/index.json').catch(() => null);
    const R = idx && await getJSON('data/grains/derived/wasde_brief/' + idx.reports[0].report + '.json').catch(() => null);
    const C = R?.commodities?.cotton;
    $('#ctFac').innerHTML = C ? `<p>${R.label} report, ${C.my}: <b>${C.outlook}</b> (score ${C.score > 0 ? '+' : ''}${C.score}).</p><div class="tbl"><table>${(C.factors || []).map(f => `<tr><td class="l"><b>${f.factor}</b></td><td>${f.tilt}</td><td class="l sv-w">${String(f.text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')}</td></tr>`).join('')}</table></div>` : '<p class="note">Not available.</p>';
  }
  return { show };
})();
