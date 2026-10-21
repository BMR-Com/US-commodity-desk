/* ===========================================================
   TRIGGERS & FLOWS TAB — trigger levels, managed-money dollar exposure,
   positioning heatmap. All from data/web/snapshot.json (no CFTC calls).
   =========================================================== */
var LV = null, LV_SEC = ['Energy', 'Grains', 'Industrial Metals', 'Precious Metals', 'Softs', 'Livestock'];
function lvUsd(v, sign) { if (v == null) return '–'; var x = Math.abs(v), s = v < 0 ? '−' : (sign ? '+' : ''); return s + '$' + (x >= 1e9 ? (x / 1e9).toFixed(2) + 'bn' : x >= 1e6 ? (x / 1e6).toFixed(0) + 'm' : (x / 1e3).toFixed(0) + 'k'); }
function lvC(v) { return v == null ? '' : v > 0 ? 'lv-pos' : v < 0 ? 'lv-neg' : ''; }
function lvPx(v) { if (v == null) return '–'; var a = Math.abs(v); return v.toLocaleString(undefined, { maximumFractionDigits: a >= 1000 ? 0 : a >= 100 ? 2 : a >= 10 ? 2 : 4 }); }
function lvChip(s) { return s === 1 ? '<span class="lv-chip lv-up">▲</span>' : s === -1 ? '<span class="lv-chip lv-dn">▼</span>' : '<span class="lv-chip lv-na">–</span>'; }

function initLevelsTab() {
  COTStore.snapshot().then(function (snap) {
    LV = snap;
    var secs = {}; (snap.commodities || []).forEach(function (c) { secs[c.sector] = 1; });
    document.getElementById('lvSec').innerHTML = '<option value="">All</option>' + LV_SEC.filter(function (s) { return secs[s]; }).map(function (s) { return '<option>' + s + '</option>'; }).join('');
    lvTrig(); lvMM(); lvHeat();
  });
}

function lvTrig() {
  var sec = document.getElementById('lvSec').value, sort = document.getElementById('lvSort').value;
  var rows = (LV.commodities || []).filter(function (c) { return c.trig && c.px_ok && (!sec || c.sector === sec); });
  var near = function (c) { var a = c.trig.next_dn ? Math.abs(c.trig.next_dn.atr) : 99, b = c.trig.next_up ? Math.abs(c.trig.next_up.atr) : 99; return Math.min(a, b); };
  var fp = function (c) { var m = (((c.v || {}).all || {}).cats || {}).managed_money; return m && m.p && m.p.N ? m.p.N.y3 : null; };
  rows.sort(sort === 'near' ? function (a, b) { return near(a) - near(b); } : sort === 'pct' ? function (a, b) { return (fp(b) || 0) - (fp(a) || 0); } :
    function (a, b) { return LV_SEC.indexOf(a.sector) - LV_SEC.indexOf(b.sector); });
  var st = function (t, k) { for (var i = 0; i < t.lv.length; i++) if (t.lv[i].k === k) return t.lv[i]; return {}; };
  document.getElementById('lvBody').innerHTML = rows.map(function (c) {
    var t = c.trig, p = fp(c), d55 = st(t, 'd55');
    var nx = function (x) { return x ? '<td class="n">' + lvPx(x.lvl) + '<br><span style="font-size:.85em;color:#666;">' + x.name + '</span></td><td class="n ' + (x.pct < 0 ? 'lv-neg' : 'lv-pos') + '">' + (x.pct * 100).toFixed(1) + '%<br><span style="font-size:.85em;color:#666;">' + Math.abs(x.atr).toFixed(1) + ' ATR</span></td>' : '<td class="n">–</td><td class="n">–</td>'; };
    return '<tr' + (near(c) <= 1 ? ' class="lv-near"' : '') + '><td class="mk" onclick="openMarket(\'' + c.ticker + '\')">' + c.name + ' <span style="color:#888;font-weight:400;">' + c.ticker + '</span></td>' +
      '<td>' + (t.src || '') + '</td><td class="n">' + lvPx(t.close) + '</td><td class="n">' + (p != null ? COTInsights.ord(p) : '–') + '</td>' +
      ['d20', 'd55', 'd100', 's50', 's100', 's200'].map(function (k) { return '<td style="text-align:center;">' + lvChip(st(t, k).state) + '</td>'; }).join('') +
      '<td style="text-align:center;">' + lvChip(t.macd) + '</td>' + nx(t.next_dn) + nx(t.next_up) +
      '<td class="n">' + lvPx(d55.dn) + ' – ' + lvPx(d55.up) + '</td></tr>';
  }).join('') || '<tr><td colspan="16" style="text-align:center;color:#999;">No current prices available.</td></tr>';
}

function lvMM() {
  var m = LV.mm_usd; if (!m) { document.getElementById('mmBody').innerHTML = '<tr><td colspan="8">No price data this week.</td></tr>'; return; }
  var row = function (cls, nm, x, tk) {
    return '<tr class="' + cls + '"><td class="' + (tk ? 'mk' : '') + '"' + (tk ? ' onclick="openMarket(\'' + tk + '\')"' : '') + '>' + nm + '</td><td class="n">' + COTInsights.k(x.N) + '</td><td class="n ' + lvC(x.dN) + '">' + COTInsights.sk(x.dN) + '</td>' +
      '<td class="n">' + lvUsd(x.Nusd) + '</td><td class="n ' + lvC(x.dNusd) + '">' + lvUsd(x.dNusd, true) + '</td><td class="n ' + lvC(x.dN4usd) + '">' + lvUsd(x.dN4usd, true) + '</td>' +
      '<td class="n">' + lvUsd(x.Lusd) + '</td><td class="n">' + lvUsd(x.Susd) + '</td></tr>';
  };
  var h = '';
  LV_SEC.forEach(function (s) {
    var ms = m.markets.filter(function (x) { return x.sector === s; }).sort(function (a, b) { return Math.abs(b.Nusd || 0) - Math.abs(a.Nusd || 0); });
    if (!ms.length) return;
    h += row('sec', s, m.sectors[s]);
    ms.forEach(function (x) { h += row('', '&nbsp;&nbsp;' + x.name, x, x.ticker); });
  });
  h += row('tot', 'All markets', m.total);
  document.getElementById('mmBody').innerHTML = h;
}

function lvHeat() {
  var H = LV.heat; if (!H || !H.dates) return;
  var col = function (v) { if (v == null) return '#f4f6f8'; var a = Math.abs(v - 50) / 50; return v >= 50 ? 'rgba(26,140,78,' + (0.08 + 0.75 * a).toFixed(2) + ')' : 'rgba(192,57,43,' + (0.08 + 0.75 * a).toFixed(2) + ')'; };
  var hd = '<tr><th></th>' + H.dates.map(function (d, i) { return '<th>' + (i % 4 === 0 || i === H.dates.length - 1 ? d.slice(5).replace('-', '/') : '') + '</th>'; }).join('') + '</tr>';
  var h = '';
  LV_SEC.forEach(function (s) {
    var rs = H.rows.filter(function (r) { return r.sector === s; }); if (!rs.length) return;
    h += '<tr class="sec"><td colspan="' + (H.dates.length + 1) + '">' + s + '</td></tr>';
    rs.forEach(function (r) {
      h += '<tr><td class="nm" onclick="openMarket(\'' + r.ticker + '\')">' + r.name + '</td>' + r.v.map(function (v, i) {
        return '<td style="background:' + col(v) + ';' + (v != null && Math.abs(v - 50) > 35 ? 'color:#fff;' : '') + '" title="' + r.name + ' ' + H.dates[i] + ': ' + (v == null ? 'n/a' : v.toFixed(0) + 'th pct') + '">' + (i === r.v.length - 1 && v != null ? v.toFixed(0) : '') + '</td>';
      }).join('') + '</tr>';
    });
  });
  document.getElementById('hmTbl').innerHTML = hd + h;
}
