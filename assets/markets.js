// Markets & macro: heat map of commodities, stock indices, currencies and US rates (Yahoo Finance, delayed),
// US Treasury curve, US economic snapshot, macro read for ags, and the US economic calendar.
const Markets = (() => {
  let built = false, M = null, X = null, C = null, U = null, hz = 'd1', cty = 'US', imp = 'HM';
  const H = [['d1', '1 day'], ['w1', '1 week'], ['m1', '1 month'], ['m3', '3 months'], ['ytd', 'YTD'], ['y1', '1 year']];
  const fx = (v, d) => v == null ? '–' : (+v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  const dp = x => x.kind === 'yield' ? 3 : x.last >= 1000 ? 1 : x.last >= 10 ? 2 : x.last >= 1 ? 3 : 4;
  const scale = k => k === 'd1' ? 2.5 : k === 'w1' ? 5 : k === 'm1' ? 8 : k === 'm3' ? 12 : 20;
  function col(v, x) {
    if (v == null) return 'var(--card, #fff)';
    const s = x.kind === 'yield' ? v / (scale(hz) * 8) : v / scale(hz);   // yields in bp
    const a = Math.min(1, Math.abs(s));
    const up = x.sym === '^VIX' ? v < 0 : v > 0;
    return up ? `rgba(22,140,72,${0.12 + 0.75 * a})` : `rgba(200,50,40,${0.12 + 0.75 * a})`;
  }
  const lbl = (v, x) => v == null ? '–' : x.kind === 'yield' ? `${v > 0 ? '+' : ''}${v.toFixed(0)} bp` : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
  function spark(a) {
    if (!a || a.length < 2) return '';
    const lo = Math.min(...a), hi = Math.max(...a), w = 90, h = 22;
    const pts = a.map((v, i) => `${(i / (a.length - 1) * w).toFixed(1)},${(h - (hi === lo ? h / 2 : (v - lo) / (hi - lo) * h)).toFixed(1)}`).join(' ');
    return `<svg width="${w}" height="${h}" class="mk-spark"><polyline fill="none" stroke="currentColor" stroke-width="1.2" points="${pts}"/></svg>`;
  }
  function heat() {
    const groups = [...new Set(M.items.map(x => x.group))];
    return groups.map(g => `<h3 class="mk-g">${g}</h3><div class="mk-grid">${M.items.filter(x => x.group === g).map(x => {
      const v = x[hz];
      return `<div class="mk-tile" style="background:${col(v, x)}" title="${x.name} · ${x.sym} · last trade ${x.time} (${x.delay_min == null ? 'delay n/a' : x.delay_min ? '~' + x.delay_min + ' min delayed' : 'real time'})
1d ${lbl(x.d1, x)} · 1w ${lbl(x.w1, x)} · 1m ${lbl(x.m1, x)} · YTD ${lbl(x.ytd, x)} · 1y ${lbl(x.y1, x)}
52-wk range ${fx(x.lo52, dp(x))}–${fx(x.hi52, dp(x))} (at ${x.pos52 ?? '–'}%) · RSI ${x.rsi ?? '–'} · trend vs 20/50/200-day ${x.trend > 0 ? '+' : ''}${x.trend}">
        <div class="mk-n">${x.name}${x.contract ? ` <span class="mk-k">${x.contract.replace('-20', ' ')}</span>` : ''}</div><div class="mk-v">${fx(x.last, dp(x))}${x.kind === 'yield' ? '%' : ''}</div><div class="mk-c">${lbl(v, x)}</div>${spark(x.spark)}
        ${x.age_min > 240 && x.group !== 'US rates' ? `<div class="mk-age">last ${x.time.slice(5, 16)}</div>` : ''}</div>`;
    }).join('')}</div>`).join('');
  }
  function table() {
    return `<div class="tbl"><table><tr><th class="l">Market</th><th>Last</th><th>1 d</th><th>1 w</th><th>1 m</th><th>3 m</th><th>YTD</th><th>1 y</th><th>52-wk pos</th><th>RSI</th><th>Trend</th><th>Move (σ)</th><th class="l">Last trade</th></tr>
      ${M.items.map(x => `<tr><td class="l">${x.name} <span class="note">${x.contract || x.sym}</span></td><td>${fx(x.last, dp(x))}</td>${['d1', 'w1', 'm1', 'm3', 'ytd', 'y1'].map(k => `<td class="${(x[k] || 0) > 0 ? 'up' : (x[k] || 0) < 0 ? 'dn' : ''}">${lbl(x[k], x)}</td>`).join('')}
        <td>${x.pos52 ?? '–'}%</td><td>${x.rsi ?? '–'}</td><td>${x.trend > 0 ? '+' : ''}${x.trend}</td><td>${x.z1 ?? '–'}</td><td class="l note">${x.time}</td></tr>`).join('')}</table></div>`;
  }
  function curve(el) {
    const T = M.treasury; if (!T || !window.Chart) return;
    const ds = [['now', 'Now', '#2f6db3'], ['m1', '1 month ago', '#c48a1c'], ['y1', '1 year ago', '#8a8984']].map(([k, l, c]) => ({ label: l, data: T.curve.map(t => t[k]), borderColor: c, backgroundColor: c, tension: .2, pointRadius: 2 }));
    new Chart(el.querySelector('#mkCurve'), { type: 'line', data: { labels: T.curve.map(t => t.tenor), datasets: ds }, options: { plugins: { legend: { position: 'bottom' } }, scales: { y: { title: { display: true, text: '%' } } } } });
    new Chart(el.querySelector('#mk210'), { type: 'line', data: { labels: T.hist_2y10y.map(r => r[0]), datasets: [{ label: '10y − 2y (bp)', data: T.hist_2y10y.map(r => r[1]), borderColor: '#2f6db3', pointRadius: 0, borderWidth: 1.5 }] },
      options: { plugins: { legend: { display: false } }, scales: { x: { ticks: { maxTicksLimit: 6 } }, y: { title: { display: true, text: 'bp' } } } } });
  }
  function cal() {
    if (!C) return '<p class="note">Calendar not built yet.</p>';
    const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
    const ev = C.events.filter(e => (cty === 'all' || e.country === cty) && (imp === 'all' || (imp === 'HM' ? /High|Medium/.test(e.impact) : e.impact === 'High')) && e.date >= addDays(today, -7));
    let last = '';
    return `<div class="tbl"><table><tr><th class="l">Date</th><th class="l">Time (ET)</th><th class="l">Country</th><th class="l">Release</th><th>Impact</th><th>Forecast</th><th>Previous</th><th class="l">Why it matters for commodities</th></tr>
      ${ev.map(e => { const d = e.date !== last ? (last = e.date, new Date(e.date + 'T12:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })) : '';
        return `<tr class="${e.date === today ? 'mk-today' : e.date < today ? 'mk-past' : ''}"><td class="l"><b>${d}</b></td><td class="l">${e.time || 'all day'}</td><td class="l">${e.country}</td><td class="l">${e.title}</td>
        <td><span class="mk-imp mk-${(e.impact || '').toLowerCase()}">${e.impact}</span></td><td>${e.forecast || '–'}</td><td>${e.previous || '–'}</td><td class="l note">${e.why || ''}</td></tr>`; }).join('') || '<tr><td colspan="8">No events.</td></tr>'}</table></div>
      <p class="note">${C.source}. Updated ${C.generated}.</p>`;
  }
  const addDays = (d, n) => { const t = new Date(d + 'T12:00'); t.setDate(t.getDate() + n); return t.toISOString().slice(0, 10); };
  function usCard() {
    if (!U) return '';
    const R = U.rates || {}, cats = ['Inflation', 'Jobs', 'Growth', 'Sentiment'];
    const sg = v => v == null ? '–' : (v > 0 ? '+' : '') + v.toFixed(1);
    const sp = a => { if (!a || a.length < 3) return ''; const v = a.map(x => x[1]), lo = Math.min(...v), hi = Math.max(...v), w = 110, h = 26;
      return `<svg width="${w}" height="${h}" class="mk-spark"><polyline fill="none" stroke="currentColor" stroke-width="1.3" points="${v.map((y, i) => `${(i / (v.length - 1) * w).toFixed(1)},${(h - (hi === lo ? h / 2 : (y - lo) / (hi - lo) * (h - 2)) - 1).toFixed(1)}`).join(' ')}"/></svg>`; };
    const main = i => i.kind === 'index' ? `${sg(i.yoy)}% y/y` : i.kind === 'k' ? `${sg(i.chg)}k` : `${i.value.toFixed(1)}${i.unit.startsWith('%') ? '%' : ''}`;
    const sub = i => i.kind === 'index' ? `m/m ${sg(i.mom)}%${i.ann3 != null ? ` · 3m ann. ${sg(i.ann3)}%` : ''} · prev ${sg(i.yoy_prev)}% y/y` : i.kind === 'k' ? `3-mo avg ${sg(i.avg3)}k · prev ${sg(i.chg_prev)}k` : `prev ${i.prev == null ? '–' : i.prev.toFixed(1)} (${sg(i.chg)})`;
    return `<div class="card" style="margin-top:12px"><h2>US economy snapshot <span class="note">${U.sources}; updated ${U.generated}</span></h2>
      <p><b>${U.read}</b></p>
      <div class="us-rates">${[['Fed funds target', R.target_lo != null ? `${R.target_lo}–${R.target_hi}%` : '–', `effective ${R.effr ?? '–'}% (${R.effr_date || ''})`],
        ['SOFR', R.sofr != null ? R.sofr + '%' : '–', R.sofr_date || ''], ['2-year Treasury', R.y2 != null ? R.y2.toFixed(2) + '%' : '–', R.y2_minus_ff != null ? `${R.y2_minus_ff > 0 ? '+' : ''}${R.y2_minus_ff} vs fed funds` : ''],
        ['10-year Treasury', R.y10 != null ? R.y10.toFixed(2) + '%' : '–', R.y3m != null ? `3m ${R.y3m}% · 30y ${R.y30}%` : ''], ['10-yr real yield (TIPS)', R.real10 != null ? R.real10.toFixed(2) + '%' : '–', R.real_date || ''],
        ['10-yr breakeven inflation', R.breakeven10 != null ? R.breakeven10.toFixed(2) + '%' : '–', R.breakeven5 != null ? `5-yr ${R.breakeven5}%` : '']]
        .map(([a, b, c]) => `<div class="us-tile"><div class="note">${a}</div><div class="us-v">${b}</div><div class="note">${c}</div></div>`).join('')}</div>
      ${(R.last_moves || []).length ? `<p class="note">Recent Fed moves: ${R.last_moves.map(m => `${m[0]} ${m[1] > 0 ? '+' : ''}${Math.round(m[1] * 100)} bp`).join(' · ')}</p>` : ''}
      ${cats.map(c => { const xs = U.indicators.filter(i => i.cat === c); return !xs.length ? '' : `<h3>${c}</h3><div class="us-grid">${xs.map(i => `<div class="us-tile" title="${i.name} · ${i.source}${i.note ? ' · ' + i.note : ''}">
        <div class="note">${i.name} · ${i.period}</div><div class="us-v">${main(i)}</div><div class="note">${sub(i)}</div>${sp(i.spark)}
        ${i.next ? `<div class="note">next ${i.next.date.slice(5)} ${i.next.time}${i.next.forecast ? ` · f'cast ${i.next.forecast}` : ''}</div>` : ''}</div>`).join('')}</div>`; }).join('')}
      <p class="note">Sparklines: last 24 months (y/y % for price indexes, monthly change for payrolls). No API keys are needed; FRED would add more series with a free key.</p></div>`;
  }
  function render() {
    const el = document.getElementById('markets');
    el.innerHTML = `<main>
      ${X ? `<div class="card"><h2>Macro outlook for commodities &amp; ags <span class="sv-badge" style="border-color:${X.view === 'tailwind' ? 'var(--up)' : X.view === 'headwind' ? 'var(--dn)' : '#666'};color:${X.view === 'tailwind' ? 'var(--up)' : X.view === 'headwind' ? 'var(--dn)' : '#666'}">${X.view} (${X.score > 0 ? '+' : ''}${X.score})</span></h2>
        <p><b>${X.summary}</b></p><div class="grid g2">${X.sections.map(s => `<div><h3>${s.title} <span class="${s.score > 0 ? 'up' : s.score < 0 ? 'dn' : 'note'}">${s.score > 0 ? '▲ tailwind' : s.score < 0 ? '▼ headwind' : '● neutral'}</span></h3><p>${s.text}</p></div>`).join('')}</div>
        <p class="note">${X.caveat} Updated ${X.generated}.</p></div>` : ''}
      ${usCard()}
      <div class="card" style="margin-top:12px"><h2>Heat map</h2>
        <div class="mk-bar">${H.map(([k, l]) => `<button data-h="${k}" class="${k === hz ? 'on' : ''}">${l}</button>`).join('')} <label class="note"><input type="checkbox" id="mkTbl"> table view</label></div>
        <div id="mkHeat">${heat()}</div>
        <p class="note">${M.source}. Snapshot ${M.generated}. Futures are the front contract Yahoo shows (month in the tile); all changes are measured on that contract, so a roll never shows as a move, and YTD/1-year are blank when the contract did not trade then. During the session the last price is the latest trade, not the settlement. Yields change in basis points. Hover a tile for details.</p></div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>US Treasury yield curve <span class="note">${M.treasury ? M.treasury.date : ''}</span></h2><canvas id="mkCurve" height="200"></canvas>
          ${M.treasury ? `<p class="note">2s10s ${M.treasury.s2s10_bp} bp (${M.treasury.s2s10_chg_1m_bp > 0 ? '+' : ''}${M.treasury.s2s10_chg_1m_bp} bp in a month); 3m10y ${M.treasury.s3m10_bp} bp. Source: US Treasury daily par yield curve (end of day).</p>` : ''}</div>
        <div class="card"><h2>2s10s, last year</h2><canvas id="mk210" height="200"></canvas></div></div>
      <div class="card" style="margin-top:12px"><h2>US economic calendar</h2>
        <div class="mk-bar">${[['High', 'High impact'], ['HM', 'High + medium'], ['all', 'All']].map(([k, l]) => `<button data-i="${k}" class="${k === imp ? 'on' : ''}">${l}</button>`).join('')}</div>
        <div id="mkCal">${cal()}</div></div></main>`;
    el.querySelectorAll('[data-h]').forEach(b => b.onclick = () => { hz = b.dataset.h; render(); });
    el.querySelectorAll('[data-i]').forEach(b => b.onclick = () => { imp = b.dataset.i; render(); });
    el.querySelector('#mkTbl').onchange = e => { el.querySelector('#mkHeat').innerHTML = e.target.checked ? table() : heat(); };
    curve(el);
  }
  async function show() {
    if (!built) {
      [M, X, C, U] = await Promise.all(['data/markets/markets.json', 'data/macro/macro.json', 'data/macro/econ_calendar.json', 'data/macro/us_econ.json'].map(u => getJSON(u).catch(() => null)));
      built = true;
    }
    history.replaceState(null, '', '#markets');
    if (!M) { document.getElementById('markets').innerHTML = '<main><div class="card"><p class="note">Market snapshot not built yet.</p></div></main>'; return; }
    render();
  }
  return { show };
})();
