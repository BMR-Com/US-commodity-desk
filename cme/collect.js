// CME daily volume / open interest + futures settlements collector.
// Runs inside a browser tab on https://www.cmegroup.com (CME blocks GitHub runners).
// Paste/execute in the page context; the last expression is a JSON object of CSV strings.
// Collects the latest trade date plus the one before it (so a preliminary print is
// overwritten by the final one on the next run).
(async () => {
  // CME product IDs (futures / options), from CME's product slate, 2026-10-19.
  const P = [
    // dairy
    { sym: 'DC', name: 'Class III milk', exch: 'CME', fut_id: 27, opt_id: 776 },
    { sym: 'GDK', name: 'Class IV milk', exch: 'CME', fut_id: 778, opt_id: 779 },
    { sym: 'CSC', name: 'Cash-settled cheese', exch: 'CME', fut_id: 5201, opt_id: 5202 },
    { sym: 'CB', name: 'Cash-settled butter', exch: 'CME', fut_id: 26, opt_id: 774 },
    { sym: 'GNF', name: 'Nonfat dry milk', exch: 'CME', fut_id: 781, opt_id: 782 },
    { sym: 'DY', name: 'Dry whey', exch: 'CME', fut_id: 36, opt_id: 784 },
    // livestock
    { sym: 'HE', name: 'Lean hogs', exch: 'CME', fut_id: 19, opt_id: 21 },
    { sym: 'LE', name: 'Live cattle', exch: 'CME', fut_id: 22, opt_id: 23 },
    { sym: 'GF', name: 'Feeder cattle', exch: 'CME', fut_id: 34, opt_id: 864 },
    // grains & oilseeds
    { sym: 'ZC', name: 'Corn', exch: 'CBOT', fut_id: 300, opt_id: 301 },
    { sym: 'ZS', name: 'Soybeans', exch: 'CBOT', fut_id: 320, opt_id: 321 },
    { sym: 'ZM', name: 'Soybean meal', exch: 'CBOT', fut_id: 310, opt_id: 311 },
    { sym: 'ZL', name: 'Soybean oil', exch: 'CBOT', fut_id: 312, opt_id: 313 },
    { sym: 'ZW', name: 'Chicago SRW wheat', exch: 'CBOT', fut_id: 323, opt_id: 324 },
    { sym: 'KE', name: 'KC HRW wheat', exch: 'CBOT', fut_id: 348, opt_id: 349 },
    { sym: 'ZO', name: 'Oats', exch: 'CBOT', fut_id: 331, opt_id: null },
    { sym: 'ZR', name: 'Rough rice', exch: 'CBOT', fut_id: 336, opt_id: null },
  ];
  const num = s => (s == null || s === '-' || s === '') ? '' : String(s).replace(/,/g, '');
  const j = u => fetch(u, { credentials: 'include' }).then(r => { if (!r.ok) throw new Error(r.status + ' ' + u); return r.json(); });
  const ex = [...new Set(P.map(p => p.exch))];
  const dates = {};
  for (const e of ex) dates[e] = (await j(`/CmeWS/mvc/Volume/TradeDates?exchange=${e}`)).slice(0, 2);
  const fut = ['trade_date,report_type,sym,exch,month,globex_vol,total_vol,block_vol,oi,oi_change,deliveries'];
  const opt = ['trade_date,report_type,sym,exch,month,cp,strike,total_vol,block_vol,oi,oi_change,exercises'];
  const set = ['trade_date,sym,exch,month,open,high,low,last,change,settle,volume,oi'];
  const errors = [];
  for (const p of P) {
    for (const d of dates[p.exch]) {
      const td = d.tradeDate, rt = d.reportType;
      try {
        const f = await j(`/CmeWS/mvc/Volume/Details/F/${p.fut_id}/${td}/P?tradeDate=${td}&pageSize=500`);
        for (const m of f.monthData || []) fut.push([td, rt, p.sym, p.exch, m.month, num(m.globex), num(m.totalVolume), num(m.blockVolume), num(m.atClose), num(m.change), num(m.deliveries)].join(','));
      } catch (e) { errors.push(String(e)); }
      if (p.opt_id) try {
        const o = await j(`/CmeWS/mvc/Volume/Details/O/${p.opt_id}/${td}/P?tradeDate=${td}&pageSize=500`);
        for (const m of o.monthData || []) for (const s of m.strikeData || []) {
          if (num(s.atClose) === '0' && num(s.totalVolume) === '0' && num(s.change) === '0') continue;
          opt.push([td, rt, p.sym, p.exch, s.month, m.label === 'Puts' ? 'P' : 'C', num(s.strike), num(s.totalVolume), num(s.blockVolume), num(s.atClose), num(s.change), num(s.exercises)].join(','));
        }
      } catch (e) { errors.push(String(e)); }
      try {
        const mdy = `${td.slice(4, 6)}/${td.slice(6, 8)}/${td.slice(0, 4)}`;
        const s = await j(`/CmeWS/mvc/Settlements/Futures/Settlements/${p.fut_id}/FUT?strategy=DEFAULT&tradeDate=${mdy}&pageSize=500`);
        for (const r of s.settlements || []) {
          if (r.month === 'Total') continue;
          set.push([td, p.sym, p.exch, r.month, num(r.open), num(r.high), num(r.low), num(r.last), num(r.change), num(r.settle), num(r.volume), num(r.openInterest)].join(','));
        }
      } catch (e) { errors.push(String(e)); }
    }
  }
  return { collected_at: new Date().toISOString(), dates, fut_volume_oi: fut.join('\n'), opt_volume_oi: opt.join('\n'), fut_settlements: set.join('\n'), errors };
})()
