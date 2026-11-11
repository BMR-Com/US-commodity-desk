// Energy section: oil and refined-product panels (crude WTI, ULSD/heating oil, RBOB gasoline), plus the futures curve,
// options summary and data-freshness table used by every desk. Ported from the retired single-page energy terminal
// (energy.html: Oil stocks, Refining & cracks, Prices, ETF options, Data tabs). Reads repo JSON/CSV only.
// mk is the desk code: 'NG' | 'CL' | 'HO' | 'RB'.
const EnergyOil = (() => {
  const EIA = 'data/energy/eia/';
  const J = (u) => getJSON(u).catch(() => null);
  const C = (u) => getCSV(u).catch(() => null);
  const DAY = 864e5;
  const toD = (s) => new Date((s.length === 7 ? s + '-01' : s) + 'T00:00:00Z');
  const iso = (d) => d.toISOString().slice(0, 10);
  const n0 = (v, d = 1) => fmt(v, d);
  const usd = (v, d = 2) => v == null || !isFinite(v) ? '–' : (v < 0 ? '−$' : '$') + fmt(Math.abs(v), d);
  const pctl = (arr, x) => arr.length ? arr.filter(v => v < x).length / arr.length * 100 : null;
  const avg = (a) => { const x = a.filter(v => v != null && isFinite(v)); return x.length ? x.reduce((p, q) => p + q, 0) / x.length : null; };
  const kpis = (items) => `<div class="kpi-row" style="display:flex;flex-wrap:wrap;gap:18px;margin:6px 0 10px">${items.filter(Boolean).map(([k, v, s]) =>
    `<div><div class="note">${k}</div><b>${v}</b>${s ? ` <span class="note">${s}</span>` : ''}</div>`).join('')}</div>`;
  const card = (h, inner, style = '') => `<div class="card" style="margin-top:12px;${style}">${h ? `<h2>${h}</h2>` : ''}${inner}</div>`;
  const cv = (id, cls = 'chart') => `<div class="${cls}"><canvas id="${id}"></canvas></div>`;
  const fail = (el, what, e) => el.insertAdjacentHTML('beforeend', `<div class="card" style="margin-top:12px"><p class="note">${what}: not available (${String((e && e.message) || e || 'missing data').slice(0, 120)}).</p></div>`);
  async function part(el, what, fn) { try { await fn(); } catch (e) { console.warn(what, e); fail(el, what, e); } }

  // ---------- EIA series ----------
  async function eia(k, scale = 1) {
    const j = await J(EIA + k + '.json');
    if (!j || !j.rows || !j.rows.length) throw new Error(`no data/energy/eia/${k}.json`);
    return j.rows.filter(r => r[1] != null).map(r => ({ d: r[0], v: r[1] * scale }));
  }
  const K = 1 / 1000; // thousand barrels (per day) -> million barrels (per day)
  const lastOf = (a) => a[a.length - 1];
  // week-of-year seasonal (53 slots): object compatible with lib seasonalDatasets()
  function wkIdx(s) { const d = toD(s), y = d.getUTCFullYear(); return [y, Math.min(52, Math.floor((d - Date.UTC(y, 0, 1)) / DAY / 7))]; }
  function wkSeason(rows, years = 5) {
    const by = {};
    rows.forEach(r => { const [y, w] = wkIdx(r.d); (by[y] ||= Array(53).fill(null))[w] = r.v; });
    const yrs = Object.keys(by).map(Number).sort(); const cy = yrs.at(-1); const prev5 = yrs.filter(y => y < cy).slice(-years);
    const stat = f => Array.from({ length: 53 }, (_, i) => { const xs = prev5.map(y => by[y][i]).filter(v => v != null); return xs.length ? f(xs) : null; });
    return { cy, by, yrs, prev5, min: stat(x => Math.min(...x)), max: stat(x => Math.max(...x)), avg: stat(x => x.reduce((a, b) => a + b, 0) / x.length) };
  }
  const WKL = Array.from({ length: 53 }, (_, i) => { const d = new Date(Date.UTC(2001, 0, 1 + i * 7)); return MON[d.getUTCMonth()] + ' ' + String(d.getUTCDate()).padStart(2, '0'); });
  const seaOpts = (unit) => ({ spanGaps: true, plugins: { legend: legendNoMin }, scales: { y: { title: { display: true, text: unit, font: { size: 10 } } } } });
  function seaChart(id, rows, unit) { const s = wkSeason(rows); chart(id, { type: 'line', data: { labels: WKL, datasets: seasonalDatasets(s) }, options: seaOpts(unit) }); return s; }
  function byYearChart(id, rows, unit, n = 6) {
    const s = wkSeason(rows), yrs = s.yrs.slice(-n), pal = ['#c9d6cc', '#a9c0ae', '#86a98d', '#5f8f68', '#2c6fbb', '#c0392b'].slice(-yrs.length);
    chart(id, { type: 'line', data: { labels: WKL, datasets: yrs.map((y, i) => ({ label: String(y), data: s.by[y], borderColor: pal[i], borderWidth: i === yrs.length - 1 ? 2.4 : 1.3, pointRadius: 0 })) }, options: seaOpts(unit) });
  }
  // stats for latest observation vs 5-yr average for the same week and vs a year ago
  function levelStats(rows) {
    const s = wkSeason(rows), l = lastOf(rows), p = rows[rows.length - 2], [y, w] = wkIdx(l.d);
    const a5 = s.avg[w], ya = s.by[y - 1] ? s.by[y - 1][w] : null;
    const chgAvg = w > 0 && s.prev5.length ? avg(s.prev5.map(yy => s.by[yy][w] != null && s.by[yy][w - 1] != null ? s.by[yy][w] - s.by[yy][w - 1] : null)) : null;
    return { l, p, chg: l.v - p.v, a5, ya, chgAvg, dev: a5 != null ? l.v - a5 : null, devPct: a5 ? (l.v / a5 - 1) * 100 : null };
  }
  function changeChart(id, rows, unit, nWeeks = 78) {
    const s = wkSeason(rows), t = rows.slice(-(nWeeks + 1)), lab = [], ch = [], a = [];
    for (let i = 1; i < t.length; i++) {
      const [y, w] = wkIdx(t[i].d); lab.push(t[i].d); ch.push(t[i].v - t[i - 1].v);
      const ys = Object.keys(s.by).map(Number).filter(yy => yy < y).slice(-5);
      a.push(w > 0 ? avg(ys.map(yy => s.by[yy][w] != null && s.by[yy][w - 1] != null ? s.by[yy][w] - s.by[yy][w - 1] : null)) : null);
    }
    chart(id, { type: 'bar', data: { labels: lab, datasets: [
      { type: 'line', label: '5-yr average change', data: a, borderColor: '#555', borderDash: [4, 3], borderWidth: 1.3, pointRadius: 0, order: 0 },
      { label: 'weekly change', data: ch, backgroundColor: ch.map(v => v >= 0 ? 'rgba(192,57,43,.65)' : 'rgba(44,111,187,.65)'), order: 1 }] },
      options: { plugins: { tooltip: { callbacks: { afterBody: (it) => { const i = it[0].dataIndex; return a[i] != null ? `vs 5-yr avg: ${(ch[i] - a[i] >= 0 ? '+' : '')}${(ch[i] - a[i]).toFixed(2)} ${unit}` : ''; } } } },
        scales: { y: { title: { display: true, text: unit, font: { size: 10 } } } } } });
  }
  const ma = (rows, n = 4) => rows.map((r, i) => i < n - 1 ? null : { d: r.d, v: avg(rows.slice(i - n + 1, i + 1).map(x => x.v)) }).filter(Boolean);
  function alignMap(rows) { const m = {}; rows.forEach(r => m[r.d] = r.v); return m; }
  function lineChart(id, labels, sets, unit, extra = {}) {
    chart(id, { type: 'line', data: { labels, datasets: sets.map((s, i) => ({ pointRadius: 0, borderWidth: 1.6, borderColor: s.color || PAL[i % PAL.length], ...s })) },
      options: deepMerge({ spanGaps: true, scales: { y: { title: { display: !!unit, text: unit, font: { size: 10 } } } } }, extra) });
  }

  // ======================= 1. Inventories =======================
  const STRIP = [['crude', 'Crude ex-SPR'], ['cushing', 'Cushing'], ['spr', 'SPR'], ['gaso', 'Gasoline'], ['dist', 'Distillate'], ['jet', 'Jet fuel']];
  const PROD = {
    HO: { k: 'dist', name: 'Distillate', prod: 'distProd', imp: 'distImp', exp: 'distExp', dem: 'demDist' },
    RB: { k: 'gaso', name: 'Gasoline', prod: 'gasoProd', imp: 'gasoImp', exp: 'gasoExp', dem: 'demGaso' } };
  async function stocks(el, mk = 'CL') {
    if (mk === 'NG') { el.innerHTML = '<div class="card"><p class="note">Oil inventories are on the crude, ULSD and RBOB desks.</p></div>'; return; }
    el.innerHTML = '<div id="eoilStMain"></div><div id="eoilStStrip"></div>';
    const main = $('#eoilStMain', el);
    if (mk === 'CL') await part(main, 'Crude inventories', () => stocksCL(main));
    else await part(main, `${PROD[mk].name} inventories`, () => stocksProd(main, mk));
    const strip = $('#eoilStStrip', el);
    await part(strip, 'Other oil stocks', () => stockStrip(strip, mk));
  }
  async function stocksCL(el) {
    const [cr, cu, spr, runs] = await Promise.all([eia('crude', K), eia('cushing', K).catch(() => null), eia('spr', K).catch(() => null), eia('runs', K).catch(() => null)]);
    const st = levelStats(cr), cs = cu && levelStats(cu);
    const dos = runs ? (() => { const m = alignMap(runs); return cr.filter(r => m[r.d]).map(r => ({ d: r.d, v: r.v / m[r.d] })); })() : null;
    const ds = dos && dos.length > 60 ? levelStats(dos) : null;
    el.innerHTML = card(`Crude oil inventories, excluding the SPR <span class="note">EIA Weekly Petroleum Status Report (Wed 10:30 ET), week ending ${st.l.d}</span>`,
      kpis([['Commercial crude', `${n0(st.l.v)} mb`], ['Week on week', `${sgn(st.chg, 1)} mb`, st.chgAvg != null ? `5-yr avg for the week ${st.chgAvg >= 0 ? '+' : ''}${n0(st.chgAvg)}` : ''],
        ['vs 5-yr average', `${sgn(st.dev, 1)} mb`, `${sgn(st.devPct, 1, '%')}`], ['vs year ago', `${sgn(st.ya != null ? st.l.v - st.ya : null, 1)} mb`, st.ya != null ? `${n0(st.ya)} then` : ''],
        cs && ['Cushing', `${n0(cs.l.v)} mb`, `w/w ${sgn(cs.chg, 1)}, vs 5-yr ${sgn(cs.dev, 1)}`],
        spr && ['SPR', `${n0(lastOf(spr).v)} mb`, `w/w ${sgn(lastOf(spr).v - spr[spr.length - 2].v, 2)}`],
        ds && ['Days of supply', `${n0(ds.l.v)} days`, `crude stocks ÷ refinery runs; 5-yr avg ${n0(ds.a5)}`]]) +
      `<div class="chart tall"><canvas id="eoilStSea"></canvas></div><p class="note">Million barrels (mb) by week of year: current year, prior year, 5-year average and min–max range. Commercial stocks exclude the Strategic Petroleum Reserve.</p>`, 'margin-top:0') +
      `<div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Weekly build and draw <span class="note">mb, last 78 weeks</span></h2>${cv('eoilStChg')}<p class="note">Bars: actual weekly change (red = build, blue = draw). Dashed: average change for the same week over the prior 5 years. The gap is the seasonal surprise.</p></div>
        <div class="card"><h2>Cushing, Oklahoma <span class="note">mb, by week of year</span></h2>${cu ? cv('eoilStCush') : '<p class="note">No Cushing data.</p>'}<p class="note">Cushing is the delivery point for WTI futures. Tank bottoms are near 20 mb; the front spread prices that operating risk well before the hub empties.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Strategic Petroleum Reserve <span class="note">mb, last 10 years</span></h2>${spr ? cv('eoilStSpr') : '<p class="note">No SPR data.</p>'}</div>
        <div class="card"><h2>Crude stocks by year <span class="note">mb, last 6 years</span></h2>${cv('eoilStYr')}</div></div>
      ${dos ? `<div class="card" style="margin-top:12px"><h2>Crude days of supply <span class="note">commercial stocks ÷ weekly refinery crude runs, days</span></h2>${cv('eoilStDos', 'chart short')}</div>` : ''}`;
    seaChart('eoilStSea', cr, 'million barrels');
    changeChart('eoilStChg', cr, 'mb');
    if (cu) seaChart('eoilStCush', cu, 'million barrels');
    if (spr) { const t = spr.filter(r => r.d >= iso(new Date(Date.now() - 3653 * DAY))); lineChart('eoilStSpr', t.map(r => r.d), [{ label: 'SPR', data: t.map(r => r.v), borderColor: '#2f6b3a' }], 'million barrels'); }
    byYearChart('eoilStYr', cr, 'million barrels');
    if (dos) seaChart('eoilStDos', dos, 'days');
  }
  async function stocksProd(el, mk) {
    const P = PROD[mk];
    const [st0, pr, im, ex, dm] = await Promise.all([eia(P.k, K), eia(P.prod, K).catch(() => null), eia(P.imp, K).catch(() => null), eia(P.exp, K).catch(() => null), eia(P.dem, K).catch(() => null)]);
    const st = levelStats(st0);
    const dem4 = dm ? ma(dm) : null;
    const dos = dem4 ? (() => { const m = alignMap(dem4); return st0.filter(r => m[r.d]).map(r => ({ d: r.d, v: r.v / m[r.d] })); })() : null;
    const ds = dos && dos.length > 60 ? levelStats(dos) : null;
    const flows = [['Refinery and blender production', pr], ['Imports', im], ['Exports', ex], ['Product supplied (demand)', dm]].filter(x => x[1]);
    const fRow = ([nm, a]) => { const a4 = ma(a), l = lastOf(a), l4 = lastOf(a4), s = wkSeason(a4), [y, w] = wkIdx(l4.d);
      const ya = s.by[y - 1] ? s.by[y - 1][w] : null;
      return `<tr><td class="l">${nm}</td><td>${n0(l.v, 2)}</td><td>${n0(l4.v, 2)}</td><td>${n0(ya, 2)}</td><td>${sgn(ya != null ? l4.v - ya : null, 2)}</td><td>${n0(s.avg[w], 2)}</td><td>${sgn(s.avg[w] != null ? l4.v - s.avg[w] : null, 2)}</td></tr>`; };
    el.innerHTML = card(`${P.name} inventories <span class="note">EIA weekly, week ending ${st.l.d}</span>`,
      kpis([[`${P.name} stocks`, `${n0(st.l.v)} mb`], ['Week on week', `${sgn(st.chg, 1)} mb`, st.chgAvg != null ? `5-yr avg for the week ${st.chgAvg >= 0 ? '+' : ''}${n0(st.chgAvg)}` : ''],
        ['vs 5-yr average', `${sgn(st.dev, 1)} mb`, sgn(st.devPct, 1, '%')], ['vs year ago', `${sgn(st.ya != null ? st.l.v - st.ya : null, 1)} mb`, st.ya != null ? `${n0(st.ya)} then` : ''],
        ds && ['Days of supply', `${n0(ds.l.v)} days`, `stocks ÷ 4-wk avg product supplied; 5-yr avg ${n0(ds.a5)}, year ago ${n0(ds.ya)}`]]) +
      `<div class="chart tall"><canvas id="eoilStSea"></canvas></div><p class="note">Million barrels (mb) by week of year vs the prior 5 years. ${mk === 'HO' ? 'Total US distillate (ULSD plus higher-sulfur and heating oil). East Coast (PADD 1) stocks matter most for the NY Harbor contract.' : 'Total US motor gasoline (finished plus blending components). East Coast stocks matter most for NY Harbor RBOB.'}</p>`, 'margin-top:0') +
      `<div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Weekly build and draw <span class="note">mb, last 78 weeks</span></h2>${cv('eoilStChg')}<p class="note">Bars: actual change (red = build, blue = draw); dashed: 5-year average change for the same week.</p></div>
        <div class="card"><h2>${P.name} stocks by year <span class="note">mb, last 6 years</span></h2>${cv('eoilStYr')}</div></div>
      ${flows.length ? `<div class="card" style="margin-top:12px"><h2>${P.name} supply and demand <span class="note">million barrels per day (mb/d), 4-week averages, last 2 years</span></h2>${cv('eoilStFlow')}
        <div class="tbl"><table><tr><th class="l">Flow (mb/d)</th><th>Latest week</th><th>4-wk avg</th><th>4-wk avg, year ago</th><th>y/y</th><th>5-yr avg, same week</th><th>vs 5-yr</th></tr>${flows.map(fRow).join('')}</table></div>
        <p class="note">Product supplied is EIA's measure of demand (disappearance from primary supply). Weekly numbers are noisy; read the 4-week average.</p></div>` : ''}
      <div class="grid g2" style="margin-top:12px">
        ${dm ? `<div class="card"><h2>Product supplied (demand) vs 5 years <span class="note">mb/d, 4-week average</span></h2>${cv('eoilStDem')}</div>` : ''}
        ${dos ? `<div class="card"><h2>Days of supply vs 5 years <span class="note">stocks ÷ 4-wk avg product supplied, days</span></h2>${cv('eoilStDos')}</div>` : ''}</div>`;
    seaChart('eoilStSea', st0, 'million barrels');
    changeChart('eoilStChg', st0, 'mb');
    byYearChart('eoilStYr', st0, 'million barrels');
    if (flows.length) {
      const since = iso(new Date(Date.now() - 730 * DAY)), base = ma(flows[0][1]).filter(r => r.d >= since), lab = base.map(r => r.d);
      lineChart('eoilStFlow', lab, flows.map(([nm, a], i) => { const m = alignMap(ma(a)); return { label: nm, data: lab.map(d => m[d] ?? null), borderColor: ['#2f6b3a', '#2c6fbb', '#d68910', '#c0392b'][i] }; }), 'mb/d');
    }
    if (dm) seaChart('eoilStDem', dem4, 'mb/d');
    if (dos) seaChart('eoilStDos', dos, 'days');
  }
  async function stockStrip(el, mk) {
    const focus = mk === 'CL' ? ['crude', 'cushing', 'spr'] : [PROD[mk].k];
    const rows = (await Promise.all(STRIP.map(async ([k, nm]) => { try { const a = await eia(k, K); return [k, nm, levelStats(a)]; } catch (e) { return null; } }))).filter(Boolean);
    if (!rows.length) throw new Error('no oil stock files');
    el.innerHTML = card(`US oil stocks at a glance <span class="note">million barrels, latest EIA week</span>`, `<div class="tbl"><table><tr><th class="l">Stock</th><th>Week</th><th>Level</th><th>Week on week</th><th>5-yr avg change</th><th>5-yr avg level</th><th>vs 5-yr</th><th>%</th><th>vs year ago</th></tr>
      ${rows.map(([k, nm, s]) => `<tr${focus.includes(k) ? ' style="font-weight:600"' : ''}><td class="l">${nm}</td><td>${s.l.d}</td><td>${n0(s.l.v)}</td><td>${sgn(s.chg, 1)}</td><td>${s.chgAvg == null ? '–' : (s.chgAvg >= 0 ? '+' : '') + n0(s.chgAvg)}</td><td>${n0(s.a5)}</td><td>${sgn(s.dev, 1)}</td><td>${sgn(s.devPct, 1, '%')}</td><td>${sgn(s.ya != null ? s.l.v - s.ya : null, 1)}</td></tr>`).join('')}</table></div>`);
  }

  // ======================= 2. Refining, demand, cracks =======================
  // front-month futures, long history: data/ohlc/<mk>.csv 'cont' (10 yrs) topped up with data/energy/prices.json
  async function front(sym) {
    const m = {};
    if (['CL', 'HO', 'RB', 'NG'].includes(sym)) { const o = await C(`data/ohlc/${sym}.csv`); if (o) o.filter(r => r.series === 'cont' && r.close != null).forEach(r => m[r.date] = r.close); }
    const p = await J('data/energy/prices.json'); (p?.prices?.[sym] || []).forEach(r => { if (r.c != null) m[r.d] = r.c; });
    return Object.keys(m).sort().map(d => ({ d, v: m[d] }));
  }
  async function crackSeries() {
    const [cl, ho, rb] = await Promise.all([front('CL'), front('HO'), front('RB')]);
    if (!cl.length || !ho.length || !rb.length) throw new Error('front-month CL/HO/RB prices missing');
    const hm = alignMap(ho), rm = alignMap(rb);
    return cl.filter(r => hm[r.d] != null && rm[r.d] != null && r.v > 0).map(r => ({ d: r.d, cl: r.v, ho: hm[r.d] * 42 - r.v, rb: rm[r.d] * 42 - r.v, c321: (2 * rm[r.d] * 42 + hm[r.d] * 42) / 3 - r.v }));
  }
  const CRK = { c321: '3-2-1 crack', ho: 'ULSD crack (HO − CL)', rb: 'Gasoline crack (RB − CL)' };
  async function refining(el, mk = 'CL') {
    if (mk === 'NG') { el.innerHTML = '<div class="card"><p class="note">Refining is on the crude, ULSD and RBOB desks.</p></div>'; return; }
    el.innerHTML = '<div id="eoilRfA"></div><div id="eoilRfB"></div><div id="eoilRfC"></div><div id="eoilRfD"></div>';
    const blocks = { runs: (h) => refRuns(h), dem: (h) => refDemand(h, mk), crk: (h) => refCracks(h, mk), wb: (h) => refWtiBrent(h) };
    const order = mk === 'CL' ? ['runs', 'dem', 'crk', 'wb'] : ['crk', 'runs', 'dem', 'wb'];
    const slots = ['A', 'B', 'C', 'D'];
    order.forEach((b, i) => $(`#eoilRf${slots[i]}`, el).dataset.b = b);
    for (const b of order) { const host = el.querySelector(`[data-b="${b}"]`); await part(host, { runs: 'Refinery runs', dem: 'Demand and supply', crk: 'Crack spreads', wb: 'WTI–Brent' }[b], () => blocks[b](host)); }
  }
  async function refRuns(host) {
    const [runs, util, prod] = await Promise.all([eia('runs', K), eia('util').catch(() => null), eia('prod', K).catch(() => null)]);
    const r = levelStats(runs), u = util && levelStats(util);
    host.innerHTML = card(`Refinery runs and utilization <span class="note">EIA weekly, week ending ${r.l.d}</span>`,
      kpis([['Refiner net crude input', `${n0(r.l.v, 2)} mb/d`, `w/w ${sgn(r.chg, 2)}`], ['vs 5-yr average', `${sgn(r.dev, 2)} mb/d`, `year ago ${n0(r.ya, 2)}`],
        u && ['Utilization', `${n0(u.l.v)}%`, `5-yr avg ${n0(u.a5)}%, year ago ${n0(u.ya)}%`], prod && ['Crude production', `${n0(lastOf(prod).v, 2)} mb/d`, lastOf(prod).d]]) +
      `<div class="grid g2"><div><h3>Crude runs, million barrels per day</h3>${cv('eoilRfRuns')}</div><div><h3>Utilization of operable capacity, %</h3>${util ? cv('eoilRfUtil') : '<p class="note">No utilization data.</p>'}</div></div>
      <p class="note">Turnarounds run roughly February–April and September–October. Runs falling while product stocks build points to weak demand; runs falling while product stocks draw is maintenance.</p>`, 'margin-top:0');
    seaChart('eoilRfRuns', runs, 'mb/d'); if (util) seaChart('eoilRfUtil', util, '%');
  }
  async function refDemand(host, mk) {
    const [g, d, j, pr, im, ex] = await Promise.all(['demGaso', 'demDist', 'demJet', 'prod', 'imp', 'exp'].map(k => eia(k, K).catch(() => null)));
    if (!g && !d) throw new Error('no product supplied data');
    const since = iso(new Date(Date.now() - 3 * 365 * DAY));
    const line = (sets) => { const b = ma(sets.find(s => s[1])[1]).filter(r => r.d >= since), lab = b.map(r => r.d);
      return [lab, sets.filter(s => s[1]).map(([nm, a, c]) => { const m = alignMap(ma(a)); return { label: nm, data: lab.map(x => m[x] ?? null), borderColor: c }; })]; };
    const yoy = (nm, a) => { if (!a) return ''; const a4 = ma(a), l = lastOf(a4), s = wkSeason(a4), [y, w] = wkIdx(l.d), ya = s.by[y - 1]?.[w];
      return `<tr><td class="l">${nm}</td><td>${l.d}</td><td>${n0(l.v, 2)}</td><td>${n0(ya, 2)}</td><td>${sgn(ya ? (l.v / ya - 1) * 100 : null, 1, '%')}</td><td>${n0(s.avg[w], 2)}</td></tr>`; };
    const D = [['Gasoline', g, '#c0392b'], ['Distillate', d, '#2f6b3a'], ['Jet fuel', j, '#7d3c98']];
    if (mk === 'HO') D.unshift(D.splice(1, 1)[0]);
    host.innerHTML = `<div class="grid g2" style="margin-top:12px">
      <div class="card"><h2>Product supplied (demand) <span class="note">mb/d, 4-week averages, last 3 years</span></h2>${cv('eoilRfDem')}
        <div class="tbl"><table><tr><th class="l">Product</th><th>Week</th><th>4-wk avg</th><th>Year ago</th><th>y/y</th><th>5-yr avg</th></tr>${D.map(([nm, a]) => yoy(nm, a)).join('')}</table></div></div>
      <div class="card"><h2>Domestic crude supply <span class="note">mb/d, 4-week averages, last 3 years</span></h2>${pr ? cv('eoilRfSup') : '<p class="note">No production data.</p>'}
        <div class="tbl"><table><tr><th class="l">Crude</th><th>Week</th><th>4-wk avg</th><th>Year ago</th><th>y/y</th><th>5-yr avg</th></tr>${yoy('Field production', pr)}${yoy('Imports (commercial)', im)}${yoy('Exports', ex)}</table></div></div></div>`;
    const [l1, s1] = line(D); lineChart('eoilRfDem', l1, s1, 'mb/d');
    if (pr) { const [l2, s2] = line([['Production', pr, '#2f6b3a'], ['Imports', im, '#2c6fbb'], ['Exports', ex, '#d68910']]); lineChart('eoilRfSup', l2, s2, 'mb/d'); }
  }
  async function refCracks(host, mk) {
    const pts = await crackSeries(), l = lastOf(pts);
    const keys = mk === 'HO' ? ['ho', 'c321', 'rb'] : mk === 'RB' ? ['rb', 'c321', 'ho'] : ['c321', 'ho', 'rb'], main = keys[0];
    const yr = pts.filter(p => p.d > iso(new Date(toD(l.d) - 365 * DAY)));
    const ago = (k, days) => { const t = iso(new Date(toD(l.d) - days * DAY)); const p = [...pts].reverse().find(x => x.d <= t); return p ? p[k] : null; };
    const recent = pts.filter(p => p.d >= iso(new Date(Date.now() - 3 * 365 * DAY)));
    const mon = {}; pts.forEach(p => { const k = p.d.slice(0, 7); (mon[k] ||= []).push(p[main]); });
    const months = Object.keys(mon).sort(), s = seasonal(months, months.map(m => avg(mon[m])));
    host.innerHTML = card(`Crack spreads <span class="note">$/bbl from front-month NYMEX futures, ${l.d}</span>`,
      kpis(keys.map(k => [CRK[k], `${usd(l[k])}/bbl`, `1 month ago ${usd(ago(k, 30))}, 1 year ago ${usd(ago(k, 365))}; 52-wk percentile ${n0(pctl(yr.map(p => p[k]), l[k]), 0)}`]))
      + cv('eoilRfCrk', 'chart tall') +
      `<p class="note">HO and RB ($/gal) × 42 gal/bbl minus WTI. 3-2-1 = (2 × RBOB + 1 × ULSD)/3 − WTI. Continuous front months: HO and RB roll at the end of the month, CL around the 20th, so a few days around each roll compare different delivery months. The old terminal used Gulf Coast spot products against WTI Cushing; NY Harbor futures are used here because they are what trades.</p>`) +
      `<div class="grid g2" style="margin-top:12px"><div class="card"><h2>${CRK[main]} seasonality <span class="note">monthly average, $/bbl, vs prior 5 years</span></h2>${cv('eoilRfSea')}</div>
        <div class="card"><h2>${CRK[main]} by month <span class="note">$/bbl</span></h2><div class="tbl"><table><tr><th class="l">Month</th><th>${s.cy}</th><th>${s.cy - 1}</th><th>5-yr avg</th><th>5-yr range</th></tr>
        ${MON.map((m, i) => `<tr><td class="l">${m}</td><td>${n0(s.by[s.cy]?.[i], 2)}</td><td>${n0(s.by[s.cy - 1]?.[i], 2)}</td><td>${n0(s.avg[i], 2)}</td><td>${s.min[i] == null ? '–' : n0(s.min[i], 1) + ' – ' + n0(s.max[i], 1)}</td></tr>`).join('')}</table></div></div></div>`;
    const col = { c321: '#2f6b3a', ho: '#d68910', rb: '#7d3c98' };
    lineChart('eoilRfCrk', recent.map(p => p.d), keys.map((k, i) => ({ label: CRK[k], data: recent.map(p => p[k]), borderColor: col[k], borderWidth: i ? 1.2 : 2.2 })), '$/bbl');
    chart('eoilRfSea', { type: 'line', data: { labels: MON, datasets: seasonalDatasets(s) }, options: { spanGaps: true, plugins: { legend: legendNoMin }, scales: { y: { title: { display: true, text: '$/bbl', font: { size: 10 } } } } } });
  }
  async function refWtiBrent(host) {
    const [cl, bz, w, b] = await Promise.all([front('CL'), front('BZ'), eia('wti').catch(() => null), eia('brent').catch(() => null)]);
    const since = iso(new Date(Date.now() - 3 * 365 * DAY)), bm = alignMap(bz);
    const fut = cl.filter(r => r.d >= since && bm[r.d] != null).map(r => ({ d: r.d, v: r.v - bm[r.d] }));
    const sm = b ? alignMap(b) : {}, spot = w ? w.filter(r => r.d >= since && sm[r.d] != null).map(r => ({ d: r.d, v: r.v - sm[r.d] })) : [];
    if (!fut.length && !spot.length) throw new Error('no WTI/Brent prices');
    const lab = [...new Set([...fut.map(r => r.d), ...spot.map(r => r.d)])].sort(), fm = alignMap(fut), spm = alignMap(spot);
    const lf = lastOf(fut), ls = lastOf(spot);
    host.innerHTML = card(`WTI–Brent <span class="note">$/bbl, last 3 years</span>`,
      kpis([lf && ['Futures, front months', `${usd(lf.v)}/bbl`, `${lf.d}; 52-wk range ${n0(Math.min(...fut.slice(-252).map(r => r.v)), 1)} to ${n0(Math.max(...fut.slice(-252).map(r => r.v)), 1)}`],
        ls && ['Spot (EIA: WTI Cushing − Brent FOB)', `${usd(ls.v)}/bbl`, ls.d]]) + cv('eoilRfWb', 'chart short') +
      `<p class="note">More negative = WTI cheaper vs Brent, which pulls US exports. Front-month Brent expires about a month before WTI, so the futures line compares adjacent delivery months.</p>`);
    lineChart('eoilRfWb', lab, [{ label: 'Futures (CL − BZ front month)', data: lab.map(d => fm[d] ?? null), borderColor: '#2f6b3a', borderWidth: 1.8 },
      { label: 'Spot (EIA)', data: lab.map(d => spm[d] ?? null), borderColor: '#2c6fbb', borderWidth: 1.2 }], '$/bbl');
  }

  // ======================= 3. Futures curve =======================
  const UNIT = { NG: '$/MMBtu', CL: '$/bbl', HO: '$/gal', RB: '$/gal' };
  const DEC = { NG: 3, CL: 2, HO: 4, RB: 4 };
  const NAME = { NG: 'Henry Hub natural gas', CL: 'WTI crude', HO: 'NY Harbor ULSD', RB: 'RBOB gasoline' };
  const MC = 'FGHJKMNQUVXZ', MABB = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
  const cmeTxt = {};
  async function cmeCurve(d8, mk) {
    if (!(d8 in cmeTxt)) cmeTxt[d8] = fetch(`data/cme/${d8}/fut_settlements.csv`).then(r => r.ok ? r.text() : null).catch(() => null);
    const t = await cmeTxt[d8]; if (!t) return null;
    const out = [];
    t.trim().split(/\r?\n/).slice(1).forEach(line => { const c = line.split(','); if (c[1] !== mk) return;
      const [mo, yy] = c[3].split(' '), mi = MABB.indexOf(mo), st = parseFloat(c[9]); if (mi < 0 || !isFinite(st)) return;
      out.push({ m: c[3], y: 2000 + +yy, mi, key: (2000 + +yy) * 12 + mi, code: mk + MC[mi] + (2000 + +yy), F: st, oi: +c[11] || null }); });
    out.sort((a, b) => a.key - b.key);
    return out.length ? { date: `${d8.slice(0, 4)}-${d8.slice(4, 6)}-${d8.slice(6)}`, rows: out } : null;
  }
  const d8 = (d) => iso(d).replace(/-/g, '');
  async function probe(mk, target, back, fwd, stopAt) {
    for (let i = 0; i <= back; i++) { const d = new Date(target - i * DAY); if (d.getUTCDay() % 6 === 0) continue; const c = await cmeCurve(d8(d), mk); if (c) return c; }
    for (let i = 1; i <= fwd; i++) { const d = new Date(+target + i * DAY); if (stopAt && iso(d) >= stopAt) break; if (d.getUTCDay() % 6 === 0) continue; const c = await cmeCurve(d8(d), mk); if (c) return c; }
    return null;
  }
  async function curve(el, mk = 'CL') {
    el.innerHTML = '<div id="eoilCvA"></div><div id="eoilCvB"></div><div id="eoilCvC"></div>';
    await part($('#eoilCvA', el), 'Futures curve', () => curveNow($('#eoilCvA', el), mk));
    await part($('#eoilCvB', el), 'Front spread history', () => curveSpread($('#eoilCvB', el), mk));
    await part($('#eoilCvC', el), 'Price history', () => curvePrice($('#eoilCvC', el), mk));
  }
  async function curveNow(host, mk) {
    const today = new Date(Date.UTC(new Date().getUTCFullYear(), new Date().getUTCMonth(), new Date().getUTCDate()));
    let now = await probe(mk, today, 12, 0);
    let src = 'CME settlements (data/cme)';
    let wk = null, mo = null, yr = null;
    if (now) {
      const t0 = toD(now.date);
      wk = await probe(mk, new Date(t0 - 7 * DAY), 5, 3, now.date);
      mo = await probe(mk, new Date(t0 - 30 * DAY), 8, 14, wk ? wk.date : now.date);
      if (mo && wk && mo.date === wk.date) mo = null;
      // only look a year back if the archive reaches back at least a month (avoids pointless 404 probes)
      const oldest = mo || wk;
      if (oldest && toD(oldest.date) <= new Date(t0 - 30 * DAY)) yr = await probe(mk, new Date(t0 - 365 * DAY), 6, 6);
    } else {
      // fallback: option underlyings from the CME options file
      const o = await J(`data/options/${mk}.json`);
      if (!o) throw new Error('no CME settlement curve or options file');
      now = { date: o.date, rows: o.expiries.map(e => { const [m, yy] = e.underlying.split(' '); const mi = MABB.indexOf(m); return { m: e.underlying, y: 2000 + +yy, mi, key: (2000 + +yy) * 12 + mi, F: e.F }; }) };
      src = 'option underlyings (data/options)';
    }
    // EIA 1st–4th month history (ends where EIA stopped publishing futures) for a year-ago curve if nothing else
    const fk = mk === 'NG' ? 'fut' : mk === 'CL' ? 'ofut' : null;
    const N = mk === 'NG' ? 24 : mk === 'CL' ? 24 : 18;
    const cur = now.rows.slice(0, N), lab = cur.map(r => r.m);
    const onLab = (c) => { if (!c) return null; const m = {}; c.rows.forEach(r => m[r.m] = r.F); return lab.map(x => m[x] ?? null); };
    const sets = [{ label: `${now.date}`, data: cur.map(r => r.F), borderColor: '#c0392b', borderWidth: 2.4, pointRadius: 2 }];
    if (wk) sets.push({ label: `${wk.date} (~1 week ago)`, data: onLab(wk), borderColor: '#2c6fbb', borderWidth: 1.3, pointRadius: 0 });
    if (mo) sets.push({ label: `${mo.date} (${Math.round((toD(now.date) - toD(mo.date)) / DAY)} days ago)`, data: onLab(mo), borderColor: '#7f8c8d', borderDash: [4, 3], borderWidth: 1.3, pointRadius: 0 });
    // spreads by position (M1-M2 etc.), now vs comparisons
    const pos = (c, i) => c && c.rows[i] ? c.rows[i].F : null;
    const sp = (c, a, b) => pos(c, a) != null && pos(c, b) != null ? pos(c, a) - pos(c, b) : null;
    const pairs = [[0, 1, 'M1 – M2'], [1, 2, 'M2 – M3'], [0, 3, 'M1 – M4'], [0, 5, 'M1 – M6'], [0, 11, 'M1 – M12']].filter(p => pos(now, p[1]) != null);
    const dp = DEC[mk];
    const struct = (v) => v == null ? '' : v > 0 ? 'backwardation' : v < 0 ? 'contango' : 'flat';
    // year-ago: CME archive if present, else EIA monthly-position curve if it reaches that far back
    let yrNote = '';
    let yrFrom = yr ? `${yr.date}` : null;
    if (!yr && fk) {
      const e = await Promise.all([1, 2, 3, 4].map(i => eia(fk + i).catch(() => null)));
      const target = iso(new Date(toD(now.date) - 365 * DAY));
      if (e[0] && lastOf(e[0]).d >= iso(new Date(toD(target) - 10 * DAY))) {
        const pick = (a) => { const p = [...a].reverse().find(r => r.d <= target); return p ? p.v : null; };
        yr = { date: target, rows: e.map((a, i) => ({ F: a ? pick(a) : null, m: 'M' + (i + 1) })) }; yrFrom = `${target} (EIA contracts 1–4)`;
      } else yrNote = `No curve archived near ${target}: the repo's CME settlement files start ${mo ? mo.date : wk ? wk.date : now.date}${fk && e[0] ? `, and EIA's contract 1–4 series end ${lastOf(e[0]).d}` : ''}. The 1-year comparison fills in as the CME archive grows.`;
    }
    host.innerHTML = card(`${NAME[mk]} futures curve <span class="note">${UNIT[mk]}, settlements by contract month; source: ${src}</span>`,
      kpis([['Front month', `${cur[0].m}: ${n0(cur[0].F, dp)} ${UNIT[mk]}`, now.date], ['M1 – M2', `${sgn(sp(now, 0, 1), dp)}`, struct(sp(now, 0, 1))],
        pos(now, 11) != null && ['M1 – M12', `${sgn(sp(now, 0, 11), dp)}`, struct(sp(now, 0, 11))],
        mk === 'NG' && (() => { const w = cur.find(r => r.mi === 0 && r.key > cur[0].key), s = cur.find(r => r.mi === 3 && w && r.key > w.key - 12 && r.key < w.key + 12 && r.y === w.y); return w && s ? ['Winter–summer (Jan – Apr)', `${sgn(w.F - s.F, 3)}`, `${w.m} vs ${s.m}`] : null; })()]) +
      cv('eoilCvChart') +
      `<div class="tbl"><table><tr><th class="l">Spread (by position)</th><th>Now (${now.date})</th>${wk ? `<th>${wk.date}</th>` : ''}${mo ? `<th>${mo.date}</th>` : ''}${yr ? `<th>${yrFrom}</th>` : ''}<th>Change vs ${mo ? 'oldest' : wk ? 'week ago' : '–'}</th><th class="l">Structure</th></tr>
        ${pairs.map(([a, b, nm]) => { const v = sp(now, a, b), base = mo || wk; return `<tr><td class="l">${nm} <span class="note">${cur[a].m} – ${cur[b].m}</span></td><td>${sgn(v, dp)}</td>${wk ? `<td>${sgn(sp(wk, a, b), dp)}</td>` : ''}${mo ? `<td>${sgn(sp(mo, a, b), dp)}</td>` : ''}${yr ? `<td>${sgn(sp(yr, a, b), dp)}</td>` : ''}<td>${base ? sgn(v != null && sp(base, a, b) != null ? v - sp(base, a, b) : null, dp) : '–'}</td><td class="l">${struct(v)}</td></tr>`; }).join('')}</table></div>
      <p class="note">Spreads are nearer minus farther contract: positive = backwardation (prompt tight), negative = contango (storage paid). Earlier columns compare the same positions (M1, M2 …), so the contract months roll. ${yrNote}</p>`, 'margin-top:0');
    lineChart('eoilCvChart', lab, sets, UNIT[mk], { interaction: { mode: 'index' }, plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y == null ? '–' : c.parsed.y.toFixed(dp)}` } } } });
  }
  async function curveSpread(host, mk) {
    const dp = DEC[mk];
    // (a) fixed pair of the two nearest listed contracts, from data/ohlc/<mk>.csv
    const o = await C(`data/ohlc/${mk}.csv`);
    const ser = {}; (o || []).filter(r => r.series && r.series !== 'cont').forEach(r => { (ser[r.series] ||= {})[r.date] = r.close; });
    const codes = Object.keys(ser).sort((a, b) => { const k = (c) => +c.slice(-4) * 12 + MC.indexOf(c.slice(-5, -4)); return k(a) - k(b); });
    let pairLab = null, pair = [];
    if (codes.length >= 2) { const [a, b] = codes; pairLab = `${a} – ${b}`; pair = Object.keys(ser[a]).sort().filter(d => ser[b][d] != null && ser[a][d] != null).map(d => ({ d, v: ser[a][d] - ser[b][d] })); }
    // (b) EIA rolling contract 1 – contract 2 (the series EIA stopped publishing in 2024)
    const fk = mk === 'NG' ? 'fut' : mk === 'CL' ? 'ofut' : null;
    let roll = [];
    if (fk) { const [f1, f2] = await Promise.all([eia(fk + '1').catch(() => null), eia(fk + '2').catch(() => null)]); if (f1 && f2) { const m = alignMap(f2); roll = f1.filter(r => m[r.d] != null).map(r => ({ d: r.d, v: r.v - m[r.d] })); } }
    if (!pair.length && !roll.length) throw new Error('no contract or EIA spread history');
    host.innerHTML = `<div class="grid g2" style="margin-top:12px">
      ${pair.length ? `<div class="card"><h2>Nearest two contracts: ${pairLab} <span class="note">${UNIT[mk]}, daily closes</span></h2>${kpis([['Latest', sgn(lastOf(pair).v, dp), lastOf(pair).d], ['3 months ago', sgn(pair[Math.max(0, pair.length - 64)].v, dp)], ['1 year ago', sgn(pair[Math.max(0, pair.length - 253)].v, dp)]])}${cv('eoilCvPair', 'chart short')}<p class="note">Same two contracts throughout (no roll), from data/ohlc. Positive = backwardation.</p></div>` : ''}
      ${roll.length ? `<div class="card"><h2>Rolling 1st – 2nd month spread <span class="note">${UNIT[mk]}, EIA contract 1 − contract 2, ${roll[0].d} to ${lastOf(roll).d}</span></h2>${cv('eoilCvRoll', 'chart short')}<p class="note">History only: EIA stopped publishing futures prices after ${lastOf(roll).d}. Use it for the range of past spreads (e.g. how deep contango got in 2020), not for today's level.</p></div>`
        : `<div class="card"><h2>Rolling 1st – 2nd month spread</h2><p class="note">EIA never published a 2nd-month ${mk === 'HO' ? 'ULSD' : 'RBOB'} futures series (only contract 1, which ended in 2024); the fixed-pair chart is the spread history available.</p></div>`}</div>`;
    if (pair.length) lineChart('eoilCvPair', pair.map(r => r.d), [{ label: pairLab, data: pair.map(r => r.v), borderColor: '#2f6b3a' }], UNIT[mk]);
    if (roll.length) lineChart('eoilCvRoll', roll.map(r => r.d), [{ label: 'M1 − M2', data: roll.map(r => r.v), borderColor: '#2c6fbb', borderWidth: 1.2 }], UNIT[mk]);
  }
  function realVol(v) { const r = []; for (let i = 1; i < v.length; i++) if (v[i] > 0 && v[i - 1] > 0) r.push(Math.log(v[i] / v[i - 1])); const m = avg(r); return r.length > 5 ? Math.sqrt(r.reduce((a, b) => a + (b - m) ** 2, 0) / (r.length - 1) * 252) * 100 : null; }
  async function curvePrice(host, mk) {
    const dp = DEC[mk];
    const spotK = { NG: ['hhSpot', 'Henry Hub spot'], CL: ['wti', 'WTI Cushing spot'], HO: ['spotDist', 'Gulf Coast ULSD spot'], RB: ['spotGaso', 'Gulf Coast conventional gasoline spot'] }[mk];
    const [f, sp, br, f1] = await Promise.all([front(mk), eia(spotK[0]).catch(() => null), mk === 'CL' ? eia('brent').catch(() => null) : null,
      eia({ NG: 'fut1', CL: 'ofut1', HO: 'hofut1', RB: 'rbfut1' }[mk]).catch(() => null)]);
    if (!f.length) throw new Error('no front-month prices');
    const since = iso(new Date(Date.now() - 3 * 365 * DAY));
    const t = f.filter(r => r.d >= since), l = lastOf(t), back = (k) => t.length > k ? t[t.length - 1 - k].v : null, win = t.slice(-252).map(r => r.v);
    const sm = sp ? alignMap(sp) : {}, bm = br ? alignMap(br) : {};
    const lab = t.map(r => r.d);
    host.innerHTML = card(`${NAME[mk]}: front-month futures and spot <span class="note">${UNIT[mk]}, last 3 years</span>`,
      kpis([['Front month', `${n0(l.v, dp)} ${UNIT[mk]}`, l.d], ['1 day', sgn(back(1) ? (l.v / back(1) - 1) * 100 : null, 1, '%')], ['1 month', sgn(back(21) ? (l.v / back(21) - 1) * 100 : null, 1, '%')],
        ['52-week range', `${n0(Math.min(...win), dp)} – ${n0(Math.max(...win), dp)}`, `percentile ${n0(pctl(win, l.v), 0)}`], ['Realized vol', `${n0(realVol(t.slice(-61).map(r => r.v)), 0)}%`, '60-day, annualized'],
        sp && [spotK[1], `${n0(lastOf(sp).v, dp)} ${UNIT[mk]}`, lastOf(sp).d]]) + cv('eoilCvPx') +
      `<p class="note">Front month: continuous NYMEX front contract (data/ohlc, topped up from data/energy/prices.json). Spot: EIA daily${mk === 'CL' ? '; Brent is FOB Europe' : ''}.${f1 ? ` EIA's own contract-1 futures series ended ${lastOf(f1).d}.` : ''}</p>`);
    const sets = [{ label: 'Front-month futures', data: t.map(r => r.v), borderColor: '#c0392b', borderWidth: 1.8 }];
    if (sp) sets.push({ label: spotK[1], data: lab.map(d => sm[d] ?? null), borderColor: '#2c6fbb', borderWidth: 1.1 });
    if (br) sets.push({ label: 'Brent spot', data: lab.map(d => bm[d] ?? null), borderColor: '#d68910', borderWidth: 1.1 });
    lineChart('eoilCvPx', lab, sets, UNIT[mk]);
  }

  // ======================= 4. Options =======================
  const ETFS = { NG: ['UNG', 'BOIL', 'KOLD'], CL: ['USO', 'USL', 'BNO'], RB: ['UGA'], HO: [] };
  async function options(el, mk = 'CL') {
    el.innerHTML = '<div id="eoilOpA"></div><div id="eoilOpB"></div>';
    await part($('#eoilOpA', el), 'CME options summary', () => optCME($('#eoilOpA', el), mk));
    await part($('#eoilOpB', el), 'ETF options', () => optETF($('#eoilOpB', el), mk));
  }
  async function optCME(host, mk) {
    const o = await J(`data/options/${mk}.json`);
    if (!o || !o.expiries) throw new Error(`no data/options/${mk}.json`);
    const dp = DEC[mk], E = o.expiries.slice(0, 6);
    const tw = (o.term_week_ago || []).reduce((m, r) => (m[r.contract] = r.atm, m), {});
    const sm = (o.strike_maps || []).slice(0, 3);
    const top = (rows, k, n = 5) => [...rows].sort((a, b) => (b[k] || 0) - (a[k] || 0)).slice(0, n);
    host.innerHTML = `<div class="card" style="margin-top:0"><h2>${o.name || mk} options on futures <span class="note">CME settlements ${o.date}; implied vol in % a year</span></h2>
      ${o.read ? `<p>${o.read}</p>` : ''}
      <div class="tbl"><table><tr><th class="l">Expiry</th><th>Options expire</th><th>Days</th><th>Futures (${UNIT[mk]})</th><th>ATM IV</th><th>IV 1 wk ago</th><th>25Δ risk reversal</th><th>25Δ butterfly</th><th>RV 20d</th><th>Expected move</th><th>Put/call OI</th><th>Call wall</th><th>Put wall</th><th>Max pain</th></tr>
      ${E.map(e => `<tr><td class="l">${e.label}</td><td>${e.expiry}</td><td>${e.dte}</td><td>${n0(e.F, dp)}</td><td><b>${n0(e.atm, 1)}%</b></td><td>${tw[e.contract] != null ? n0(tw[e.contract], 1) + '%' : '–'}</td><td>${sgn(e.rr25, 2)}</td><td>${n0(e.bf25, 2)}</td><td>${n0(e.rv20, 1)}%</td><td>±${n0(e.move, dp)} (${n0(e.move_pct, 1)}%)</td><td>${n0(e.pc_oi, 2)}</td><td>${e.call_wall ?? '–'}</td><td>${e.put_wall ?? '–'}</td><td>${e.max_pain ?? '–'}</td></tr>`).join('')}</table></div>
      <p class="note">25Δ risk reversal = 25-delta call IV minus 25-delta put IV (positive = calls bid, upside skew). Call/put wall = strike with the most call/put open interest. Expected move = futures × ATM IV × √(days/365). ${o.note || ''}</p></div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>ATM implied vol term structure <span class="note">% a year</span></h2>${cv('eoilOpTerm', 'chart short')}</div>
        <div class="card"><h2>Open interest by strike: ${sm[0] ? sm[0].label : ''} <span class="note">contracts; calls up, puts down</span></h2>${sm[0] ? cv('eoilOpOi', 'chart short') : '<p class="note">No strike data.</p>'}</div></div>
      ${sm.length ? `<div class="card" style="margin-top:12px"><h2>Largest open-interest strikes <span class="note">top 5 calls and puts per expiry, contracts</span></h2><div class="grid g2">
        ${sm.map(s => `<div><h3>${s.label} (futures ${n0(s.F, dp)})</h3><div class="tbl"><table><tr><th>Call strike</th><th>Call OI</th><th>Put strike</th><th>Put OI</th></tr>
          ${(() => { const c = top(s.rows, 'cOI'), p = top(s.rows, 'pOI'); return c.map((r, i) => `<tr><td>${r.K}</td><td>${fmt(r.cOI, 0)}</td><td>${p[i] ? p[i].K : '–'}</td><td>${p[i] ? fmt(p[i].pOI, 0) : '–'}</td></tr>`).join(''); })()}</table></div></div>`).join('')}</div></div>` : ''}`;
    const term = o.term || [];
    chart('eoilOpTerm', { type: 'line', data: { labels: term.map(t => t.label), datasets: [
      { label: o.date, data: term.map(t => t.atm), borderColor: '#c0392b', borderWidth: 2, pointRadius: 2 },
      { label: `${o.week_ago || 'week ago'}`, data: term.map(t => tw[t.contract] ?? null), borderColor: '#2c6fbb', borderDash: [4, 3], borderWidth: 1.2, pointRadius: 0 }] },
      options: { scales: { y: { title: { display: true, text: 'ATM IV, %', font: { size: 10 } } } } } });
    if (sm[0]) {
      const r = sm[0].rows.filter(x => x.K > sm[0].F * 0.7 && x.K < sm[0].F * 1.3);
      chart('eoilOpOi', { type: 'bar', data: { labels: r.map(x => x.K), datasets: [{ label: 'call OI', data: r.map(x => x.cOI), backgroundColor: 'rgba(47,107,58,.7)' }, { label: 'put OI', data: r.map(x => -x.pOI), backgroundColor: 'rgba(192,57,43,.7)' }] },
        options: { scales: { x: { stacked: true, title: { display: true, text: `strike, ${UNIT[mk]} (futures ${sm[0].F})`, font: { size: 10 } } }, y: { stacked: true, ticks: { callback: (v) => Math.abs(v).toLocaleString() } } },
          plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${Math.abs(c.parsed.y).toLocaleString()}` } } } } });
    }
  }
  function etfStats(ch) {
    const und = ch.spot, byK = {};
    ch.rows.forEach(r => { const b = byK[r.strike] ||= { c: 0, p: 0, cv: 0, pv: 0 }; if (r.type === 'C') { b.c += r.oi || 0; b.cv += r.vol || 0; } else { b.p += r.oi || 0; b.pv += r.vol || 0; } });
    const ks = Object.keys(byK).map(Number).sort((a, b) => a - b).filter(K => !und || (K > und * 0.55 && K < und * 1.7));
    const sum = (f) => ks.reduce((a, K) => a + byK[K][f], 0);
    let mp = null, best = Infinity;
    ks.forEach(K => { let pain = 0; ks.forEach(K2 => { if (K > K2) pain += (K - K2) * byK[K2].c; if (K < K2) pain += (K2 - K) * byK[K2].p; }); if (pain < best) { best = pain; mp = K; } });
    const cw = ks.length ? ks.reduce((a, K) => byK[K].c > byK[a].c ? K : a, ks[0]) : null, pw = ks.length ? ks.reduce((a, K) => byK[K].p > byK[a].p ? K : a, ks[0]) : null;
    return { und, byK, ks, co: sum('c'), po: sum('p'), cv: sum('cv'), pv: sum('pv'), mp, cw, pw, exps: ch.expiries || [] };
  }
  async function optETF(host, mk) {
    const list = ETFS[mk] || [];
    if (!list.length) { host.innerHTML = card('ETF options', '<p class="note">No listed ETF tracks ULSD/heating oil with an active option chain, so this desk has no ETF option panel.</p>'); return; }
    const o = await J('data/energy/options.json');
    if (!o || !o.chains) throw new Error('no data/energy/options.json');
    const have = list.filter(t => o.chains[t] && o.chains[t].rows && o.chains[t].rows.length);
    if (!have.length) throw new Error(`no chains for ${list.join('/')}`);
    const S = Object.fromEntries(have.map(t => [t, etfStats(o.chains[t])]));
    host.innerHTML = card(`ETF option open interest and volume <span class="note">all listed expiries, Yahoo chains, generated ${o.generated}</span>`,
      `<div class="tbl"><table><tr><th class="l">ETF</th><th>Price ($)</th><th>Expiries</th><th>Call OI</th><th>Put OI</th><th>Put/call OI</th><th>Call vol</th><th>Put vol</th><th>Put/call vol</th><th>Volume ÷ OI</th><th>Call wall ($)</th><th>Put wall ($)</th><th>Max pain ($)</th></tr>
      ${have.map(t => { const s = S[t]; return `<tr><td class="l"><b>${t}</b></td><td>${n0(s.und, 2)}</td><td>${s.exps.length}</td><td>${fmt(s.co, 0)}</td><td>${fmt(s.po, 0)}</td><td>${n0(s.po / Math.max(1, s.co), 2)}</td><td>${fmt(s.cv, 0)}</td><td>${fmt(s.pv, 0)}</td><td>${n0(s.pv / Math.max(1, s.cv), 2)}</td><td>${n0((s.cv + s.pv) / Math.max(1, s.co + s.po), 2)}</td><td>${s.cw}</td><td>${s.pw}</td><td>${s.mp} <span class="note">(${sgn(s.und ? (s.mp / s.und - 1) * 100 : null, 1, '%')})</span></td></tr>`; }).join('')}</table></div>
      <div class="mk-bar" id="eoilOpEtfBar" style="margin-top:10px">${have.map((t, i) => `<button data-t="${t}" class="${i ? '' : 'on'}">${t}</button>`).join('')}</div>
      <div class="grid g2"><div><h3>Open interest by strike (calls up, puts down)</h3>${cv('eoilOpEtfOi', 'chart short')}</div><div><h3>Volume by strike (calls up, puts down)</h3>${cv('eoilOpEtfVol', 'chart short')}</div></div>
      <p class="note">Strikes within 55%–170% of the ETF price. Max pain = strike where option holders' total payoff at expiry is smallest. ${mk === 'NG' ? 'BOIL and KOLD are 2× leveraged long/short Henry Hub ETFs; UNG holds front-month futures.' : mk === 'CL' ? 'USO holds front-month WTI, USL a 12-month strip, BNO Brent.' : 'UGA holds front-month RBOB.'}</p>`);
    const draw = (t) => { const s = S[t], lab = s.ks.map(K => K);
      const bar = (id, a, b, nm) => chart(id, { type: 'bar', data: { labels: lab, datasets: [{ label: 'call ' + nm, data: s.ks.map(K => s.byK[K][a]), backgroundColor: 'rgba(47,107,58,.7)' }, { label: 'put ' + nm, data: s.ks.map(K => -s.byK[K][b]), backgroundColor: 'rgba(192,57,43,.7)' }] },
        options: { scales: { x: { stacked: true, title: { display: true, text: `${t} strike, $ (price ${n0(s.und, 2)})`, font: { size: 10 } } }, y: { stacked: true, ticks: { callback: (v) => Math.abs(v).toLocaleString() } } },
          plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${Math.abs(c.parsed.y).toLocaleString()}` } } } } });
      bar('eoilOpEtfOi', 'c', 'p', 'OI'); bar('eoilOpEtfVol', 'cv', 'pv', 'volume'); };
    $$('#eoilOpEtfBar button', host).forEach(b => b.onclick = () => { $$('#eoilOpEtfBar button', host).forEach(x => x.classList.toggle('on', x === b)); draw(b.dataset.t); });
    draw(have[0]);
  }

  // ======================= 5. Data freshness =======================
  function bizDays(from, to) { let n = 0; const d = new Date(from); while (d < to) { d.setUTCDate(d.getUTCDate() + 1); if (d.getUTCDay() % 6 !== 0 && d <= to) n++; } return n; }
  async function freshness(el) {
    try {
      const ix = await J(EIA + 'index.json');
      if (!ix || !ix.series) throw new Error('no data/energy/eia/index.json');
      const now = new Date(), today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
      const keys = Object.keys(ix.series);
      const rows = await Promise.all(keys.map(async k => {
        const meta = ix.series[k], j = await J(EIA + k + '.json');
        const r = j?.rows || [], freq = j?.freq || (k.startsWith('steo') ? 'monthly' : '?');
        // latest observation not in the future (STEO carries forecasts)
        const past = r.filter(x => x[1] != null && toD(x[0]) <= today), lastObs = past.length ? past.at(-1)[0] : null, lastAny = r.length ? r.at(-1)[0] : null;
        let age = null, stale = !j || !lastObs, why = !j ? 'file missing' : !lastObs ? 'no observations' : '';
        if (lastObs) {
          const ld = toD(lastObs); if (lastObs.length === 7) ld.setUTCMonth(ld.getUTCMonth() + 1, 0); // month end
          age = Math.round((today - ld) / DAY);
          if (freq === 'weekly' && age > 14) { stale = true; why = `${age} days old (weekly; a missed release)`; }
          else if (freq === 'daily' && bizDays(ld, today) > 4) { stale = true; why = `${bizDays(ld, today)} business days old`; }
          else if (freq === 'monthly' && age > 75) { stale = true; why = `${age} days after month end`; }
        }
        if (stale && /^(o?fut\d|hofut1|rbfut1)$/.test(k) && lastObs) why += '; EIA stopped publishing futures prices — the desk uses CME settlements instead';
        return { k, label: j?.label || meta.label, freq, lastObs, lastAny, rows: r.length || meta.rows || 0, fetched: j?.fetched || '–', id: j?.id || meta.id, stale, why, fc: lastAny && lastAny !== lastObs };
      }));
      const others = await Promise.all([['data/energy/prices.json', 'Futures and ETF prices (Yahoo)', 'generated'], ['data/energy/summary.json', 'Energy summary (cracks, vol, inventories)', 'generated'],
        ['data/energy/sd.json', 'Supply-demand models', 'generated'], ['data/energy/options.json', 'ETF option chains', 'generated'], ['data/energy/wx/signal.json', 'Gas weather / positioning signal', 'generated'],
        ...['NG', 'CL', 'HO', 'RB'].map(m => [`data/options/${m}.json`, `${m} options on futures (CME settlements)`, 'date'])].map(async ([u, nm, f]) => {
        const j = await J(u); const g = j ? j[f] : null; const gd = g ? new Date(String(g).replace(' UTC', 'Z').replace(' ', 'T') + (String(g).length <= 10 ? 'T00:00:00Z' : '')) : null;
        const bd = gd && !isNaN(gd) ? bizDays(new Date(Date.UTC(gd.getUTCFullYear(), gd.getUTCMonth(), gd.getUTCDate())), today) : null;
        return { u, nm, g: g || 'missing', stale: !j || bd == null || bd > 3, bd };
      }));
      const nStale = rows.filter(r => r.stale).length;
      const flag = (r) => r.stale ? `<span class="flag dn">stale</span>` : `<span class="flag up">ok</span>`;
      el.innerHTML = `<div class="card"><h2>Data freshness <span class="note">checked ${iso(today)}; ${keys.length} EIA series, ${nStale} flagged</span></h2>
        <div class="tbl"><table><tr><th class="l">File</th><th class="l">Generated / dated</th><th>Business days old</th><th class="l">Status</th></tr>
        ${others.map(o => `<tr><td class="l">${o.nm} <span class="note">${o.u}</span></td><td class="l">${o.g}</td><td>${o.bd ?? '–'}</td><td class="l">${flag(o)}</td></tr>`).join('')}</table></div>
        <h3>EIA series (data/energy/eia)</h3>
        <div class="tbl"><table><tr><th class="l">Key</th><th class="l">Series</th><th class="l">Frequency</th><th>Last observation</th><th>Rows</th><th class="l">Fetched</th><th class="l">Status</th></tr>
        ${rows.sort((a, b) => (b.stale - a.stale) || a.k.localeCompare(b.k)).map(r => `<tr><td class="l">${r.k}</td><td class="l">${r.label}<br><span class="note">${r.id || ''}</span></td><td class="l">${r.freq}</td><td>${r.lastObs || '–'}${r.fc ? `<br><span class="note">forecast to ${r.lastAny}</span>` : ''}</td><td>${fmt(r.rows, 0)}</td><td class="l">${r.fetched}</td><td class="l">${flag(r)} ${r.why ? `<span class="note">${r.why}</span>` : ''}</td></tr>`).join('')}</table></div>
        <p class="note">Stale rules: weekly series more than 14 days past the last observation (EIA publishes a Friday week the following Wednesday/Thursday, so a healthy series can be 13 days old just before a release), daily series more than 4 business days, monthly series more than 75 days after the end of the last month (EIA monthly data normally lags about two months). STEO series include EIA forecasts; the last observation shown is the latest month not in the future. Other files flagged after 3 business days.</p></div>`;
    } catch (e) { el.innerHTML = `<div class="card"><p class="note">Data freshness: not available (${String(e.message || e).slice(0, 120)}).</p></div>`; }
  }

  return { stocks, refining, curve, options, freshness };
})();
