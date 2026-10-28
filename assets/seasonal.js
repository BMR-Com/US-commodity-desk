// Seasonality tab: every desk market (data/seasonal/<SYM>.json, summary.json; models/seasonal_desk.py).
// Crops run on their marketing year, livestock, dairy and energy on the calendar year. Deep link: #seasonal/<SYM>.
const Seasonal = (() => {
  let S = null, D = {}, sym = 'ZC', scope = 'soon', hm = 'avg', sp = 'avg', seasKey = null, built = false;
  const f = (v, d = 1) => v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
  const col = (v, s) => { if (v == null || isNaN(v)) return ''; const a = Math.min(1, Math.abs(v) / s) * 0.5; return `background:rgba(${v >= 0 ? '31,122,58' : '179,38,30'},${a.toFixed(3)})`; };
  const days = d => Math.round((new Date(d + 'T00:00:00Z') - new Date(Date.now())) / 864e5);
  const usd = v => v == null ? '' : `${v >= 0 ? '+' : '−'}$${Math.abs(Math.round(v)).toLocaleString()}`;
  const css = `<style>
    #seasonal .sz-chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0}
    #seasonal .sz-chips .lab{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-right:4px}
    #seasonal .sz-chip{font:inherit;font-size:12px;padding:3px 10px;border-radius:999px;border:1px solid var(--line);background:#fff;color:#444;cursor:pointer}
    #seasonal .sz-chip.on{background:var(--acc);border-color:var(--acc);color:#fff}
    #seasonal .sz-grp{font-size:11px;color:var(--muted);margin:0 2px 0 8px}
    #seasonal tr.sz-due td{background:#fffbea}
    #seasonal .sz-tag{display:inline-block;font-size:10px;font-weight:700;padding:1px 6px;border-radius:5px;background:#ffe066;color:#5b4500;margin-left:6px}
    #seasonal .sz-l5 span{display:inline-block;min-width:34px;padding:1px 4px;margin:0 1px;border-radius:4px;text-align:center}
    #seasonal .sz-hm td{text-align:center;min-width:50px}
    #seasonal .sz-hm td:first-child{text-align:left;font-weight:600}
    #seasonal .sz-hm td small{display:block;font-size:10px;opacity:.75}
    #seasonal .sz-grid td{text-align:center;min-width:40px;padding:4px 3px}
    #seasonal .sz-grid tr.ft td{font-weight:700;border-top:2px solid var(--line)}
    #seasonal td.l{text-align:left;white-space:normal}
    #seasonal .sz-two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}
    @media(max-width:1000px){#seasonal .sz-two{grid-template-columns:minmax(0,1fr)}}
    #seasonal .card{margin-bottom:12px}
  </style>`;

  function chips(el, items, cur, cb, label) {
    el.innerHTML = (label ? `<span class="lab">${label}</span>` : '') + items.map(it => it.grp ? `<span class="sz-grp">${it.grp}</span>` :
      `<button class="sz-chip${it[0] === cur ? ' on' : ''}" data-k="${it[0]}">${it[1]}</button>`).join('');
    $$('button', el).forEach(b => b.onclick = () => cb(b.dataset.k));
  }
  function render() {
    const el = document.getElementById('seasonal');
    el.innerHTML = css + `<main>
      <div class="card"><h2>Seasonality — every desk market</h2>
        <p class="note" id="szAsof"></p>
        <div class="sz-chips" id="szMk"></div>
        <p class="note">Crops are shown on their marketing year (corn, soybeans, meal and oil Sep–Aug; wheat Jun–May; cotton Aug–Jul). Livestock, dairy and energy have no crop year, so they run on the calendar year (Jan–Dec), and contracts roll every month for dairy and energy.</p></div>
      <div class="card"><h2>Seasonal trades</h2>
        <p class="note">Rules that worked in at least 70% of years, are statistically clear (t ≥ 2) and worked in both halves of the history (before and after 2016). Rows are highlighted when the next window starts within 45 days. Spreads are one lot each leg; "sell front" = short the nearby, long the deferred. Energy history starts 2015, so energy rules rest on about 11 years.</p>
        <div class="sz-chips" id="szScope"></div><div class="tbl"><table id="szTrades"></table></div></div>
      <div class="card"><h2 id="szPathH">Front contract through the season</h2>
        <p class="note" id="szPathNote"></p>
        <div style="position:relative;height:320px"><canvas id="szPath"></canvas></div>
        <div class="tbl" style="margin-top:8px"><table id="szPathYrs"></table></div></div>
      <div class="card"><h2>Contracts and spreads by weeks to the roll date</h2>
        <div class="sz-chips" id="szSeasChips"></div>
        <div class="note" style="margin:2px 0 6px"><span style="color:#2a78d6">■</span> current contract &nbsp; <span style="color:#eb6834">■</span> same contract last year &nbsp; <span style="color:#8a8984">■</span> 5-year average &nbsp; shaded: 10–90th and 25–75th percentile of past years</div>
        <div style="position:relative;height:320px"><canvas id="szSeas"></canvas></div>
        <div class="tbl" style="margin-top:8px"><table id="szPct"></table></div>
        <p class="note">Each contract is aligned on weeks before its desk roll date (first position / notice day for physical contracts, last trading day for cash-settled ones, two days before it for energy), so the same point of every year lines up.</p></div>
      <div class="sz-two">
        <div class="card"><h2>Contract return by calendar month</h2><div class="sz-chips" id="szHmSw"></div><div class="tbl"><table class="sz-hm" id="szHm"></table></div>
          <p class="note">Row = contract, column = calendar month in the 12 months before delivery (last close of the prior month to the last close of the month, stopping at the roll date).</p></div>
        <div class="card"><h2>Calendar spreads by month — first three spreads</h2><div class="sz-chips" id="szSpSw"></div><div class="tbl"><table class="sz-hm" id="szSp"></table></div>
          <p class="note">Spread = nearby minus deferred, for the front contract that is not rolled in that month. Positive = front gained (bull spread). Cell shows the pair traded in that month.</p></div>
      </div>
      <div class="card"><h2 id="szGridH">Front-month return by month</h2><div class="tbl"><table class="sz-grid" id="szGrid"></table></div>
        <p class="note">Front = nearest contract not rolled before month end, so each month is measured on one contract with no roll gap.</p></div>
      <div class="card"><h2>Roll switch — the next contract from 5 days before the front's roll date</h2><div class="tbl"><table id="szRoll"></table></div>
        <p class="note">Entry at the close 5 trading days before the front contract's roll date, held 10 or 21 trading days. Last 5 = most recent years, % return.</p></div>
      <p class="note">Seasonal tendencies, not forecasts: a rule that worked in 75% of years still fails one year in four. Exchange closes; no commissions or slippage.</p>
    </main>`;
    sw('#szScope', [['soon', 'Next 60 days, all markets'], ['all', 'All markets'], ['mk', 'Selected market']], () => scope, k => { scope = k; trades(); }, 'Show');
    sw('#szHmSw', [['avg', 'Average %'], ['hit', '% of years up']], () => hm, k => { hm = k; heat(); });
    sw('#szSpSw', [['avg', 'Average change'], ['hit', '% of years front gained']], () => sp, k => { sp = k; spreads(); });
  }
  function sw(id, items, get, set, label = 'Cell') {
    const el = $(id); el.innerHTML = `<span class="lab">${label}</span>` + items.map(i => `<button class="sz-chip${i[0] === get() ? ' on' : ''}" data-k="${i[0]}">${i[1]}</button>`).join('');
    $$('button', el).forEach(b => b.onclick = () => { $$('button', el).forEach(x => x.classList.toggle('on', x === b)); set(b.dataset.k); });
  }
  function marketBar() {
    const groups = [...new Set(S.markets.map(m => m.group))];
    const items = []; groups.forEach(g => { items.push({ grp: g }); S.markets.filter(m => m.group === g).forEach(m => items.push([m.sym, m.name])); });
    chips($('#szMk'), items, sym, k => go(k), 'Market');
  }
  async function go(k) {
    sym = k; seasKey = null; history.replaceState(null, '', '#seasonal/' + sym); marketBar();
    if (!D[sym]) D[sym] = await getJSON(`data/seasonal/${sym}.json`);
    const d = D[sym];
    $('#szAsof').textContent = `Exchange closes of every contract since ${d.first_year} · prices through ${d.as_of} · rebuilt ${S.generated}`;
    trades(); path(); seas(); heat(); spreads(); grid(); roll();
  }
  function trades() {
    let L = S.trades.filter(t => scope === 'all' || (scope === 'mk' ? t.sym === sym : (d => d >= -10 && d <= 60)(days(t.next_entry))));
    L = L.slice().sort((a, b) => (a.next_entry || '9') < (b.next_entry || '9') ? -1 : 1);
    const unit = s => (S.markets.find(m => m.sym === s) || {}).unit || '';
    let h = '<tr><th class="l">Market</th><th class="l">Trade</th><th>Next window</th><th>% of years worked</th><th>Last 10 yrs</th><th>Average per trade</th><th>Worst year</th><th>Last 5 years</th><th>Years</th></tr>';
    if (!L.length) h += '<tr><td colspan="9" class="l note">No rule passes the screen for this market.</td></tr>';
    L.forEach(t => {
      const d = days(t.next_entry), due = d >= 0 && d <= 45, u = unit(t.sym);
      const avg = t.avg_pct != null ? `${f(t.avg_pct, 2)}%${t.usd != null ? ' · ' + usd(t.usd) : ''}` : `${f(t.avg_chg, 3)} ${u} · ${usd(t.usd)}`;
      const worst = t.worst_pct != null ? f(t.worst_pct, 1) + '%' : `${f(t.worst_chg, 3)} ${u}`;
      const sc = t.avg_pct != null ? 5 : Math.abs(t.avg_chg) * 2 || 1;
      h += `<tr class="${due ? 'sz-due' : ''}"><td class="l"><a href="#seasonal/${t.sym}" data-s="${t.sym}">${t.market}</a></td><td class="l">${t.what}${t.contract ? ` <span class="note">(${t.contract})</span>` : ''}${due ? `<span class="sz-tag">in ${d}d</span>` : ''}</td>
        <td>${t.next_entry} → ${t.next_exit}</td><td><b>${t.hit}%</b></td><td>${t.hit_last10 == null ? '–' : t.hit_last10 + '%'}</td><td>${avg}</td><td class="dn">${worst}</td>
        <td class="sz-l5">${(t.last5 || []).map(x => `<span style="${col(x, sc)}">${f(x, t.avg_pct != null ? 1 : 2)}</span>`).join('')}</td><td>${t.n}</td></tr>`;
    });
    $('#szTrades').innerHTML = h;
    $$('#szTrades a[data-s]').forEach(a => a.onclick = e => { e.preventDefault(); go(a.dataset.s); });
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
    const d = D[sym], x = d.path, P = a => (a || []).map(p => ({ x: p[0], y: p[1] }));
    const m0 = MON.indexOf(x.start_month);
    const wl = w => { const dt = new Date(Date.UTC(2001, m0, 1 + 7 * w)); return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }); };
    const lab = x.season_label === 'Marketing year' ? `${x.season}/${String(x.season + 1).slice(2)}` : `${x.season}`;
    $('#szPathH').textContent = `${d.name}: front contract through the ${x.season_label.toLowerCase()} (${x.start_month} start)`;
    $('#szPathNote').textContent = `Cumulative % change of the front contract, rolled at each roll date (no roll gaps), from the start of the ${x.season_label.toLowerCase()}. ${x.n_years} past ${x.season_label === 'Marketing year' ? 'marketing years' : 'years'} since ${x.first_year}.`;
    chart('szPath', { type: 'line', data: { datasets: [...bandsDS(x, P),
      { label: '5-yr avg', data: P(x.avg5), borderColor: '#8a8984', borderWidth: 1.5, pointRadius: 0, borderDash: [5, 4] },
      { label: 'Last year', data: P(x.last_year), borderColor: '#eb6834', borderWidth: 1.8, pointRadius: 0 },
      { label: lab, data: P(x.current), borderColor: '#2a78d6', borderWidth: 2.8, pointRadius: 0 }] },
      options: { plugins: { legend: { labels: { filter: i => !i.text.startsWith('_'), boxWidth: 10, font: { size: 11 } } }, tooltip: { filter: i => !i.dataset.label.startsWith('_'),
        callbacks: { title: i => 'Week of ' + wl(i[0].parsed.x), label: c => `${c.dataset.label}: ${c.parsed.y.toFixed(1)}%` } } },
        scales: { x: { type: 'linear', min: 0, max: 51, ticks: { callback: v => wl(v), stepSize: 4.35, maxTicksLimit: 13 } }, y: { ticks: { callback: v => v + '%' } } } } });
    const yrs = Object.keys(x.by_year).map(Number).sort((a, b) => b - a);
    const yl = y => x.season_label === 'Marketing year' ? `${y}/${String(y + 1).slice(2)}` : y;
    $('#szPathYrs').innerHTML = `<tr><th class="l">${x.season_label}</th>${yrs.map(y => `<th>${yl(y)}</th>`).join('')}</tr><tr><td class="l">Front, whole season</td>${yrs.map(y => `<td style="${col(x.by_year[y], 30)}">${f(x.by_year[y], 0)}%</td>`).join('')}</tr>`;
  }
  function seas() {
    const d = D[sym], L = d.seasonal;
    if (!L.length) { $('#szSeasChips').innerHTML = '<span class="note">Not enough history.</span>'; return; }
    if (!seasKey || !L.some(s => s.key === seasKey)) seasKey = L[0].key;
    chips($('#szSeasChips'), L.map(s => [s.key, (s.kind === 'px' ? '' : 'Spread ') + s.label]), seasKey, k => { seasKey = k; seas(); }, 'Series');
    const f2 = v => v == null ? '–' : (+v).toFixed(Math.abs(v) < 10 ? 3 : 2);
    $('#szPct').innerHTML = '<tr><th class="l">Series</th><th>Roll date</th><th>Now</th><th>Weeks to roll</th><th>Percentile, same week</th><th>Years</th></tr>' + L.map(s => {
      const p = s.pct_same_time, b = p != null && (p >= 80 || p <= 20);
      return `<tr><td class="l">${s.kind === 'px' ? '' : 'Spread '}${s.label}</td><td>${s.roll}</td><td><b>${f2(s.now)}</b></td><td>${s.wk_now ?? '–'}</td><td${b ? ' style="font-weight:700;color:var(--acc)"' : ''}>${p ?? '–'}</td><td>${s.n_years}</td></tr>`;
    }).join('');
    const x = L.find(s => s.key === seasKey), rd = new Date(x.roll + 'T00:00:00Z'), P = a => (a || []).map(p => ({ x: p[0], y: p[1] }));
    const lab = w => { const dt = new Date(rd); dt.setUTCDate(dt.getUTCDate() - 7 * w); return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }); };
    chart('szSeas', { type: 'line', data: { datasets: [...bandsDS(x, P),
      { label: '5-yr avg', data: P(x.avg5), borderColor: '#8a8984', borderWidth: 1.5, pointRadius: 0, borderDash: [5, 4] },
      { label: 'Last year', data: P(x.last_year), borderColor: '#eb6834', borderWidth: 1.8, pointRadius: 0 },
      { label: x.label, data: P(x.current), borderColor: '#2a78d6', borderWidth: 2.8, pointRadius: 0 }] },
      options: { plugins: { legend: { labels: { filter: i => !i.text.startsWith('_'), boxWidth: 10, font: { size: 11 } } }, tooltip: { filter: i => !i.dataset.label.startsWith('_'),
        callbacks: { title: i => `${i[0].parsed.x} weeks to roll (~${lab(i[0].parsed.x)})`, label: c => `${c.dataset.label}: ${f2(c.parsed.y)} ${d.unit}` } } },
        scales: { x: { type: 'linear', reverse: true, min: 0, max: 52, ticks: { callback: v => lab(v), maxTicksLimit: 9 } } } } });
  }
  function heat() {
    const d = D[sym], H = d.contract_heat, order = d.month_order;
    let h = `<tr><th class="l">Contract</th>${order.map(m => `<th>${m}</th>`).join('')}</tr>`;
    Object.keys(H).forEach((code, i) => {
      h += `<tr><td>${d.cycle[i]}</td>` + order.map(m => { const c = H[code][m]; if (!c) return '<td class="note">·</td>';
        const v = hm === 'avg' ? c.avg : c.hit - 50; return `<td style="${col(v, hm === 'avg' ? 3 : 25)}" title="${d.cycle[i]} in ${m}: avg ${f(c.avg, 2)}%, up ${c.hit}% of ${c.n} years">${hm === 'avg' ? f(c.avg, 1) + '%' : c.hit + '%'}<small>${hm === 'avg' ? c.hit + '% up' : f(c.avg, 1) + '%'}</small></td>`; }).join('') + '</tr>';
    });
    $('#szHm').innerHTML = h;
  }
  function spreads() {
    const d = D[sym], Sx = d.spread_heat, order = d.month_order;
    const vals = []; ['s1', 's2', 's3'].forEach(s => order.forEach(m => Sx[s][m] && vals.push(Math.abs(Sx[s][m].avg)))); vals.sort((a, b) => a - b);
    const sc = vals[Math.floor(vals.length * 0.8)] || 1, dd = sc < 0.1 ? 3 : 2;
    let h = `<tr><th class="l">Spread</th>${order.map(m => `<th>${m}</th>`).join('')}</tr>`;
    [['s1', 'Front – 2nd'], ['s2', '2nd – 3rd'], ['s3', '3rd – 4th']].forEach(r => {
      h += `<tr><td>${r[1]}</td>` + order.map(m => { const c = Sx[r[0]][m]; if (!c) return '<td class="note">·</td>';
        const v = sp === 'avg' ? c.avg : c.hit - 50; return `<td style="${col(v, sp === 'avg' ? sc : 25)}" title="${c.pair} in ${m}: avg ${f(c.avg, 3)} ${d.unit} (${usd(c.avg * d.mult)}), front gained ${c.hit}% of ${c.n} years">${sp === 'avg' ? f(c.avg, dd) : c.hit + '%'}<small>${c.pair}</small></td>`; }).join('') + '</tr>';
    });
    $('#szSp').innerHTML = h;
  }
  function grid() {
    const d = D[sym], G = d.front_grid, A = d.front_avg, order = d.month_order, mk = d.season_kind === 'Marketing year';
    $('#szGridH').textContent = `Front-month return by month — ${mk ? `marketing year (${order[0]}–${order[11]})` : 'calendar year'}`;
    const yrs = Object.keys(G).map(Number).sort((a, b) => b - a);
    let h = `<tr><th class="l">${mk ? 'Marketing year' : 'Year'}</th>${order.map(m => `<th>${m}</th>`).join('')}<th>Season</th></tr>`;
    yrs.forEach(y => { let tot = 1, any = false;
      h += `<tr><td class="l">${mk ? `${y}/${String(y + 1).slice(2)}` : y}</td>` + order.map(m => { const v = G[y][m]; if (v != null) { tot *= 1 + v / 100; any = true; } return `<td style="${col(v, 10)}">${v == null ? '' : f(v, 1)}</td>`; }).join('');
      const ty = any ? (tot - 1) * 100 : null; h += `<td style="${col(ty, 30)}"><b>${ty == null ? '' : f(ty, 0) + '%'}</b></td></tr>`; });
    h += `<tr class="ft"><td class="l">Average</td>${order.map(m => `<td style="${col(A[m] && A[m].avg, 3)}">${A[m] ? f(A[m].avg, 1) : ''}</td>`).join('')}<td></td></tr>`;
    h += `<tr class="ft"><td class="l">% up</td>${order.map(m => `<td style="${col(A[m] && A[m].hit - 50, 25)}">${A[m] ? A[m].hit + '%' : ''}</td>`).join('')}<td></td></tr>`;
    $('#szGrid').innerHTML = h;
  }
  function roll() {
    const L = D[sym].roll_switch || [];
    $('#szRoll').innerHTML = '<tr><th class="l">Buy</th><th class="l">5 days before roll of</th><th>Hold</th><th>% of years up</th><th>Average</th><th>Average $/lot</th><th>Worst</th><th>Last 5 years</th><th>Years</th></tr>' +
      L.map(r => `<tr><td class="l"><b>${r.contract}</b></td><td class="l">${r.prev}</td><td>${r.hold} days</td><td style="${col(r.hit - 50, 25)}"><b>${r.hit}%</b></td><td class="${r.avg >= 0 ? 'up' : 'dn'}">${f(r.avg, 2)}%</td>
        <td class="${r.usd >= 0 ? 'up' : 'dn'}">${usd(r.usd)}</td><td class="dn">${f(r.worst, 1)}%</td><td class="sz-l5">${r.last5.map(x => `<span style="${col(x, 6)}">${f(x, 1)}</span>`).join('')}</td><td>${r.n}</td></tr>`).join('');
  }
  async function show() {
    const want = (location.hash.match(/^#seasonal\/(\w+)/) || [])[1];
    if (!built) {
      render(); built = true;
      try { S = await getJSON('data/seasonal/summary.json'); } catch (e) { $('#szAsof').textContent = 'Could not load seasonal data.'; return; }
    }
    go(want && S.markets.some(m => m.sym === want) ? want : sym);
  }
  return { show };
})();
