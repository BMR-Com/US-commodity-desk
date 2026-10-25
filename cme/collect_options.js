// CME option settlements collector (standard American monthly options) for the desk's ag products.
// Runs inside a browser tab on https://www.cmegroup.com (same-origin fetch; CME blocks GitHub runners).
// Evaluate the whole file; it returns a promise of a gzip+base64 JSON string for `python cme/ingest_options.py`.
// DAYS = how many of the latest trade dates to fetch (CME keeps the last 5); 1 for the nightly run.
// CME's edge blocks a browser that fires a few hundred requests quickly (it did on 2026-10-21 after ~300), so
// requests are spaced out, only the nearest main expiries are fetched (see MAIN/NCAP), and the run stops after repeated failures.
// It takes a few minutes: start it without awaiting (window.__optp = <this file>; window.__optp.then(v => window.__opt_b64 = v))
// and poll window.__opt_b64.
// The cap hits after roughly 250-300 requests, so the products with the fewest stored dates (HAVE) go first: a product
// cut off one day is collected first the next, instead of the same tail (soyoil, wheat, energy) always missing out.
// FUTHAVE: ['ZC|10/23/2026', ...] product-dates whose futures settlements collect.js already stored
// (data/cme/<date>/fut_settlements.csv, see `python3 cme/options_have.py fut`); those are not fetched again and
// ingest_options.py reads the underlying from that file instead.
(async (DAYS = 1, MAXEXP = 10, GAP = 700, HAVE = [], FUTHAVE = []) => {   // HAVE: ['ZC|10/22/2026', ...] already stored, skipped
  // futures product id -> symbol (option product ids come from CME's own expiration list)
  const P0 = [['DC', 27], ['GDK', 778], ['CSC', 5201], ['CB', 26], ['GNF', 781], ['DY', 36], ['HE', 19], ['LE', 22], ['GF', 34],
             ['ZC', 300], ['ZS', 320], ['ZM', 310], ['ZL', 312], ['ZW', 323], ['KE', 348],
             ['NG', 444], ['CL', 425], ['HO', 426], ['RB', 429]];   // NYMEX energy (energy desk)
  // Expiries kept per product (Ma, 2026-10-25: "first 8 main contracts", oil "first 12 months"): options whose month is a
  // listed futures month (serial and weekly months are skipped), the nearest 8 for ags, livestock and dairy and the
  // nearest 12 for NYMEX energy. These caps are fixed here; the MAXEXP argument is kept for call compatibility only.
  const MAIN = { ZC: 'HKNUZ', ZS: 'FHKNQUX', ZM: 'FHKNQUVZ', ZL: 'FHKNQUVZ', ZW: 'HKNUZ', KE: 'HKNUZ',
                 HE: 'GJKMNQVZ', LE: 'GJMQVZ', GF: 'FHJKQUVX' };   // others (dairy, energy) list every month
  const NCAP = sym => ['NG', 'CL', 'HO', 'RB'].includes(sym) ? 12 : 8;
  const isMain = (sym, e) => !MAIN[sym] || MAIN[sym].includes(String(e.contractId).slice(-3, -2));
  const nHave = sym => HAVE.filter(h => h.startsWith(sym + '|')).length;
  const P = P0.map((x, i) => [x, i]).sort((a, b) => nHave(a[0][0]) - nHave(b[0][0]) || a[1] - b[1]).map(x => x[0]);
  // background tabs throttle setTimeout to about once a minute; a MessageChannel loop keeps the pacing honest
  const sleep = ms => new Promise(r => { const t0 = performance.now(); const mc = new MessageChannel();
    mc.port1.onmessage = () => { if (performance.now() - t0 >= ms) { mc.port1.close(); r(); } else mc.port2.postMessage(0); };
    mc.port2.postMessage(0); });
  // Pacing (2026-10-25): CME's edge cut the browser off after ~300 requests at 0.7 s and then again after ~37, so
  // requests now go at least 3 s apart with 0-60% random extra, plus a 45 s pause every 40 requests. GAP below 3000 ms
  // (the nightly task passes 700) is raised to 3000. A day's run (~200 requests) takes about 15-18 minutes.
  const G = Math.max(GAP, 3000);
  let fails = 0, nreq = 0;
  const j = async u => {
    for (let k = 0; k < 2; k++) {
      if (++nreq % 40 === 0) await sleep(45000);
      await sleep(G * (1 + 0.6 * Math.random()));
      try { const r = await fetch(u, { credentials: 'include' }); if (!r.ok) throw new Error(r.status + ' ' + u); fails = 0; return await r.json(); }
      catch (e) { if (++fails >= 4) throw new Error('STOP: CME stopped answering (' + e + ')'); await sleep(15000); }
    }
    throw new Error('failed ' + u);
  };
  const out = { collected_at: new Date().toISOString(), days: DAYS, products: {}, errors: [] };
  for (const [sym, fid] of P) {
    const prod = { fut_id: fid, calendar: [], exps: [], futures: {} };
    try {
      const t = await j(`/CmeWS/mvc/Settlements/Options/TradeDateAndExpirations/${fid}`);
      const ame = t.find(x => x.optionType === 'AME');
      if (!ame) { out.errors.push(sym + ': no American options'); continue; }
      const oid = ame.expirations[0]?.productId;
      prod.opt_id = oid;
      try {
        const cal = await j(`/CmeWS/mvc/ProductCalendar/Options/${oid}`);
        const c = cal.find(x => x.optionType === 'AME') || cal[0];
        prod.calendar = (c?.calendarEntries || []).map(e => [e.productCode, e.contractMonth, e.lastTrade]);
      } catch (e) { out.errors.push(String(e)); }
      // the latest DAYS trade dates across this product's expirations
      const all = [...new Set(ame.expirations.flatMap(e => e.tradeDates.map(d => d.formatedDate)))]
        .sort((a, b) => new Date(b) - new Date(a)).slice(0, DAYS);
      for (const td of all) {
        if (HAVE.includes(`${sym}|${td}`)) continue;
        if (!FUTHAVE.includes(`${sym}|${td}`)) try {   // futures settlements for the same trade date (underlying prices)
          const f = await j(`/CmeWS/mvc/Settlements/Futures/Settlements/${fid}/FUT?strategy=DEFAULT&tradeDate=${td}&pageSize=500`);
          prod.futures[td] = (f.settlements || []).filter(r => r.month !== 'Total').map(r => [r.month, r.settle, r.openInterest, r.volume]);
        } catch (e) { out.errors.push(String(e)); if (String(e).includes('STOP')) throw e; }
        for (const e of ame.expirations.filter(e => isMain(sym, e)).slice(0, NCAP(sym))) {
          if (!e.tradeDates.some(d => d.formatedDate === td)) continue;
          try {
            const r = await j(`/CmeWS/mvc/Settlements/Options/Settlements/${e.productId}/OOF?strategy=DEFAULT&optionProductId=${e.productId}&monthYear=${e.contractId}&optionExpiration=${e.productId}-${e.expiration.code}&tradeDate=${td}&pageSize=500`);
            const rows = (r.settlements || []).filter(x => x.strike && x.strike !== 'Total' && (x.openInterest !== '0' || x.volume !== '0' || (x.settle !== 'CAB' && x.settle !== '-')))
              .map(x => [x.type === 'Call' ? 'C' : 'P', x.strike, x.settle, x.openInterest, x.volume, x.change]);
            prod.exps.push({ td, contract: e.contractId, label: e.label, month: e.expiration.month, year: e.expiration.year, report: r.reportType, rows });
          } catch (err) { out.errors.push(String(err)); if (String(err).includes('STOP')) throw err; }
        }
      }
    } catch (e) { out.errors.push(sym + ': ' + e); }
    out.products[sym] = prod;
    if (out.errors.some(x => String(x).includes('STOP'))) break;
  }
  const s = JSON.stringify(out);
  const buf = new Uint8Array(await new Response(new Blob([s]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
  let b = ''; for (let i = 0; i < buf.length; i += 0x8000) b += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  return btoa(b);
})();
