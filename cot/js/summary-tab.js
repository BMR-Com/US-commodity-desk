/* ===========================================================
   SUMMARY TAB — Desk Brief, Positioning Monitor, league tables, range table
   All cross-market numbers come from the pre-computed weekly snapshot
   (data/web/snapshot.json, cached in the browser), so this tab renders
   instantly and makes no CFTC calls. Legacy live-API fallback kept for the
   case where the snapshot file is missing.
   =========================================================== */

var _deskA = null, _deskSort = { k: 'score', dir: -1 }, _snap = null;

function initSummaryTab() {
  generateSummary();
  document.querySelectorAll('#monTable th[data-k]').forEach(function (th) {
    th.onclick = function () {
      var k = th.getAttribute('data-k');
      if (k === 'spark' || k === 'read') return;
      _deskSort = { k: k, dir: (_deskSort.k === k ? -_deskSort.dir : (k === 'name' || k === 'drv' ? 1 : -1)) };
      document.querySelectorAll('#monTable th').forEach(function (h) { h.classList.remove('sorted', 'asc'); });
      th.classList.add('sorted'); if (_deskSort.dir > 0) th.classList.add('asc');
      renderMonitor();
    };
  });
}

/* Entry point (also called by other code). Idempotent and cache-backed. */
function generateSummary() {
  var sub = document.getElementById('briefSub');
  COTStore.snapshot().then(function (snap) {
    _snap = snap;
    try { renderDesk(); }
    catch (e) {  /* a rendering bug is NOT "data missing" — say what happened */
      console.error('[Summary] render error', e);
      if (sub) sub.innerHTML = '⚠ Could not render the summary (' + (e && e.message) + '). Try a hard refresh (Ctrl/Cmd+Shift+R).';
    }
  }, function (e) {
    console.warn('[Summary] snapshot unavailable, using live CFTC API:', e && e.message);
    if (sub) sub.textContent = 'Pre-computed data not reachable (' + (e && e.message) + ') — falling back to the live CFTC API (slower).';
    try { legacyGenerateSummary(); } catch (e2) { console.error(e2); showL(false); }
  });
}

function deskOpts() {
  var w = document.getElementById('dkWin'), c = document.getElementById('dkCrop');
  return { win: w ? w.value : 'y3', crop: c ? c.value : 'all' };
}

function renderDesk() {
  if (!_snap) return;
  var o = deskOpts();
  _deskA = COTInsights.analyze(_snap, o);
  var a = _deskA, W = COTInsights.WIN_LBL[o.win];
  var stale = (_snap.commodities || []).filter(function (c) { return c.stale; }).map(function (c) { return c.name; });
  document.getElementById('briefSub').innerHTML = 'CFTC Disaggregated F&amp;O combined · positions as of <b>' + fmtDate(a.date) + '</b> · look-back ' + W +
    (o.crop !== 'all' ? ' · ' + o.crop + '-crop view for grains/softs/hogs' : '') +
    (stale.length ? ' · left out (no recent CFTC data): ' + stale.join(', ') : '') +
    ' · not reported by CFTC: ' + BCOM_NOT_REPORTED.join(', ');

  /* narrative */
  document.getElementById('briefBody').innerHTML = COTInsights.brief(a).map(function (l) {
    return '<div class="bh">' + l.h + '</div><div>' + l.t + '</div>';
  }).join('');

  /* setup cards */
  function card(title, tone, rows, val) {
    var body = rows.length ? rows.map(function (r) {
      return '<div class="setup-item" onclick="openInCot(\'' + r.ticker + '\')" title="' + r.read.replace(/"/g, '&quot;') + '"><span>' + r.name + '</span><span class="sv">' + val(r) + '</span></div>';
    }).join('') : '<div class="empty">None this week</div>';
    return '<div class="setup-card ' + tone + '"><h4>' + title + '</h4>' + body + '</div>';
  }
  var sc = function (r) { return (r.score > 0 ? '+' : '') + r.score; };
  document.getElementById('setupCards').innerHTML =
    card('&#x2705; Contrarian long setups', 'bull', a.longSetups, sc) +
    card('&#x274C; Contrarian short setups', 'bear', a.shortSetups, sc) +
    card('&#x1F525; Short-squeeze fuel', 'warn', a.squeeze, function (r) { return 'shorts ' + COTInsights.ord(r.mm.p.S[a.win]) + ' pct'; }) +
    card('&#x26A0;&#xFE0F; Long-liquidation risk', 'warn', a.liqRisk, function (r) { return 'longs ' + COTInsights.ord(r.mm.p.L[a.win]) + ' pct'; });

  try { renderIdeas(); } catch (e) { console.error('[Ideas]', e); }
  try { renderSofts(); } catch (e) { console.error('[Softs]', e); }
  renderSectors();
  renderMonitor();
  renderLeagueAndRanges();
  /* AI tab reads scData for context when present */
  try { scData = COTInsights.scatterRows(_snap, 'f', 'all'); } catch (e) { }
}

function renderSectors() {
  var el = document.getElementById('secStrip'); if (!el || !_deskA) return;
  el.innerHTML = _deskA.sectors.slice().sort(function (x, y) { return y.cot - x.cot; }).map(function (s) {
    var c = s.cot, bg = c >= 75 ? 'rgba(192,57,43,.12)' : c <= 25 ? 'rgba(26,140,78,.12)' : '#f7f9fb';
    return '<div class="sec-card" style="background:' + bg + '" title="' + s.names.join(', ') + '"><div class="sn">' + s.sector + '</div>' +
      '<div class="sv">' + Math.round(c) + '</div><div class="sm">avg COT idx · ' + s.buy + '↑ ' + s.sell + '↓ · Δnet ' + (s.dnp >= 0 ? '+' : '') + s.dnp.toFixed(1) + ' pts OI</div></div>';
  }).join('');
}

function spark(arr, w, h) {
  w = w || 90; h = h || 22;
  var a = (arr || []).filter(function (v) { return v != null; }); if (a.length < 2) return '';
  var mn = Math.min.apply(null, a), mx = Math.max.apply(null, a), rg = (mx - mn) || 1;
  var pts = a.map(function (v, i) { return (i / (a.length - 1) * w).toFixed(1) + ',' + (h - (v - mn) / rg * (h - 2) - 1).toFixed(1); }).join(' ');
  var zero = (mn < 0 && mx > 0) ? '<line x1="0" x2="' + w + '" y1="' + (h - (0 - mn) / rg * (h - 2) - 1).toFixed(1) + '" y2="' + (h - (0 - mn) / rg * (h - 2) - 1).toFixed(1) + '" stroke="#bbb" stroke-dasharray="2,2"/>' : '';
  var last = a[a.length - 1], col = last >= 0 ? '#1a8c4e' : '#c0392b';
  return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' + zero + '<polyline fill="none" stroke="' + col + '" stroke-width="1.5" points="' + pts + '"/></svg>';
}

function renderMonitor() {
  var tb = document.getElementById('monBody'); if (!tb || !_deskA) return;
  var k = _deskSort.k, d = _deskSort.dir;
  var pxBy = {}; (_snap.commodities || []).forEach(function (c) { pxBy[c.ticker] = c.px; });
  var val = function (r) {
    if (k === 'px4w') { var p0 = pxBy[r.ticker]; return p0 && p0.r4w != null ? p0.r4w : -1e9; }
    switch (k) {
      case 'name': return r.name; case 'drv': return r.drv.main; case 'N': return r.mm.N; case 'dN': return r.mm.dN;
      default: return r[k] == null ? -1e9 : r[k];
    }
  };
  var rows = _deskA.rows.slice().sort(function (a, b) { var x = val(a), y = val(b); return typeof x === 'string' ? d * x.localeCompare(y) : d * (x - y); });
  var K = COTInsights.k, SK = COTInsights.sk, ORD = COTInsights.ord;
  tb.innerHTML = rows.map(function (r) {
    var f = '';
    r.flags.forEach(function (fl) { f += fl.key === 'squeeze' ? '<span class="flag" title="' + fl.txt + '">&#x1F525;</span>' : fl.key === 'liq' ? '<span class="flag" title="' + fl.txt + '">&#x26A0;&#xFE0F;</span>' : fl.key === 'fast' ? '<span class="flag" title="' + fl.txt + '">&#x23E9;</span>' : ''; });
    if (r.comm) f += '<span class="flag" title="' + r.comm.txt + '">&#x2195;&#xFE0F;</span>';
    var sw = Math.abs(r.score) / 2, sl = r.score >= 0 ? 50 : 50 - sw, scol = r.score >= 0 ? '#1a8c4e' : '#c0392b';
    return '<tr>' +
      '<td><span class="mk" onclick="openInCot(\'' + r.ticker + '\')">' + r.name + '</span><span class="tk">' + r.ticker + (r.crop !== 'all' ? ' · ' + r.crop : '') + '</span> ' + f + '</td>' +
      (function () { var p0 = pxBy[r.ticker]; if (!p0 || p0.r4w == null) return '<td class="num">–</td>'; return '<td class="num ' + (p0.r4w >= 0 ? 'pos' : 'neg') + '" title="last ' + COTInsights.pxf(p0.close) + ' · 12m ' + COTInsights.pctf(p0.r52w) + '">' + COTInsights.pctf(p0.r4w) + '</td>'; })() +
      '<td><span class="badge b-' + r.reg.tone + '">' + r.reg.lbl + '</span></td>' +
      '<td class="num ' + (r.mm.N >= 0 ? 'pos' : 'neg') + '">' + K(r.mm.N) + '</td>' +
      '<td class="num ' + (r.mm.dN >= 0 ? 'pos' : 'neg') + '">' + SK(r.mm.dN) + '</td>' +
      '<td class="num ' + (r.z >= 0 ? 'pos' : 'neg') + '" title="' + r.size + '">' + (r.z >= 0 ? '+' : '−') + Math.abs(r.z).toFixed(1) + '</td>' +
      '<td title="' + r.drv.detail + '">' + r.drv.main + (Math.abs(r.mm.streak) >= 3 ? ' <small>(' + Math.abs(r.mm.streak) + 'w)</small>' : '') + '</td>' +
      '<td>' + spark(r.mm.spark) + '</td>' +
      '<td class="num"><span class="cotbar"><i style="left:' + Math.max(0, Math.min(100, r.cot)) + '%"></i></span>' + Math.round(r.cot) + '</td>' +
      '<td class="num">' + ORD(r.pN) + '</td>' +
      '<td class="num">' + (r.pmP == null ? '–' : ORD(r.pmP)) + '</td>' +
      '<td class="num"><span class="scorebar"><b style="left:' + sl + '%;width:' + sw + '%;background:' + scol + '"></b></span>' + (r.score > 0 ? '+' : '') + r.score + '</td>' +
      '<td class="read">' + r.read + '</td></tr>';
  }).join('');
}

/* League tables (exec) + range table, from the same snapshot */
function renderLeagueAndRanges() {
  var o = deskOpts(), w = o.win;
  var ex = COTInsights.scatterRows(_snap, w, o.crop);
  document.getElementById('execSec').style.display = 'block';
  fillPctTables('', ex);
  var t = document.querySelector('#execSec .exec-title');
  if (t) t.innerHTML = '&#x1F4CA; Percentile League Tables — Managed Money (' + COTInsights.WIN_LBL[w] + ')';

  document.getElementById('sumSec').style.display = 'block';
  sumData = snapToSumRows(_snap, o.crop);
  renderSum('sumBody', sumData);
}

/* Range-table rows (Net / Net%OI / Long / Long%OI / Short / Short%OI, full history) */
function snapToSumRows(snap, crop) {
  var out = [];
  (snap.commodities || []).forEach(function (cm) {
    if (cm.stale) return;
    var v = (crop && crop !== 'all' && cm.v[crop]) ? cm.v[crop] : cm.v.all; if (!v) return;
    var nm = cm.name + (crop && crop !== 'all' && cm.v[crop] ? ' (' + crop + ')' : '');
    CATS.forEach(function (cat) {
      var c = v.cats[cat]; if (!c) return;
      out.push({ comm: nm, cat: CAT_LBL[cat], catKey: cat, sec: cm.sector,
        net: c.N, netMn: c.r.N[0], netMx: c.r.N[1], nPct: c.np, nPctMn: c.r.np[0], nPctMx: c.r.np[1],
        lon: c.L, lonMn: c.r.L[0], lonMx: c.r.L[1], lPct: c.lp, lPctMn: c.r.lp[0], lPctMx: c.r.lp[1],
        sho: c.S, shoMn: c.r.S[0], shoMx: c.r.S[1], sPct: c.sp, sPctMn: c.r.sp[0], sPctMx: c.r.sp[1] });
    });
  });
  return out;
}

/* Kept for compatibility (scatter-tab used to call this to fill the exec section) */
function popExec(data) { document.getElementById('execSec').style.display = 'block'; fillPctTables('', data); }

/* Jump from Summary to the full COT Analyzer for one market */
function openInCot(ticker) {
  var it = allBCOM.filter(function (b) { return b.ticker === ticker; })[0]; if (!it) return;
  window._autoLoaded = true; try { _autoLoaded = true; } catch (e) { }
  switchTab('cot');
  var go = function () {
    var sel = document.getElementById('commoditySelect'); if (!sel) return setTimeout(go, 100);
    sel.value = it.api; if (typeof onCommChange === 'function') onCommChange();
    fetchData(); window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  go();
}

/* Plain-text brief for pasting into notes / client emails */
function copyBrief() {
  if (!_deskA) return;
  var a = _deskA, txt = 'COT DESK BRIEF — positions as of ' + a.date + ' (look-back ' + COTInsights.WIN_LBL[a.win] + ')\n\n';
  COTInsights.brief(a).forEach(function (l) { txt += l.h.toUpperCase() + ': ' + l.t + '\n\n'; });
  txt += 'MARKET READS\n';
  a.rows.slice().sort(function (x, y) { return y.score - x.score; }).forEach(function (r) { txt += '• ' + r.name + ' [' + (r.score > 0 ? '+' : '') + r.score + ']: ' + r.read + '\n'; });
  if (_ideas && _ideas.ideas.length) { txt += '\nTRADE IDEAS\n'; _ideas.ideas.forEach(function (i) { txt += '• ' + i.side + ' ' + i.row.name + ' [' + i.conv + ', ' + i.kind + '] ref ' + COTInsights.pxf(i.lv.entry) + ', stop ' + COTInsights.pxf(i.lv.stop) + ', target ' + COTInsights.pxf(i.lv.target) + ' — ' + i.why[1] + '\n'; }); }
  txt += '\nSource: CFTC Disaggregated COT, futures & options combined. Positioning read, not a price forecast.';
  var done = function () { var b = document.getElementById('copyBriefBtn'); if (b) { var t = b.innerHTML; b.innerHTML = '✓ Copied'; setTimeout(function () { b.innerHTML = t; }, 1500); } };
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(txt).then(done, function () { fallbackCopy(txt); done(); });
  else { fallbackCopy(txt); done(); }
}
function fallbackCopy(t) { var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) { } ta.remove(); }

/* ===========================================================
   LEGACY FALLBACK — live CFTC API (only if the snapshot is missing).
   One request per commodity (was one per commodity × category = 4× more).
   =========================================================== */
function legacyGenerateSummary() {
  showL(true, 'Generating summary (live CFTC)...'); document.getElementById('sumSec').style.display = 'block'; sumData = [];
  var ep = EP[document.getElementById('reportType') ? document.getElementById('reportType').value : 'combined'] || EP.combined;
  var list = liveBCOM(), done = 0; if (!list.length) { showL(false); return; }
  list.forEach(function (it) {
    fetchT(ep + "?$where=" + liveWhere(it.api) + " AND report_date_as_yyyy_mm_dd >= '2006-01-01'&$order=report_date_as_yyyy_mm_dd ASC&$limit=10000", 25000)
      .then(function (r) { return r.json(); }).then(function (data) {
        if (!data.length) return;
        CATS.forEach(function (cat) {
          var p = procData(data, cat); if (!p) return; var l = p.net.length - 1;
          var mn = function (a) { return Math.min.apply(null, a); }, mx = function (a) { return Math.max.apply(null, a); };
          sumData.push({ comm: it.name, cat: CAT_LBL[cat], catKey: cat, sec: it.sector, net: p.net[l], netMn: mn(p.net), netMx: mx(p.net), nPct: p.nPct[l], nPctMn: mn(p.nPct), nPctMx: mx(p.nPct), lon: p.long[l], lonMn: mn(p.long), lonMx: mx(p.long), lPct: p.lPct[l], lPctMn: mn(p.lPct), lPctMx: mx(p.lPct), sho: p.short[l], shoMn: mn(p.short), shoMx: mx(p.short), sPct: p.sPct[l], sPctMn: mn(p.sPct), sPctMx: mx(p.sPct) });
        });
      }).catch(function () { }).finally(function () { done++; if (done >= list.length) { renderSum('sumBody', sumData); showL(false); } });
  });
}


/* ===========================================================
   TRADE IDEAS (trend × carry × positioning × technicals)
   =========================================================== */
var _ideas = null;
function renderIdeas() {
  var sec = document.getElementById('ideasSec'); if (!sec || !_snap || !_deskA) return;
  var hasPx = (_snap.commodities || []).some(function (c) { return c.px; });
  if (!hasPx) {
    document.getElementById('ideasSub').textContent = 'Price data not loaded yet — it is downloaded by the Weekly COT Data Update workflow.';
    return;
  }
  var I = _ideas = COTInsights.ideas(_snap, _deskA), P = COTInsights.pctf, X = COTInsights.pxf;
  document.getElementById('ideasSub').innerHTML = 'Prices updated ' + (I.pricesAt || '?') + ' · COT as of <b>' + fmtDate(_snap.report_date) + '</b> · ' + I.ideas.length + ' active ideas, ' + I.watch.length + ' on watch, ' + I.flat.length + ' flat';
  var g = I.regime || {};
  document.getElementById('regimeBar').innerHTML = g.spx ?
    '<span class="' + (I.riskOff ? 'off' : 'on') + '">' + (I.riskOff ? 'RISK-OFF: sizes halved' : 'Risk regime: normal') + '</span>' +
    '<span>S&amp;P 500 ' + g.spx.toLocaleString() + ' (' + (g.spx_above_200d ? 'above' : 'below') + ' 200d ' + Math.round(g.spx_200d).toLocaleString() + ')</span><span>VIX ' + g.vix + '</span>' : '';

  function card(i) {
    var r = i.row, l = i.lv, cls = i.dir > 0 ? 'long' : 'short';
    return '<div class="idea ' + cls + '"><div class="idea-h"><div><span class="idea-t" onclick="openInCot(\'' + r.ticker + '\')"><span class="idea-side">' + i.side + '</span>' + r.name + ' <small style="color:#888;font-weight:400">' + r.ticker + '</small></span><div class="idea-k">' + i.kind + (i.riskShare != null && i.conv !== 'Watch' ? ' · ' + Math.round(i.riskShare * 100) + '% of risk budget' : '') + '</div></div><span class="conv conv-' + i.conv + '">' + i.conv + '</span></div>' +
      '<div class="lvls"><div><span>Ref' + (r.px.contract ? ' ' + r.px.contract : '') + '</span><b>' + X(l.entry) + '</b></div><div><span>Stop (2×ATR)</span><b>' + X(l.stop) + '</b><span>' + P(l.stopPct) + '</span></div><div><span>Target (2R)</span><b>' + X(l.target) + '</b><span>' + P(l.tgtPct) + '</span></div><div><span>Size</span><b>' + (r.size >= 1 ? 'Full' : r.size >= 0.5 ? 'Half' : r.size > 0 ? Math.round(r.size * 100) + '%' : '—') + '</b><span>vol ' + (r.vol ? Math.round(r.vol * 100) + '%' : '–') + '</span></div></div>' +
      '<ul>' + i.why.map(function (w) { return '<li>' + w + '</li>'; }).join('') + '</ul><div class="tm">' + i.timing + '</div>' +
      (r.px.note ? '<div class="mon-note" style="margin-top:6px">Note: ' + r.px.note + '</div>' : '') + '</div>';
  }
  document.getElementById('ideaCards').innerHTML = I.ideas.length ? I.ideas.map(card).join('') : '<div class="empty">No market currently passes the rules.</div>';
  document.getElementById('watchCards').innerHTML = I.watch.length ? I.watch.map(card).join('') : '<div class="empty">None this week.</div>';

  var tr = function (t) { return t === 1 ? '<span class="pos">▲ up</span>' : t === 0.5 ? '<span class="pos">△ up (partial)</span>' : t === -1 ? '<span class="neg">▼ down</span>' : t === -0.5 ? '<span class="neg">▽ down (partial)</span>' : '<span style="color:#888">— none</span>'; };
  var cl = function (x) { return x == null ? '' : x >= 0 ? 'pos' : 'neg'; };
  document.getElementById('boardBody').innerHTML = I.board.slice().sort(function (a, b) { return b.size * b.dir - a.size * a.dir || b.trend - a.trend; }).map(function (r) {
    var p = r.px, v200 = p.vs200, rng = p.rng52;
    return '<tr><td><span class="mk" onclick="openInCot(\'' + r.ticker + '\')">' + r.name + '</span><span class="tk">' + r.ticker + '</span></td>' +
      '<td class="num" title="' + (p.contract || 'continuous front') + '">' + X(p.close) + (p.contract ? ' <small style="color:#888">' + p.contract + '</small>' : '') + '</td><td class="num ' + cl(p.r1w) + '">' + P(p.r1w) + '</td><td class="num ' + cl(p.r4w) + '">' + P(p.r4w) + '</td><td class="num ' + cl(p.r26w) + '">' + P(p.r26w) + '</td><td class="num ' + cl(p.r52w) + '">' + P(p.r52w) + '</td>' +
      '<td class="num ' + cl(v200) + '">' + P(v200) + '</td><td class="num">' + (p.rsi == null ? '–' : p.rsi.toFixed(0)) + '</td><td>' + tr(r.trend) + '</td>' +
      '<td class="num ' + (r.px.carry && r.px.carry.seasonal ? '' : cl(r.carry)) + '" title="' + r.cTxt + '">' + (r.carry == null ? '–' : P(r.carry)) + (r.px.carry && r.px.carry.seasonal ? '*' : '') + '</td>' +
      '<td>' + r.rule + '</td><td class="num">' + Math.round(r.cot) + '</td><td class="num">' + (r.vol ? Math.round(r.vol * 100) + '%' : '–') + '</td>' +
      '<td class="num">' + (r.size > 0 ? (r.dir > 0 ? '<span class="pos">L ' : '<span class="neg">S ') + Math.round(r.size * 100) + '%</span>' : '–') + '</td>' +
      '<td class="num" title="position in 52-week range">' + (rng == null ? '–' : '<span class="cotbar" style="background:linear-gradient(90deg,#e9ecef,#cfd8e6)"><i style="left:' + rng.toFixed(0) + '%"></i></span>' + rng.toFixed(0) + '%') + '</td></tr>';
  }).join('');
}


/* ===========================================================
   SOFTS FOCUS — cocoa, coffee, sugar, cotton side by side
   =========================================================== */
var SOFTS = ['CT', 'KC', 'CC', 'SB'];
function renderSofts() {
  var el = document.getElementById('softCards'); if (!el || !_snap || !_deskA) return;
  var rows = {}; _deskA.rows.forEach(function (r) { rows[r.ticker] = r; });
  var ideaBy = {}; if (_ideas) { _ideas.ideas.forEach(function (i) { ideaBy[i.row.ticker] = i; }); _ideas.watch.forEach(function (i) { ideaBy[i.row.ticker] = i; }); }
  var snapBy = {}; (_snap.commodities || []).forEach(function (c) { snapBy[c.ticker] = c; });
  var K = COTInsights.k, SK = COTInsights.sk, P = COTInsights.pctf, X = COTInsights.pxf, W = _deskA.win;
  el.innerHTML = SOFTS.map(function (tk) {
    var r = rows[tk], cm = snapBy[tk]; if (!r || !cm) return '';
    var px = cm.px || {}, i = ideaBy[tk];
    var crop = '';
    ['old', 'other'].forEach(function (ct) {
      var v = cm.v[ct]; if (!v || !v.cats || !v.cats.managed_money) return;
      var mm = v.cats.managed_money, ci = COTInsights.cotIdx(mm, W);
      crop += '<div><span>' + (ct === 'old' ? 'Old crop' : 'New crop') + '</span><b>' + K(mm.N) + '</b><span>COT idx ' + Math.round(ci) + '</span></div>';
    });
    if (!crop) crop = '<div style="grid-column:span 2"><span>Crop-year split</span><b>n/a</b><span>not reported for ' + cm.name + '</span></div>';
    var tr = px.trend > 0 ? '<span class="pos">▲ uptrend' + (px.trend < 1 ? ' (partial)' : '') + '</span>' : px.trend < 0 ? '<span class="neg">▼ downtrend' + (px.trend > -1 ? ' (partial)' : '') + '</span>' : '<span style="color:#888">no trend</span>';
    var idea = i ? '<span class="conv conv-' + i.conv + '">' + i.side + ' · ' + i.conv + '</span>' : '<span class="conv conv-Low">No trade</span>';
    return '<div class="soft"><div class="soft-h"><div><span class="idea-t" onclick="openInCot(\'' + tk + '\')">' + cm.name + '</span> <small style="color:#888">' + (px.contract || tk) + ' ' + X(px.close) + ' <span class="' + ((px.r4w || 0) >= 0 ? 'pos' : 'neg') + '">' + P(px.r4w) + ' 4w</span></small></div>' + idea + '</div>' +
      '<div class="soft-row"><span class="badge b-' + r.reg.tone + '">' + r.reg.lbl + '</span> ' + tr + '</div>' +
      '<div class="lvls"><div><span>MM net</span><b>' + K(r.mm.N) + '</b><span class="' + (r.mm.dN >= 0 ? 'pos' : 'neg') + '">' + SK(r.mm.dN) + ' w/w</span></div><div><span>COT idx</span><b>' + Math.round(r.cot) + '</b><span>' + COTInsights.WIN_LBL[W] + '</span></div>' + crop + '</div>' +
      '<div class="soft-row" style="justify-content:space-between">' + spark(r.mm.spark, 150, 26) + '<small>P/M ' + (r.pmP == null ? '–' : COTInsights.ord(r.pmP)) + ' pct · flow ' + (r.z >= 0 ? '+' : '−') + Math.abs(r.z).toFixed(1) + 'σ</small></div>' +
      '<div class="soft-read">' + r.read + '</div></div>';
  }).join('');
}
