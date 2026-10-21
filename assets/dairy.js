// Dairy section: primer calculator, S&D, flows, outlook.
const D = 'data/dairy/derived/';
const ord = n => { n = Math.round(n); const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
const SYM = { DC: 'Class III', GDK: 'Class IV', CSC: 'Cheese', CB: 'Butter', GNF: 'NDM', DY: 'Dry whey' };
const UNIT = { DC: '$/cwt', GDK: '$/cwt', CSC: '$/lb', CB: '¢/lb', GNF: '¢/lb', DY: '¢/lb' };

// ── FMMO formulas (mirror of models/dairy_class.py) ──
function regime(ym) {
  const r = ym >= '2025-06'
    ? { ma_cheese: .2519, ma_butter: .2272, ma_ndm: .2393, ma_whey: .2668, bf_rec: .91, prot_yield: 1.589 }
    : { ma_cheese: .2003, ma_butter: .1715, ma_ndm: .1678, ma_whey: .1991, bf_rec: .90, prot_yield: 1.572 };
  Object.assign(r, ym >= '2025-12' ? { protein: 3.3, other: 6.0, nfs: 9.3 } : { protein: 3.1, other: 5.9, nfs: 9.0 });
  return r;
}
function components(cheese, butter, ndm, whey, r) {
  const bf = (butter - r.ma_butter) * 1.211, nfs = (ndm - r.ma_ndm) * .99, other = (whey - r.ma_whey) * 1.03;
  const a = cheese - r.ma_cheese, protein = a * 1.383 + (a * r.prot_yield - r.bf_rec * bf) * 1.17;
  const c3s = protein * r.protein + other * r.other, c4s = nfs * r.nfs;
  return { butterfat: bf, protein, other_solids: other, nonfat_solids: nfs, class3_skim: c3s, class4_skim: c4s, class3: .965 * c3s + 3.5 * bf, class4: .965 * c4s + 3.5 * bf };
}

let SD, FLOWS, REB, IMPL, SUMM, sym = 'DC', optMonth = null;

async function init() {
  [SD, FLOWS, REB, IMPL, SUMM] = await Promise.all([getJSON(D + 'sd.json'), getJSON(D + 'flows.json'),
    getCSV(D + 'class_rebuild.csv'), getCSV(D + 'class_futures_implied.csv').catch(() => []), getJSON(D + 'class_summary.json')]);
  IMPL = IMPL.slice(0, 18);  // deferred component months are illiquid; their settlements go stale
  const cot = FLOWS.cot.DC?.summary;
  $('#meta').innerHTML = `Dairy data: ERS through ${SD.milk.fat.metrics.last_month} · class prices through ${SUMM.last_announced} · COT ${cot?.date ?? '–'} · CME ${FLOWS.oi.DC?.date ?? '–'}`;
  initPrimer(); initSD(); initFlows(); initOutlook();
  tabs($('#dairy'), t => { if (t === 'd-geo' && !$('#dGeo').dataset.on) { $('#dGeo').dataset.on = 1; Geo.mount($('#dGeo'), ['milk', 'cheese', 'butter', 'nfdm'], ['Milk', 'Cheese', 'Butter', 'Nonfat dry milk']); } if (t === 'd-flows') { drawFlows(); if (!$('#dCotDesk').dataset.on) { $('#dCotDesk').dataset.on = 1; CotDesk.mount($('#dCotDesk'), ['DC', 'GDK', 'CSC', 'CB', 'GNF', 'DY']); } } if (t === 'd-sd') drawSD(); if (t === 'd-outlook' && !$('#dTech').dataset.on) { $('#dTech').dataset.on = 1; Tech.mount($('#dTech'), ['DC', 'GDK', 'CSC', 'CB', 'GNF', 'DY']); } });
  const h = location.hash.slice(1); if (h) $(`nav.tabs button[data-tab="${h}"]`)?.click();
}

// ── PRIMER ──
const SL = { cheese: 'sCheese', butter: 'sButter', ndm: 'sNdm', whey: 'sWhey' };
let calcMonth = null;
function setSliders(v, month, note) {
  for (const k in SL) { $('#' + SL[k]).value = v[k]; }
  calcMonth = month; $('#presetNote').textContent = note; calc();
}
function calc() {
  const v = {}; for (const k in SL) { v[k] = +$('#' + SL[k]).value; $('#o' + SL[k].slice(1)).textContent = '$' + v[k].toFixed(4); }
  const ym = calcMonth || new Date().toISOString().slice(0, 7), r = regime(ym), c = components(v.cheese, v.butter, v.ndm, v.whey, r);
  $('#oC3').textContent = '$' + c.class3.toFixed(2); $('#oC4').textContent = '$' + c.class4.toFixed(2);
  $('#oSpr').innerHTML = sgn(c.class3 - c.class4, 2);
  $('#tComp').innerHTML = `<tr><th>Component</th><th>$/lb</th><th class="l">Driven by</th></tr>
    <tr><td>Butterfat</td><td>${fmt(c.butterfat, 4)}</td><td class="l">butter</td></tr>
    <tr><td>Protein</td><td>${fmt(c.protein, 4)}</td><td class="l">cheese, net of butterfat</td></tr>
    <tr><td>Other solids</td><td>${fmt(c.other_solids, 4)}</td><td class="l">dry whey</td></tr>
    <tr><td>Nonfat solids</td><td>${fmt(c.nonfat_solids, 4)}</td><td class="l">NDM</td></tr>
    <tr><td>Class III skim ($/cwt)</td><td>${fmt(c.class3_skim, 2)}</td><td class="l">${r.protein}% protein, ${r.other}% other solids</td></tr>
    <tr><td>Class IV skim ($/cwt)</td><td>${fmt(c.class4_skim, 2)}</td><td class="l">${r.nfs}% nonfat solids</td></tr>`;
  const base = c, rows = [];
  for (const k of ['cheese', 'butter', 'ndm', 'whey']) {
    const w = { ...v }; w[k] += .10; const x = components(w.cheese, w.butter, w.ndm, w.whey, r);
    rows.push(`<tr><td>${{ cheese: 'Cheese', butter: 'Butter', ndm: 'NDM', whey: 'Dry whey' }[k]} +10¢</td><td>${sgn(x.class3 - base.class3, 2)}</td><td>${sgn(x.class4 - base.class4, 2)}</td></tr>`);
  }
  $('#tSens').innerHTML = `<tr><th>Move</th><th>Class III $/cwt</th><th>Class IV $/cwt</th></tr>` + rows.join('');
}
function initPrimer() {
  for (const k in SL) $('#' + SL[k]).oninput = calc;
  const last = REB.at(-1);
  const presets = {
    ams: () => setSliders({ cheese: last.cheese, butter: last.butter, ndm: last.ndm, whey: last.whey }, last.month, `USDA monthly averages for ${last.month}: Class III announced $${fmt(last.class3_ams)}, IV $${fmt(last.class4_ams)}.`),
    mtd: () => { const n = SUMM.nowcast?.at(-1); if (n) setSliders(n, n.month, `${n.month} NDPSR month-to-date (${n.weeks_in} weeks through ${n.through}).`); },
  };
  $$('[data-preset]').forEach(b => b.onclick = () => presets[b.dataset.preset]());
  const sel = $('#presetFut');
  sel.innerHTML = `<option value="">Futures month…</option>` + IMPL.map(r => `<option value="${r.month}">${r.month} futures</option>`).join('');
  sel.onchange = () => { const r = IMPL.find(x => x.month === sel.value); if (r) setSliders({ cheese: r.cheese, butter: r.butter / 100, ndm: r.ndm / 100, whey: r.whey / 100 }, r.month, `CME settlements ${r.trade_date} for ${r.month}: Class III futures $${fmt(r.class3_futures)}, IV $${fmt(r.class4_futures)}.`); };
  presets.ams();
}

// ── S&D ──
const BAL = { 'milk:fat': 'Milk, milk-fat basis', 'milk:skim': 'Milk, skim-solids basis', 'products:cheese_american': 'American cheese', 'products:cheese_other': 'Other cheese',
  'products:butter': 'Butter', 'products:ndm_smp': 'NDM / skim milk powder', 'products:dry_whey': 'Dry whey', 'products:wpc': 'WPC', 'products:lactose': 'Lactose' };
const bal = key => { const [g, k] = key.split(':'); return SD[g][k]; };
function initSD() {
  const k = [['milk:fat', 'Milk (fat basis)'], ['products:cheese_american', 'American cheese'], ['products:butter', 'Butter'], ['products:ndm_smp', 'NDM / SMP'], ['products:dry_whey', 'Dry whey']];
  const nm = SD.nass_milk;
  const nassCard = nm ? (() => { const i = nm.month.length - 1; return `<div class="card kpi"><div class="lbl">NASS milk production · ${nm.month[i]}</div>
      <div class="val">${sgn(nm.yoy_pct[i], 1, '%')}</div><div class="sub">${fmt(nm.production_bn_lb[i], 1)} bn lb, released ${nm.released[i]}</div>
      <div class="sub">cows ${fmt(nm.cows_mil[i], 2)}m (${sgn(nm.cows_yoy_k[i], 0)}k y/y) · ${fmt(nm.per_cow_lb[i], 0)} lb/cow</div><div class="sub">first print; ERS balances lag ~1 month</div></div>`; })() : '';
  $('#sdKpis').innerHTML = nassCard + k.map(([key, nm]) => { const m = bal(key).metrics, st = m.ending_stocks || {};
    return `<div class="card kpi"><div class="lbl">${nm} · ${m.last_month}</div>
      <div class="val">${sgn(m.production?.yoy_pct, 1, '%')}</div><div class="sub">production y/y · YTD ${sgn(m.production?.ytd_yoy_pct, 1, '%')}</div>
      <div class="sub">stocks ${sgn(st.yoy_pct, 1, '%')} y/y · ${sgn(st.vs_5y_avg_pct, 1, '%')} vs 5y · ${fmt(st.months_of_use, 2)} mo of use</div>
      <div class="sub">exports y/y ${sgn(m.exports?.yoy_pct, 1, '%')}</div></div>`; }).join('');
  $('#sdProd').innerHTML = Object.entries(BAL).map(([k, v]) => `<option value="${k}">${v}</option>`).join('');
  $('#sdProd').onchange = drawSD;
  // WASDE table
  const W = SD.wasde, rows = [];
  const yrs = [...new Set(Object.values(W.milk_fat || {}).flatMap(a => Object.keys(a)))].sort().slice(-2);
  const line = (lbl, key, attr, d = 1) => { const a = W[key]?.[attr]; if (!a) return '';
    return `<tr><td>${lbl}</td>${yrs.map(y => a[y] ? `<td>${fmt(a[y].value, d)}</td><td>${sgn(a[y].change, d)}</td>` : '<td>–</td><td></td>').join('')}</tr>`; };
  const hdr = `<tr><th></th>${yrs.map(y => `<th>${y}</th><th>chg</th>`).join('')}</tr>`;
  const sec = t => `<tr><td colspan="${1 + 2 * yrs.length}" class="l"><b>${t}</b></td></tr>`;
  $('#tWasde').innerHTML = hdr + sec('Milk, milk-fat basis (bn lb)') + line('Marketings', 'milk_fat', 'Marketings') + line('Imports', 'milk_fat', 'Imports') + line('Exports', 'milk_fat', 'Exports') + line('Domestic use', 'milk_fat', 'Domestic Use') + line('Ending stocks', 'milk_fat', 'Ending Stocks')
    + sec('Milk, skim-solids basis (bn lb)') + line('Imports', 'milk_skim', 'Imports') + line('Exports', 'milk_skim', 'Exports') + line('Domestic use', 'milk_skim', 'Domestic Use') + line('Ending stocks', 'milk_skim', 'Ending Stocks')
    + sec('Prices') + line('All milk $/cwt', 'milk', 'Prices', 2) + line('Class III $/cwt', 'class3', 'Prices', 2) + line('Class IV $/cwt', 'class4', 'Prices', 2)
    + line('Cheese $/lb', 'cheese', 'Prices', 3) + line('Butter $/lb', 'butter', 'Prices', 3) + line('NDM $/lb', 'ndm', 'Prices', 3) + line('Dry whey $/lb', 'whey', 'Prices', 3);
  const opts = [];
  for (const [key, attrs] of Object.entries(W)) for (const [attr, ys] of Object.entries(attrs)) for (const y of Object.keys(ys)) if (yrs.includes(y)) opts.push([`${key}|${attr}|${y}`, `${key.replace('_', ' ')} · ${attr} · ${y}`]);
  $('#wasdeItem').innerHTML = opts.map(([v, t]) => `<option value="${v}" ${v === `class3|Prices|${yrs.at(-1)}` ? 'selected' : ''}>${t}</option>`).join('');
  $('#wasdeItem').onchange = drawWasde;
  // nowcast
  const n = SUMM.nowcast?.at(-1), f = IMPL.find(r => r.month === n?.month);
  $('#nowcast').innerHTML = n ? `<div class="bigout"><div><div class="note">${n.month} Class III (MTD)</div><div class="v">$${fmt(n.class3)}</div></div><div><div class="note">${n.month} Class IV (MTD)</div><div class="v">$${fmt(n.class4)}</div></div></div>
    <p>${n.weeks_in} NDPSR weeks through ${n.through}: cheese $${fmt(n.cheese, 4)}, butter $${fmt(n.butter, 4)}, NDM $${fmt(n.ndm, 4)}, whey $${fmt(n.whey, 4)}.</p>
    ${f ? `<p>Futures for ${n.month}: Class III $${fmt(f.class3_futures)} (${sgn(f.class3_futures - n.class3, 2)} vs MTD), Class IV $${fmt(f.class4_futures)} (${sgn(f.class4_futures - n.class4, 2)} vs MTD). The gap is what the market expects the remaining weeks to add.</p>` : ''}` : '<p class="note">No unannounced month with NDPSR data yet.</p>';
  const e = SUMM.rebuild_max_abs_err_since_2025_06, e2 = SUMM.rebuild_max_abs_err_2013_2025_05;
  $('#rebuildNote').textContent = `Largest rebuild error: ${e.class3_err.toFixed(2)} (III) / ${e.class4_err.toFixed(2)} (IV) $/cwt since June 2025, ${e2.class3_err.toFixed(2)} / ${e2.class4_err.toFixed(2)} for 2013–May 2025, i.e. rounding only.`;
}
function drawSD() {
  const b = bal($('#sdProd').value), s = b.series;
  $('#sdAsOf').textContent = `through ${b.metrics.last_month}`;
  const sp = seasonal(s.month, s.production), ss = seasonal(s.month, s.ending_stocks);
  const sopt = { plugins: { legend: legendNoMin } };
  chart('cSdProd', { type: 'line', data: { labels: MON, datasets: seasonalDatasets(sp) }, options: sopt });
  chart('cSdStocks', { type: 'line', data: { labels: MON, datasets: seasonalDatasets(ss) }, options: sopt });
  const yoy = a => a.map((v, i) => i >= 12 && v != null && a[i - 12] ? 100 * (v / a[i - 12] - 1) : null);
  const n = 24, L = s.month.slice(-n);
  chart('cSdUse', { type: 'bar', data: { labels: L, datasets: [
    { label: 'Exports y/y %', data: yoy(s.exports || []).slice(-n), backgroundColor: '#2c6fbb' },
    { label: 'Domestic disappearance y/y %', data: yoy(s.domestic_disappearance || []).slice(-n), backgroundColor: '#d68910' }] } });
  if (s.price && s.months_of_use) {
    $('#sdScatterTitle').textContent = 'Stocks in months of use vs price ($/lb)';
    const pts = s.month.map((m, i) => ({ x: s.months_of_use[i], y: s.price[i], m })).filter(p => p.x != null && p.y != null);
    const recent = pts.slice(-12), older = pts.slice(0, -12);
    chart('cSdScatter', { type: 'scatter', data: { datasets: [
      { label: 'earlier', data: older, backgroundColor: 'rgba(120,120,120,.35)', pointRadius: 3 },
      { label: 'last 12 months', data: recent, backgroundColor: '#c0392b', pointRadius: 4 }] },
      options: { interaction: { mode: 'nearest', intersect: true }, plugins: { tooltip: { callbacks: { label: c => `${c.raw.m}: ${c.raw.x.toFixed(2)} mo, $${c.raw.y.toFixed(3)}` } } },
        scales: { x: { title: { display: true, text: 'months of use' }, grid: { color: '#eee' } }, y: { title: { display: true, text: '$/lb' } } } } });
  } else {
    $('#sdScatterTitle').textContent = 'Ending stocks (million lb)';
    chart('cSdScatter', { type: 'line', data: { labels: s.month.slice(-60), datasets: [{ label: 'ending stocks', data: s.ending_stocks.slice(-60), borderColor: PAL[0], pointRadius: 0 }] } });
  }
  drawWasde(); drawRebuild();
}
function drawWasde() {
  const [k, a, y] = $('#wasdeItem').value.split('|'), h = SD.wasde[k][a][y].history;
  chart('cWasde', { type: 'line', data: { labels: h.map(x => x[0].replace(/(\w{3})\w* (\d{4})/, '$1 $2')), datasets: [{ label: `${k} ${a} ${y}`, data: h.map(x => x[1]), borderColor: PAL[0], stepped: true, pointRadius: 3 }] } });
}
function drawRebuild() {
  const r = REB.slice(-60);
  chart('cRebuild', { type: 'line', data: { labels: r.map(x => x.month), datasets: [
    { label: 'Class III announced', data: r.map(x => x.class3_ams), borderColor: PAL[0], pointRadius: 0, borderWidth: 2 },
    { label: 'Class III rebuild', data: r.map(x => x.class3_model), borderColor: '#9ad29f', borderDash: [4, 3], pointRadius: 0 },
    { label: 'Class IV announced', data: r.map(x => x.class4_ams), borderColor: PAL[2], pointRadius: 0, borderWidth: 2 },
    { label: 'Class IV rebuild', data: r.map(x => x.class4_model), borderColor: '#9cc3ee', borderDash: [4, 3], pointRadius: 0 }] } });
}

// ── FLOWS ──
function initFlows() {
  const syms = Object.keys(SYM).filter(s => FLOWS.cot[s]);
  $('#tCot').innerHTML = `<tr><th>Contract</th><th>Report</th><th>Open int.</th><th>MM net</th><th>w/w</th><th>% of OI</th><th>Pctl all</th><th>Pctl 3y</th><th>Prod/merch net</th><th>Swap net</th></tr>` +
    syms.map(s => { const c = FLOWS.cot[s].summary; return `<tr><td>${SYM[s]} (${s})</td><td>${c.date}</td><td>${fmt(c.oi, 0)}</td><td>${sgn(c.mm_net, 0)}</td><td>${sgn(c.mm_net_wow, 0)}</td><td>${fmt(c.mm_net_pct_oi, 1)}%</td><td>${fmt(c.mm_net_percentile_all, 0)}</td><td>${fmt(c.mm_net_percentile_3y, 0)}</td><td>${sgn(c.pm_net, 0)}</td><td>${sgn(c.sw_net, 0)}</td></tr>`; }).join('');
  $('#flowSyms').innerHTML = Object.keys(SYM).map(s => `<button class="btn ${s === sym ? 'on' : ''}" data-s="${s}">${SYM[s]}</button>`).join(' ');
  $$('#flowSyms button').forEach(b => b.onclick = () => { sym = b.dataset.s; optMonth = null; $$('#flowSyms button').forEach(x => x.classList.toggle('on', x === b)); drawFlows(); });
}
function drawFlows() {
  const px = FLOWS.prices[sym];
  if (px) chart('cPx', { type: 'line', data: { labels: px.date.slice(-750), datasets: [{ label: `${SYM[sym]} front month (${UNIT[sym]})`, data: px.c1.slice(-750), borderColor: PAL[0], pointRadius: 0, borderWidth: 1.4 }] } });
  const c = FLOWS.cot[sym]?.series;
  if (c) { const n = 260; chart('cCot', { type: 'line', data: { labels: c.date.slice(-n), datasets: [
    { label: 'Managed money net', data: c.mm_net.slice(-n), borderColor: PAL[1], pointRadius: 0, borderWidth: 2 },
    { label: 'Producer/merchant net', data: c.pm_net.slice(-n), borderColor: PAL[2], pointRadius: 0, borderWidth: 1.4 },
    { label: 'Swap dealer net', data: c.sw_net.slice(-n), borderColor: '#999', pointRadius: 0, borderWidth: 1 }] } }); }
  const cv = FLOWS.curves[sym];
  if (cv) { const days = Object.keys(cv).sort(), d1 = days.at(-1), d0 = days.length > 1 ? days[0] : null;
    $('#curveTitle').textContent = `Forward curve (${UNIT[sym]}) · ${d1}${d0 ? ' vs ' + d0 : ''}`;
    chart('cCurve', { type: 'line', data: { labels: cv[d1].month, datasets: [
      { label: d1, data: cv[d1].settle, borderColor: PAL[0], borderWidth: 2, pointRadius: 2 },
      ...(d0 ? [{ label: d0, data: cv[d1].month.map(m => { const i = cv[d0].month.indexOf(m); return i < 0 ? null : cv[d0].settle[i]; }), borderColor: '#aaa', borderDash: [4, 3], pointRadius: 0 }] : [])] } }); }
  const oi = FLOWS.oi[sym];
  if (oi) { $('#oiTitle').textContent = `Open interest by month and daily change · ${oi.date}`;
    chart('cOi', { type: 'bar', data: { labels: oi.month.map(m => m.replace(/(\w{3}) \d{2}(\d{2})/, '$1 $2')), datasets: [
      { label: 'Open interest', data: oi.oi, backgroundColor: 'rgba(47,107,58,.55)', yAxisID: 'y' },
      { label: 'Change', data: oi.oi_change, backgroundColor: oi.oi_change.map(v => v >= 0 ? '#1f7a3a' : '#b3261e'), yAxisID: 'y1' }] },
      options: { scales: { y1: { position: 'right', grid: { display: false }, ticks: { font: { size: 10 } } } } } }); }
  drawOptions(); drawImplied();
}
function drawOptions() {
  const o = FLOWS.options[sym];
  if (!o) { $('#optMonths').innerHTML = ''; $('#optNote').textContent = 'No options data.'; chart('cOpt', { type: 'bar', data: { labels: [], datasets: [] } }); return; }
  const ms = Object.keys(o.months); optMonth ||= ms[Math.min(1, ms.length - 1)];
  $('#optMonths').innerHTML = ms.map(m => `<button class="btn ${m === optMonth ? 'on' : ''}" data-m="${m}">${m}</button>`).join(' ');
  $$('#optMonths button').forEach(b => b.onclick = () => { optMonth = b.dataset.m; drawOptions(); });
  const x = o.months[optMonth];
  $('#optNote').textContent = ` ${o.date} · put/call OI ${x.put_call_oi ?? '–'}`;
  chart('cOpt', { type: 'bar', data: { labels: x.strike, datasets: [
    { label: 'Call OI', data: x.call_oi, backgroundColor: 'rgba(31,122,58,.7)' }, { label: 'Put OI', data: x.put_oi.map(v => -v), backgroundColor: 'rgba(179,38,30,.7)' },
    { label: 'Call OI chg', data: x.call_chg, backgroundColor: 'rgba(31,122,58,.25)', hidden: true }, { label: 'Put OI chg', data: x.put_chg.map(v => -v), backgroundColor: 'rgba(179,38,30,.25)', hidden: true }] },
    options: { indexAxis: 'y', scales: { x: { stacked: false, ticks: { callback: v => Math.abs(v) } }, y: { ticks: { autoSkip: true, maxTicksLimit: 30 } } },
      plugins: { tooltip: { callbacks: { label: c => `${c.dataset.label}: ${Math.abs(c.raw)}` } } } } });
}
function drawImplied() {
  if (!IMPL.length) return;
  chart('cImplied', { type: 'line', data: { labels: IMPL.map(r => r.month), datasets: [
    { label: 'Class III futures', data: IMPL.map(r => r.class3_futures), borderColor: PAL[0], borderWidth: 2, pointRadius: 2 },
    { label: 'Class III implied', data: IMPL.map(r => r.class3_implied), borderColor: '#9ad29f', borderDash: [4, 3], pointRadius: 0 },
    { label: 'Class IV futures', data: IMPL.map(r => r.class4_futures), borderColor: PAL[2], borderWidth: 2, pointRadius: 2 },
    { label: 'Class IV implied', data: IMPL.map(r => r.class4_implied), borderColor: '#9cc3ee', borderDash: [4, 3], pointRadius: 0 }] } });
}

// ── OUTLOOK ──
async function initOutlook() {
  const L = [], P = SD.products, M = SD.milk.fat.metrics, W = SD.wasde;
  $('#olAsOf').textContent = `Built ${SD.generated.slice(0, 10)} from ERS balances through ${M.last_month}, class prices through ${SUMM.last_announced}, CME settlements ${IMPL[0]?.trade_date ?? '–'}, COT ${FLOWS.cot.DC?.summary.date ?? '–'}.`;
  L.push(`<b>Milk supply:</b> production ${sgn(M.production.yoy_pct, 1, '%')} y/y in ${M.last_month} (${sgn(M.production.ytd_yoy_pct, 1, '%')} YTD); domestic disappearance ${sgn(M.disappearance.yoy_pct, 1, '%')}, exports ${sgn(M.exports.yoy_pct, 1, '%')} on a milk-fat basis.`);
  const tight = [], heavy = [];
  for (const [k, nm] of [['cheese_american', 'American cheese'], ['butter', 'butter'], ['ndm_smp', 'NDM/SMP'], ['dry_whey', 'dry whey']]) {
    const s = P[k].metrics.ending_stocks; if (!s) continue;
    (s.vs_5y_avg_pct <= -5 ? tight : s.vs_5y_avg_pct >= 5 ? heavy : []).push(`${nm} ${sgn(s.vs_5y_avg_pct, 0, '%')} vs 5y (${fmt(s.months_of_use, 2)} mo of use)`);
  }
  L.push(`<b>Stocks:</b> ${tight.length ? 'below normal: ' + tight.join(', ') + '. ' : ''}${heavy.length ? 'above normal: ' + heavy.join(', ') + '.' : ''}${!tight.length && !heavy.length ? 'all four settlement products within ±5% of the 5-year seasonal average.' : ''}`);
  const n = SUMM.nowcast?.at(-1), f = IMPL.find(r => r.month === n?.month);
  if (n && f) L.push(`<b>Nearby settlement:</b> ${n.month} Class III is tracking $${fmt(n.class3)} on ${n.weeks_in} NDPSR weeks vs $${fmt(f.class3_futures)} futures (${sgn(f.class3_futures - n.class3, 2)}); Class IV $${fmt(n.class4)} vs $${fmt(f.class4_futures)} (${sgn(f.class4_futures - n.class4, 2)}). Futures above MTD need firmer product prices in the remaining weeks.`);
  const g3 = IMPL.slice(0, 6).map(r => r.class3_gap), g4 = IMPL.slice(0, 6).map(r => r.class4_gap), avg = a => a.reduce((x, y) => x + y, 0) / a.length;
  if (IMPL.length) L.push(`<b>Milk vs components:</b> first six months Class III futures average ${sgn(avg(g3), 2)} $/cwt vs component-implied, Class IV ${sgn(avg(g4), 2)}. ${Math.abs(avg(g4)) > .15 || Math.abs(avg(g3)) > .15 ? 'A gap this size is tradable relative value against the component strip.' : 'Milk is priced in line with its components.'}`);
  const curve = IMPL.slice(0, 13).map(r => r.class3_futures);
  if (curve.length > 6) L.push(`<b>Curve:</b> Class III ${curve[0] < curve.at(-1) ? 'contango' : 'backwardation'} from $${fmt(curve[0])} (${IMPL[0].month}) to $${fmt(curve.at(-1))} (${IMPL[curve.length - 1].month}); Class IV from $${fmt(IMPL[0].class4_futures)} to $${fmt(IMPL[curve.length - 1].class4_futures)}.`);
  const yr = Object.keys(W.class3?.Prices || {}).sort().at(-1);
  if (yr) { const w = k => W[k]?.Prices?.[yr]; L.push(`<b>WASDE (${w('class3').report}):</b> ${yr} Class III $${fmt(w('class3').value)} (${sgn(w('class3').change, 2)}), Class IV $${fmt(w('class4').value)} (${sgn(w('class4').change, 2)}); marketings ${fmt(W.milk_fat.Marketings[yr].value, 1)} bn lb (${sgn(W.milk_fat.Marketings[yr].change, 1)}).`); }
  const CB = await getJSON('data/derived/cot_backtest.json').catch(() => ({}));
  const pos = Object.entries(FLOWS.cot).map(([s, v]) => [s, v.summary]).filter(([, c]) => c.mm_net_percentile_3y >= 90 || c.mm_net_percentile_3y <= 10);
  const ev = (s, c) => { const t = CB[s]?.w4?.[c.mm_net >= 0 ? 'extreme_long' : 'extreme_short']; return t ? ` (history after similar readings: ${sgn(t.mean_pct, 1, '%')} over 4 weeks, up ${Math.round(100 * t.up_share)}% of the time, n=${t.n})` : ''; };
  L.push(`<b>Positioning (secondary):</b> ${pos.length ? pos.map(([s, c]) => `${SYM[s]} ${c.mm_net >= 0 ? 'long' : 'short'} ${ord(c.mm_net_percentile_3y)} pctl`).join(', ') + '. Settlement is set by USDA cash prices, so positioning only matters at the margin; in Class III, Class IV and cheese, extremes have tended to persist.' : 'no dairy contract at a 3-year positioning extreme.'}`);
  $('#olList').innerHTML = L.map(x => `<li>${x}</li>`).join('');
  const BT = await getJSON(D + 'backtest.json').catch(() => null);
  if (BT) {
    const n3 = BT.nowcast.class3['2019-2026'], n4 = BT.nowcast.class4['2019-2026'];
    const row = k => `<tr><td>${k} week${k > 1 ? 's' : ''}</td><td>${fmt(n3[k]?.nowcast_err)}</td><td>${fmt(n3[k]?.futures_err)}</td><td>${fmt(n4[k]?.nowcast_err)}</td><td>${fmt(n4[k]?.futures_err)}</td><td>${fmt(n3[k]?.prev_err)}</td></tr>`;
    const sd1 = BT.sd_to_price.h1['stocks+use'], sd3 = BT.sd_to_price.h3['stocks+use'];
    const sdr = p => `<tr><td>${p}</td><td>${sgn(sd1[p]?.oos_r2_vs_no_change, 2)}</td><td>${fmt(100 * (sd1[p]?.hit_rate ?? NaN), 0)}%</td><td>${sgn(sd3[p]?.oos_r2_vs_no_change, 2)}</td><td>${fmt(100 * (sd3[p]?.hit_rate ?? NaN), 0)}%</td></tr>`;
    const cot = s => { const x = CB[s]?.w4; if (!x) return ''; const f = y => y ? `${sgn(y.mean_pct, 2, '%')} · ${Math.round(100 * y.up_share)}% up · n${y.n}` : '–'; return `<tr><td>${SYM[s] || s}</td><td>${f(x.all)}</td><td>${f(x.extreme_short)}</td><td>${f(x.extreme_long)}</td></tr>`; };
    const DCV = await getJSON(D + 'dairy_convergence.json').catch(() => null);
    const CBI = await getJSON('data/derived/convergence_bias.json').catch(() => null);
    const SPT = await getJSON(D + 'dairy_spot.json').catch(() => null);
    let conv = '';
    if (DCV) {
      const c3 = DCV.tests['2013-2026'].class3, c4 = DCV.tests['2013-2026'].class4;
      conv = `<h3>Convergence: who forecasts the announced class price better? (mean abs error $/cwt, weekly origins 2013–2026)</h3>
      <div class="tbl"><table><tr><th>Months ahead</th><th>III futures</th><th>III fundamental</th><th>IV futures</th><th>IV fundamental</th></tr>
      ${[0, 1, 2, 3, 6].map(h => `<tr><td>${h === 0 ? 'current month' : h}</td><td>${fmt(c3[h].mae_futures)}</td><td>${fmt(Math.min(c3[h].mae_persist, c3[h].mae_seasonal))}</td><td>${fmt(c4[h].mae_futures)}</td><td>${fmt(Math.min(c4[h].mae_persist, c4[h].mae_seasonal))}</td></tr>`).join('')}</table></div>
      <p class="note">Each contract is scored against the USDA price it settled to. Fundamental = NDPSR weeks to date plus latest week carried (current month), latest NDPSR prices through the formula with and without seasonal adjustment (later months); best of the two shown. Futures win at every horizon: they trade the daily CME spot auctions that NDPSR reflects 1–2 weeks later.</p>`;
    }
    if (SPT?.tests) {
      const r = (c, k) => { const x = SPT.tests[c]?.[k]; return x ? `<td>${fmt(x.mae_futures, 2)}</td><td>${fmt(x.mae_ndpsr, 2)}</td><td>${fmt(x.mae_spot, 2)}</td>` : '<td></td><td></td><td></td>'; };
      const cur = SPT.current;
      conv += `<h3>Does the CME daily spot auction improve the current-month nowcast? (since ${SPT.since}, $/cwt)</h3>
      <div class="tbl"><table><tr><th></th><th>III futures</th><th>III NDPSR</th><th>III + spot</th><th>IV futures</th><th>IV NDPSR</th><th>IV + spot</th></tr>
      ${['2+ weeks left', '1 week left', 'final week'].map(k => `<tr><td>${k}</td>${r('class3', k)}${r('class4', k)}</tr>`).join('')}</table></div>
      <p class="note">“+ spot” fills the month's remaining NDPSR weeks with the last 5 CME spot sessions plus the usual NDPSR-minus-spot spread. It is no better than carrying the latest NDPSR week, and futures beat both: the CME spot auction is already in the futures price.${cur ? ` Current reading (${cur.month}, spot to ${cur.spot_date}, ${cur.weeks_left} NDPSR weeks left): Class III ${fmt(cur.class3, 2)}, Class IV ${fmt(cur.class4, 2)}.` : ''}</p>`;
    }
    if (CBI) {
      const row = s => { const v = CBI[s]; return v ? `<tr><td>${SYM[s] || s}</td>${['h20', 'h60', 'h120'].map(h => `<td>${sgn(v[h]?.mean_pct, 2, '%')} · ${Math.round(100 * (v[h]?.up_share ?? 0))}% up · t ${fmt(v[h]?.t, 1)}</td>`).join('')}</tr>` : ''; };
      conv += `<h3>Systematic convergence: futures vs their own final settlement (expired contracts since 2010)</h3>
      <div class="tbl"><table><tr><th>Contract</th><th>From 20 business days out</th><th>From 60</th><th>From 120</th></tr>${['DC', 'GDK', 'CSC', 'CB', 'GNF', 'DY'].map(row).join('')}</table></div>
      <p class="note">Positive = futures settled above where they traded. Dry whey has settled ~3% above its 60-day-out price in both 2010–17 and 2018–26; the NDM and Class IV discounts seen in 2010–17 have not persisted. t-stats overstate significance because neighbouring contracts share shocks.</p>`;
    }
    $('#olTests').innerHTML = conv + `<h3>Month-to-date nowcast vs futures (mean abs error to announced price, $/cwt, 2019–2026)</h3>
      <div class="tbl"><table><tr><th>NDPSR weeks in</th><th>III nowcast</th><th>III futures</th><th>IV nowcast</th><th>IV futures</th><th>III no-change</th></tr>${[1, 2, 3, 4].map(row).join('')}</table></div>
      <p class="note">Front-month futures beat the NDPSR month-to-date early in the month: they price the CME spot market daily, NDPSR lags it 1–2 weeks. From week 3 the futures comparison is contaminated by TradingView's continuous-contract roll; per-contract history from the nightly CME download will fix that going forward.</p>
      <h3>Do S&amp;D stocks predict product prices? (walk-forward, out of sample, from 2016)</h3>
      <div class="tbl"><table><tr><th>Product</th><th>1m R² vs no-change</th><th>1m hit</th><th>3m R²</th><th>3m hit</th></tr>${['cheese', 'butter', 'ndm', 'whey', 'pooled'].map(sdr).join('')}</table></div>
      <p class="note">Negative R² = worse than assuming no change. Stocks and months-of-use, known with the ~2-month NASS/ERS lag, carry no out-of-sample edge except dry whey one month ahead. The market prices them before they publish; treat them as context, not a signal.</p>
      <h3>Managed-money extremes and the next 4 weeks (roll-adjusted front month)</h3>
      <div class="tbl"><table><tr><th>Contract</th><th>All weeks</th><th>After extreme short (≤10th pctl 3y)</th><th>After extreme long (≥90th)</th></tr>${['DC', 'CSC', 'CB', 'GNF', 'GDK', 'DY'].map(cot).join('')}</table></div>
      <p class="note">Fund extremes have tended to persist: Class III and Class IV rose after extreme longs (t≈2), cheese fell after extreme shorts (t≈−2.5); the other contracts show nothing. No contract shows a reliable contrarian squeeze.</p>`;
  }
  try { const t = await fetch('data/dairy/outlook.md').then(r => r.ok ? r.text() : ''); if (t.trim()) $('#olView').innerHTML = t.split(/\n\s*\n/).map(p => `<p>${p.replace(/^#+\s*/, '')}</p>`).join(''); } catch (e) {}
}

init();
