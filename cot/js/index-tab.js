/* ===========================================================
   INDEX (CIT) TAB — CFTC Supplemental index-trader positions.
   Reads data/web/snapshot.json (cit, cit_agg) and series/<T>.json (cit).
   Charts mirror the COT Analyzer (shared mkLine / pts helpers).
   =========================================================== */
var IX = null, ixCharts = {}, ixZ = {}, ixSnap = null;
function ixUsd(v, sign) { if (v == null) return '–'; var x = Math.abs(v), s = v < 0 ? '−' : (sign ? '+' : ''); return s + '$' + (x >= 1e9 ? (x / 1e9).toFixed(2) + 'bn' : x >= 1e6 ? (x / 1e6).toFixed(0) + 'm' : (x / 1e3).toFixed(0) + 'k'); }
function ixK(v) { return v == null ? '–' : COTInsights.k(v); }
function ixSK(v) { return v == null ? '–' : COTInsights.sk(v); }
function ixC(v) { return v == null ? '' : v > 0 ? 'ix-pos' : v < 0 ? 'ix-neg' : ''; }

function initIndexTab() {
  COTStore.snapshot().then(function (snap) {
    ixSnap = snap;
    var a = snap.cit_agg;
    if (!a) { document.getElementById('ixNote').textContent = 'Index-trader data is not available yet. It is added by the weekly update.'; return; }
    var T = a.total;
    document.getElementById('ixDate').innerHTML = 'Report of ' + a.date + (a.rebal ? ' &nbsp;<span class="ix-rb">January reweight window</span>' : '');
    var kp = [
      { k: 'Index net exposure', v: ixUsd(T.Nusd), m: 'long ' + ixUsd(T.Lusd) + ' · short ' + ixUsd(T.Susd) },
      { k: 'Index flow, week', v: ixUsd(T.dNusd, true), m: ixSK(T.dN) + ' lots' },
      { k: 'Managed money flow, week', v: ixUsd(T.mmdNusd, true), m: ixSK(T.mmdN) + ' lots · net ' + ixUsd(T.mmNusd) },
      { k: 'Index flow, 4 weeks', v: ixUsd(T.dN4usd, true), m: ixSK(T.dN4) + ' lots' },
      { k: 'Markets adding (4w)', v: a.adding4 + ' / ' + a.n, m: 'breadth ' + (a.breadth4_pct != null ? COTInsights.ord(a.breadth4_pct) + ' pct of history' : '–') }
    ];
    document.getElementById('ixKpis').innerHTML = kp.map(function (x) { return '<div class="ix-kpi"><div class="k">' + x.k + '</div><div class="v">' + x.v + '</div><div class="m">' + x.m + '</div></div>'; }).join('');
    var br = COTInsights.brief(COTInsights.analyze(snap, {})).filter(function (l) { return l.h === 'Index flows'; })[0];
    document.getElementById('ixNote').textContent = br ? br.t : '';
    ixTable();
    ixBreadth(a.breadth_hist);
    var rows = (snap.commodities || []).filter(function (c) { return c.cit; });
    var sel = document.getElementById('ixSel');
    sel.innerHTML = rows.map(function (c) { return '<option value="' + c.ticker + '"' + (c.ticker === 'CT' ? ' selected' : '') + '>' + c.name + '</option>'; }).join('');
    ixLoad();
  });
}

function ixTable() {
  var a = ixSnap && ixSnap.cit_agg; if (!a) return;
  var four = document.getElementById('ixFlowWin').value === '4';
  var secOrder = ['Grains', 'Softs', 'Livestock'], sel = document.getElementById('ixSel').value;
  function row(cls, name, x, t) {
    var dI = four ? x.dN4 : x.dN, dIu = four ? x.dN4usd : x.dNusd;
    return '<tr class="' + cls + (t && t === sel ? ' sel' : '') + '"' + (t ? ' data-t="' + t + '"' : '') + '><td class="nm">' + name + '</td>' +
      '<td>' + ixK(x.N) + '</td><td class="' + ixC(dI) + '">' + ixSK(dI) + '</td><td class="' + ixC(dIu) + '">' + ixUsd(dIu, true) + '</td>' +
      '<td>' + ixUsd(x.Nusd) + '</td><td>' + ixUsd(x.Lusd) + ' / ' + ixUsd(x.Susd) + '</td>' +
      '<td>' + ixK(x.mmN) + '</td><td class="' + ixC(x.mmdN) + '">' + (four ? '–' : ixSK(x.mmdN)) + '</td><td class="' + ixC(x.mmdNusd) + '">' + (four ? '–' : ixUsd(x.mmdNusd, true)) + '</td><td>' + ixUsd(x.mmNusd) + '</td></tr>';
  }
  var h = '';
  secOrder.forEach(function (s) {
    var ms = (a.markets || []).filter(function (m) { return m.sector === s; }).sort(function (x, y) { return (y.Nusd || 0) - (x.Nusd || 0); });
    if (!ms.length) return;
    h += row('sec', s, a.sectors[s]);
    ms.forEach(function (m) { h += row('', '&nbsp;&nbsp;' + m.name, m, m.t); });
  });
  h += row('tot', 'All ' + a.n + ' markets', a.total);
  document.getElementById('ixFlowBody').innerHTML = h;
  document.querySelectorAll('#ixFlowBody tr[data-t]').forEach(function (tr) {
    tr.onclick = function () { document.getElementById('ixSel').value = tr.getAttribute('data-t'); ixLoad(); };
  });
}

function ixLoad() {
  var t = document.getElementById('ixSel').value; if (!t) return;
  ixTable(); ixPctTable();
  var from = document.getElementById('ixFrom').value || '2006-01-01';
  COTStore.series(t).then(function (s) {
    if (!s.cit) return;
    var c = s.cit, mm = s.ct.all.managed_money, d = { name: s.name, dates: [], L: [], S: [], N: [], oi: [], tL: [], tS: [], px: [], ncN: [], cmN: [], nrN: [], mmN: [], ncL: [], cmL: [], nrL: [], mmL: [], ncS: [], cmS: [], nrS: [], mmS: [] };
    for (var i = 0; i < s.dates.length; i++) {
      if (s.dates[i] < from || c.l[i] == null || c.oi[i] == null) continue;
      d.dates.push(s.dates[i]); d.L.push(c.l[i]); d.S.push(c.s[i]); d.N.push(c.l[i] - c.s[i]); d.oi.push(c.oi[i]);
      d.tL.push(c.tl[i]); d.tS.push(c.ts[i]); d.px.push(c.px[i]);
      d.ncL.push(c.ncl[i]); d.ncS.push(c.ncs[i]); d.ncN.push(c.ncl[i] - c.ncs[i]);
      d.cmL.push(c.cml[i]); d.cmS.push(c.cms[i]); d.cmN.push(c.cml[i] - c.cms[i]);
      d.nrL.push(c.nrl[i]); d.nrS.push(c.nrs[i]); d.nrN.push(c.nrl[i] - c.nrs[i]);
      d.mmL.push(mm.l[i]); d.mmS.push(mm.s[i]); d.mmN.push(mm.l[i] != null ? mm.l[i] - mm.s[i] : null);
    }
    d.mult = c.mult;
    d.usd = function (arr) { return arr.map(function (v, i) { return (v == null || d.px[i] == null || !d.mult) ? null : v * d.px[i] * d.mult; }); };
    IX = d;
    ixDrawPos(); ixDrawCmp(); ixDrawTrd(); ixDrawSz();
  });
}

function ixPctBar(v) {
  if (v == null) return '<td class="pc" style="text-align:center;color:#999;">–</td>';
  return '<td class="pc"><div class="pb" title="' + v.toFixed(0) + 'th percentile"><i style="left:' + Math.max(3, Math.min(97, v)) + '%"></i><span style="' + (v > 60 ? 'left:5px;right:auto;' : '') + '">' + v.toFixed(0) + '</span></div></td>';
}
function ixPctTable() {
  var W = [['y5', '5 years', 'w5'], ['y10', '10 years', 'w10'], ['f', 'Since 2006', 'wf']];
  var P = [['N', 'Net'], ['np', 'Net %OI'], ['L', 'Long'], ['Nusd', 'Net $']];
  document.getElementById('ixPctHead').innerHTML =
    '<tr><th rowspan="2">Market</th><th rowspan="2">Net (lots)</th><th rowspan="2">Net ($)</th><th rowspan="2">% of OI</th>' +
    W.map(function (w) { return '<th colspan="' + P.length + '" class="' + w[2] + '">' + w[1] + '</th>'; }).join('') + '</tr><tr>' +
    W.map(function (w) { return P.map(function (p) { return '<th class="' + w[2] + '">' + p[1] + '</th>'; }).join(''); }).join('') + '</tr>';
  var sec = { Grains: 0, Softs: 1, Livestock: 2 }, sel = document.getElementById('ixSel').value;
  var rows = (ixSnap.commodities || []).filter(function (c) { return c.cit; })
    .sort(function (a, b) { return (sec[a.sector] - sec[b.sector]) || ((b.cit.Nusd || 0) - (a.cit.Nusd || 0)); });
  var h = '', last = null;
  rows.forEach(function (c) {
    if (c.sector !== last) { h += '<tr class="sec"><td class="nm" colspan="' + (4 + W.length * P.length) + '" style="text-align:left;">' + c.sector + '</td></tr>'; last = c.sector; }
    var x = c.cit;
    h += '<tr data-t="' + c.ticker + '"' + (c.ticker === sel ? ' class="sel"' : '') + '><td class="nm">' + c.name + '</td><td>' + ixK(x.N) + '</td><td>' + ixUsd(x.Nusd) + '</td><td>' + (x.np != null ? x.np.toFixed(1) + '%' : '–') + '</td>' +
      W.map(function (w) { return P.map(function (p) { var s = x.p && x.p[p[0]]; return ixPctBar(s ? s[w[0]] : null); }).join(''); }).join('') + '</tr>';
  });
  document.getElementById('ixPctBody').innerHTML = h;
  document.querySelectorAll('#ixPctBody tr[data-t]').forEach(function (tr) {
    tr.onclick = function () { document.getElementById('ixSel').value = tr.getAttribute('data-t'); ixLoad(); };
  });
}

function ixFinish(key, ch) { ixCharts[key] = ch; ixApplyZoom(key); }
function ixZoom(key, val) { ixZ[key] = parseInt(val, 10); var s = document.getElementById('ixz_' + key); if (s) s.value = val; ixApplyZoom(key); }
function ixApplyZoom(key) {
  var ch = ixCharts[key]; if (!ch || !IX) return;
  var p = ixZ[key] || 100, n = IX.dates.length, lbl = document.getElementById('ixzl_' + key);
  if (p >= 100) { ch.options.scales.x.min = undefined; ch.options.scales.x.max = undefined; if (lbl) lbl.textContent = 'All data'; }
  else { var show = Math.max(8, Math.round(n * p / 100)); ch.options.scales.x.min = IX.dates[Math.max(0, n - show)]; ch.options.scales.x.max = IX.dates[n - 1]; if (lbl) lbl.textContent = 'Last ~' + show + ' wks'; }
  ch.update('none');
}
function ixDs(label, vals, col, fill) { return { label: label, data: pts(IX.dates, vals), borderColor: col, backgroundColor: col + '18', borderWidth: 2, pointRadius: 0, fill: !!fill, tension: 0.4, spanGaps: true }; }

function ixDrawPos() {
  if (!IX) return; var m = document.getElementById('ixPosMet').value;
  if (ixCharts.pos) ixCharts.pos.destroy();
  var pc = function (a) { return a.map(function (v, i) { return IX.oi[i] > 0 ? v / IX.oi[i] * 100 : null; }); };
  var V = { net: [IX.N, 'Net', '#2a5298'], long: [IX.L, 'Long', '#1a8c4e'], short: [IX.S, 'Short', '#c0392b'], net_pct: [pc(IX.N), 'Net%OI', '#2a5298'], long_pct: [pc(IX.L), 'Long%OI', '#1a8c4e'],
            net_usd: [IX.usd(IX.N).map(function (v) { return v == null ? null : v / 1e9; }), 'Net ($bn)', '#2a5298'], long_usd: [IX.usd(IX.L).map(function (v) { return v == null ? null : v / 1e9; }), 'Long ($bn)', '#1a8c4e'] }[m];
  var ds = [ixDs(V[1], V[0], V[2], true)];
  var y = m.indexOf('pct') > -1 ? '% OI' : m.indexOf('usd') > -1 ? 'US$ bn' : 'Contracts';
  var pxOk = IX.px.filter(function (v) { return v != null; }).length > IX.dates.length * 0.5;
  if (pxOk) ds.push({ label: 'Front-month price', data: pts(IX.dates, IX.px), borderColor: 'rgba(70,70,70,.75)', borderWidth: 1.3, borderDash: [4, 3], pointRadius: 0, fill: false, yAxisID: 'y1', tension: 0.2 });
  ixFinish('pos', mkLine(document.getElementById('ixPosChart').getContext('2d'), ds, true, y, m.indexOf('pct') > -1, pxOk));
  if (pxOk) { ixCharts.pos.options.scales.y1 = { position: 'right', grid: { drawOnChartArea: false }, ticks: { font: { size: 9 }, color: '#555' }, title: { display: true, text: 'Price', font: { size: 10, weight: 'bold' }, color: '#555' } }; ixCharts.pos.update('none'); }
  if (m.indexOf('usd') > -1) { ixCharts.pos.options.scales.y.ticks.callback = function (v) { return '$' + v.toFixed(1) + 'bn'; }; ixCharts.pos.update('none'); }
}
function ixDrawCmp() {
  if (!IX) return; var m = document.getElementById('ixCmpMet').value;
  if (ixCharts.cmp) ixCharts.cmp.destroy();
  var pick = function (L, S, N) { if (m === 'long') return L; if (m === 'short') return S; if (m === 'net_pct') return N.map(function (v, i) { return v == null || !(IX.oi[i] > 0) ? null : v / IX.oi[i] * 100; }); return N; };
  var ds = [ixDs('Index traders (CIT)', pick(IX.L, IX.S, IX.N), '#b7791f'), ixDs('Non-commercial ex-CIT', pick(IX.ncL, IX.ncS, IX.ncN), '#2a5298'),
            ixDs('Commercial ex-CIT', pick(IX.cmL, IX.cmS, IX.cmN), '#c0392b'), ixDs('Non-reportable', pick(IX.nrL, IX.nrS, IX.nrN), '#7f8c8d'),
            ixDs('Managed money (disaggregated)', pick(IX.mmL, IX.mmS, IX.mmN), '#8e44ad')];
  ds[4].borderDash = [5, 3];
  ixFinish('cmp', mkLine(document.getElementById('ixCmpChart').getContext('2d'), ds, true, m === 'net_pct' ? '% OI' : '', m === 'net_pct', true));
}
function ixDrawTrd() {
  if (!IX) return; var m = document.getElementById('ixTrdMet').value;
  if (ixCharts.trd) ixCharts.trd.destroy();
  var ds = m === 'long' ? [ixDs('Long', IX.tL, '#1a8c4e', true)] : m === 'short' ? [ixDs('Short', IX.tS, '#c0392b', true)] : [ixDs('Long', IX.tL, '#1a8c4e'), ixDs('Short', IX.tS, '#c0392b')];
  ixFinish('trd', mkLine(document.getElementById('ixTrdChart').getContext('2d'), ds, true, 'Traders', false, m === 'both'));
}
function ixDrawSz() {
  if (!IX) return; var m = document.getElementById('ixSzMet').value;
  if (ixCharts.sz) ixCharts.sz.destroy();
  var per = IX.L.map(function (v, i) { return IX.tL[i] > 0 ? v / IX.tL[i] : null; });
  var ds = m === 'per_trader_long' ? [ixDs('Long/Trader', per, '#1a8c4e', true)]
    : [ixDs('Long/Trader ($m)', per.map(function (v, i) { return v == null || IX.px[i] == null || !IX.mult ? null : v * IX.px[i] * IX.mult / 1e6; }), '#1a8c4e', true)];
  ixFinish('sz', mkLine(document.getElementById('ixSzChart').getContext('2d'), ds, true, m === 'per_trader_long' ? 'Contracts/Trader' : 'US$ m/Trader', false, false));
}
function ixBreadth(h) {
  if (!h || !h.dates) return;
  if (ixCharts.b) ixCharts.b.destroy();
  var ds = [{ label: 'Markets adding (%)', data: h.dates.map(function (d, i) { return { x: d, y: h.v[i] }; }), borderColor: '#2a5298', backgroundColor: '#2a529818', borderWidth: 2, pointRadius: 0, fill: true, tension: 0.4 }];
  ixCharts.b = mkLine(document.getElementById('ixBreadth').getContext('2d'), ds, true, '% of markets', true, false);
  ixCharts.b.options.scales.y.min = 0; ixCharts.b.options.scales.y.max = 100; ixCharts.b.update('none');
}
