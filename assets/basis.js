// Basis tab: cash minus nearby futures for cotton, grains and livestock, its seasonal pattern and what followed.
// Data: data/basis/<SYM>.json + summary.json (models/basis_desk.py); cotton from the cotton-crop-progress site.
// Deep link: #basis/<SYM>. Basis.mount(el, sym) embeds one market (used by the Cotton tab).
const Basis = (() => {
  const ORG = 'https://bmr-com.github.io';
  const COTTON = ORG + '/cotton-crop-progress/basis.html';
  let S = null, D = {}, sym = 'LE', loc = null, built = false;
  const f = (v, d = 2) => v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
  const nth = v => v == null ? '' : `${v}${v % 100 >= 11 && v % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' })[v % 10] || 'th'}`;
  const col = (v, s) => { if (v == null || isNaN(v)) return ''; const a = Math.min(1, Math.abs(v) / s) * 0.5; return `background:rgba(${v >= 0 ? '31,122,58' : '179,38,30'},${a.toFixed(3)})`; };
  const css = `<style>
    .bs .sz-chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0}
    .bs .sz-chips .lab{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-right:4px}
    .bs .sz-chip{font:inherit;font-size:12px;padding:3px 10px;border-radius:999px;border:1px solid var(--line);background:#fff;color:#444;cursor:pointer}
    .bs .sz-chip.on{background:var(--acc);border-color:var(--acc);color:#fff}
    .bs .card{margin-bottom:12px}
    .bs .kp{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:8px 0}
    @media(max-width:900px){.bs .kp{grid-template-columns:repeat(2,minmax(0,1fr))}}
    .bs .kp>div{border:1px solid var(--line);border-radius:8px;padding:8px 10px}
    .bs .kp .l{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}.bs .kp .v{font-size:19px;font-weight:600}.bs .kp .s{font-size:11px;color:var(--muted)}
    .bs .st{display:inline-block;font-size:11px;font-weight:600;padding:1px 7px;border-radius:6px;background:#eee;color:#555}
    .bs .st.Weak{background:#fbe9e7;color:var(--dn)}.bs .st.Firm{background:#e6f4ea;color:var(--up)}
    .bs .idea{border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:8px;padding:10px 12px;background:#fafaf7}
    .bs td.l{text-align:left;white-space:normal}.bs tr.on td{font-weight:700;background:#f4f6f0}
    .bs .two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}@media(max-width:1000px){.bs .two{grid-template-columns:minmax(0,1fr)}}
    .bs iframe.bsframe{width:100%;height:calc(100vh - 160px);min-height:900px;border:1px solid var(--line);border-radius:8px;background:#fff}
  </style>`;
  const MKTS = [['CT', 'Cotton'], ['ZC', 'Corn'], ['ZS', 'Soybeans'], ['ZW', 'Chicago wheat'], ['KE', 'KC wheat'], ['LE', 'Live cattle'], ['HE', 'Lean hogs']];

  function chips(el, items, cur, cb, label) {
    el.innerHTML = (label ? `<span class="lab">${label}</span>` : '') + items.map(it => `<button class="sz-chip${it[0] === cur ? ' on' : ''}" data-k="${it[0]}">${it[1]}</button>`).join('');
    $$('button', el).forEach(b => b.onclick = () => cb(b.dataset.k));
  }
  function overview() {
    if (!S) return '';
    return `<div class="tbl"><table><tr><th class="l">Market</th><th class="l">Cash series</th><th>Basis</th><th>Vs normal</th><th>State</th><th class="l">Lean</th><th>History</th></tr>
      <tr><td class="l"><a href="#basis/CT" data-s="CT">Cotton</a></td><td class="l">AMS spot 41-4-34, designated markets</td><td colspan="4" class="l note">See the cotton page (Cotton → Basis &amp; ideas)</td><td>2000–</td></tr>
      ${S.markets.map(m => `<tr><td class="l"><a href="#basis/${m.sym}" data-s="${m.sym}">${m.name}</a></td><td class="l">${m.location}</td><td>${f(m.basis)} <span class="note">${m.unit}</span></td><td>${f(m.anom)}</td>
        <td><span class="st ${m.state || ''}">${m.state || '–'}</span>${m.pct != null ? ` <span class="note">${nth(m.pct)} pct</span>` : ''}</td>
        <td class="l">${m.idea ? `<b>${m.idea.side}</b>, next ${m.idea.horizon} weeks${m.idea.in_window ? '' : ' (outside its window)'}` : '<span class="note">no lean</span>'}</td><td>${m.since.slice(0, 4)}–</td></tr>`).join('')}</table></div>`;
  }
  function shell(el, single) {
    el.innerHTML = css + `<div class="bs">${single ? '' : `<div class="card"><h2>Cash basis — cash minus nearby futures</h2>
      <p class="note" id="bsAsof"></p><div id="bsOver"></div><div class="sz-chips" id="bsMk"></div>
      <p class="note">"Vs normal" compares basis with its usual level for the same week in other seasons. A lean is shown only where basis has led futures consistently across seasons: live cattle (weak basis before lower futures, firm before higher, 2005 on), Chicago wheat (a weak Illinois SRW basis before lower futures, 2007 on) and cotton. For corn, soybeans, KC wheat and lean hogs, weak and firm basis were followed by about the same futures moves over 20 seasons, so the page shows where basis stands without a lean.</p></div>`}
      <div id="bsBody"></div></div>`;
  }
  async function go(k, el) {
    sym = k; loc = null;
    if (!el.dataset.single) { history.replaceState(null, '', '#basis/' + sym); chips($('#bsMk'), MKTS, sym, x => go(x, el), 'Market'); }
    const body = $('#bsBody', el);
    if (sym === 'CT') { body.innerHTML = `<div class="card" style="padding:6px"><iframe class="bsframe" src="${COTTON}" title="Cotton basis and trade ideas" loading="lazy" referrerpolicy="no-referrer" sandbox="allow-scripts allow-same-origin allow-popups"></iframe></div>`; return; }
    if (!D[sym]) D[sym] = await getJSON(`data/basis/${sym}.json`);
    paint(body);
  }
  function paint(body) {
    const d = D[sym]; if (!loc) loc = d.locations[0].location;
    const L = d.locations.find(x => x.location === loc), n = L.now, u = d.unit, idea = d.idea;
    const H = [1, 2, 4, 8];
    const rec = L.record ? `<div class="tbl"><table><tr><th class="l">Basis state (${L.window})</th><th>Weeks</th>${H.map(h => `<th>Futures ${h}w</th>`).join('')}${H.map(h => `<th>% up ${h}w</th>`).join('')}${[1, 4, 8].map(h => `<th>Spread ${h}w $/lot</th>`).join('')}</tr>
      ${L.record.map(r => `<tr class="${r.state === n.state ? 'on' : ''}"><td class="l">${r.state}${r.state === n.state ? ' (now)' : ''}</td><td>${r.n}</td>${H.map(h => `<td style="${col(r['px' + h], 3)}">${f(r['px' + h])}%</td>`).join('')}
        ${H.map(h => `<td>${r['up' + h] ?? '–'}%</td>`).join('')}${[1, 4, 8].map(h => `<td>${r['sp' + h] == null ? '–' : (r['sp' + h] >= 0 ? '+' : '−') + '$' + Math.abs(r['sp' + h]).toLocaleString()}</td>`).join('')}</tr>`).join('')}</table></div>` : '<p class="note">Not enough history yet.</p>';
    body.innerHTML = `<div class="card"><h2>${d.name}: ${L.location}</h2>
      <div class="sz-chips" id="bsLoc"></div>
      <div class="kp"><div><div class="l">Cash</div><div class="v">${(+n.cash).toFixed(2)}</div><div class="s">${u} · ${L.cash_as_of}${L.stale ? ' <b class="dn">(no recent quote)</b>' : ''}</div></div>
        <div><div class="l">Nearby futures</div><div class="v">${(+n.fut).toFixed(2)}</div><div class="s">${n.near}</div></div>
        <div><div class="l">Basis</div><div class="v">${f(n.basis)}</div><div class="s">normal this week ${f(n.norm)}</div></div>
        <div><div class="l">Vs normal</div><div class="v">${f(n.anom)}</div><div class="s"><span class="st ${n.state || ''}">${n.state || '–'} basis</span> ${n.pct != null ? nth(n.pct) + ' pct' : ''}</div></div>
        <div><div class="l">4-week change</div><div class="v">${f(n.chg4)}</div><div class="s">${u}</div></div>
        <div><div class="l">Same week, past seasons</div><div class="v" style="font-size:15px">${n.same_week ? f(n.same_week[0], 1) + ' to ' + f(n.same_week[1], 1) : '–'}</div><div class="s">10th–90th percentile</div></div></div>
      ${!d.tested ? `<p class="note">No reliable lead from basis for ${d.name.toLowerCase()}: weak and firm basis were followed by about the same futures moves. Shown for reference.</p>` :
        idea && L.primary ? `<div class="idea"><b>${idea.side} on ${d.name.toLowerCase()} futures, next ${idea.horizon} weeks</b>${idea.in_window ? '' : ' <span class="note">(outside the months it was tested in)</span>'}<br>
          <span class="note">${L.location} basis is ${n.state.toLowerCase()} for the time of year. In the ${n.state.toLowerCase()} third since ${L.since.slice(0, 4)}, the front contract moved ${f(idea.avg)}% on average over ${idea.horizon} weeks and went the lean's way ${idea.hit}% of the time (${idea.n} weeks).</span></div>` :
        (L.stale ? `<p class="note">USDA has not quoted this series since ${L.cash_as_of}, so there is no current reading.</p>` : `<p class="note">Basis is ${n.state ? n.state.toLowerCase() : '–'} for the time of year${L.primary ? ' — no lean (the lean only triggers in the weak or firm third)' : '; the lean uses the ' + d.locations[0].location + ' series'}.</p>`)}
      </div>
      <div class="two"><div class="card"><h2>Basis through the ${L.seasonal.season_kind.toLowerCase()} (${L.seasonal.start_month} start)</h2>
        <div class="note"><span style="color:#2a78d6">■</span> this season &nbsp;<span style="color:#eb6834">■</span> last season &nbsp;<span style="color:#8a8984">■</span> 5-season average &nbsp; shaded: 10–90th and 25–75th percentile, ${L.seasonal.n_years} seasons</div>
        <div style="position:relative;height:300px"><canvas id="bsSeas"></canvas></div></div>
      <div class="card"><h2>What followed, by basis state</h2>${rec}
        <p class="note">Weak / normal / firm = thirds of basis vs its normal for the week. Futures = % change of the nearest contract not rolling in the period; spread = that contract minus the next, $ per one-lot spread (positive = front gained). Each row starts at the first close after the cash number is published. ${L.seasons} seasons since ${L.since.slice(0, 4)}.</p></div></div>
      <div class="card"><h2>Basis history (weekly, ${u})</h2><div style="position:relative;height:260px"><canvas id="bsHist"></canvas></div></div>`;
    chips($('#bsLoc', body), d.locations.map(x => [x.location, x.location + (x.primary ? ' ★' : '')]), loc, k => { loc = k; paint(body); }, 'Cash series');
    const s = L.seasonal, P = a => (a || []).map(p => ({ x: p[0], y: p[1] })), m0 = MON.indexOf(s.start_month);
    const wl = w => new Date(Date.UTC(2001, m0, 1 + 7 * w)).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
    const band = 'rgba(138,137,132,.16)', band2 = 'rgba(138,137,132,.28)';
    chart('bsSeas', { type: 'line', data: { datasets: [
      { label: '_90', data: P(s.bands[90]), borderWidth: 0, pointRadius: 0, fill: false }, { label: '10–90th', data: P(s.bands[10]), borderWidth: 0, pointRadius: 0, backgroundColor: band, fill: '-1' },
      { label: '_75', data: P(s.bands[75]), borderWidth: 0, pointRadius: 0, fill: false }, { label: '25–75th', data: P(s.bands[25]), borderWidth: 0, pointRadius: 0, backgroundColor: band2, fill: '-1' },
      { label: 'Median', data: P(s.bands[50]), borderColor: '#8a8984', borderWidth: 1, pointRadius: 0, borderDash: [2, 3] },
      { label: '5-season avg', data: P(s.avg5), borderColor: '#8a8984', borderWidth: 1.5, pointRadius: 0, borderDash: [5, 4] },
      { label: 'Last season', data: P(s.last_year), borderColor: '#eb6834', borderWidth: 1.8, pointRadius: 0 },
      { label: 'This season', data: P(s.current), borderColor: '#2a78d6', borderWidth: 2.8, pointRadius: 0 }] },
      options: { plugins: { legend: { display: false }, tooltip: { filter: i => !i.dataset.label.startsWith('_'), callbacks: { title: i => 'Week of ' + wl(i[0].parsed.x), label: c => `${c.dataset.label}: ${c.parsed.y.toFixed(2)} ${u}` } } },
        scales: { x: { type: 'linear', min: 0, max: 52, ticks: { callback: v => wl(v), stepSize: 4.35, maxTicksLimit: 13 } } } } });
    chart('bsHist', { type: 'line', data: { labels: L.weekly.map(p => p[0]), datasets: [{ label: 'Basis', data: L.weekly.map(p => p[1]), borderColor: '#2a78d6', borderWidth: 1.4, pointRadius: 0 }] },
      options: { plugins: { legend: { display: false } }, scales: { x: { ticks: { maxTicksLimit: 10 } } } } });
  }
  async function load() { if (!S) S = await getJSON('data/basis/summary.json'); }
  async function show() {
    const el = document.getElementById('basis');
    if (!built) { shell(el, false); built = true; }
    try { await load(); } catch (e) { $('#bsAsof').textContent = 'Could not load basis data.'; return; }
    $('#bsAsof').textContent = `Weekly readings · rebuilt ${S.generated}`;
    $('#bsOver').innerHTML = overview();
    $$('#bsOver a[data-s]').forEach(a => a.onclick = e => { e.preventDefault(); go(a.dataset.s, el); });
    const want = (location.hash.match(/^#basis\/(\w+)/) || [])[1];
    go(want && MKTS.some(m => m[0] === want) ? want : sym, el);
  }
  function mount(el, s) { el.dataset.single = '1'; shell(el, true); go(s, el); }
  return { show, mount };
})();
