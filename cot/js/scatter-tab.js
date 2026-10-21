/* ===========================================================
   SCATTER TAB — Prod/Merch vs Managed Money positioning percentiles
   Rendered from the pre-computed weekly snapshot (no CFTC calls).
   =========================================================== */

function initScatterTab() {
  doScatter();
  doScatterPct();
}

function scOpts() {
  var w = document.getElementById('scWin'), c = document.getElementById('scCrop');
  return { win: w ? w.value : 'f', crop: c ? c.value : 'all' };
}

function doScatter() {
  document.getElementById('chart6').style.display = 'block';
  var o = scOpts();
  COTStore.snapshot().then(function (snap) {
    scData = COTInsights.scatterRows(snap, o.win, o.crop);
    var combos = [
      { c: 'sc1', x: 'pSP', y: 'mSP', xl: 'Prod Short', yl: 'MM Short', xv: 'pS', yv: 'mS' },
      { c: 'sc2', x: 'pSP', y: 'mLP', xl: 'Prod Short', yl: 'MM Long', xv: 'pS', yv: 'mL' },
      { c: 'sc3', x: 'pLP', y: 'mSP', xl: 'Prod Long', yl: 'MM Short', xv: 'pL', yv: 'mS' },
      { c: 'sc4', x: 'pLP', y: 'mLP', xl: 'Prod Long', yl: 'MM Long', xv: 'pL', yv: 'mL' },
      { c: 'sc5', x: 'pNP', y: 'mNP', xl: 'Prod Net', yl: 'MM Net', xv: 'pN', yv: 'mN' },
      /* crowded-and-still-adding (top-right) vs crowded-and-exiting (bottom-right) */
      { c: 'sc6', x: 'mNP', y: 'mZ', xl: 'MM Net', yl: 'MM weekly flow', xv: 'mN', yv: 'mDN', yMin: -3, yMax: 3, ySigma: true }
    ];
    drawScatter('sc', scData, combos);
    drawLeg('scLeg', scData);
  }).catch(function (e) { legacyScatter(); });
}

function doScatterPct() {
  document.getElementById('chart7').style.display = 'block';
  var o = scOpts();
  COTStore.snapshot().then(function (snap) {
    spData = COTInsights.scatterRows(snap, o.win, o.crop);
    var combos = [
      { c: 'sp1', x: 'pSPo', y: 'mSPo', xl: 'Prod S%', yl: 'MM S%', xv: 'pSo', yv: 'mSo', pct: true },
      { c: 'sp2', x: 'pSPo', y: 'mLPo', xl: 'Prod S%', yl: 'MM L%', xv: 'pSo', yv: 'mLo', pct: true },
      { c: 'sp3', x: 'pLPo', y: 'mSPo', xl: 'Prod L%', yl: 'MM S%', xv: 'pLo', yv: 'mSo', pct: true },
      { c: 'sp4', x: 'pLPo', y: 'mLPo', xl: 'Prod L%', yl: 'MM L%', xv: 'pLo', yv: 'mLo', pct: true },
      { c: 'sp5', x: 'pNPo', y: 'mNPo', xl: 'Prod N%', yl: 'MM N%', xv: 'pNo', yv: 'mNo', pct: true },
      { c: 'sp6', x: 'mLPo', y: 'mSPo', xl: 'MM L%', yl: 'MM S%', xv: 'mLo', yv: 'mSo', pct: true }
    ];
    drawScatter('sp', spData, combos);
    drawLeg('spLeg', spData);
  }).catch(function () { /* legacyScatter() fills both */ });
}

/* Point styles cycling through distinct shapes */
var PS = ['circle', 'rect', 'triangle', 'star', 'cross', 'rectRot', 'rectRounded', 'crossRot'];
/* Distinct color palette covering all BCOM commodities */
var UC = ['#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#42d4f4', '#f032e6', '#9A6324', '#000075', '#469990', '#2c3e50', '#1abc9c', '#d35400', '#c0392b', '#2ecc71', '#8e44ad', '#16a085', '#e8a838', '#a9a9a9', '#dcbeff', '#aaffc3', '#800000', '#808000', '#bfef45'];

/* Draw the ticker next to each point so the chart reads without the legend */
var tickerLabelPlugin = {
  id: 'tickerLabels',
  afterDatasetsDraw: function (chart) {
    var ctx = chart.ctx; ctx.save(); ctx.font = '600 9px Segoe UI, sans-serif'; ctx.fillStyle = '#333'; ctx.textBaseline = 'middle';
    chart.data.datasets.forEach(function (ds, i) {
      if (!ds._tk) return; var meta = chart.getDatasetMeta(i); if (meta.hidden) return;
      var pt = meta.data[0]; if (!pt) return; ctx.fillText(ds._tk, pt.x + 8, pt.y);
    });
    ctx.restore();
  }
};

function fmtV(v, pct) { if (v == null) return '–'; return pct ? v.toFixed(1) + '% OI' : COTInsights.k(v); }

function drawScatter(pfx, data, combos) {
  combos.forEach(function (c, idx) {
    var el = document.getElementById(c.c); if (!el) return;
    var ctx = el.getContext('2d'), ck = pfx + (idx + 1); if (charts[ck]) charts[ck].destroy();
    var ds = data.filter(function (it) { return it[c.x] != null && it[c.y] != null; }).map(function (it) {
      var col = UC[it.idx % UC.length], ps = PS[it.idx % PS.length];
      var y = it[c.y]; if (c.yMin != null) y = Math.max(c.yMin, Math.min(c.yMax, y));
      return { label: it.comm, _tk: it.ticker, data: [{ x: it[c.x], y: y, comm: it.comm, xv: it[c.xv], yv: it[c.yv], yRaw: it[c.y] }],
        backgroundColor: col, borderColor: col, pointStyle: ps, pointRadius: 6, pointHoverRadius: 10, borderWidth: 1.5 };
    });
    var yMid = c.ySigma ? 0 : 50, yMin = c.yMin != null ? c.yMin : 0, yMax = c.yMax != null ? c.yMax : 100;
    ds.push({ data: [{ x: 50, y: yMin }, { x: 50, y: yMax }], borderColor: 'rgba(0,0,0,0.2)', borderDash: [4, 4], pointRadius: 0, fill: false, showLine: true, label: '_q1' });
    ds.push({ data: [{ x: 0, y: yMid }, { x: 100, y: yMid }], borderColor: 'rgba(0,0,0,0.2)', borderDash: [4, 4], pointRadius: 0, fill: false, showLine: true, label: '_q2' });
    charts[ck] = new Chart(ctx, {
      type: 'scatter', data: { datasets: ds }, plugins: [tickerLabelPlugin],
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            filter: function (i) { return i.dataset.label.charAt(0) !== '_'; },
            callbacks: {
              title: function (i) { return i[0].raw.comm; },
              label: function (i) {
                var r = i.raw;
                var yl = c.ySigma ? c.yl + ': ' + (r.yRaw >= 0 ? '+' : '') + r.yRaw.toFixed(2) + 'σ (' + COTInsights.sk(r.yv) + ')' : c.yl + ': ' + r.y.toFixed(1) + ' %ile (' + fmtV(r.yv, c.pct) + ')';
                return [c.xl + ': ' + r.x.toFixed(1) + ' %ile (' + fmtV(r.xv, c.pct) + ')', yl];
              }
            }
          }
        },
        scales: {
          x: { min: 0, max: 100, title: { display: true, text: c.xl + ' %ile', font: { size: 8 }, color: '#333' }, ticks: { font: { size: 7 }, color: '#333', maxTicksLimit: 6 } },
          y: { min: yMin, max: yMax, title: { display: true, text: c.ySigma ? c.yl + ' (σ, capped ±3)' : c.yl + ' %ile', font: { size: 8 }, color: '#333' }, ticks: { font: { size: 7 }, color: '#333', maxTicksLimit: 7 } }
        }
      }
    });
  });
}

function drawLeg(id, data) {
  var ct = document.getElementById(id); if (!ct) return; ct.innerHTML = '';
  data.forEach(function (d) {
    var e = document.createElement('div'); e.className = 'comm-legend-item';
    e.innerHTML = '<div style="background:' + UC[d.idx % UC.length] + ';width:11px;height:11px;border-radius:2px;"></div><span>' + d.comm + ' (' + d.ticker + ')</span>';
    ct.appendChild(e);
  });
}

/* ===========================================================
   LEGACY FALLBACK — live CFTC API if the snapshot is missing.
   One fetch per market feeds BOTH scatter sections (was 2× fetches).
   =========================================================== */
function legacyScatter() {
  showL(true, 'Generating scatter (live CFTC)...');
  var list = liveBCOM(), done = 0; scData = []; spData = [];
  if (!list.length) { showL(false); return; }
  list.forEach(function (it, idx) {
    fetchT(EP.combined + "?$where=" + liveWhere(it.api) + " AND report_date_as_yyyy_mm_dd >= '2006-01-01'&$order=report_date_as_yyyy_mm_dd ASC&$limit=10000", 25000)
      .then(function (r) { return r.json(); }).then(function (data) {
        if (data.length < 10) return; var pr = procData(data, 'prod_merc'), mm = procData(data, 'managed_money'); if (!pr || !mm) return;
        var l = pr.net.length - 1;
        var row = { comm: it.name, ticker: it.ticker, idx: idx,
          pSP: pct(pr.short, pr.short[l]), mSP: pct(mm.short, mm.short[l]), mLP: pct(mm.long, mm.long[l]), pLP: pct(pr.long, pr.long[l]), pNP: pct(pr.net, pr.net[l]), mNP: pct(mm.net, mm.net[l]),
          pS: pr.short[l], mS: mm.short[l], pL: pr.long[l], mL: mm.long[l], pN: pr.net[l], mN: mm.net[l],
          pSPo: pct(pr.sPct, pr.sPct[l]), mSPo: pct(mm.sPct, mm.sPct[l]), mLPo: pct(mm.lPct, mm.lPct[l]), pLPo: pct(pr.lPct, pr.lPct[l]), pNPo: pct(pr.nPct, pr.nPct[l]), mNPo: pct(mm.nPct, mm.nPct[l]),
          pSo: pr.sPct[l], mSo: mm.sPct[l], pLo: pr.lPct[l], mLo: mm.lPct[l], pNo: pr.nPct[l], mNo: mm.nPct[l], mZ: 0, mDN: mm.net[l] - mm.net[l - 1] };
        row.mSPoi = row.mSPo; row.mLPoi = row.mLPo; row.mNPoi = row.mNPo;
        scData.push(row); spData.push(row);
      }).catch(function () { }).finally(function () {
        done++; if (done < list.length) return;
        drawScatter('sc', scData, [{ c: 'sc1', x: 'pSP', y: 'mSP', xl: 'Prod Short', yl: 'MM Short', xv: 'pS', yv: 'mS' }, { c: 'sc2', x: 'pSP', y: 'mLP', xl: 'Prod Short', yl: 'MM Long', xv: 'pS', yv: 'mL' }, { c: 'sc3', x: 'pLP', y: 'mSP', xl: 'Prod Long', yl: 'MM Short', xv: 'pL', yv: 'mS' }, { c: 'sc4', x: 'pLP', y: 'mLP', xl: 'Prod Long', yl: 'MM Long', xv: 'pL', yv: 'mL' }, { c: 'sc5', x: 'pNP', y: 'mNP', xl: 'Prod Net', yl: 'MM Net', xv: 'pN', yv: 'mN' }]);
        drawScatter('sp', spData, [{ c: 'sp1', x: 'pSPo', y: 'mSPo', xl: 'Prod S%', yl: 'MM S%', xv: 'pSo', yv: 'mSo', pct: true }, { c: 'sp2', x: 'pSPo', y: 'mLPo', xl: 'Prod S%', yl: 'MM L%', xv: 'pSo', yv: 'mLo', pct: true }, { c: 'sp3', x: 'pLPo', y: 'mSPo', xl: 'Prod L%', yl: 'MM S%', xv: 'pLo', yv: 'mSo', pct: true }, { c: 'sp4', x: 'pLPo', y: 'mLPo', xl: 'Prod L%', yl: 'MM L%', xv: 'pLo', yv: 'mLo', pct: true }, { c: 'sp5', x: 'pNPo', y: 'mNPo', xl: 'Prod N%', yl: 'MM N%', xv: 'pNo', yv: 'mNo', pct: true }, { c: 'sp6', x: 'mLPo', y: 'mSPo', xl: 'MM L%', yl: 'MM S%', xv: 'mLo', yv: 'mSo', pct: true }]);
        drawLeg('scLeg', scData); drawLeg('spLeg', spData);
        if (document.getElementById('execSec')) popExec(scData);
        showL(false);
      });
  });
}
