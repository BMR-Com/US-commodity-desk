// CME Group exchange maintenance margins for the desk's contracts (runs inside a cmegroup.com page).
// Returns {asof, rows: [{code, exchange, name, period, maint, maint_long, maint_short}]}; first 3 periods per product.
(async () => {
  const j = u => fetch(u, { credentials: 'include' }).then(r => r.ok ? r.json() : null).catch(() => null);
  const AG = { CBT: ['C', 'S', '06', '07', 'W', 'KW', 'O', '14', 'YC', 'YK', 'YW', 'MKC', 'MZC', 'MZS', 'MZM', 'MZL', 'MZW'],
    CME: ['DA', 'DK', 'CSC', 'CB', 'NF', 'DY', '48', '62', 'LN', 'PRK'] };
  const EN = [['CL', 'CRUDE OIL'], ['QM', 'CRUDE OIL'], ['MCL', 'CRUDE OIL'], ['NG', 'NATURAL GAS'], ['QG', 'NATURAL GAS'], ['MNG', 'NATURAL GAS'],
    ['HO', 'REFINED PRODUCTS'], ['MHO', 'REFINED PRODUCTS'], ['RB', 'REFINED PRODUCTS'], ['MRB', 'REFINED PRODUCTS'], ['TT', 'AGRICULTURE']];
  const rows = [];
  for (const [ex, codes] of Object.entries(AG)) for (const c of codes) {
    const r = await j(`/CmeWS/mvc/Margins/OUTRIGHT?1=1&sortField=exchange&sortAsc=true&clearingCode=${c}&exchange=${ex}&pageSize=60&pageNumber=1`);
    for (const m of (r?.marginRates || []).slice(0, 3))
      rows.push({ code: c, exchange: ex, name: m.name, period: m.startPeriod + (m.endPeriod && m.endPeriod !== m.startPeriod ? '-' + m.endPeriod : ''), maint: m.maintenanceRate });
  }
  for (const [c, s] of EN) {
    const r = await j(`/services/margins/OUTRIGHT?1=1&sortField=exchange&sortAsc=true&clearingCode=${c}&sector=${encodeURIComponent(s)}&exchange=NYM&pageSize=3&pageNumber=1&isProtected`);
    for (const m of (r?.marginRates || []).slice(0, 3))
      rows.push({ code: c, exchange: 'NYMEX', name: m.name, period: m.period || m.startPeriod, maint: m.maintenanceRate || null, maint_long: m.maintenanceMarginLong || null, maint_short: m.maintenanceMarginShort || null });
  }
  return { asof: new Date().toISOString().slice(0, 10), rows };
})()
