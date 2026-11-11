// Natural gas panels for the Energy section (ported from the retired single-page energy terminal, energy.html).
// Everything reads same-origin repo JSON written by the workflows; no browser API calls.
// Mounts: EnergyNG.storage(el), EnergyNG.sdMonthly(el) (appends), EnergyNG.weather(el, mk), EnergyNG.model(el).
const EnergyNG = (() => {
  const MS_D = 86400000;
  const J = {};                                   // module-level JSON cache
  const load = (u) => (J[u] ||= fetch(u + '?v=' + Date.now().toString().slice(0, 8)).then(r => { if (!r.ok) throw new Error(u.split('/').pop() + ' ' + r.status); return r.json(); }).catch(e => { delete J[u]; throw e; }));
  const eia = async (k) => (await load(`data/energy/eia/${k}.json`)).rows.map(r => ({ d: dp(r[0]), s: r[0], v: r[1] }));
  const dp = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d || 1)); };
  const ds = (dt) => dt.toISOString().slice(0, 10);
  const ym = (dt) => ds(dt).slice(0, 7);
  const n = (v, d = 0) => fmt(v, d);
  const sg = (v, d = 0, suf = '') => sgn(v, d, suf);
  const avg = (a) => { const x = a.filter(v => v != null && !isNaN(v)); return x.length ? x.reduce((p, c) => p + c, 0) / x.length : null; };
  const sum = (a) => a.reduce((p, c) => p + (c || 0), 0);
  const BLUE = '#2c6fbb', RED = '#c0392b', GREEN = '#2f6b3a', GREY = '#999', ORANGE = '#d68910', PURPLE = '#7d3c98', TEAL = '#17a589';
  const kpis = (rows) => `<div class="kpi-row" style="display:flex;flex-wrap:wrap;gap:22px;margin:8px 0 10px">${rows.map(([k, v, s]) => `<div><div class="note">${k}</div><b style="font-size:17px">${v}</b>${s ? `<div class="note">${s}</div>` : ''}</div>`).join('')}</div>`;
  const card = (id, extra = '') => `<div class="card" id="${id}" style="margin-top:12px${extra}"><p class="note">Loading…</p></div>`;
  const fail = (id, e) => { const c = document.getElementById(id); if (c) c.innerHTML = `<p class="note">This panel could not be built (${String(e && e.message || e).slice(0, 140)}).</p>`; };
  // run one panel builder; a failure shows a short note in that panel only
  async function panel(id, fn) { try { const c = document.getElementById(id); if (c) await fn(c); } catch (e) { console.warn('EnergyNG', id, e); fail(id, e); } }
  const still = (h) => location.hash === h;       // user may switch tabs while data loads
  const xMax = { x: { ticks: { maxTicksLimit: 10 } } };

  /* ---------- gas-year helpers (gas year starts 1 April) ---------- */
  function gasDay(dt) { const y = dt.getUTCMonth() >= 3 ? dt.getUTCFullYear() : dt.getUTCFullYear() - 1; return { gy: y, day: Math.round((dt - Date.UTC(y, 3, 1)) / MS_D) }; }
  function seasonMap(rows) { const by = {}; rows.forEach(r => { const g = gasDay(r.d); (by[g.gy] ||= []).push({ day: g.day, v: r.v, d: r.d }); }); Object.values(by).forEach(a => a.sort((x, y) => x.day - y.day)); return by; }
  function interpAtDay(arr, day) { if (!arr || !arr.length) return null; let best = null, bd = 8; for (const p of arr) { const dd = Math.abs(p.day - day); if (dd < bd) { bd = dd; best = p.v; } } return best; }
  function fiveYrAvgAt(by, gy, day) { const v = []; for (let y = gy - 5; y < gy; y++) { const a = interpAtDay(by[y], day); if (a !== null) v.push(a); } return v.length ? avg(v) : null; }
  const gdLabel = (d) => { const dt = new Date(Date.UTC(2001, 3, 1) + d * MS_D); return MON[dt.getUTCMonth()] + ' ' + String(dt.getUTCDate()).padStart(2, '0'); };
  const gyLbl = (y) => `${y}/${String(y + 1).slice(2)}`;

  /* ---------- degree-day helpers ---------- */
  let HH = null;  // {dd:{date:[hdd,cdd]}, normH:{MM-DD}, normC:{MM-DD}, last}
  async function hddHist() {
    if (HH) return HH;
    const j = await load('data/energy/wx/hdd_hist.json');
    const accH = {}, accC = {};
    for (const [d, [h, c]] of Object.entries(j.daily)) {
      const y = +d.slice(0, 4); if (y < 2016 || y > 2025) continue;
      const k = d.slice(5); (accH[k] ||= []).push(h); (accC[k] ||= []).push(c);
    }
    const normH = {}, normC = {}; for (const k in accH) { normH[k] = avg(accH[k]); normC[k] = avg(accC[k]); }
    const dates = Object.keys(j.daily).sort();
    HH = { dd: j.daily, normH, normC, first: dates[0], last: dates.at(-1), generated: j.generated, cities: j.cities };
    return HH;
  }
  const md = (dt) => (typeof dt === 'string' ? dt.slice(5) : ds(dt).slice(5));
  const nH = (H, dt) => H.normH[md(dt)] ?? H.normH[md(dt) === '02-29' ? '02-28' : ''] ?? 0;
  const nC = (H, dt) => H.normC[md(dt)] ?? H.normC[md(dt) === '02-29' ? '02-28' : ''] ?? 0;
  const ensName = (R) => { const m = R.at(-1).models; return Object.keys(m).find(k => /^ECMWF ENS/.test(k)) || Object.keys(m)[0]; };

  /* ======================================================================
     1. STORAGE
     ====================================================================== */
  async function storage(el) {
    const h = location.hash;
    el.innerHTML = `${card('engStHero', ';margin-top:0')}
      <div class="grid g2">${card('engStNet')}${card('engStDev')}</div>
      ${card('engStReg')}${card('engStGy')}
      <div class="grid g2">${card('engStTot')}${card('engStHh')}</div>`;
    let stor; try { stor = await eia('storL48'); } catch (e) { ['engStHero', 'engStNet', 'engStDev', 'engStGy', 'engStTot'].forEach(id => fail(id, e)); }
    if (!still(h)) return;
    if (stor) {
      await panel('engStHero', c => storHero(c, stor, 5));
      await panel('engStNet', c => storNet(c, stor));
      await panel('engStDev', c => storDev(c, stor));
      await panel('engStGy', c => storGasYears(c, stor));
      await panel('engStTot', c => storTotals(c, stor));
    }
    await panel('engStReg', storRegions);
    await panel('engStHh', hhSeason);
  }
  function storHero(c, stor, nBack) {
    const by = seasonMap(stor), years = Object.keys(by).map(Number).sort((a, b) => a - b);
    const cur = years.at(-1), prev = cur - 1, hist = years.filter(y => y < cur && y >= cur - nBack);
    const days = []; for (let d = 0; d <= 364; d += 7) days.push(d);
    const st = (f) => days.map(d => { const v = hist.map(y => interpAtDay(by[y], d)).filter(x => x !== null); return v.length ? f(v) : null; });
    const a = st(avg), mn = st(v => Math.min(...v)), mx = st(v => Math.max(...v));
    const curY = days.map(d => interpAtDay(by[cur], d)), prevY = days.map(d => interpAtDay(by[prev], d));
    const last = stor.at(-1), pw = stor.at(-2), g = gasDay(last.d);
    const avgNow = avg(hist.map(y => interpAtDay(by[y], g.day)).filter(x => x !== null));
    const yrAgo = interpAtDay(by[prev], g.day), chg = last.v - pw.v;
    const avgChg = avg(hist.map(y => { const p = interpAtDay(by[y], g.day), q = interpAtDay(by[y], g.day - 7); return p !== null && q !== null ? p - q : null; }).filter(x => x !== null));
    c.innerHTML = `<h2>Lower 48 working gas <span class="note">EIA weekly storage report (Thu 10:30 ET), week ending ${last.s}; Bcf</span>
        <select id="engStYrs" style="float:right">${[3, 5, 10].map(y => `<option value="${y}" ${y === nBack ? 'selected' : ''}>${y} seasons</option>`).join('')}</select></h2>
      ${kpis([['Working gas', n(last.v) + ' Bcf', ''], ['Weekly change', sg(chg) + ' Bcf', `${nBack}-yr avg ${sg(avgChg)} · surprise ${sg(chg - avgChg)} Bcf`],
        [`vs ${nBack}-yr average`, sg(last.v - avgNow) + ' Bcf', sg((last.v / avgNow - 1) * 100, 1, '%')], ['vs year ago', sg(last.v - yrAgo) + ' Bcf', n(yrAgo) + ' Bcf then'],
        ['Season', g.day < 214 ? 'Injection' : 'Withdrawal', `day ${g.day} of gas year ${gyLbl(g.gy)}`]])}
      <div class="chart tall"><canvas id="engStSea"></canvas></div><p class="note">Gas year runs 1 April to 31 March. Shaded band = ${nBack}-season min–max.</p>`;
    chart('engStSea', { type: 'line', data: { labels: days.map(gdLabel), datasets: [
      { label: `${nBack}-yr range`, data: mx, borderWidth: 0, pointRadius: 0, backgroundColor: 'rgba(214,137,16,.15)', fill: '+1' },
      { label: '_min', data: mn, borderWidth: 0, pointRadius: 0, fill: false },
      { label: `${nBack}-yr average`, data: a, borderColor: GREY, borderDash: [4, 3], borderWidth: 1.2, pointRadius: 0 },
      { label: gyLbl(prev), data: prevY, borderColor: BLUE, borderWidth: 1.4, pointRadius: 0 },
      { label: gyLbl(cur), data: curY, borderColor: RED, borderWidth: 2.4, pointRadius: 2 }] },
      options: { plugins: { legend: legendNoMin }, scales: { y: { title: { display: true, text: 'Bcf', font: { size: 10 } } } } } });
    document.getElementById('engStYrs').onchange = (ev) => storHero(c, stor, +ev.target.value);
  }
  function storNet(c, stor) {
    const by = seasonMap(stor), years = Object.keys(by).map(Number);
    const tail = stor.slice(-79), nets = [], navg = [], nd = [];
    for (let i = 1; i < tail.length; i++) {
      nets.push(tail[i].v - tail[i - 1].v); nd.push(tail[i].s);
      const g = gasDay(tail[i].d);
      navg.push(avg(years.filter(y => y < g.gy && y >= g.gy - 5).map(y => { const p = interpAtDay(by[y], g.day), q = interpAtDay(by[y], g.day - 7); return p !== null && q !== null ? p - q : null; }).filter(x => x !== null)));
    }
    c.innerHTML = `<h2>Weekly net change vs 5-year average <span class="note">Bcf, last 78 weeks</span></h2><div class="chart"><canvas id="engStNetC"></canvas></div>`;
    chart('engStNetC', { type: 'bar', data: { labels: nd, datasets: [
      { type: 'line', label: '5-yr average change', data: navg, borderColor: '#555', borderDash: [3, 3], borderWidth: 1.3, pointRadius: 0 },
      { label: 'actual change', data: nets, backgroundColor: nets.map(v => v >= 0 ? 'rgba(47,107,58,.7)' : 'rgba(192,57,43,.7)') }] },
      options: { scales: { y: { title: { display: true, text: 'Bcf/week', font: { size: 10 } } } } } });
  }
  function storDev(c, stor) {
    const by = seasonMap(stor), years = Object.keys(by).map(Number);
    const dev = [], dd = [];
    stor.slice(-160).forEach(r => { const g = gasDay(r.d); const v = years.filter(y => y < g.gy && y >= g.gy - 5).map(y => interpAtDay(by[y], g.day)).filter(x => x !== null); if (v.length) { dev.push(r.v - avg(v)); dd.push(r.s); } });
    c.innerHTML = `<h2>Surplus / deficit to 5-year average <span class="note">Bcf, last ~3 years</span></h2><div class="chart"><canvas id="engStDevC"></canvas></div>
      <p class="note">The slope matters more than the level: a shrinking surplus is a tightening balance even while the number stays positive.</p>`;
    chart('engStDevC', { type: 'bar', data: { labels: dd, datasets: [{ label: 'vs 5-yr average', data: dev, backgroundColor: dev.map(v => v >= 0 ? 'rgba(47,107,58,.65)' : 'rgba(192,57,43,.65)') }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { title: { display: true, text: 'Bcf', font: { size: 10 } } } } } });
  }
  async function storRegions(c) {
    const R = [['East', 'storEast'], ['Midwest', 'storMw'], ['Mountain', 'storMtn'], ['Pacific', 'storPac'], ['South Central', 'storSc'], ['&nbsp;&nbsp;— salt', 'storScSalt'], ['&nbsp;&nbsp;— non-salt', 'storScNon']];
    const rows = await Promise.all(R.map(([, k]) => eia(k).catch(() => null)));
    let asof = '', body = '';
    R.forEach(([name], i) => {
      const arr = rows[i]; if (!arr || !arr.length) { body += `<tr><td>${name}</td><td colspan="6" class="l note">no data</td></tr>`; return; }
      const l = arr.at(-1), p = arr.at(-2), by = seasonMap(arr), g = gasDay(l.d), a5 = fiveYrAvgAt(by, g.gy, g.day), ya = interpAtDay(by[g.gy - 1], g.day);
      asof = l.s;
      body += `<tr><td>${name}</td><td>${n(l.v)}</td><td>${p ? sg(l.v - p.v) : '–'}</td><td>${n(a5)}</td><td>${sg(l.v - a5)}</td><td>${a5 ? sg((l.v / a5 - 1) * 100, 1, '%') : '–'}</td><td>${ya != null ? sg(l.v - ya) : '–'}</td></tr>`;
    });
    c.innerHTML = `<h2>Regional storage <span class="note">Bcf, week ending ${asof}</span></h2><div class="tbl"><table><tr><th>Region</th><th>Working gas</th><th>Weekly change</th><th>5-yr avg</th><th>vs 5-yr avg</th><th>vs 5-yr avg %</th><th>vs year ago</th></tr>${body}</table></div>
      <p class="note">South Central salt caverns cycle fastest and are the cleanest read on near-term physical tightness.</p>`;
  }
  function storGasYears(c, stor) {
    const by = seasonMap(stor), years = Object.keys(by).map(Number).sort((a, b) => a - b).slice(-8);
    const days = []; for (let d = 0; d <= 364; d += 7) days.push(d);
    const pal = ['#c9d6e3', '#a9bfd6', '#89a8c9', '#6a91bb', '#4c7aad', '#7f8c8d', BLUE, RED];
    c.innerHTML = `<h2>Storage by gas year <span class="note">Bcf, April through March, last 8 gas years</span></h2><div class="chart tall"><canvas id="engStGyC"></canvas></div>`;
    chart('engStGyC', { type: 'line', data: { labels: days.map(gdLabel), datasets: years.map((y, i) => ({ label: gyLbl(y), data: days.map(d => interpAtDay(by[y], d)),
      borderColor: pal[i + pal.length - years.length] || GREY, borderWidth: i === years.length - 1 ? 2.6 : 1.3, pointRadius: 0 })) } });
  }
  function storTotals(c, stor) {
    const by = seasonMap(stor), years = Object.keys(by).map(Number).sort((a, b) => a - b).slice(-10).reverse();
    let t = '<tr><th>Gas year</th><th>1 Apr</th><th>Autumn peak</th><th>Injected</th><th>Winter trough</th><th>Withdrawn</th></tr>';
    years.forEach(y => {
      const a = by[y]; if (!a || a.length < 3) return;
      const s0 = interpAtDay(a, 0), pkA = a.filter(p => p.day >= 180 && p.day <= 240).map(p => p.v), trA = a.filter(p => p.day >= 270).map(p => p.v);
      const pk = pkA.length ? Math.max(...pkA) : null, tr = trA.length ? Math.min(...trA) : null;
      t += `<tr><td>${gyLbl(y)}${y === years[0] ? ' <span class="note">(in progress)</span>' : ''}</td><td>${n(s0)}</td><td>${n(pk)}</td><td>${pk != null && s0 != null ? sg(pk - s0) : '–'}</td><td>${n(tr)}</td><td>${tr != null && pk != null ? sg(tr - pk) : '–'}</td></tr>`;
    });
    c.innerHTML = `<h2>Season totals <span class="note">Bcf, Lower 48</span></h2><div class="tbl"><table>${t}</table></div><p class="note">Peak = highest reading Sep 27–Nov 27; trough = lowest from late Dec to the end of March.</p>`;
  }
  async function hhSeason(c) {
    const sp = await eia('hhSpot');
    const byM = {}; sp.forEach(r => { (byM[r.s.slice(0, 7)] ||= []).push(r.v); });
    const mo = Array.from({ length: 12 }, () => []), curY = sp.at(-1).s.slice(0, 4), cy = Array(12).fill(null);
    for (const k in byM) { const m = +k.slice(5) - 1, a = avg(byM[k]); if (k.slice(0, 4) === curY) cy[m] = a; else mo[m].push(a); }
    c.innerHTML = `<h2>Henry Hub monthly seasonality <span class="note">$/MMBtu, monthly average spot, ${sp[0].s.slice(0, 4)}–${+curY - 1} vs ${curY}</span></h2><div class="chart"><canvas id="engStHhC"></canvas></div>
      <p class="note">EIA Henry Hub daily spot, latest ${sp.at(-1).s} at $${n(sp.at(-1).v, 2)}/MMBtu.</p>`;
    chart('engStHhC', { type: 'line', data: { labels: MON, datasets: [
      { label: 'range', data: mo.map(a => a.length ? Math.max(...a) : null), borderWidth: 0, pointRadius: 0, backgroundColor: 'rgba(214,137,16,.15)', fill: '+1' },
      { label: '_min', data: mo.map(a => a.length ? Math.min(...a) : null), borderWidth: 0, pointRadius: 0, fill: false },
      { label: 'average', data: mo.map(a => avg(a)), borderColor: GREEN, borderWidth: 2, pointRadius: 2 },
      { label: curY, data: cy, borderColor: RED, borderWidth: 2, pointRadius: 3 }] },
      options: { plugins: { legend: legendNoMin }, scales: { y: { title: { display: true, text: '$/MMBtu', font: { size: 10 } } } } } });
  }

  /* ======================================================================
     2. GAS S&D (monthly) — appended under the shared S&D tab
     ====================================================================== */
  const toBcfd = (arr) => { const o = {}; arr.forEach(r => { const dim = new Date(Date.UTC(r.d.getUTCFullYear(), r.d.getUTCMonth() + 1, 0)).getUTCDate(); o[r.s.slice(0, 7)] = r.v / 1000 / dim; }); return o; };
  async function sdMonthly(el) {
    const h = location.hash;
    const keys = ['prodDry', 'consTot', 'consRes', 'consCom', 'consInd', 'consPow', 'expLng', 'expTot', 'impTot'];
    const got = await Promise.all(keys.map(k => eia(k).catch(() => null)));
    const steoK = ['steoProd', 'steoCons', 'steoLng', 'steoHdd', 'steoCdd'];
    const steo = await Promise.all(steoK.map(k => eia(k).catch(() => null)));
    // the shared S&D view (energy_desk.js) replaces the tab body after its own fetch; wait for it before appending
    for (let i = 0; i < 60 && !el.querySelector('#esdSea, .card, .note'); i++) await new Promise(r => setTimeout(r, 100));
    await new Promise(r => setTimeout(r, 50));
    if (!still(h) || !el.isConnected) return;
    document.getElementById('engSdRoot')?.remove();
    el.insertAdjacentHTML('beforeend', `<div id="engSdRoot">${card('engSdBal')}<div class="grid g2">${card('engSdCons')}${card('engSdImp')}</div>${card('engSdTbl')}${card('engSdSteo')}<div class="grid g2">${card('engSdDd')}${card('engSdStor')}</div></div>`);
    const S = {}; keys.forEach((k, i) => S[k] = got[i] ? toBcfd(got[i]) : null);
    const ST = {}; steoK.forEach((k, i) => ST[k] = steo[i]);
    await panel('engSdBal', c => sdBalance(c, S, 60));
    await panel('engSdSteo', c => sdSteo(c, ST));
  }
  function sdBalance(c, S, nM) {
    if (!S.prodDry) throw new Error('dry production series missing');
    const months = Object.keys(S.prodDry).sort().slice(-nM);
    const g = (k) => months.map(m => S[k]?.[m] ?? null);
    const P = g('prodDry'), C = g('consTot'), L = g('expLng'), E = g('expTot'), I = g('impTot');
    const NI = I.map((v, i) => v == null || E[i] == null ? null : v - E[i]);
    const R = g('consRes'), CM = g('consCom'), IN = g('consInd'), PW = g('consPow');
    const IB = P.map((v, i) => C[i] == null || NI[i] == null ? null : v + NI[i] - C[i]);
    const li = P.length - 1, yoy = (a) => a[li] != null && a[li - 12] != null ? a[li] - a[li - 12] : null;
    c.innerHTML = `<h2>Monthly gas balance <span class="note">Bcf/d, EIA Natural Gas Monthly (about two months lagged)</span>
        <select id="engSdMo" style="float:right">${[[36, '3 years'], [60, '5 years'], [120, '10 years']].map(([v, l]) => `<option value="${v}" ${v === nM ? 'selected' : ''}>${l}</option>`).join('')}</select></h2>
      ${kpis([['Dry production', n(P[li], 1) + ' Bcf/d', 'y/y ' + sg(yoy(P), 1)], ['Total consumption', n(C[li], 1) + ' Bcf/d', 'y/y ' + sg(yoy(C), 1)], ['LNG exports', n(L[li], 1) + ' Bcf/d', 'y/y ' + sg(yoy(L), 1)],
        ['Net trade', n(NI[li], 1) + ' Bcf/d', 'imports − all exports (pipeline + LNG); y/y ' + sg(yoy(NI), 1)], ['Latest month', months[li], '']])}
      <div class="chart"><canvas id="engSdBalC"></canvas></div>`;
    chart('engSdBalC', { type: 'line', data: { labels: months, datasets: [
      { label: 'Dry production', data: P, borderColor: GREEN, borderWidth: 2.2, pointRadius: 0 }, { label: 'Consumption', data: C, borderColor: BLUE, borderWidth: 1.8, pointRadius: 0 },
      { label: 'LNG exports', data: L, borderColor: PURPLE, borderWidth: 1.6, pointRadius: 0 }, { label: 'Net trade (imports − all exports incl. LNG)', data: NI, borderColor: ORANGE, borderWidth: 1.4, pointRadius: 0 }] },
      options: { scales: { y: { title: { display: true, text: 'Bcf/d', font: { size: 10 } } } } } });
    document.getElementById('engSdMo').onchange = (ev) => { sdBalance(c, S, +ev.target.value); };
    panel('engSdCons', cc => {
      cc.innerHTML = `<h2>Consumption by sector <span class="note">Bcf/d</span></h2><div class="chart"><canvas id="engSdConsC"></canvas></div>`;
      chart('engSdConsC', { type: 'line', data: { labels: months, datasets: [
        { label: 'Residential', data: R, borderColor: BLUE, borderWidth: 1.7, pointRadius: 0 }, { label: 'Commercial', data: CM, borderColor: TEAL, borderWidth: 1.5, pointRadius: 0 },
        { label: 'Industrial', data: IN, borderColor: PURPLE, borderWidth: 1.5, pointRadius: 0 }, { label: 'Electric power', data: PW, borderColor: ORANGE, borderWidth: 1.7, pointRadius: 0 }] } });
    });
    panel('engSdImp', cc => {
      cc.innerHTML = `<h2>Implied balance <span class="note">Bcf/d: production + net trade − consumption</span></h2><div class="chart"><canvas id="engSdImpC"></canvas></div>
        <p class="note">The residual should roughly match the storage change; the gap is EIA's balancing item (supplemental gas, pipeline fuel, lease and plant use not in consumption).</p>`;
      chart('engSdImpC', { type: 'bar', data: { labels: months, datasets: [{ label: 'implied balance', data: IB, backgroundColor: IB.map(v => v >= 0 ? 'rgba(47,107,58,.65)' : 'rgba(192,57,43,.65)') }] },
        options: { plugins: { legend: { display: false } } } });
    });
    panel('engSdTbl', cc => {
      let b = '';
      for (let i = li; i >= Math.max(0, li - 17); i--) b += `<tr><td>${months[i]}</td>${[P, C, R, CM, IN, PW, L, NI].map(a => `<td>${n(a[i], 2)}</td>`).join('')}<td>${sg(IB[i], 2)}</td></tr>`;
      cc.innerHTML = `<h2>Balance table <span class="note">Bcf/d, last 18 months</span></h2><div class="tbl"><table><tr><th>Month</th><th>Production</th><th>Consumption</th><th>Residential</th><th>Commercial</th><th>Industrial</th><th>Power</th><th>LNG exports</th><th>Net trade (incl. LNG)</th><th>Implied</th></tr>${b}</table></div>`;
    });
  }
  function sdSteo(c, ST) {
    const cut = '2019-01';
    const f = (k) => (ST[k] || []).filter(r => r.s >= cut);
    const P = f('steoProd'), Cn = f('steoCons'), L = f('steoLng');
    if (!P.length) throw new Error('STEO production series missing');
    const months = P.map(r => r.s.slice(0, 7)), mp = (a) => { const o = {}; a.forEach(r => o[r.s.slice(0, 7)] = r.v); return months.map(m => o[m] ?? null); };
    const Cv = mp(Cn), Lv = mp(L), Pv = P.map(r => r.v), li = Pv.length - 1, now = ym(new Date()), fw = months.findIndex(m => m >= now);
    const fetched = '';
    c.innerHTML = `<h2>EIA Short-Term Energy Outlook (STEO) <span class="note">Bcf/d; history and EIA's forecast to ${months[li]}</span></h2>
      ${kpis([['Production, end of forecast', n(Pv[li], 1) + ' Bcf/d', months[li]], ['Production change, now → end', fw > 0 ? sg(Pv[li] - Pv[fw], 1) + ' Bcf/d' : '–', fw > 0 ? 'from ' + months[fw] : ''],
        ['Consumption, end', n(Cv[li], 1) + ' Bcf/d', ''], ['LNG exports, end', n(Lv[li], 1) + ' Bcf/d', fw > 0 ? 'now ' + n(Lv[fw], 1) : '']])}
      <div class="chart"><canvas id="engSdSteoC"></canvas></div><p class="note">Shaded = forecast months (from ${now}).${fetched}</p>`;
    const fc = { id: 'engFc', beforeDraw(ch) { if (fw < 0) return; const { ctx, chartArea: a, scales: { x } } = ch; const x0 = x.getPixelForValue(fw); ctx.save(); ctx.fillStyle = 'rgba(0,0,0,.04)'; ctx.fillRect(x0, a.top, a.right - x0, a.bottom - a.top); ctx.restore(); } };
    chart('engSdSteoC', { type: 'line', data: { labels: months, datasets: [
      { label: 'Dry production', data: Pv, borderColor: GREEN, borderWidth: 2.2, pointRadius: 0 }, { label: 'Consumption', data: Cv, borderColor: BLUE, borderWidth: 1.8, pointRadius: 0 },
      { label: 'LNG exports', data: Lv, borderColor: PURPLE, borderWidth: 1.6, pointRadius: 0 }] }, plugins: [fc],
      options: { scales: { y: { title: { display: true, text: 'Bcf/d', font: { size: 10 } } } } } });
    panel('engSdDd', cc => {
      const H = f('steoHdd'), D = f('steoCdd'); if (!H.length) throw new Error('STEO degree days missing');
      const hm = H.map(r => r.s.slice(0, 7)), dmap = {}; D.forEach(r => dmap[r.s.slice(0, 7)] = r.v); const fw2 = hm.findIndex(m => m >= now);
      cc.innerHTML = `<h2>STEO forecast degree days <span class="note">US population-weighted, degree days per month</span></h2><div class="chart"><canvas id="engSdDdC"></canvas></div>`;
      chart('engSdDdC', { type: 'bar', data: { labels: hm, datasets: [
        { label: 'Heating degree days', data: H.map(r => r.v), backgroundColor: hm.map((m, i) => i >= fw2 && fw2 >= 0 ? 'rgba(44,111,187,.35)' : 'rgba(44,111,187,.75)') },
        { type: 'line', label: 'Cooling degree days', data: hm.map(m => dmap[m] ?? null), borderColor: RED, borderWidth: 1.6, pointRadius: 0 }] } });
      cc.insertAdjacentHTML('beforeend', '<p class="note">Lighter bars = forecast months.</p>');
    });
    panel('engSdStor', cc => {
      cc.innerHTML = `<h2>STEO forecast end-of-month storage</h2><p class="note">Not available: the STEO storage series (NGESPUS) is not among the repo's EIA files. The weekly storage model on the Storage model tab projects the near-term path instead.</p>`;
    });
  }

  /* ======================================================================
     3. WEATHER
     ====================================================================== */
  async function weather(el, mk) {
    const h = location.hash;
    if (mk && mk !== 'NG') { el.innerHTML = '<div class="card"><p class="note">Weather panels are for natural gas.</p></div>'; return; }
    el.innerHTML = `${card('engWxSq', ';margin-top:0')}${card('engWxRuns')}${card('engWxExt')}
      <div class="grid g2">${card('engWxTele')}${card('engWxPv')}</div>${card('engWxObs')}
      <div class="grid g2">${card('engWxSnow')}${card('engWxCpc')}</div>`;
    const tasks = [['engWxSq', wxSqueeze], ['engWxRuns', wxRuns], ['engWxExt', wxExt], ['engWxTele', wxTele], ['engWxPv', wxVortex], ['engWxObs', wxObs], ['engWxSnow', wxSnow], ['engWxCpc', wxCpc]];
    for (const [id, fn] of tasks) { if (!still(h)) return; await panel(id, fn); }
  }
  async function wxSqueeze(c) {
    const S = await load('data/energy/wx/signal.json');
    const col = { HIGH: RED, ELEVATED: ORANGE, 'LONG-SQUEEZE': RED, LOW: GREEN }[S.regime] || '';
    const p = S.positioning || {}, t24 = S.trend_24h, t72 = S.trend_72h, ex = S.extended;
    let ext = '';
    if (ex && ex.by_model) {
      ext = '<h3>Weeks 3–5 (extended ensembles)</h3><div class="tbl"><table><tr><th>Extended model</th><th>Week 3</th><th>Week 4</th><th>Week 5</th></tr>';
      for (const [nm, r] of Object.entries(ex.by_model)) ext += `<tr><td>${nm}</td>${['wk3', 'wk4', 'wk5'].map(k => r[k] ? `<td>${sg(r[k].mean, 0)} HDD <span class="note">(from ${r[k].from}; p10/p90 ${sg(r[k].p10, 0)}/${sg(r[k].p90, 0)}${r[k].chg_24h != null ? '; 24h ' + sg(r[k].chg_24h, 0) : ''})</span></td>` : '<td>–</td>').join('')}</tr>`;
      ext += '</table></div>';
    }
    const trendRows = (t) => t && t.by_model ? Object.entries(t.by_model).map(([k, v]) => `${k} ${sg(v.hdd, 1)} (${v.days} d, vs ${v.vs_run.replace('T', ' ')})`).join(' · ') : '';
    c.innerHTML = `<h2>Squeeze risk: weather trend × fund positioning <span class="note">as of ${S.generated.replace('T', ' ')} UTC</span></h2>
      ${kpis([['Squeeze risk', `<span style="color:${col}">${S.regime}</span>`, `${S.cold_checks_on} of ${S.cold_checks.length} cold-risk checks on`],
        ['Managed money net', p.net !== undefined ? n(p.net / 1000, 0) + 'k contracts' : '–', p.pct_3y !== undefined ? `${n(p.pct_3y, 0)} percentile of 3 yrs · 4 wks ${sg(p.chg_4w / 1000, 0)}k · as of ${p.date}` : ''],
        ['15-day trend, 24h / 2–3 days', `${t24 ? sg(t24.avg_hdd, 1) : '–'} / ${t72 ? sg(t72.avg_hdd, 1) : '–'} HDD`, t72 ? `≈ ${sg(-t72.bcf, 0)} Bcf over 2–3 days` : ''],
        ['Weeks 3–4 vs normal', ex && ex.wk34_avg != null ? sg(ex.wk34_avg, 0) + ' HDD/week' : '–', 'extended ensembles'],
        ...(S.price ? [['NG front month', '$' + n(S.price.last, 3) + '/MMBtu', `${S.price.date} · 5d ${sg(S.price.chg_5d_pct, 1, '%')} · RSI14 ${n(S.price.rsi14, 0)}`]] : [])])}
      <p><b>${S.action}</b></p>
      <div style="line-height:1.75;margin:6px 0">${S.cold_checks.map(k => `<div style="opacity:${k.on ? 1 : .6}">${k.on ? '●' : '○'} ${k.text}</div>`).join('')}</div>
      ${t24 ? `<p class="note">24h trend by model: ${trendRows(t24)}</p>` : ''}${t72 ? `<p class="note">2–3 day trend by model: ${trendRows(t72)}</p>` : ''}
      ${ext}
      <p class="note">HDD + = colder than normal. Trend = change in the 15-day ensembles on the same dates vs ~24h and 2–3 days earlier. Sources: GEFS/ECMWF ensembles, NOAA CPC teleconnections, 10 hPa 60°N wind, CFTC managed money (NYMEX Henry Hub).</p>`;
  }
  async function wxRuns(c) {
    const R = await load('data/energy/wx/runs.json');
    if (!R || !R.length) { c.innerHTML = '<p class="note">Model-run history builds after the next weather sync.</p>'; return; }
    const BCF = 1.6;  // weekly storage change per gas-weighted HDD in winter weeks (storage regression, 2019-2026)
    const last = R.at(-1), rows = [], daily = {};
    for (const [name, m] of Object.entries(last.models)) {
      let prev = null, prevT = null;   // previous run of the same model with different numbers
      for (let i = R.length - 2; i >= 0; i--) { const p = R[i].models[name]; if (p && JSON.stringify(p.daily) !== JSON.stringify(m.daily)) { prev = p; prevT = R[i].generated; break; } }
      const dd = Object.keys(m.daily).filter(d => prev && d in prev.daily);
      const chg = dd.reduce((a, d) => a + m.daily[d] - prev.daily[d], 0);
      const tot = sum(Object.values(m.daily)), nrm = sum(Object.keys(m.daily).map(d => m.normal[d] || 0));
      rows.push({ name, m, prevT, chg: prev ? chg : null, n: dd.length, tot, nrm });
      daily[name] = { ds: dd, cur: m.daily, prev: prev ? prev.daily : null };
    }
    const av = rows.filter(r => r.chg !== null), mc = av.length ? av.reduce((a, r) => a + r.chg, 0) / av.length : null;
    let tb = '<tr><th>Model</th><th>Window</th><th>HDD</th><th>Normal</th><th>vs normal (p10 / p50 / p90)</th><th>Change vs previous run</th><th>≈ storage, Bcf</th><th>Previous run (UTC)</th></tr>';
    rows.forEach(r => { tb += `<tr><td>${r.name}${r.m.new_run === false ? ' <span class="note">(same run as before)</span>' : ''}</td><td>${r.m.from} to ${r.m.to}</td><td>${n(r.tot)}</td><td>${n(r.nrm)}</td><td>${sg(r.m.p10)} / ${sg(r.m.p50)} / ${sg(r.m.p90)}</td><td><b>${r.chg === null ? '–' : sg(r.chg, 1)}</b>${r.chg === null ? '' : ` <span class="note">over ${r.n} days</span>`}</td><td>${r.chg === null ? '–' : sg(-r.chg * BCF)}</td><td>${r.prevT ? r.prevT.replace('T', ' ') : '–'}</td></tr>`; });
    const all = [...new Set(Object.values(daily).flatMap(x => x.ds))].sort();
    let dt = '';
    if (all.length) {
      dt = `<h3>Day-by-day HDD change, previous run → latest run</h3><div class="tbl"><table><tr><th>Model</th>${all.map(d => `<th>${d.slice(5)}</th>`).join('')}<th>Total</th></tr>`;
      for (const [name, x] of Object.entries(daily)) {
        if (!x.prev) continue; let tt = 0;
        dt += `<tr><td>${name}</td>${all.map(d => { const v = d in x.cur && d in x.prev ? x.cur[d] - x.prev[d] : null; if (v != null) tt += v; const bg = v == null ? '' : v > 0.3 ? `background:rgba(44,111,187,${Math.min(.45, .08 + Math.abs(v) / 10)})` : v < -0.3 ? `background:rgba(192,57,43,${Math.min(.45, .08 + Math.abs(v) / 10)})` : ''; return `<td style="${bg}">${v == null ? '' : (v > 0 ? '+' : '') + v.toFixed(1)}</td>`; }).join('')}<td><b>${sg(tt, 1)}</b></td></tr>`;
      }
      dt += '</table></div>';
    }
    c.innerHTML = `<h2>Model runs: what the latest run changed <span class="note">runs fetched ${last.generated.replace('T', ' ')} UTC</span></h2>
      ${kpis([['Change vs previous run', mc === null ? '–' : sg(mc, 1) + ' HDD', 'average of the ensembles, same dates'], ['≈ storage effect', mc === null ? '–' : sg(-mc * BCF) + ' Bcf', `+ = more gas left in storage; about ${BCF} Bcf per gas-weighted HDD`],
        ['15-day HDD vs normal', sg(avg(rows.map(r => r.m.mean))) + ' HDD', 'ensemble means'],
        ['Members warmer than normal by 30+ HDD', Math.round(avg(rows.map(r => r.m.share_warm30)) * 100) + '%', 'colder by 30+: ' + Math.round(avg(rows.map(r => r.m.share_cold30)) * 100) + '%']])}
      <div class="tbl"><table>${tb}</table></div>${dt}
      <p class="note">Positive change = the newer run is colder (more heating demand); blue cells colder, red warmer. A model shown as 'same run as before' had not published a new cycle when the data was fetched; it is compared with its last different run. Ensembles: NOAA GEFS (31 members), ECMWF ENS (51), ECMWF AIFS ENS (51); 21-metro gas-weighted HDD, base 65°F; normal 2016–2025.</p>`;
  }
  async function wxExt(c) {
    const E = await load('data/energy/wx/hdd_ext.json');
    const names = Object.keys(E.models), maxW = Math.max(...names.map(k => E.models[k].weeks.length));
    const wk = []; for (let i = 1; i <= Math.min(maxW, 5); i++) wk.push(i);
    let t = `<tr><th>Model</th>${wk.map(w => { const r = names.map(k => E.models[k].weeks.find(x => x.week === w)).find(Boolean); return `<th>Week ${w}<br><span class="note" style="text-transform:none">${r ? r.from.slice(5) + ' to ' + r.to.slice(5) : ''}</span></th>`; }).join('')}</tr>`;
    names.forEach(k => {
      const M = E.models[k];
      t += `<tr><td>${k} <span class="note">(${M.members} members)</span></td>${wk.map(w => { const r = M.weeks.find(x => x.week === w); return r ? `<td style="white-space:normal;min-width:120px"><b>${sg(r.mean)}</b><br><span class="note">p10/50/90 ${sg(r.p10)}/${sg(r.p50)}/${sg(r.p90)}<br>normal ${n(r.normal_hdd)} · ${Math.round(r.share_cold * 100)}% of members colder</span></td>` : '<td>–</td>'; }).join('')}</tr>`;
    });
    c.innerHTML = `<h2>Extended range, weeks 1–5 <span class="note">gas-weighted HDD per week vs normal; + = colder than normal; built ${E.generated.replace('T', ' ')} UTC</span></h2>
      <div class="tbl"><table>${t}</table></div><div class="chart short" style="margin-top:10px"><canvas id="engWxExtC"></canvas></div>
      <p class="note">Normal: ${E.normal}. Week 1 starts on the run date.</p>`;
    chart('engWxExtC', { type: 'bar', data: { labels: wk.map(w => 'Week ' + w), datasets: names.map((k, i) => ({ label: k + ' mean vs normal (HDD)', data: wk.map(w => E.models[k].weeks.find(x => x.week === w)?.mean ?? null), backgroundColor: [BLUE, ORANGE, GREEN][i % 3] })) },
      options: { scales: { y: { title: { display: true, text: 'HDD vs normal / week', font: { size: 10 } } } } } });
  }
  async function wxTele(c) {
    const V = await load('data/energy/wx/vortex.json'), T = V.teleconnections || {};
    const idx = ['ao', 'nao', 'pna'].filter(k => T[k]?.gefs?.days);
    const dates = [...new Set(idx.flatMap(k => Object.keys(T[k].gefs.days)))].sort();
    const colr = { ao: BLUE, nao: TEAL, pna: ORANGE }, NM = { ao: 'Arctic Oscillation', nao: 'North Atlantic Oscillation', pna: 'Pacific–North American' };
    const ds = [];
    idx.forEach(k => {
      const d = T[k].gefs.days;
      ds.push({ label: '_' + k + 'max', data: dates.map(x => d[x]?.max ?? null), borderWidth: 0, pointRadius: 0, backgroundColor: colr[k] + '22', fill: '+1' });
      ds.push({ label: '_' + k + 'min', data: dates.map(x => d[x]?.min ?? null), borderWidth: 0, pointRadius: 0, fill: false });
      ds.push({ label: `${k.toUpperCase()} (${NM[k]})`, data: dates.map(x => d[x]?.mean ?? null), borderColor: colr[k], borderWidth: 2, pointRadius: 0 });
    });
    const ini = idx.length ? T[idx[0]].gefs.init : '';
    const now = (k) => { const d = T[k].gefs.days, ks = Object.keys(d).sort(); return d[ks[0]]?.mean; };
    c.innerHTML = `<h2>Teleconnections <span class="note">NOAA CPC GEFS forecast, initialised ${ini}; index units (standard deviations)</span></h2>
      <div class="chart short"><canvas id="engWxTeleC"></canvas></div>
      <p class="note">Now: ${idx.map(k => `${k.toUpperCase()} ${sg(now(k), 2)}`).join(' · ')}. Negative AO/NAO and positive PNA (western ridge, eastern trough) favour cold in the eastern US gas-demand belt. Shading = ensemble min–max.</p>`;
    chart('engWxTeleC', { type: 'line', data: { labels: dates, datasets: ds }, options: { plugins: { legend: { labels: { filter: i => !i.text.startsWith('_'), boxWidth: 10, font: { size: 11 } } } }, scales: xMax } });
  }
  async function wxVortex(c) {
    const V = await load('data/energy/wx/vortex.json'), U = V.u10_60N_ms || {};
    const nm = { gfs_seamless: 'GFS', ecmwf_ifs025: 'ECMWF IFS' };
    const dates = [...new Set(Object.values(U).flatMap(o => Object.keys(o)))].sort();
    c.innerHTML = `<h2>Polar vortex: 10 hPa zonal wind at 60°N <span class="note">m/s, built ${V.generated.replace('T', ' ')} UTC</span></h2>
      <div class="chart short"><canvas id="engWxPvC"></canvas></div><p class="note">${V.note || ''}</p>`;
    chart('engWxPvC', { type: 'line', data: { labels: dates, datasets: [
      ...Object.keys(U).map((k, i) => ({ label: nm[k] || k, data: dates.map(d => U[k][d] ?? null), borderColor: [BLUE, ORANGE, GREEN][i % 3], borderWidth: 2, pointRadius: 0 })),
      { label: '0 m/s (sudden stratospheric warming)', data: dates.map(() => 0), borderColor: RED, borderDash: [4, 3], borderWidth: 1, pointRadius: 0 }] },
      options: { scales: { ...xMax, y: { title: { display: true, text: 'm/s', font: { size: 10 } } } } } });
  }
  async function wxObs(c) {
    const H = await hddHist();
    let R = null; try { R = await load('data/energy/wx/runs.json'); } catch (e) { R = null; }
    const last = dp(H.last), keys = Object.keys(H.dd);
    const accum = (from, to) => { let a = 0, nn = 0, k = 0; for (let t = +from; t <= +to; t += MS_D) { const s = ds(new Date(t)), v = H.dd[s]; if (v) { a += v[0]; k++; } nn += nH(H, s); } return { a, n: nn, k }; };
    const y0 = last.getUTCMonth() >= 6 ? last.getUTCFullYear() : last.getUTCFullYear() - 1;
    const sJul = accum(new Date(Date.UTC(y0, 6, 1)), last), sJulLy = accum(new Date(Date.UTC(y0 - 1, 6, 1)), new Date(Date.UTC(last.getUTCFullYear() - 1, last.getUTCMonth(), last.getUTCDate())));
    const m0 = new Date(Date.UTC(last.getUTCFullYear(), last.getUTCMonth(), 1)), sMon = accum(m0, last);
    const l7 = accum(new Date(+last - 6 * MS_D), last);
    // last 60 days observed + forecast window
    const obsD = []; for (let t = +last - 59 * MS_D; t <= +last; t += MS_D) obsD.push(ds(new Date(t)));
    let fcD = [], models = {};
    if (R && R.length) { models = R.at(-1).models; fcD = [...new Set(Object.values(models).flatMap(m => Object.keys(m.daily)))].sort(); }
    const allD = [...new Set([...obsD, ...fcD])].sort();
    const fcRows = Object.entries(models).map(([k, m]) => { const dd = Object.keys(m.daily); const tot = sum(dd.map(d => m.daily[d])), nr = sum(dd.map(d => nH(H, d))); return `<tr><td>${k}</td><td>${m.from} to ${m.to}</td><td>${n(tot)}</td><td>${n(nr)}</td><td>${sg(tot - nr)}</td><td>${sg(avg(dd.map(d => m.daily[d] - nH(H, d))), 1)}</td></tr>`; }).join('');
    c.innerHTML = `<h2>Gas-weighted degree days: observed vs normal <span class="note">${H.cities.length}-metro gas-weighted HDD, base 65°F; normal = 2016–2025 daily mean; observed to ${H.last}</span></h2>
      ${kpis([['Season to date (since 1 Jul)', n(sJul.a) + ' HDD', `normal ${n(sJul.n)} · ${sg(sJul.a - sJul.n)} (${sg((sJul.a / sJul.n - 1) * 100, 1, '%')}) · last year ${n(sJulLy.a)}`],
        [`${MON[last.getUTCMonth()]} to date`, n(sMon.a) + ' HDD', `normal ${n(sMon.n)} · ${sg(sMon.a - sMon.n)}`], ['Last 7 days', n(l7.a) + ' HDD', `normal ${n(l7.n)} · ${sg(l7.a - l7.n)}`]])}
      <div class="chart"><canvas id="engWxObsC"></canvas></div>
      ${fcRows ? `<h3>Current forecast window vs the 2016–2025 normal (latest run, ${R.at(-1).generated.replace('T', ' ')} UTC)</h3><div class="tbl"><table><tr><th>Model</th><th>Window</th><th>Forecast HDD</th><th>Normal HDD</th><th>vs normal</th><th>Per day</th></tr>${fcRows}</table></div>` : ''}
      <p class="note">Bars = observed daily HDD (last 60 days); lines = latest ensemble means; dashed = normal. + = colder than normal.</p>`;
    const cols = [GREEN, BLUE, ORANGE, PURPLE];
    chart('engWxObsC', { type: 'bar', data: { labels: allD, datasets: [
      { label: 'Observed HDD', data: allD.map(d => H.dd[d]?.[0] ?? null), backgroundColor: 'rgba(44,111,187,.55)' },
      { type: 'line', label: 'Normal HDD', data: allD.map(d => nH(H, d)), borderColor: '#555', borderDash: [4, 3], borderWidth: 1.3, pointRadius: 0 },
      ...Object.entries(models).map(([k, m], i) => ({ type: 'line', label: k + ' forecast', data: allD.map(d => m.daily[d] ?? null), borderColor: cols[i % 4], borderWidth: 1.8, pointRadius: 0 }))] },
      options: { scales: { ...xMax, y: { title: { display: true, text: 'HDD per day', font: { size: 10 } } } } } });
  }
  async function wxSnow(c) {
    const S = await load('data/energy/wx/snow.json');
    const e = Object.entries(S.by_date).sort((a, b) => a[0] < b[0] ? -1 : 1);
    const cur = e.at(-1), hist = e.slice(0, -1).map(x => x[1].cover_pct).filter(v => v != null);
    c.innerHTML = `<h2>Snow cover, Lower 48 <span class="note">% of area, same date each year; ${S.source}</span></h2>
      ${kpis([['Snow cover ' + cur[0], n(cur[1].cover_pct, 1) + '%', `average of prior years ${n(avg(hist), 1)}%`]])}
      <div class="chart short"><canvas id="engWxSnowC"></canvas></div><p class="note">Early snow cover keeps nights colder and lifts heating demand; low cover leans warm.</p>`;
    chart('engWxSnowC', { type: 'bar', data: { labels: e.map(x => x[0]), datasets: [{ label: 'snow cover %', data: e.map(x => x[1].cover_pct), backgroundColor: e.map((x, i) => i === e.length - 1 ? RED : 'rgba(44,111,187,.6)') }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { title: { display: true, text: '% of Lower 48', font: { size: 10 } } } } } });
  }
  async function wxCpc(c) {
    const D = await load('data/energy/wx/cpc_dd.json'), W = D.heating_weekly;
    if (!W || !W.us || !W.us.length) throw new Error('no CPC weekly lines');
    const head = (W.head || []).join('\n'), wk = (head.match(/LAST DATE OF FORECAST WEEK IS ([A-Z]{3}\s+\d+,\s*\d{4})/) || [])[1], seas = (head.match(/ACCUMULATIONS ARE FROM (.+)/) || [])[1];
    const lbl = ['Population-weighted', 'Gas-heating-customer weighted', 'Weighting 3', 'Weighting 4'];
    const rows = W.us.slice(0, 2).map((l, i) => { const v = l.replace(/UNITED STATES/, '').trim().split(/\s+/).map(Number); return `<tr><td>${lbl[i]}</td><td>${n(v[0])}</td><td>${sg(v[1])}</td><td>${sg(v[2])}</td><td>${n(v[3])}</td><td>${sg(v[4])}</td><td>${sg(v[5])}</td></tr>`; }).join('');
    c.innerHTML = `<h2>NOAA CPC weekly heating degree days, United States <span class="note">forecast week ending ${wk ? wk.replace(/\s+/g, ' ') : '–'}</span></h2>
      <div class="tbl"><table><tr><th>Weighting</th><th>Week fcst HDD</th><th>vs normal</th><th>vs last yr</th><th>Season HDD</th><th>vs normal</th><th>vs last yr</th></tr>${rows}</table></div>
      <p class="note">Season accumulation ${seas ? 'from ' + seas.trim().toLowerCase() : ''}. Negative = warmer (fewer HDD) than normal or last year. Source: CPC hfstwpws.txt.</p>`;
  }

  /* ======================================================================
     4. GAS MODEL — weather-driven storage model and storage-implied fair value
     ====================================================================== */
  function ols(X, y) {
    const nn = X.length, p = X[0].length, A = Array.from({ length: p }, () => new Array(p + 1).fill(0));
    for (let i = 0; i < nn; i++) for (let a = 0; a < p; a++) { A[a][p] += X[i][a] * y[i]; for (let b = 0; b < p; b++) A[a][b] += X[i][a] * X[i][b]; }
    for (let c = 0; c < p; c++) {
      let piv = c; for (let r = c + 1; r < p; r++) if (Math.abs(A[r][c]) > Math.abs(A[piv][c])) piv = r;
      if (Math.abs(A[piv][c]) < 1e-12) return null; [A[c], A[piv]] = [A[piv], A[c]];
      for (let r = 0; r < p; r++) { if (r === c) continue; const f = A[r][c] / A[c][c]; for (let k = c; k <= p; k++) A[r][k] -= f * A[c][k]; }
    }
    const b = A.map((r, i) => r[p] / r[i]), fit = X.map(r => r.reduce((a, v, i) => a + v * b[i], 0));
    const my = avg(y), ssr = y.reduce((a, v, i) => a + (v - fit[i]) ** 2, 0), sst = y.reduce((a, v) => a + (v - my) ** 2, 0);
    return { b, fit, r2: 1 - ssr / sst, rmse: Math.sqrt(ssr / nn), n: nn };
  }
  let M = null;  // model state
  async function model(el) {
    const h = location.hash;
    el.innerHTML = `${card('engMdFit', ';margin-top:0')}<div class="grid g2">${card('engMdPath')}${card('engMdScen')}</div>${card('engMdFv')}
      <div class="grid g2">${card('engMdCurve')}${card('engMdFwd')}</div><div class="grid g2">${card('engMdSens')}${card('engMdStrip')}</div>`;
    const [stor, H, R, spot, vol, px] = await Promise.all([eia('storL48'), hddHist(), load('data/energy/wx/runs.json').catch(() => null), eia('hhSpot').catch(() => null),
      load('data/vol/vol.json').catch(() => null), load('data/energy/prices.json').catch(() => null)]);
    let fc = null; try { fc = await load('data/energy/wx/hdd_fcst.json'); } catch (e) { fc = null; }
    if (!still(h)) return;
    M = { stor, H, R, spot, vol, px, fc, fit: null, fv: null, wx: null };
    await panel('engMdFit', fitModel);
    await panel('engMdPath', drawPath);
    await panel('engMdScen', scenario);
    await panel('engMdFv', c => fitFV(c, 8));
  }
  // daily HDD/CDD after the last storage week: observed, then latest ECMWF ENS run, then hdd_fcst, then normal
  function wxForward() {
    const { stor, H, R, fc } = M, last = stor.at(-1).d;
    const ens = R && R.length ? R.at(-1).models[ensName(R)] : null;
    const fcE = fc?.models?.ens_ecmwf_ifs025 || fc?.models?.ecmwf_ifs025 || null;
    const endF = ens ? Object.keys(ens.daily).sort().at(-1) : (fcE ? Object.keys(fcE).sort().at(-1) : H.last);
    const out = []; const src = { obs: 0, ens: 0, fc: 0, norm: 0 };
    for (let t = +last + MS_D; t <= +dp(endF); t += MS_D) {
      const s = ds(new Date(t)); let hdd, cdd, how;
      if (H.dd[s]) { [hdd, cdd] = H.dd[s]; how = 'obs'; }
      else if (ens && s in ens.daily) { hdd = ens.daily[s]; cdd = fcE && fcE[s] ? fcE[s][1] : nC(H, s); how = 'ens'; }
      else if (fcE && fcE[s]) { [hdd, cdd] = fcE[s]; how = 'fc'; }
      else { hdd = nH(H, s); cdd = nC(H, s); how = 'norm'; }
      src[how]++; out.push({ d: new Date(t), s, hdd, cdd, how });
    }
    return { days: out, src, model: ens ? ensName(R) + ' run ' + R.at(-1).generated.replace('T', ' ') + ' UTC' : 'no ensemble run' };
  }
  function fitModel(c) {
    const { stor, H } = M;
    const rows = [], ys = [], meta = [];
    for (let i = 1; i < stor.length; i++) {
      const end = stor[i].d, start = stor[i - 1].d;
      if (stor[i].s < '2016-01-01' || (end - start) / MS_D > 8) continue;
      let hh = 0, cc = 0, ok = true;
      for (let k = 0; k < 7; k++) { const v = H.dd[ds(new Date(+end - k * MS_D))]; if (!v) { ok = false; break; } hh += v[0]; cc += v[1]; }
      if (!ok) continue;
      rows.push([1, hh, cc, i]); ys.push(stor[i].v - stor[i - 1].v); meta.push({ d: stor[i].s, hdd: hh, cdd: cc });
    }
    if (rows.length < 60) throw new Error(`only ${rows.length} overlapping storage weeks`);
    const m = ols(rows, ys); if (!m) throw new Error('regression did not solve');
    M.fit = { m, rows, ys, meta };
    const tail = 156, md = meta.slice(-tail).map(r => r.d);
    c.innerHTML = `<h2>Weather-driven storage model <span class="note">fitted on ${m.n} storage weeks, ${meta[0].d} to ${meta.at(-1).d}</span></h2>
      <p class="note">Weekly Lower 48 storage change regressed on the week's gas-weighted HDD and CDD (7 days ending on the report Friday) and a linear trend that absorbs production and LNG growth. Degree days: repo 21-metro gas-weighted history.</p>
      ${kpis([['Bcf per HDD', n(m.b[1], 2), 'weekly storage change per gas-weighted HDD'], ['Bcf per CDD', n(m.b[2], 2), 'power-burn channel'], ['Trend', sg(m.b[3] * 52, 1) + ' Bcf/yr', 'on the weekly change'],
        ['R²', n(m.r2, 3), 'weekly change explained'], ['Residual s.d.', '±' + n(m.rmse, 1) + ' Bcf', 'one-week forecast error']])}
      <div class="chart"><canvas id="engMdFitC"></canvas></div>`;
    chart('engMdFitC', { type: 'line', data: { labels: md, datasets: [
      { label: 'Actual weekly change', data: ys.slice(-tail), borderColor: GREEN, borderWidth: 1.8, pointRadius: 0 },
      { label: 'Model', data: m.fit.slice(-tail), borderColor: BLUE, borderWidth: 1.4, borderDash: [3, 2], pointRadius: 0 }] },
      options: { scales: { y: { title: { display: true, text: 'Bcf/week', font: { size: 10 } } } } } });
  }
  function pathWeeks() {
    const { m, rows } = M.fit, last = M.stor.at(-1), tIdx = rows.at(-1)[3];
    const W = wxForward(); M.wx = W;
    const weeks = [];
    for (let w = 0; w + 7 <= W.days.length; w += 7) { const ch = W.days.slice(w, w + 7); weeks.push({ d: ch.at(-1).s, hdd: sum(ch.map(x => x.hdd)), cdd: sum(ch.map(x => x.cdd)), how: [...new Set(ch.map(x => x.how))] }); }
    let lvl = last.v; const path = [{ d: last.s, v: last.v, dlt: null }];
    weeks.forEach((w, k) => { const dlt = m.b[0] + m.b[1] * w.hdd + m.b[2] * w.cdd + m.b[3] * (tIdx + k + 1); lvl += dlt; path.push({ d: w.d, v: lvl, dlt, hdd: w.hdd, how: w.how }); });
    return path;
  }
  function drawPath(c) {
    if (!M.fit) throw new Error('model not fitted');
    const path = pathWeeks(), m = M.fit.m, W = M.wx;
    if (path.length < 2) { c.innerHTML = '<h2>Forward storage path</h2><p class="note">Not enough forecast days past the last storage report to build a full week.</p>'; return; }
    const tb = path.slice(1).map((p, i) => `<tr><td>${p.d}</td><td>${n(p.hdd)}</td><td>${sg(p.dlt, 1)}</td><td>${n(p.v)}</td><td>±${n(m.rmse * Math.sqrt(i + 1))}</td><td class="l note">${p.how.map(x => ({ obs: 'observed', ens: 'ensemble', fc: 'forecast', norm: 'normal' })[x]).join(' + ')}</td></tr>`).join('');
    c.innerHTML = `<h2>Forward storage path <span class="note">Bcf, from the week ending ${path[0].d}</span></h2><div class="chart short"><canvas id="engMdPathC"></canvas></div>
      <div class="tbl"><table><tr><th>Week ending</th><th>HDD</th><th>Change, Bcf</th><th>Storage, Bcf</th><th>±1σ</th><th class="l">Weather used</th></tr>${tb}</table></div>
      <p class="note">Implied next report: <b>${sg(path[1].dlt, 1)} Bcf</b> to ${n(path[1].v)} Bcf, one-sigma band ±${n(m.rmse, 1)} Bcf. Weather: observed gas-weighted HDD to ${M.H.last}, then ${W.model}${W.src.norm ? `, then normal for ${W.src.norm} day(s)` : ''}. Weeks beyond the first also carry weather-forecast error, which is not in the band.</p>`;
    chart('engMdPathC', { type: 'line', data: { labels: path.map(p => p.d), datasets: [
      { label: '+1σ', data: path.map((p, i) => p.v + m.rmse * Math.sqrt(i)), borderWidth: 0, pointRadius: 0, backgroundColor: 'rgba(44,111,187,.12)', fill: '+1' },
      { label: '_lo', data: path.map((p, i) => p.v - m.rmse * Math.sqrt(i)), borderWidth: 0, pointRadius: 0, fill: false },
      { label: 'Projected storage', data: path.map(p => p.v), borderColor: GREEN, borderWidth: 2.2, pointRadius: 3 }] },
      options: { plugins: { legend: legendNoMin } } });
  }
  function scenario(c) {
    if (!M.fit) throw new Error('model not fitted');
    c.innerHTML = `<h2>End-of-season scenario <span class="note">normal weather scaled by your HDD anomaly, plus balance shifts</span></h2>
      <div style="display:grid;grid-template-columns:auto 90px;gap:6px 10px;align-items:center;max-width:380px;font-size:13px">
        <label>Weeks to project</label><input type="number" id="engScW" value="21" min="1" max="30">
        <label>HDD anomaly vs normal (%)</label><input type="number" id="engScH" value="0" step="1">
        <label>Production vs current (Bcf/d)</label><input type="number" id="engScP" value="0" step="0.1">
        <label>LNG feedgas change (Bcf/d)</label><input type="number" id="engScL" value="0" step="0.1">
        <label>Power burn adjustment (Bcf/d)</label><input type="number" id="engScB" value="0" step="0.1"></div>
      <div style="margin:10px 0"><button class="btn" id="engScRun">Run scenario</button></div><div id="engScOut"></div><div class="chart short"><canvas id="engScC"></canvas></div>`;
    const run = () => {
      const { m, rows } = M.fit, H = M.H, last = M.stor.at(-1), tIdx = rows.at(-1)[3], v = (id) => parseFloat(document.getElementById(id).value) || 0;
      const nW = Math.max(1, Math.min(30, parseInt(document.getElementById('engScW').value, 10) || 21)), an = v('engScH') / 100, adj = (v('engScP') - v('engScL') - v('engScB')) * 7;
      let lvl = last.v; const path = [lvl], dts = [last.s];
      for (let k = 1; k <= nW; k++) {
        const end = +last.d + k * 7 * MS_D; let hh = 0, cc = 0;
        for (let j = 0; j < 7; j++) { const s = ds(new Date(end - j * MS_D)); hh += nH(H, s); cc += nC(H, s); }
        hh *= 1 + an; lvl += m.b[0] + m.b[1] * hh + m.b[2] * cc + m.b[3] * (tIdx + k) + adj; path.push(lvl); dts.push(ds(new Date(end)));
      }
      const by = seasonMap(M.stor), ge = gasDay(dp(dts.at(-1))), a5 = fiveYrAvgAt(by, ge.gy, ge.day);
      document.getElementById('engScOut').innerHTML = kpis([['Ending storage', n(path.at(-1)) + ' Bcf', dts.at(-1)], ['vs 5-yr avg then', a5 ? sg(path.at(-1) - a5) + ' Bcf' : '–', a5 ? '5-yr avg ' + n(a5) : ''],
        ['Change over window', sg(path.at(-1) - last.v) + ' Bcf', nW + ' weeks'], ['Path low / high', n(Math.min(...path)) + ' / ' + n(Math.max(...path)) + ' Bcf', ''], ['Balance adjustment', sg(adj / 7, 2) + ' Bcf/d', 'applied every week']]);
      chart('engScC', { type: 'line', data: { labels: dts, datasets: [{ label: 'Scenario storage, Bcf', data: path, borderColor: ORANGE, borderWidth: 2, pointRadius: 0 }] } });
    };
    document.getElementById('engScRun').onclick = run; run();
    c.insertAdjacentHTML('beforeend', '<p class="note">Normal = 2016–2025 daily mean HDD and CDD. Default 21 weeks reaches the end of March from an end-October start.</p>');
  }
  function fitFV(c, yrs) {
    const { stor, spot } = M;
    if (!spot || !spot.length) throw new Error('Henry Hub spot missing');
    const by = seasonMap(stor), sp = {}; spot.forEach(r => sp[r.s] = r.v);
    const obs = [], cutoff = +stor.at(-1).d - yrs * 365.25 * MS_D;
    for (let i = 1; i < stor.length; i++) {
      const r = stor[i]; if (+r.d < cutoff) continue;
      const g = gasDay(r.d), a5 = fiveYrAvgAt(by, g.gy, g.day); if (!a5) continue;
      const px = []; for (let k = 0; k < 7; k++) { const v = sp[ds(new Date(+r.d - k * MS_D))]; if (v !== undefined && v > 0) px.push(v); }
      if (px.length < 3) continue;
      const P = avg(px), x = (r.v - a5) / a5, doy = (r.d - Date.UTC(r.d.getUTCFullYear(), 0, 1)) / MS_D;
      obs.push({ d: r.d, s: r.s, x, P, lp: Math.log(P), sn: Math.sin(2 * Math.PI * doy / 365), cs: Math.cos(2 * Math.PI * doy / 365), stor: r.v, a5 });
    }
    if (obs.length < 80) throw new Error(`only ${obs.length} weeks where storage and spot overlap`);
    obs.forEach((o, i) => o.t = i);
    const m = ols(obs.map(o => [1, o.x, o.x * o.x, o.sn, o.cs, o.t]), obs.map(o => o.lp)); if (!m) throw new Error('regression did not solve');
    M.fv = { m, obs, by };
    const fitP = m.fit.map(Math.exp), last = obs.at(-1), fvNow = fitP.at(-1), spotNow = spot.at(-1), sd = m.rmse, prem = spotNow.v / fvNow - 1;
    const front = M.px?.prices?.NG?.at(-1);
    c.innerHTML = `<h2>Storage-implied fair value <span class="note">Henry Hub spot, $/MMBtu; fitted on ${m.n} weeks, ${obs[0].s} to ${last.s}</span>
        <select id="engFvWin" style="float:right">${[[5, '5 years'], [8, '8 years'], [12, '12 years'], [99, 'everything']].map(([v, l]) => `<option value="${v}" ${v === yrs ? 'selected' : ''}>${l}</option>`).join('')}</select></h2>
      <p class="note">Log Henry Hub (weekly average spot) regressed on inventory deviation from the five-year average (%), a squared term for convexity, an annual cycle and a trend for the shale and LNG regime shift. Spot history in the repo starts ${spot[0].s}.</p>
      ${kpis([['Fair value', '$' + n(fvNow, 2), `at ${n(last.stor)} Bcf, ${sg(last.x * 100, 1, '%')} vs 5-yr avg (${last.s})`], ['Spot', '$' + n(spotNow.v, 2), spotNow.s + (front ? ` · front-month futures $${n(front.c, 3)} (${front.d})` : '')],
        ['Spot vs fair value', sg(prem * 100, 1, '%'), sg(spotNow.v - fvNow, 2) + ' $/MMBtu'], ['One-sigma band', '$' + n(fvNow * Math.exp(-sd), 2) + ' – ' + n(fvNow * Math.exp(sd), 2), 'residual s.d. ' + n(sd * 100, 0) + '%'],
        ['R²', n(m.r2, 3), m.n + ' weekly observations']])}
      <div class="chart"><canvas id="engMdFvC"></canvas></div>`;
    chart('engMdFvC', { type: 'line', data: { labels: obs.map(o => o.s), datasets: [
      { label: '±1 standard error', data: fitP.map(v => v * Math.exp(sd)), borderWidth: 0, pointRadius: 0, backgroundColor: 'rgba(44,111,187,.12)', fill: '+1' },
      { label: '_lo', data: fitP.map(v => v * Math.exp(-sd)), borderWidth: 0, pointRadius: 0, fill: false },
      { label: 'Spot (weekly avg)', data: obs.map(o => o.P), borderColor: GREEN, borderWidth: 1.7, pointRadius: 0 },
      { label: 'Fair value', data: fitP, borderColor: BLUE, borderWidth: 1.6, pointRadius: 0 }] },
      options: { plugins: { legend: legendNoMin }, scales: { y: { title: { display: true, text: '$/MMBtu', font: { size: 10 } } } } } });
    document.getElementById('engFvWin').onchange = (ev) => panel('engMdFv', cc => fitFV(cc, +ev.target.value));
    panel('engMdCurve', cc => {
      const base = m.b[3] * last.sn + m.b[4] * last.cs + m.b[5] * last.t;
      const lo = Math.min(...obs.map(o => o.x)), hi = Math.max(...obs.map(o => o.x)), cur = [];
      for (let k = 0; k <= 60; k++) { const xv = lo + (hi - lo) * k / 60; cur.push({ x: xv * 100, y: Math.exp(m.b[0] + m.b[1] * xv + m.b[2] * xv * xv + base) }); }
      cc.innerHTML = `<h2>Price against inventory deviation <span class="note">$/MMBtu vs storage % from 5-yr average</span></h2><div class="chart"><canvas id="engMdCurveC"></canvas></div>
        <p class="note">Line = fitted fair value at today's season and trend; dots = weekly observations; red = latest week.</p>`;
      chart('engMdCurveC', { type: 'scatter', data: { datasets: [
        { label: 'weekly', data: obs.map(o => ({ x: o.x * 100, y: o.P })), pointRadius: 2, backgroundColor: 'rgba(214,137,16,.4)' },
        { label: 'fitted now', data: cur, showLine: true, borderColor: BLUE, borderWidth: 2, pointRadius: 0 },
        { label: 'latest', data: [{ x: last.x * 100, y: spotNow.v }], pointRadius: 6, backgroundColor: RED }] },
        options: { interaction: { mode: 'nearest', intersect: false }, scales: { x: { title: { display: true, text: 'storage vs 5-yr avg, %', font: { size: 10 } } }, y: { title: { display: true, text: '$/MMBtu', font: { size: 10 } } } } } });
    });
    panel('engMdSens', buildSensitivity);
    panel('engMdFwd', drawFwdFV);
    panel('engMdStrip', impliedStrip);
  }
  function fvAt(level, dt) {
    const { m, by, obs } = M.fv, g = gasDay(dt), a5 = fiveYrAvgAt(by, g.gy, g.day); if (!a5) return null;
    const x = (level - a5) / a5, doy = (dt - Date.UTC(dt.getUTCFullYear(), 0, 1)) / MS_D, t = obs.at(-1).t + Math.max(0, (dt - obs.at(-1).d) / (7 * MS_D));
    return { p: Math.exp(m.b[0] + m.b[1] * x + m.b[2] * x * x + m.b[3] * Math.sin(2 * Math.PI * doy / 365) + m.b[4] * Math.cos(2 * Math.PI * doy / 365) + m.b[5] * t), x, a5 };
  }
  function buildSensitivity(c) {
    const last = M.stor.at(-1), hz = [4, 8, 13, 26];
    let t = `<tr><th>Storage vs 5-yr avg</th>${hz.map(h => `<th>+${h} wks<br><span class="note" style="text-transform:none">${ds(new Date(+last.d + h * 7 * MS_D))}</span></th>`).join('')}</tr>`;
    [-25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25].forEach(pc => {
      t += `<tr><td>${pc > 0 ? '+' : ''}${pc}%</td>${hz.map(h => { const dt = new Date(+last.d + h * 7 * MS_D), g = gasDay(dt), a5 = fiveYrAvgAt(M.fv.by, g.gy, g.day); const f = a5 ? fvAt(a5 * (1 + pc / 100), dt) : null; return `<td${pc === 0 ? ' style="font-weight:600"' : ''}>${f ? '$' + n(f.p, 2) : '–'}</td>`; }).join('')}</tr>`;
    });
    c.innerHTML = `<h2>Sensitivity <span class="note">model fair value, $/MMBtu, by storage deviation and horizon</span></h2><div class="tbl"><table>${t}</table></div>`;
  }
  function drawFwdFV(c) {
    if (!M.fit) { c.innerHTML = '<h2>Forward fair value</h2><p class="note">Needs the weather-driven storage model, which did not fit.</p>'; return; }
    const path = pathWeeks(); if (path.length < 2) { c.innerHTML = '<h2>Forward fair value</h2><p class="note">Not enough forecast days to build a week.</p>'; return; }
    const fv = path.map(p => fvAt(p.v, dp(p.d))?.p ?? null), spotNow = M.spot.at(-1).v;
    c.innerHTML = `<h2>Forward fair value <span class="note">$/MMBtu along the forecast storage path</span></h2><div class="chart short"><canvas id="engMdFwdC"></canvas></div>
      <p class="note">At the forecast weather path, inventories reach <b>${n(path.at(-1).v)} Bcf</b> by ${path.at(-1).d}, which the model prices at <b>$${n(fv.at(-1), 2)}</b> against spot of $${n(spotNow, 2)}.</p>`;
    chart('engMdFwdC', { type: 'line', data: { labels: path.map(p => p.d), datasets: [{ label: 'Fair value', data: fv, borderColor: BLUE, borderWidth: 2.2, pointRadius: 3 },
      { label: 'Spot now', data: path.map(() => spotNow), borderColor: GREEN, borderDash: [4, 3], borderWidth: 1.2, pointRadius: 0 }] } });
  }
  const MCODE = { F: 0, G: 1, H: 2, J: 3, K: 4, M: 5, N: 6, Q: 7, U: 8, V: 9, X: 10, Z: 11 };
  async function impliedStrip(c) {
    const { m } = M.fv, last = M.stor.at(-1), cg = gasDay(last.d), cx = (last.v - fiveYrAvgAt(M.fv.by, cg.gy, cg.day)) / fiveYrAvgAt(M.fv.by, cg.gy, cg.day);
    let strip = [], src = '';
    const C = M.vol?.markets?.NG?.contracts;
    if (C && C.length) {
      strip = C.slice(0, 8).map(k => { const mm = k.code.match(/^NG([FGHJKMNQUVXZ])(\d{4})$/); return mm ? { lbl: `${k.label} (${k.code})`, p: k.last, dt: new Date(Date.UTC(+mm[2], MCODE[mm[1]], 15)) } : null; }).filter(Boolean);
      src = `NYMEX settlements as of ${C[0].date} (data/vol/vol.json)`;
    } else {
      for (let k = 1; k <= 4; k++) { try { const a = await eia('fut' + k); strip.push({ lbl: 'EIA contract ' + k + ' (' + a.at(-1).s + ')', p: a.at(-1).v, dt: new Date(+last.d + (k - 0.5) * 30.4 * MS_D) }); } catch (e) { } }
      src = 'EIA contracts 1–4 (may be stale)';
    }
    if (!strip.length) throw new Error('no futures strip in the repo');
    let t = '<tr><th>Contract</th><th>Price</th><th>Implied storage, Bcf</th><th>vs 5-yr avg</th><th>5-yr avg, Bcf</th><th>Gap, Bcf</th></tr>';
    strip.forEach(s => {
      const g = gasDay(s.dt), a5 = fiveYrAvgAt(M.fv.by, g.gy, g.day); if (!a5) return;
      const doy = (s.dt - Date.UTC(s.dt.getUTCFullYear(), 0, 1)) / MS_D, tt = M.fv.obs.at(-1).t + Math.max(0, (s.dt - M.fv.obs.at(-1).d) / (7 * MS_D));
      const cst = m.b[0] + m.b[3] * Math.sin(2 * Math.PI * doy / 365) + m.b[4] * Math.cos(2 * Math.PI * doy / 365) + m.b[5] * tt - Math.log(s.p);
      const disc = m.b[1] ** 2 - 4 * m.b[2] * cst; let x = null;
      if (disc >= 0 && Math.abs(m.b[2]) > 1e-9) { const r1 = (-m.b[1] + Math.sqrt(disc)) / (2 * m.b[2]), r2 = (-m.b[1] - Math.sqrt(disc)) / (2 * m.b[2]); x = Math.abs(r1 - cx) < Math.abs(r2 - cx) ? r1 : r2; }
      else if (Math.abs(m.b[1]) > 1e-9) x = -cst / m.b[1];
      const lvl = x === null ? null : a5 * (1 + x);
      t += `<tr><td>${s.lbl}</td><td>$${n(s.p, 3)}</td><td>${lvl !== null ? n(lvl) : '–'}</td><td>${x !== null ? sg(x * 100, 1, '%') : '–'}</td><td>${n(a5)}</td><td>${lvl !== null ? sg(lvl - a5) : '–'}</td></tr>`;
    });
    c.innerHTML = `<h2>What the strip is pricing <span class="note">storage level each contract price implies, by inverting the fair-value model</span></h2><div class="tbl"><table>${t}</table></div>
      <p class="note">Contract dated mid delivery month. Negative = the price implies a deficit to the 5-year average. Futures: ${src}. The repo's EIA contract 1–4 series stop in ${(await eia('fut1').catch(() => [{ s: '?' }])).at(-1).s.slice(0, 7)}, so the live strip comes from the CME settlement file instead. Extrapolating the trend term months ahead adds error.</p>`;
  }

  return { storage, sdMonthly, weather, model };
})();
