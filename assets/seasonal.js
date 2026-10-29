// Seasonality and technical studies for every desk market (data/seasonal/<SYM>.json, summary.json; models/seasonal_desk.py;
// data/backtest/tech.json). Crops run on their marketing year, livestock, dairy and energy on the calendar year.
//   Seasonal.show()                      top-level Seasonality tab, deep link #seasonal/<SYM>
//   MktStudy.mount(el, syms)             per-commodity "Seasonality & technicals" sub-tab (picker when several symbols)
//   MktStudy.upcoming(el, syms, onOpen)  compact Outlook card: seasonal windows due soon + best tested pattern
(() => {
  if (document.getElementById('szCss')) return;
  const st = document.createElement('style'); st.id = 'szCss';
  st.textContent = `
    .sz .sz-chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0}
    .sz .sz-chips .lab{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-right:4px}
    .sz .sz-chip{font:inherit;font-size:12px;padding:3px 10px;border-radius:999px;border:1px solid var(--line);background:#fff;color:#444;cursor:pointer}
    .sz .sz-chip.on{background:var(--acc);border-color:var(--acc);color:#fff}
    .sz .sz-grp{font-size:11px;color:var(--muted);margin:0 2px 0 8px}
    .sz tr.sz-due td{background:#fffbea}
    .sz .sz-tag{display:inline-block;font-size:10px;font-weight:700;padding:1px 6px;border-radius:5px;background:#ffe066;color:#5b4500;margin-left:6px}
    .sz .sz-l5 span{display:inline-block;min-width:34px;padding:1px 4px;margin:0 1px;border-radius:4px;text-align:center}
    .sz .sz-hm td{text-align:center;min-width:50px}
    .sz .sz-hm td:first-child{text-align:left;font-weight:600}
    .sz .sz-hm td small{display:block;font-size:10px;opacity:.75}
    .sz .sz-grid td{text-align:center;min-width:40px;padding:4px 3px}
    .sz .sz-grid tr.ft td{font-weight:700;border-top:2px solid var(--line)}
    .sz td.l{text-align:left;white-space:normal}
    .sz .sz-two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}
    @media(max-width:1000px){.sz .sz-two{grid-template-columns:minmax(0,1fr)}}
    .sz .card{margin-bottom:12px}
    .sz h2.sz-sec{margin:18px 0 8px;font-size:15px;border-bottom:2px solid var(--line);padding-bottom:4px}`;
  document.head.appendChild(st);
})();

const SzData = (() => {
  let S = null, TL;
  const D = {};
  return {
    summary: async () => S || (S = await getJSON('data/seasonal/summary.json')),
    market: async sym => D[sym] || (D[sym] = await getJSON(`data/seasonal/${sym}.json`)),
    tech: async () => TL !== undefined ? TL : (TL = await getJSON('data/backtest/tech.json').catch(() => null)),
  };
})();

const szF = (v, d = 1) => v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
const szCol = (v, s) => { if (v == null || isNaN(v)) return ''; const a = Math.min(1, Math.abs(v) / s) * 0.5; return `background:rgba(${v >= 0 ? '31,122,58' : '179,38,30'},${a.toFixed(3)})`; };
const szDays = d => { const t = new Date(); return Math.round((new Date(d + 'T00:00:00Z') - Date.UTC(t.getFullYear(), t.getMonth(), t.getDate())) / 864e5); };
const szUsd = v => v == null ? '' : `${v >= 0 ? '+' : '−'}$${Math.abs(Math.round(v)).toLocaleString()}`;
function szChips(el, items, cur, cb, label) {
  el.innerHTML = (label ? `<span class="lab">${label}</span>` : '') + items.map(it => it.grp ? `<span class="sz-grp">${it.grp}</span>` :
    `<button class="sz-chip${it[0] === cur ? ' on' : ''}" data-k="${it[0]}">${it[1]}</button>`).join('');
  $$('button', el).forEach(b => b.onclick = () => cb(b.dataset.k));
}
function szTradeRows(S, L, link) {
  const unit = s => (S.markets.find(m => m.sym === s) || {}).unit || '';
  let h = '<tr><th class="l">Market</th><th class="l">Trade</th><th>Next window</th><th>% of years worked</th><th>Last 10 yrs</th><th>Average per trade</th><th>Worst year</th><th>Last 5 years</th><th>Years</th></tr>';
  if (!L.length) h += '<tr><td colspan="9" class="l note">No rule passes the screen for this market.</td></tr>';
  L.forEach(t => {
    const d = szDays(t.next_entry), due = d >= 0 && d <= 45, u = unit(t.sym);
    const avg = t.avg_pct != null ? `${szF(t.avg_pct, 2)}%${t.usd != null ? ' · ' + szUsd(t.usd) : ''}` : `${szF(t.avg_chg, 3)} ${u} · ${szUsd(t.usd)}`;
    const worst = t.worst_pct != null ? szF(t.worst_pct, 1) + '%' : `${szF(t.worst_chg, 3)} ${u}`;
    const sc = t.avg_pct != null ? 5 : Math.abs(t.avg_chg) * 2 || 1;
    h += `<tr class="${due ? 'sz-due' : ''}"><td class="l">${link ? `<a href="#seasonal/${t.sym}" data-s="${t.sym}">${t.market}</a>` : t.market}</td><td class="l">${t.what}${t.contract ? ` <span class="note">(${t.contract})</span>` : ''}${due ? `<span class="sz-tag">in ${d}d</span>` : d < 0 && d >= -10 ? '<span class="sz-tag">open</span>' : ''}</td>
      <td>${t.next_entry} → ${t.next_exit}</td><td><b>${t.hit}%</b></td><td>${t.hit_last10 == null ? '–' : t.hit_last10 + '%'}</td><td>${avg}</td><td class="dn">${worst}</td>
      <td class="sz-l5">${(t.last5 || []).map(x => `<span style="${szCol(x, sc)}">${szF(x, t.avg_pct != null ? 1 : 2)}</span>`).join('')}</td><td>${t.n}</td></tr>`;
  });
  return h;
}

// One seasonality view in `root`. opts.full = top-level tab (market bar + trade scope chips); otherwise embedded, one market at a time.
function SeasonView(root, opts = {}) {
  const p = opts.prefix || 'sz', full = !!opts.full;
  let S = null, cur = null, sym = opts.sym || 'ZC', scope = full ? 'soon' : 'mk', hm = 'avg', sp = 'avg', seasKey = null;
  const q = id => root.querySelector('#' + p + id);
  root.classList.add('sz');
  root.innerHTML = `
    ${full ? `<div class="card"><h2>Seasonality — every desk market</h2>
      <p class="note" id="${p}Asof"></p><div class="sz-chips" id="${p}Mk"></div>
      <p class="note">Crops are shown on their marketing year (corn, soybeans, meal and oil Sep–Aug; wheat Jun–May; cotton Aug–Jul). Livestock, dairy and energy have no crop year, so they run on the calendar year (Jan–Dec), and contracts roll every month for dairy and energy.</p></div>` : ''}
    <div class="card"><h2 id="${p}TrH">Seasonal trades</h2>${full ? '' : `<p class="note" id="${p}Asof"></p>`}
      <p class="note">Rules that worked in at least 70% of years, are statistically clear (t ≥ 2) and worked in both halves of the history (before and after 2016). Rows are highlighted when the next window starts within 45 days. Spreads are one lot each leg; "sell front" = short the nearby, long the deferred.${full ? ' Energy history starts 2015, so energy rules rest on about 11 years.' : ''}</p>
      ${full ? `<div class="sz-chips" id="${p}Scope"></div>` : ''}<div class="tbl"><table id="${p}Trades"></table></div></div>
    <div class="card"><h2 id="${p}PathH">Front contract through the season</h2>
      <p class="note" id="${p}PathNote"></p>
      <div style="position:relative;height:320px"><canvas id="${p}Path"></canvas></div>
      <div class="tbl" style="margin-top:8px"><table id="${p}PathYrs"></table></div></div>
    <div class="card"><h2>Contracts and spreads by weeks to the roll date</h2>
      <div class="sz-chips" id="${p}SeasChips"></div>
      <div class="note" style="margin:2px 0 6px"><span style="color:#2a78d6">■</span> current contract &nbsp; <span style="color:#eb6834">■</span> same contract last year &nbsp; <span style="color:#8a8984">■</span> 5-year average &nbsp; shaded: 10–90th and 25–75th percentile of past years</div>
      <div style="position:relative;height:320px"><canvas id="${p}Seas"></canvas></div>
      <div class="tbl" style="margin-top:8px"><table id="${p}Pct"></table></div>
      <p class="note">Each contract is aligned on weeks before its desk roll date (first position / notice day for physical contracts, last trading day for cash-settled ones, two days before it for energy), so the same point of every year lines up.</p></div>
    <div class="sz-two">
      <div class="card"><h2>Contract return by calendar month</h2><div class="sz-chips" id="${p}HmSw"></div><div class="tbl"><table class="sz-hm" id="${p}Hm"></table></div>
        <p class="note">Row = contract, column = calendar month in the 12 months before delivery (last close of the prior month to the last close of the month, stopping at the roll date).</p></div>
      <div class="card"><h2>Calendar spreads by month — first three spreads</h2><div class="sz-chips" id="${p}SpSw"></div><div class="tbl"><table class="sz-hm" id="${p}Sp"></table></div>
        <p class="note">Spread = nearby minus deferred, for the front contract that is not rolled in that month. Positive = front gained (bull spread). Cell shows the pair traded in that month.</p></div>
    </div>
    <div class="card"><h2 id="${p}GridH">Front-month return by month</h2><div class="tbl"><table class="sz-grid" id="${p}Grid"></table></div>
      <p class="note">Front = nearest contract not rolled before month end, so each month is measured on one contract with no roll gap.</p></div>
    <div class="card"><h2>Roll switch — the next contract from 5 days before the front's roll date</h2><div class="tbl"><table id="${p}Roll"></table></div>
      <p class="note">Entry at the close 5 trading days before the front contract's roll date, held 10 or 21 trading days. Last 5 = most recent years, % return.</p></div>
    <p class="note">Seasonal tendencies, not forecasts: a rule that worked in 75% of years still fails one year in four. Exchange closes; no commissions or slippage.</p>`;
  function sw(id, items, get, set, label = 'Cell') {
    const el = q(id); el.innerHTML = `<span class="lab">${label}</span>` + items.map(i => `<button class="sz-chip${i[0] === get() ? ' on' : ''}" data-k="${i[0]}">${i[1]}</button>`).join('');
    $$('button', el).forEach(b => b.onclick = () => { $$('button', el).forEach(x => x.classList.toggle('on', x === b)); set(b.dataset.k); });
  }
  if (full) sw('Scope', [['soon', 'Next 60 days, all markets'], ['all', 'All markets'], ['mk', 'Selected market']], () => scope, k => { scope = k; trades(); }, 'Show');
  sw('HmSw', [['avg', 'Average %'], ['hit', '% of years up']], () => hm, k => { hm = k; heat(); });
  sw('SpSw', [['avg', 'Average change'], ['hit', '% of years front gained']], () => sp, k => { sp = k; spreads(); });

  function marketBar() {
    const groups = [...new Set(S.markets.map(m => m.group))];
    const items = []; groups.forEach(g => { items.push({ grp: g }); S.markets.filter(m => m.group === g).forEach(m => items.push([m.sym, m.name])); });
    szChips(q('Mk'), items, sym, k => go(k), 'Market');
  }
  async function go(k) {
    sym = k; seasKey = null;
    if (!S) { try { S = await SzData.summary(); } catch (e) { q('Asof').textContent = 'Could not load seasonal data.'; return; } }
    if (full) { history.replaceState(null, '', '#seasonal/' + sym); marketBar(); }
    let d; try { d = await SzData.market(sym); } catch (e) { q('Asof').textContent = 'No seasonal data for this market yet.'; return; }
    if (sym !== k) return;   // a newer selection arrived while loading
    cur = d;
    q('Asof').textContent = `Exchange closes of every contract since ${d.first_year} · prices through ${d.as_of} · rebuilt ${S.generated}`;
    if (!full) q('TrH').textContent = `Seasonal trades — ${d.name}`;
    trades(); path(); seas(); heat(); spreads(); grid(); roll();
  }
  function trades() {
    let L = S.trades.filter(t => scope === 'all' || (scope === 'mk' ? t.sym === sym : (d => d >= -10 && d <= 60)(szDays(t.next_entry))));
    L = L.slice().sort((a, b) => (a.next_entry || '9') < (b.next_entry || '9') ? -1 : 1);
    q('Trades').innerHTML = szTradeRows(S, L, full);
    if (full) $$('a[data-s]', q('Trades')).forEach(a => a.onclick = e => { e.preventDefault(); go(a.dataset.s); });
  }
  function bandsDS(x, P) {
    const band = 'rgba(138,137,132,.16)', band2 = 'rgba(138,137,132,.28)';
    return [{ label: '_90', data: P(x.bands[90]), borderWidth: 0, pointRadius: 0, fill: false },
      { label: '10–90th', data: P(x.bands[10]), borderWidth: 0, pointRadius: 0, backgroundColor: band, fill: '-1' },
      { label: '_75', data: P(x.bands[75]), borderWidth: 0, pointRadius: 0, fill: false },
      { label: '25–75th', data: P(x.bands[25]), borderWidth: 0, pointRadius: 0, backgroundColor: band2, fill: '-1' },
      { label: 'Median', data: P(x.bands[50]), borderColor: '#8a8984', borderWidth: 1, pointRadius: 0, borderDash: [2, 3] }];
  }
  function path() {
    const d = D(), x = d.path, P = a => (a || []).map(p => ({ x: p[0], y: p[1] }));
    const m0 = MON.indexOf(x.start_month);
    const wl = w => { const dt = new Date(Date.UTC(2001, m0, 1 + 7 * w)); return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }); };
    const lab = x.season_label === 'Marketing year' ? `${x.season}/${String(x.season + 1).slice(2)}` : `${x.season}`;
    q('PathH').textContent = `${d.name}: front contract through the ${x.season_label.toLowerCase()} (${x.start_month} start)`;
    q('PathNote').textContent = `Cumulative % change of the front contract, rolled at each roll date (no roll gaps), from the start of the ${x.season_label.toLowerCase()}. ${x.n_years} past ${x.season_label === 'Marketing year' ? 'marketing years' : 'years'} since ${x.first_year}.`;
    chart(p + 'Path', { type: 'line', data: { datasets: [...bandsDS(x, P),
      { label: '5-yr avg', data: P(x.avg5), borderColor: '#8a8984', borderWidth: 1.5, pointRadius: 0, borderDash: [5, 4] },
      { label: 'Last year', data: P(x.last_year), borderColor: '#eb6834', borderWidth: 1.8, pointRadius: 0 },
      { label: lab, data: P(x.current), borderColor: '#2a78d6', borderWidth: 2.8, pointRadius: 0 }] },
      options: { plugins: { legend: { labels: { filter: i => !i.text.startsWith('_'), boxWidth: 10, font: { size: 11 } } }, tooltip: { filter: i => !i.dataset.label.startsWith('_'),
        callbacks: { title: i => 'Week of ' + wl(i[0].parsed.x), label: c => `${c.dataset.label}: ${c.parsed.y.toFixed(1)}%` } } },
        scales: { x: { type: 'linear', min: 0, max: 51, ticks: { callback: v => wl(v), stepSize: 4.35, maxTicksLimit: 13 } }, y: { ticks: { callback: v => v + '%' } } } } });
    const yrs = Object.keys(x.by_year).map(Number).sort((a, b) => b - a);
    const yl = y => x.season_label === 'Marketing year' ? `${y}/${String(y + 1).slice(2)}` : y;
    q('PathYrs').innerHTML = `<tr><th class="l">${x.season_label}</th>${yrs.map(y => `<th>${yl(y)}</th>`).join('')}</tr><tr><td class="l">Front, whole season</td>${yrs.map(y => `<td style="${szCol(x.by_year[y], 30)}">${szF(x.by_year[y], 0)}%</td>`).join('')}</tr>`;
  }
  function seas() {
    const d = D(), L = d.seasonal;
    if (!L.length) { q('SeasChips').innerHTML = '<span class="note">Not enough history.</span>'; return; }
    if (!seasKey || !L.some(s => s.key === seasKey)) seasKey = L[0].key;
    szChips(q('SeasChips'), L.map(s => [s.key, (s.kind === 'px' ? '' : 'Spread ') + s.label]), seasKey, k => { seasKey = k; seas(); }, 'Series');
    const f2 = v => v == null ? '–' : (+v).toFixed(Math.abs(v) < 10 ? 3 : 2);
    q('Pct').innerHTML = '<tr><th class="l">Series</th><th>Roll date</th><th>Now</th><th>Weeks to roll</th><th>Percentile, same week</th><th>Years</th></tr>' + L.map(s => {
      const pc = s.pct_same_time, b = pc != null && (pc >= 80 || pc <= 20);
      return `<tr><td class="l">${s.kind === 'px' ? '' : 'Spread '}${s.label}</td><td>${s.roll}</td><td><b>${f2(s.now)}</b></td><td>${s.wk_now ?? '–'}</td><td${b ? ' style="font-weight:700;color:var(--acc)"' : ''}>${pc ?? '–'}</td><td>${s.n_years}</td></tr>`;
    }).join('');
    const x = L.find(s => s.key === seasKey), rd = new Date(x.roll + 'T00:00:00Z'), P = a => (a || []).map(pt => ({ x: pt[0], y: pt[1] }));
    const lab = w => { const dt = new Date(rd); dt.setUTCDate(dt.getUTCDate() - 7 * w); return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }); };
    chart(p + 'Seas', { type: 'line', data: { datasets: [...bandsDS(x, P),
      { label: '5-yr avg', data: P(x.avg5), borderColor: '#8a8984', borderWidth: 1.5, pointRadius: 0, borderDash: [5, 4] },
      { label: 'Last year', data: P(x.last_year), borderColor: '#eb6834', borderWidth: 1.8, pointRadius: 0 },
      { label: x.label, data: P(x.current), borderColor: '#2a78d6', borderWidth: 2.8, pointRadius: 0 }] },
      options: { plugins: { legend: { labels: { filter: i => !i.text.startsWith('_'), boxWidth: 10, font: { size: 11 } } }, tooltip: { filter: i => !i.dataset.label.startsWith('_'),
        callbacks: { title: i => `${i[0].parsed.x} weeks to roll (~${lab(i[0].parsed.x)})`, label: c => `${c.dataset.label}: ${f2(c.parsed.y)} ${d.unit}` } } },
        scales: { x: { type: 'linear', reverse: true, min: 0, max: 52, ticks: { callback: v => lab(v), maxTicksLimit: 9 } } } } });
  }
  function heat() {
    const d = D(); if (!d) return; const H = d.contract_heat, order = d.month_order;
    let h = `<tr><th class="l">Contract</th>${order.map(m => `<th>${m}</th>`).join('')}</tr>`;
    Object.keys(H).forEach((code, i) => {
      h += `<tr><td>${d.cycle[i]}</td>` + order.map(m => { const c = H[code][m]; if (!c) return '<td class="note">·</td>';
        const v = hm === 'avg' ? c.avg : c.hit - 50; return `<td style="${szCol(v, hm === 'avg' ? 3 : 25)}" title="${d.cycle[i]} in ${m}: avg ${szF(c.avg, 2)}%, up ${c.hit}% of ${c.n} years">${hm === 'avg' ? szF(c.avg, 1) + '%' : c.hit + '%'}<small>${hm === 'avg' ? c.hit + '% up' : szF(c.avg, 1) + '%'}</small></td>`; }).join('') + '</tr>';
    });
    q('Hm').innerHTML = h;
  }
  function spreads() {
    const d = D(); if (!d) return; const Sx = d.spread_heat, order = d.month_order;
    const vals = []; ['s1', 's2', 's3'].forEach(s => order.forEach(m => Sx[s][m] && vals.push(Math.abs(Sx[s][m].avg)))); vals.sort((a, b) => a - b);
    const sc = vals[Math.floor(vals.length * 0.8)] || 1, dd = sc < 0.1 ? 3 : 2;
    let h = `<tr><th class="l">Spread</th>${order.map(m => `<th>${m}</th>`).join('')}</tr>`;
    [['s1', 'Front – 2nd'], ['s2', '2nd – 3rd'], ['s3', '3rd – 4th']].forEach(r => {
      h += `<tr><td>${r[1]}</td>` + order.map(m => { const c = Sx[r[0]][m]; if (!c) return '<td class="note">·</td>';
        const v = sp === 'avg' ? c.avg : c.hit - 50; return `<td style="${szCol(v, sp === 'avg' ? sc : 25)}" title="${c.pair} in ${m}: avg ${szF(c.avg, 3)} ${d.unit} (${szUsd(c.avg * d.mult)}), front gained ${c.hit}% of ${c.n} years">${sp === 'avg' ? szF(c.avg, dd) : c.hit + '%'}<small>${c.pair}</small></td>`; }).join('') + '</tr>';
    });
    q('Sp').innerHTML = h;
  }
  function grid() {
    const d = D(), G = d.front_grid, A = d.front_avg, order = d.month_order, mk = d.season_kind === 'Marketing year';
    q('GridH').textContent = `Front-month return by month — ${mk ? `marketing year (${order[0]}–${order[11]})` : 'calendar year'}`;
    const yrs = Object.keys(G).map(Number).sort((a, b) => b - a);
    let h = `<tr><th class="l">${mk ? 'Marketing year' : 'Year'}</th>${order.map(m => `<th>${m}</th>`).join('')}<th>Season</th></tr>`;
    yrs.forEach(y => { let tot = 1, any = false;
      h += `<tr><td class="l">${mk ? `${y}/${String(y + 1).slice(2)}` : y}</td>` + order.map(m => { const v = G[y][m]; if (v != null) { tot *= 1 + v / 100; any = true; } return `<td style="${szCol(v, 10)}">${v == null ? '' : szF(v, 1)}</td>`; }).join('');
      const ty = any ? (tot - 1) * 100 : null; h += `<td style="${szCol(ty, 30)}"><b>${ty == null ? '' : szF(ty, 0) + '%'}</b></td></tr>`; });
    h += `<tr class="ft"><td class="l">Average</td>${order.map(m => `<td style="${szCol(A[m] && A[m].avg, 3)}">${A[m] ? szF(A[m].avg, 1) : ''}</td>`).join('')}<td></td></tr>`;
    h += `<tr class="ft"><td class="l">% up</td>${order.map(m => `<td style="${szCol(A[m] && A[m].hit - 50, 25)}">${A[m] ? A[m].hit + '%' : ''}</td>`).join('')}<td></td></tr>`;
    q('Grid').innerHTML = h;
  }
  function roll() {
    const L = D().roll_switch || [];
    q('Roll').innerHTML = '<tr><th class="l">Buy</th><th class="l">5 days before roll of</th><th>Hold</th><th>% of years up</th><th>Average</th><th>Average $/lot</th><th>Worst</th><th>Last 5 years</th><th>Years</th></tr>' +
      (L.length ? L.map(r => `<tr><td class="l"><b>${r.contract}</b></td><td class="l">${r.prev}</td><td>${r.hold} days</td><td style="${szCol(r.hit - 50, 25)}"><b>${r.hit}%</b></td><td class="${r.avg >= 0 ? 'up' : 'dn'}">${szF(r.avg, 2)}%</td>
        <td class="${r.usd >= 0 ? 'up' : 'dn'}">${szUsd(r.usd)}</td><td class="dn">${szF(r.worst, 1)}%</td><td class="sz-l5">${r.last5.map(x => `<span style="${szCol(x, 6)}">${szF(x, 1)}</span>`).join('')}</td><td>${r.n}</td></tr>`).join('')
        : '<tr><td colspan="9" class="l note">Not enough history.</td></tr>');
  }
  const D = () => cur;
  return { go, get sym() { return sym; }, has: s => !S || S.markets.some(m => m.sym === s) };
}

// Technical-pattern studies for one market, from the desk back-test (data/backtest/tech.json; same tests as Backtest › Technical patterns).
function TechStudyView(root, p) {
  const n = (v, d = 2) => v == null || isNaN(v) ? '–' : (+v).toFixed(d);
  const sg = (v, d = 2) => v == null || isNaN(v) ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${(+v).toFixed(d)}</span>`;
  const tbl = (h, rows) => `<div class="tbl"><table><tr>${h.map((x, i) => `<th${i < 2 ? ' class="l"' : ''}>${x}</th>`).join('')}</tr>${rows.join('')}</table></div>`;
  const pt = rows => tbl(['Pattern', 'Family', 'Side', 'Hold (days)', 'Trades', 'Win %', 'Avg %', 'Edge vs any day %', 'Profit factor', 'Avg worst dip %', 'Sharpe', '2007-18', '2019+'],
    rows.map(r => `<tr><td class="l">${r.rule}</td><td class="l note">${r.family || ''}</td><td>${r.side}</td><td>${r.hold}</td><td>${r.n}</td><td>${n(r.win, 0)}</td><td>${sg(r.avg)}</td><td>${sg(r.edge)}</td><td>${n(r.pf)}</td><td>${n(r.mae, 1)}</td><td><b>${sg(r.sharpe)}</b></td><td>${sg(r.is_sharpe)}</td><td>${sg(r.oos_sharpe)}</td></tr>`));
  root.innerHTML = `<div class="card"><h2 id="${p}TH">Technical studies</h2><p class="note" id="${p}TAs"></p><div id="${p}TB"><p class="note">Loading…</p></div></div>`;
  async function go(sym) {
    const TL = await SzData.tech(), body = root.querySelector('#' + p + 'TB');
    const x = TL && TL.per_market && TL.per_market[sym];
    if (!x) { body.innerHTML = '<p class="note">Technical pattern tests are not built for this market yet.</p>'; return; }
    root.querySelector('#' + p + 'TH').textContent = `Technical studies — ${x.name}`;
    root.querySelector('#' + p + 'TAs').textContent = `Daily roll-adjusted price, 2007 on · tests rebuilt ${TL.generated} · signal at a close, entry next close, exit after 5, 10 or 20 days, 5 bp cost per side`;
    const rec = TL.recovery && TL.recovery.by_market && TL.recovery.by_market[x.name], pb = TL.pullback && TL.pullback.by_market && TL.pullback.by_market[x.name];
    const best = x.best || [], top = best[0];
    body.innerHTML = `
      ${top ? `<p>Strongest robust setup in ${x.name}: <b>${top.rule}</b> (${top.side}, ${top.hold}-day hold) — ${n(top.win, 0)}% winners over ${top.n} trades, Sharpe ${n(top.sharpe)}, positive in both 2007-18 (${n(top.is_sharpe)}) and 2019+ (${n(top.oos_sharpe)}).</p>` : ''}
      <h3>Best patterns (20+ trades, positive in both halves)</h3>${best.length ? pt(best) : '<p class="note">No pattern was positive in both halves with 20+ trades.</p>'}
      <details><summary>Worst patterns in this market</summary>${pt(x.worst || [])}</details>
      <div class="sz-two" style="margin-top:8px">
        <div><h3>After a close X% below the 9-day MA <span class="note">next 20 days</span></h3>${rec ? tbl(['Below 9-day by', '', 'Cases', 'Regains signal-day MA level %', 'Avg dip first %', '10d %', 'Up after 10d %'],
          Object.entries(rec).map(([k, r]) => `<tr><td class="l"><b>${k}%</b></td><td></td><td>${r.events}</td><td>${n(r.orig_pct, 0)}</td><td>${n(r.mae_avg, 1)}</td><td>${sg(r.r10)}</td><td>${n(r.win10, 0)}</td></tr>`)) : '<p class="note">No cases.</p>'}</div>
        <div><h3>Buying the dip in an uptrend <span class="note">50-day above a rising 200-day</span></h3>${pb ? tbl(['Dip to', '', 'Cases', 'New 20-day high within 20d %', 'Avg dip %', '20d %', 'Up after 20d %'],
          Object.entries(pb).map(([k, r]) => `<tr><td class="l"><b>${k}-day MA</b></td><td></td><td>${r.events}</td><td>${n(r.new_high_pct, 0)}</td><td>${n(r.mae_avg, 1)}</td><td>${sg(r.r20)}</td><td>${n(r.win20, 0)}</td></tr>`)) : '<p class="note">No cases.</p>'}</div>
      </div>
      <p class="note"><b>Edge vs any day</b> = average trade minus holding any day for as long in the same direction. Sharpe at 10% volatility. With ${TL.n_tests} tests, a t-stat near ${TL.noise_t} is what the luckiest test shows by chance, so trust patterns that held in both halves. Cross-market results: Backtest › Technical patterns.</p>`;
  }
  return { go };
}

const MktStudy = (() => {
  let uid = 0;
  const NAMES = { ZC: 'Corn', ZS: 'Soybeans', ZM: 'Meal', ZL: 'Soy oil', ZW: 'Chicago wheat', KE: 'KC wheat', CT: 'Cotton', LE: 'Live cattle', GF: 'Feeder cattle', HE: 'Lean hogs',
    DC: 'Class III', GDK: 'Class IV', CSC: 'Cheese', CB: 'Butter', GNF: 'NFDM', DY: 'Dry whey', CL: 'WTI crude', NG: 'Natural gas', HO: 'ULSD', RB: 'RBOB' };
  // Full sub-tab: picker (several symbols) → seasonality + technical studies.
  function mount(el, syms) {
    const p = 'ms' + (++uid);
    let sym = syms[0];
    el.innerHTML = `<div class="sz">${syms.length > 1 ? `<div class="card"><div class="sz-chips" id="${p}Pk"></div></div>` : ''}
      <h2 class="sz-sec">Seasonality</h2><div id="${p}S"></div>
      <h2 class="sz-sec">Technical studies</h2><div id="${p}T"></div>
      <p class="note">Seasonal trades for every market side by side: the Seasonality tab at the top. Live price chart with indicators: the Outlook tab.</p></div>`;
    const S = SeasonView(el.querySelector('#' + p + 'S'), { prefix: p + 's', sym });
    const T = TechStudyView(el.querySelector('#' + p + 'T'), p + 't');
    const go = k => { sym = k; if (syms.length > 1) szChips(el.querySelector('#' + p + 'Pk'), syms.map(s => [s, NAMES[s] || s]), sym, go, 'Market'); S.go(sym); T.go(sym); };
    go(sym);
  }
  // Outlook card: seasonal windows opening within 90 days (or open now) and the best tested technical pattern, per symbol.
  async function upcoming(el, syms, onOpen) {
    el.innerHTML = '<div class="card"><h2>Seasonal &amp; technical studies</h2><p class="note">Loading…</p></div>';
    const [S, TL] = await Promise.all([SzData.summary().catch(() => null), SzData.tech()]);
    if (!S) { el.innerHTML = ''; return; }
    const L = S.trades.filter(t => syms.includes(t.sym) && (d => d >= -10 && d <= 90)(szDays(t.next_entry))).sort((a, b) => a.next_entry < b.next_entry ? -1 : 1);
    const tops = syms.map(s => TL?.per_market?.[s]?.best?.[0] && [s, TL.per_market[s].best[0]]).filter(Boolean);
    el.innerHTML = `<div class="card sz"><h2>Seasonal &amp; technical studies <a href="#" class="note" data-open style="font-weight:400;margin-left:8px">full studies →</a></h2>
      <h3>Seasonal windows in the next 90 days</h3><div class="tbl"><table>${L.length ? szTradeRows(S, L, false) : '<tr><td class="l note">No screened seasonal rule opens in the next 90 days for this market.</td></tr>'}</table></div>
      ${tops.length ? `<h3>Best tested technical pattern</h3><ul class="read">${tops.map(([s, r]) => `<li><b>${NAMES[s] || s}:</b> ${r.rule} (${r.side}, ${r.hold}-day hold) — ${Math.round(r.win)}% winners, ${r.n} trades, Sharpe ${(+r.sharpe).toFixed(2)}; held in 2007-18 and 2019+.</li>`).join('')}</ul>` : ''}
      <p class="note">Tendencies from history, not forecasts. Rules, heat maps, seasonal charts and all pattern tests are in the Seasonality &amp; technicals tab.</p></div>`;
    const a = el.querySelector('[data-open]'); if (a) a.onclick = e => { e.preventDefault(); onOpen && onOpen(); };
  }
  return { mount, upcoming };
})();

// Top-level Seasonality tab (all markets).
const Seasonal = (() => {
  let V = null;
  async function show() {
    const want = (location.hash.match(/^#seasonal\/(\w+)/) || [])[1];
    if (!V) { const el = document.getElementById('seasonal'); el.innerHTML = '<main></main>'; V = SeasonView($('main', el), { prefix: 'sz', full: true }); }
    let S = null; try { S = await SzData.summary(); } catch (e) {}
    V.go(want && S && S.markets.some(m => m.sym === want) ? want : V.sym);
  }
  return { show };
})();
