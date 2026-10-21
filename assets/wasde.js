// WASDE analysis view: report brief, factor outlook, key changes, revisions vs past same-month reports,
// balance sheets (this vs previous release, three marketing years) and revision paths.
// Shared by grains (data/grains/derived/wasde_brief) and cotton (BMR-Com/wasde-analytics brief, adapted).
const WasdeView = (() => {
  const md = t => String(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const f = (v, d) => v == null || isNaN(v) ? '–' : (+v).toLocaleString('en-US', { minimumFractionDigits: d ?? (Math.abs(v) >= 100 ? 0 : Math.abs(v) < 10 ? 2 : 1), maximumFractionDigits: d ?? (Math.abs(v) >= 100 ? 0 : Math.abs(v) < 10 ? 2 : 1) });
  const ch = (v, d, inv) => { if (v == null || isNaN(v) || Math.abs(v) < 1e-9) return '<span class="note">–</span>'; const up = inv ? v < 0 : v > 0; return `<span class="${up ? 'up' : 'dn'}">${v > 0 ? '+' : ''}${f(v, d)}</span>`; };
  const TILT = { bullish: ['#dcfce7', '#166534'], bearish: ['#fee2e2', '#b91c1c'], neutral: ['#f1f2f4', '#444'] };
  const tag = l => { const k = /bull/.test(l) ? 'bullish' : /bear/.test(l) ? 'bearish' : 'neutral'; return `<span class="wtag" style="background:${TILT[k][0]};color:${TILT[k][1]}">${esc(l)}</span>`; };
  const state = {};

  async function mount(el, opts) {
    // opts: {base, index, key} grains | {cotton:true, base:'https://bmr-com.github.io/wasde-analytics/data/brief/', index}
    const S = state[opts.key || 'cotton'] ||= { report: opts.index.reports[0].report, region: null, rev: null };
    const idx = opts.index;
    el.innerHTML = `<div class="wv"><div class="card" style="margin-bottom:10px"><div class="wv-top">
        <label class="note">WASDE report <select id="wvRep">${idx.reports.map(r => `<option value="${r.report}" ${r.report === S.report ? 'selected' : ''}>${r.label}</option>`).join('')}</select></label>
        <span id="wvTag"></span><span class="note" id="wvGen">Built ${esc(idx.generated || '')}</span></div></div><div id="wvBody"><p class="note">Loading…</p></div></div>`;
    el.querySelector('#wvRep').onchange = e => { S.report = e.target.value; draw(); };
    let revs = null;
    async function draw() {
      const body = el.querySelector('#wvBody');
      let R = await getJSON(opts.base + S.report + '.json').catch(() => null);
      let C = R && (opts.cotton ? adaptCotton(R) : R.commodities?.[opts.key]);
      if (!C) { body.innerHTML = '<div class="card"><p class="note">No analysis for this report.</p></div>'; return; }
      el.querySelector('#wvTag').innerHTML = `${C.name} ${C.my} outlook: ${tag(C.outlook)}`;
      const U = C.unit, WU = C.wunit || 'MMT';
      const FT = (C.factors || []).map(x => `<tr><td class="l"><b>${esc(x.factor)}</b></td><td>${tag(x.tilt)}</td><td class="l sv-w">${md(esc(x.text))}</td></tr>`).join('');
      const regs = C.changes || [];
      const CH = regs.map(r => {
        const isUS = r.region === 'United States', d = isUS ? 0 : 2;
        const cell = a => { const x = r[a] || {}; return `<td>${f(x.now, isUS ? undefined : d)}</td><td>${ch(x.chg, isUS ? undefined : d, a === 'Ending Stocks' || a === 'Production' ? false : false)}</td>`; };
        const s = r['S/U'] || {};
        return `<tr${isUS || r.region.startsWith('World') ? ' class="wv-hl"' : ''}><td class="l"><b>${esc(r.region)}</b> <span class="note">${isUS ? U : WU}</span></td>${['Production', 'Domestic Use', 'Exports', 'Imports', 'Ending Stocks'].map(cell).join('')}<td>${s.now == null ? '–' : (s.now * 100).toFixed(1) + '%'}</td><td>${s.chg == null ? '–' : ch(s.chg * 100, 1)}</td></tr>`;
      }).join('');
      const HI = (C.history || []).map(h => `<tr><td class="l">${esc(h.region)} · ${esc(h.attr.toLowerCase())}</td><td>${ch(h.chg)}</td><td>±${f(h.avg_abs)}</td><td>${Math.round(h.up_share * 100)}%</td><td>${h.pct_abs}%</td><td class="l">${esc(h.note)}</td></tr>`).join('');
      const B = C.balance;
      body.innerHTML = `
        <div class="grid g2">
          <div class="card"><h2>Brief — ${esc(R.label)}</h2>${C.brief.map(b => `<h3>${esc(b.h)}</h3><p>${md(esc(b.t))}</p>`).join('')}
            <p class="note">“At the report” checks use data available about ten days after release; “latest data” runs to the next report (or today), which is what drives the outlook.</p></div>
          <div class="card"><h2>Outlook factors</h2><div class="tbl"><table><tr><th class="l">Factor</th><th>Tilt</th><th class="l">Reading</th></tr>${FT || '<tr><td class="note" colspan=3>No factors.</td></tr>'}</table></div>
            <p class="note">Score ${C.score > 0 ? '+' : ''}${C.score ?? 0}: each bullish factor +1, bearish −1. ±2 or more = bullish/bearish, ±1 = modestly.</p>
            ${HI ? `<h2 style="margin-top:14px">This month's revisions vs past ${esc(R.label.split(' ')[0])} reports</h2><div class="tbl"><table><tr><th class="l">Estimate</th><th>Change</th><th>Avg move</th><th>Past raises</th><th>Pctile of size</th><th class="l">Read</th></tr>${HI}</table></div>
            <p class="note">Avg move = mean absolute revision in the same month of past years; pctile = share of past same-month revisions smaller than this one.</p>` : ''}</div>
        </div>
        <div class="card" style="margin-top:12px"><h2>Key changes vs the previous report — ${esc(C.my)}</h2><div class="tbl"><table class="wv-ch">
          <tr><th class="l" rowspan=2>Region</th>${['Production', 'Domestic use', 'Exports', 'Imports', 'Ending stocks', 'Stocks/use'].map(x => `<th colspan=2>${x}</th>`).join('')}</tr>
          <tr>${Array(6).fill('<th>Now</th><th>Chg</th>').join('')}</tr>${CH}</table></div>
          <p class="note">US in ${esc(U)}; other regions in ${esc(WU)}. Stocks/use for countries = ending stocks ÷ (domestic use + exports); world = ÷ domestic use.</p></div>
        ${C.preview ? `<div class="card" style="margin-top:12px"><h2>Next report preview — ${C.preview.month} WASDE</h2><div class="grid g2">
          <div><h3>How USDA usually revises in ${C.preview.month}</h3><div class="tbl"><table><tr><th class="l">Line</th><th>Now</th><th>Raised</th><th>Cut</th><th>Unch.</th><th>Avg change</th><th>Avg size</th></tr>
            ${C.preview.rows.map(r => `<tr><td class="l">${esc(r.region)} · ${esc(r.attr.toLowerCase())}</td><td>${f(r.now, r.attr === 'Yield' ? 1 : undefined)}</td><td>${r.up}</td><td>${r.down}</td><td>${r.unch}</td><td>${ch(r.avg)}</td><td>±${f(r.avg_abs)}</td></tr>`).join('')}</table></div></div>
          <div><h3>Desk signals going in</h3>${C.preview.signals.length ? `<div class="tbl"><table><tr><th class="l">Line</th><th>USDA now</th><th>Desk</th><th>Leans</th><th class="l">Basis</th></tr>
            ${C.preview.signals.map(x => `<tr><td class="l">${esc(x.line)}</td><td>${f(x.usda, /yield/.test(x.line) ? 1 : undefined)}</td><td><b>${f(x.desk, /yield/.test(x.line) ? 1 : undefined)}</b></td><td class="${x.dir === 'up' ? 'up' : x.dir === 'down' ? 'dn' : ''}">${x.dir}</td><td class="l sv-w">${esc(x.basis)}</td></tr>`).join('')}</table></div>` : '<p class="note">See the cotton brief for the crop and export cross-checks.</p>'}
            <p class="note">Counts are past ${C.preview.month} reports for the marketing year in focus. Trade estimates (analyst surveys) are not public data, so compare with your own survey sheet before the release.</p></div></div></div>` : ''}
        ${B ? `<div class="card" style="margin-top:12px"><h2>Balance sheets — this report vs previous, last three marketing years</h2>
          <div class="tbar"><div class="grp"><span class="lab">Region</span>${Object.keys(B.regions).map(r => `<button class="chip ${r === (S.region && B.regions[S.region] ? S.region : Object.keys(B.regions)[0]) ? 'on' : ''}" data-r="${esc(r)}">${esc(r)}</button>`).join('')}</div></div>
          <div class="tbl" id="wvBS"></div></div>` : ''}
        <div class="card" style="margin-top:12px"><h2>Revision path — each marketing year, release by release</h2>
          <div class="tbar"><div class="grp"><span class="lab">Series</span><select id="wvRevSel"></select></div></div>
          <div style="height:340px"><canvas id="wvRev"></canvas></div>
          <p class="note">x-axis = report month; one line per marketing year (bold = current). Shows how USDA has walked each estimate over the season.</p></div>`;
      if (B) {
        const bs = () => {
          const reg = S.region && B.regions[S.region] ? S.region : Object.keys(B.regions)[0];
          el.querySelectorAll('[data-r]').forEach(b => b.classList.toggle('on', b.dataset.r === reg));
          el.querySelector('#wvBS').innerHTML = `<table><tr><th class="l">${esc(reg)}</th>${B.mys.map(m => `<th colspan=3>${m}</th>`).join('')}</tr>
            <tr><th></th>${B.mys.map(() => '<th>This</th><th>Prev</th><th>Chg</th>').join('')}</tr>
            ${B.regions[reg].map(r => `<tr${/Ending|Stocks\/use|Production|Exports/.test(r.attr) ? ' class="wv-hl"' : ''}><td class="l">${esc(r.attr)} <span class="note">${esc(shortU(r.unit))}</span></td>${B.mys.map(m => { const [a, b] = r.vals[m] || []; return `<td>${f(a)}</td><td class="note">${f(b)}</td><td>${a != null && b != null ? ch(a - b) : '–'}</td>`; }).join('')}</tr>`).join('')}</table>`;
        };
        el.querySelectorAll('[data-r]').forEach(b => b.onclick = () => { S.region = b.dataset.r; bs(); });
        bs();
      }
      // revisions
      if (!revs) revs = opts.cotton ? null : await getJSON(opts.base + 'revisions.json').then(d => d[opts.key]).catch(() => null);
      const sel = el.querySelector('#wvRevSel');
      if (!revs) { sel.innerHTML = '<option>not available</option>'; return; }
      const keys = Object.keys(revs); S.rev = S.rev && revs[S.rev] ? S.rev : keys[0];
      sel.innerHTML = keys.map(k => `<option value="${esc(k)}" ${k === S.rev ? 'selected' : ''}>${esc(revs[k].region)} · ${esc(revs[k].attr)}</option>`).join('');
      const drawRev = () => {
        const R2 = revs[S.rev], mys = Object.keys(R2.mys), L = Math.max(...mys.map(m => R2.mys[m].length));
        const cur = mys.at(-1);
        const lng = mys.map(m => R2.mys[m]).sort((a, b) => b.length - a.length)[0], m0 = +lng[0][0].slice(5) - 1;
        const lab = Array.from({ length: L }, (_, i) => MON[(m0 + i) % 12] + (i >= 12 ? ` (yr ${Math.floor(i / 12) + 1})` : ''));
        chart('wvRev', { type: 'line', data: { labels: lab, datasets: mys.map((m, j) => ({ label: m, data: R2.mys[m].map(p => p[1]), borderColor: m === cur ? '#c0392b' : PAL[(j + 2) % PAL.length], borderWidth: m === cur ? 3 : 1.4, pointRadius: m === cur ? 3 : 0, tension: .2 })) },
          options: { plugins: { tooltip: { callbacks: { title: c => { const m = c[0].dataset.label, p = R2.mys[m][c[0].dataIndex]; return p ? p[0] : ''; } } } }, scales: { y: { title: { display: true, text: shortU(R2.unit) } } } } });
      };
      sel.onchange = e => { S.rev = e.target.value; drawRev(); };
      drawRev();
    }
    draw();
  }
  const shortU = u => String(u || '').replace(/Million Bushels/i, 'm bu').replace(/Million Metric Tons/i, 'MMT').replace(/Million Acres/i, 'm ac').replace(/Bushels/i, 'bu/ac')
    .replace(/Thousand Short Tons/i, 'k st').replace(/Million Pounds/i, 'm lb').replace(/Million 480 Lb. Bales/i, 'm bales').replace(/Dollars per Bushel/i, '$/bu');

  // cotton brief files (wasde-analytics) carry a cotton block per report; map to this view's shape
  function adaptCotton(R) {
    const c = R.Cotton; if (!c) return null;
    return { name: 'Cotton', my: c.my, unit: 'm 480-lb bales', wunit: 'm 480-lb bales', changes: c.changes.map(r => ({ ...r, region: r.region })),
      history: c.history, factors: c.factors, score: c.score, outlook: c.outlook, brief: c.brief, balance: null };
  }
  return { mount };
})();
