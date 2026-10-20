// Desk summary: one card per market with fundamentals, technicals, flows, overall outlook and trade ideas.
const Summary = (() => {
  let built = false, S = null;
  const LINK = { grains: k => [`#g/${k}/g-outlook`, 'grains'], livestock: (k, s) => [s === 'HE' ? '#h-outlook' : '#c-outlook', s === 'HE' ? 'hogs' : 'cattle'], dairy: () => ['#d-outlook', 'dairy'] };
  const badge = (v, c) => { const col = /bullish/.test(v) ? 'var(--up)' : /bearish/.test(v) ? 'var(--dn)' : '#666'; return `<span class="sv-badge" style="border-color:${col};color:${col}">${v}${c ? ` · ${c} conviction` : ''}</span>`; };
  const bar = v => { if (v == null) return '–'; const w = Math.round(Math.abs(v) * 40); return `<span class="sv-bar"><span style="${v >= 0 ? 'left:50%' : `right:50%`};width:${w}%;background:${v >= 0 ? 'var(--up)' : 'var(--dn)'}"></span></span>`; };
  const f = (v, d) => v == null ? '–' : (+v).toFixed(d);
  const ord = v => { if (v == null) return '–'; const n = Math.round(v); return n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th')); };
  function go(m) { const [h, c] = LINK[m.group](m.key, m.sym); location.hash = h; document.querySelector(`nav.comm button[data-c="${c}"]`).click();
    if (c === 'dairy') document.querySelector('nav.tabs button[data-tab="d-outlook"]')?.click(); window.scrollTo(0, 0); }
  function render() {
    const el = document.getElementById('summary');
    const M = S.markets;
    const groups = [['grains', 'Grains & oilseeds'], ['livestock', 'Livestock'], ['dairy', 'Dairy']];
    el.innerHTML = `<main><div class="card"><h2>Desk summary</h2>
      <p class="note">Built automatically from the data and models behind every tab (updated ${S.generated}). Fundamentals weigh 40%, technicals 30%, flows 30%. Each trade idea names its method and says how that method has tested; untested ideas are context, not edges. A standing caveat from the back-tests: in these cash-settled and delivery markets futures have been the best forecast of their own settlement, so the edge is in timing, structure and the few tested biases (e.g. the live cattle convergence premium), not in out-forecasting the curve. Research only, not investment advice.</p>
      <div class="tbl"><table class="sv-tbl"><tr><th>Market</th><th>Contract</th><th>Last</th><th>1 wk</th><th>Overall view</th><th>Fundamental</th><th>Technical</th><th>Flows</th><th>Funds pct 3y · 10y · all</th><th>Trend score</th><th>Ideas</th></tr>
      ${groups.map(([g, gl]) => `<tr class="sv-sec"><td colspan="11">${gl}</td></tr>` + M.filter(m => m.group === g).map(m => `<tr><td><a href="#" data-go="${m.key}">${m.name}</a></td><td>${m.contract || ''}</td><td>${f(m.price, m.dp)}</td>
        <td class="${m.chg_1w > 0 ? 'up' : m.chg_1w < 0 ? 'dn' : ''}">${m.chg_1w == null ? '–' : (m.chg_1w > 0 ? '+' : '') + m.chg_1w.toFixed(1) + '%'}</td><td>${badge(m.view, m.conviction)}</td>
        <td>${bar(m.scores.fundamental)}</td><td>${bar(m.scores.technical)}</td><td>${bar(m.scores.flows)}</td><td>${ord(m.mm_pct3)} · ${ord(m.mm_pct10)} · ${ord(m.mm_pct_all)}</td><td>${m.cta_score == null ? '–' : (m.cta_score > 0 ? '+' : '') + m.cta_score.toFixed(2)}</td><td>${m.ideas.length}</td></tr>`).join('')).join('')}</table></div></div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>Key events, next 3 weeks</h2><div id="svCal"></div></div>
        <div class="card"><h2>Latest headlines</h2><div id="svNews"></div></div></div>
      <div class="card" style="margin-top:12px"><h2>Weather watch: US, Brazil, Argentina</h2><div id="svWx"></div></div>
      ${groups.map(([g, gl]) => `<h2 class="sv-h">${gl}</h2>` + M.filter(m => m.group === g).map(m => `<div class="card sv-card" id="sv-${m.key}">
        <div class="sv-head"><h2>${m.name} <span class="note">${m.contract || ''} ${f(m.price, m.dp)} ${m.unit || ''}</span></h2>${badge(m.view, m.conviction)}<a href="#" data-go="${m.key}" class="sv-link">open desk →</a></div>
        <div class="grid g2"><div><h3>Fundamentals ${bar(m.scores.fundamental)}</h3><p>${m.paras.fundamental}</p><h3>Technicals &amp; seasonality ${bar(m.scores.technical)}</h3><p>${m.paras.technical}</p></div>
        <div><h3>Flows &amp; positioning ${bar(m.scores.flows)}</h3><p>${m.paras.flows}</p><h3>Outlook</h3><p><b>${m.paras.outlook}</b></p></div></div>
        ${m.ideas.length ? `<h3>Trade ideas by method</h3><div class="tbl"><table><tr><th>Method</th><th>Side</th><th>Instrument</th><th>Entry</th><th>Stop</th><th>Target</th><th>R:R</th><th>Horizon</th><th class="l">Why</th><th class="l">How it has tested</th></tr>
          ${m.ideas.map(i => `<tr><td>${i.method}</td><td class="${/Long|Bull/.test(i.side) ? 'up' : 'dn'}"><b>${i.side}</b></td><td>${i.instrument}</td><td>${f(i.entry, m.dp)}</td><td>${f(i.stop, m.dp)}</td><td>${f(i.target, m.dp)}</td><td>${i.rr ?? '–'}</td><td>${i.horizon}</td><td class="l sv-w">${i.why}</td><td class="l sv-w note">${i.evidence}</td></tr>`).join('')}</table></div>`
          : '<p class="note">No method currently gives a trade signal here.</p>'}
        <div class="grid g2"><div><h3>This market's next events</h3><div class="sv-cal" data-m="${m.sym}"></div></div><div><h3>Recent headlines</h3><div class="sv-news" data-k="${m.key}"></div></div></div></div>`).join('')).join('')}</main>`;
    el.querySelectorAll('[data-go]').forEach(a => a.onclick = e => { e.preventDefault(); go(M.find(m => m.key === a.dataset.go)); });
    Intel.calendar(document.getElementById('svCal'), { days: 21, minImp: 2 });
    Intel.news(document.getElementById('svNews'), { n: 18 });
    Intel.weather(document.getElementById('svWx'));
    const NT = { corn: ['corn'], soybeans: ['soybeans', 'south_america'], meal: ['meal'], oil: ['oil'], wheat: ['wheat'], kc: ['wheat'], hogs: ['hogs'], cattle: ['cattle'], feeders: ['cattle'], class3: ['dairy'], class4: ['dairy'] };
    el.querySelectorAll('.sv-cal').forEach(x => Intel.calendar(x, { markets: [x.dataset.m], days: 30, minImp: 2 }));
    el.querySelectorAll('.sv-news').forEach(x => Intel.news(x, { tags: NT[x.dataset.k], n: 4, chips: false }));
  }
  async function show() {
    if (!built) { S = await getJSON('data/summary/summary.json').catch(() => null); built = true; }
    if (!S) { document.getElementById('summary').innerHTML = '<main><div class="card"><p class="note">Summary not built yet.</p></div></main>'; return; }
    history.replaceState(null, '', '#summary'); render();
  }
  return { show };
})();
