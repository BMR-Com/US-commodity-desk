/* ===========================================================
   COT DATA STORE — pre-computed static data with version-keyed caching
   -----------------------------------------------------------
   The weekly GitHub Action writes data/web/{manifest,snapshot}.json and
   data/web/series/<TICKER>.json. This module:
     1. fetches the tiny manifest with no-cache (≈1 KB) to learn report_date;
     2. serves snapshot/series from localStorage / IndexedDB when the stored
        copy matches that version — i.e. ZERO data downloads when the CFTC
        hasn't published anything new;
     3. otherwise downloads once, stores, and serves from memory thereafter.
   Every function returns a Promise. If the static files are missing, callers
   fall back to the legacy live-API path.
   =========================================================== */
var COTStore = (function () {
  var BASE = 'data/web/';
  var man = null, manP = null, snapP = null, serMem = {}, serP = {};

  /* ---------- tiny storage helpers (all failure-tolerant) ---------- */
  function lsGet(k) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* quota / private mode */ } }

  var dbP = null;
  function db() {
    if (dbP) return dbP;
    dbP = new Promise(function (res) {
      try {
        if (!window.indexedDB) return res(null);
        var rq = indexedDB.open('cot-store', 1);
        rq.onupgradeneeded = function () { rq.result.createObjectStore('series'); };
        rq.onsuccess = function () { res(rq.result); };
        rq.onerror = function () { res(null); };
        rq.onblocked = function () { res(null); };
      } catch (e) { res(null); }
    });
    return dbP;
  }
  function idbGet(k) {
    return db().then(function (d) {
      if (!d) return null;
      return new Promise(function (res) {
        try { var rq = d.transaction('series', 'readonly').objectStore('series').get(k); rq.onsuccess = function () { res(rq.result || null); }; rq.onerror = function () { res(null); }; }
        catch (e) { res(null); }
      });
    });
  }
  function idbPut(k, v) {
    return db().then(function (d) {
      if (!d) return;
      try { d.transaction('series', 'readwrite').objectStore('series').put(v, k); } catch (e) { }
    });
  }

  /* ---------- manifest / version ---------- */
  function manifest() {
    if (manP) return manP;
    manP = fetch(BASE + 'manifest.json', { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error('manifest HTTP ' + r.status); return r.json(); })
      .then(function (m) { man = m; return m; });
    manP.catch(function () { manP = null; });
    return manP;
  }
  function ver() { return man ? (man.report_date + '|' + man.generated) : ''; }

  /* ---------- snapshot (≈160 KB, localStorage) ---------- */
  function snapshot() {
    if (snapP) return snapP;
    snapP = manifest().then(function () {
      var c = lsGet('cot_snapshot');
      if (c && c.v === ver() && c.d) return c.d;
      return fetch(BASE + 'snapshot.json?v=' + encodeURIComponent(ver()))
        .then(function (r) { if (!r.ok) throw new Error('snapshot HTTP ' + r.status); return r.json(); })
        .then(function (d) { lsSet('cot_snapshot', { v: ver(), d: d }); return d; });
    });
    snapP.catch(function () { snapP = null; });
    return snapP;
  }

  /* ---------- per-commodity series (IndexedDB) ---------- */
  function series(ticker) {
    if (serMem[ticker]) return Promise.resolve(serMem[ticker]);
    if (serP[ticker]) return serP[ticker];
    serP[ticker] = manifest().then(function () {
      var key = ticker + '@' + ver();
      return idbGet(key).then(function (hit) {
        if (hit) return hit;
        return fetch(BASE + 'series/' + encodeURIComponent(ticker) + '.json?v=' + encodeURIComponent(ver()))
          .then(function (r) { if (!r.ok) throw new Error('series ' + ticker + ' HTTP ' + r.status); return r.json(); })
          .then(function (d) { idbPut(key, d); return d; });
      });
    }).then(function (d) { serMem[ticker] = d; delete serP[ticker]; return d; });
    serP[ticker].catch(function () { delete serP[ticker]; });
    return serP[ticker];
  }

  /* ---------- lookups ---------- */
  function itemByApi(api) {
    for (var i = 0; i < allBCOM.length; i++) if (allBCOM[i].api === api) return allBCOM[i];
    return null;
  }
  function tickerForApi(api) { var it = itemByApi(api); return it ? it.ticker : null; }
  function seriesForApi(api) {
    var t = tickerForApi(api);
    return t ? series(t) : Promise.reject(new Error('No static series for ' + api));
  }

  /* ---------- static series -> procData()-shaped object ---------- */
  function toProc(s, cat, crop, comm, sd, ed) {
    crop = crop || 'all'; cat = cat || 'managed_money';
    var blk = s.ct[crop] || (crop !== 'all' ? null : s.ct.all);
    if (!blk || !blk[cat]) return null;
    var c = blk[cat], p = { dates: [], long: [], short: [], spread: [], tL: [], tS: [], oi: [], cat: cat, crop: crop, comm: comm || s.name, _static: true };
    for (var i = 0; i < s.dates.length; i++) {
      var d = s.dates[i];
      if (sd && d < sd) continue;
      if (ed && d > ed) continue;
      if (blk.oi[i] == null || c.l[i] == null) continue;
      p.dates.push(d); p.long.push(c.l[i] || 0); p.short.push(c.s[i] || 0); p.spread.push(c.sp[i] || 0);
      p.tL.push(c.tl[i] || 0); p.tS.push(c.ts[i] || 0); p.oi.push(blk.oi[i] || 0);
    }
    if (!p.dates.length) return null;
    p.tT = p.tL.map(function (v, i) { return v + p.tS[i]; });
    p.net = p.long.map(function (v, i) { return v - p.short[i]; });
    p.lPct = p.oi.map(function (v, i) { return v > 0 ? p.long[i] / v * 100 : 0; });
    p.sPct = p.oi.map(function (v, i) { return v > 0 ? p.short[i] / v * 100 : 0; });
    p.nPct = p.lPct.map(function (v, i) { return v - p.sPct[i]; });
    p.plL = p.tL.map(function (v, i) { return v > 0 ? p.long[i] / v : 0; });
    p.plS = p.tS.map(function (v, i) { return v > 0 ? p.short[i] / v : 0; });
    return p;
  }

  /* ---------- freshness: is a newer CFTC report out than our data? ---------- */
  /* CFTC publishes Tuesday's positions on Friday 3:30pm ET (holiday weeks shift). */
  function expectedReportDate(now) {
    now = now || new Date();
    var et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
    var d = new Date(et); var dow = d.getDay();
    var sinceFri = (dow - 5 + 7) % 7;
    var fri = new Date(d); fri.setDate(d.getDate() - sinceFri);
    if (sinceFri === 0 && (et.getHours() * 60 + et.getMinutes()) < 15 * 60 + 45) fri.setDate(fri.getDate() - 7);
    var tue = new Date(fri); tue.setDate(fri.getDate() - 3);
    return tue.getFullYear() + '-' + String(tue.getMonth() + 1).padStart(2, '0') + '-' + String(tue.getDate()).padStart(2, '0');
  }
  function liveLatestDate() {
    var url = EP.combined + "?$select=max(report_date_as_yyyy_mm_dd) as d&$where=cftc_contract_market_code='033661'";
    return fetchT(url, 8000).then(function (r) { return r.json(); })
      .then(function (a) { return a && a[0] && a[0].d ? String(a[0].d).slice(0, 10) : null; });
  }

  return {
    manifest: manifest, snapshot: snapshot, series: series, seriesForApi: seriesForApi,
    tickerForApi: tickerForApi, itemByApi: itemByApi, toProc: toProc,
    expectedReportDate: expectedReportDate, liveLatestDate: liveLatestDate,
    get man() { return man; }
  };
})();

/* Wrap a static series so legacy code that stores "raw" arrays (agriRaw,
   rawCache-style caches) can keep passing it to procData(). */
function staticRaw(series, api) { return { __series: series, __api: api, length: series.dates.length }; }

/* ---------- Data status strip (top of page) ---------- */
function fmtDate(iso) {
  if (!iso) return '?';
  var d = new Date(iso + 'T12:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
}
function renderDataStatus() {
  var el = document.getElementById('dataStatus'); if (!el) return;
  COTStore.manifest().then(function (m) {
    var exp = COTStore.expectedReportDate();
    var mon = function (d) { var x = new Date(d + 'T12:00:00'); return x.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }); };
    var stale = (m.commodities || []).filter(function (c) { return c.stale; }).map(function (c) { return c.name + ' (last ' + mon(c.last_date) + ')'; });
    var h = '<span class="ds-dot ds-ok"></span>CFTC positions as of <b>' + fmtDate(m.report_date) + '</b>' +
      '<span class="ds-sep">·</span>pre-computed ' + m.generated;
    if (m.report_date < exp) h = h.replace('ds-ok', 'ds-warn') + '<span class="ds-sep">·</span><span class="ds-warn-txt">checking CFTC for the ' + fmtDate(exp) + ' report…</span>';
    if (stale.length) h += '<span class="ds-sep">·</span><span title="These markets have no CFTC report in the data for 3+ weeks, so they are left out of Summary and Scatter. WTI / Nat Gas / Brent were renamed by the CFTC in 2022 and are backfilled by the next Weekly COT Data Update run; COMEX Aluminum is no longer published by the CFTC.">⚠ no recent CFTC data: ' + stale.join(', ') + '</span>';
    el.innerHTML = h; el.style.display = 'flex';
    if (m.report_date < exp) {
      COTStore.liveLatestDate().then(function (live) {
        var t = el.querySelector('.ds-warn-txt'); if (!t) return;
        if (live && live > m.report_date) t.innerHTML = 'CFTC has published the <b>' + fmtDate(live) + '</b> report — the weekly job will pick it up (or run <i>Weekly COT Data Update</i> manually).';
        else t.textContent = 'latest available (CFTC report for ' + fmtDate(exp) + ' not out yet / holiday delay).';
      }).catch(function () { var t = el.querySelector('.ds-warn-txt'); if (t) t.textContent = 'could not reach CFTC to check for a newer report.'; });
    }
  }).catch(function () { el.style.display = 'none'; });
}
