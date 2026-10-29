// Cotton › AMS market review: USDA AMS Weekly Cotton Market Review (crop progress and mill demand in brief, prices, spot trades)
// and the AMS Forward Contracting Report. Data: data/cotton_review/latest.json, forward_contracting.json.
const AmsReview = (() => {
  const css = `<style id="arCss">
    .ar .ar-kpi{display:flex;flex-wrap:wrap;gap:18px;margin:6px 0 4px}.ar .ar-kpi div{min-width:110px}.ar .ar-kpi b{font-size:18px}
    .ar ul.read li{margin:5px 0;line-height:1.45}.ar td.l{text-align:left;white-space:normal}
    .ar .ar-lvl{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;border:1px solid var(--line);margin-left:4px}
    .ar .ar-two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}@media(max-width:1000px){.ar .ar-two{grid-template-columns:minmax(0,1fr)}}
  </style>`;
  const n = (v, d = 2) => v == null ? '–' : (+v).toFixed(d);
  const sg = (v, d = 2) => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${(+v).toFixed(d)}</span>`;
  const lvlCol = l => !l ? '' : /inactive|slow|light|weak/.test(l) ? 'color:var(--dn);border-color:var(--dn)' : /active|heavy|good|strong/.test(l) ? 'color:var(--up);border-color:var(--up)' : '';
  async function mount(el) {
    if (!document.getElementById('arCss')) document.head.insertAdjacentHTML('beforeend', css);
    el.innerHTML = '<div class="card"><p class="note">Loading the AMS market review…</p></div>';
    const [D, FC] = await Promise.all([getJSON('data/cotton_review/latest.json').catch(() => null), getJSON('data/cotton_review/forward_contracting.json').catch(() => null)]);
    if (!D) { el.innerHTML = '<div class="card"><p class="note">The AMS Weekly Cotton Market Review has not been collected yet.</p></div>'; return; }
    const P = D.prices || {}, F = (D.futures || []).at(-1) || {}, B = D.brief || {};
    const basis = P.spot_7mkt_avg != null && P.dec_settle != null ? Math.round((P.spot_7mkt_avg - P.dec_settle) * 100) : null;
    const g41 = (D.spot_41_4_34 || []), last = g41.at(-1), first = g41[0];
    const mk = ['SE', 'ND', 'SD', 'ETX-STX', 'WTX-KS-OK', 'DSW', 'SJV', '7-MKT AVG'];
    const g31 = (D.spot_31_3_36 || []).at(-1);
    const regs = D.regions || [];
    const fcR = FC && FC.reports && FC.reports[FC.latest];
    const ser = D.series || [];
    el.innerHTML = `<div class="ar">
      <div class="card"><h2>AMS Weekly Cotton Market Review — ${D.date} <span class="note">${D.volume || ''} · <a href="${D.source}" target="_blank" rel="noopener">report PDF ↗</a> · next issue Friday</span></h2>
        <div class="ar-kpi">
          <div><div class="note">Spot 41-4-34, 7-market avg</div><b>${n(P.spot_7mkt_avg)}¢</b> ${sg(P.chg_week_pts != null ? P.chg_week_pts : null, 0)} pts</div>
          <div><div class="note">Basis vs Dec futures</div><b>${basis == null ? '–' : (basis > 0 ? '+' : '') + basis}</b> pts</div>
          <div><div class="note">Dec futures (week end)</div><b>${n(P.dec_settle)}¢</b></div>
          <div><div class="note">A Index (Far East)</div><b>${n(F.a_index)}¢</b></div>
          <div><div class="note">Adjusted World Price</div><b>${n(D.awp)}¢</b> <span class="note">${D.awp_window || ''}</span></div>
          <div><div class="note">Spot a year ago</div><b>${n(P.year_ago)}¢</b></div>
        </div>
        <ul class="read">${(B.headline || []).map(x => `<li>${x}</li>`).join('')}</ul></div>
      <div class="ar-two" style="margin-top:12px">
        <div class="card"><h2>Crop progress in brief</h2><ul class="read">${(B.crop || []).map(x => `<li><b>${x.area}:</b> ${x.t}</li>`).join('') || '<li class="note">No crop notes this week.</li>'}</ul></div>
        <div class="card"><h2>Mill demand in brief</h2><ul class="read">${(B.mill || []).map(x => `<li><b>${x.area}:</b> ${x.t}</li>`).join('')}</ul>
          ${(D.export_inquiries || []).length ? `<h3>Export inquiries</h3><div class="tbl"><table><tr><th class="l">Buyer</th><th class="l">Quality asked</th><th class="l">Shipment</th><th class="l">Reported in</th></tr>
            ${D.export_inquiries.map(e => `<tr><td class="l"><b>${e.countries.join(', ')}</b></td><td class="l">${e.quality ? 'color ' + e.quality : '–'}</td><td class="l">${e.when || '–'}</td><td class="l">${e.sub}</td></tr>`).join('')}</table></div>` : ''}</div>
      </div>
      <div class="card" style="margin-top:12px"><h2>Spot market by region</h2><div class="tbl"><table><tr><th class="l">Market</th><th>Trading</th><th>Demand</th><th>Supplies</th><th>Foreign inquiries</th></tr>
        ${regs.flatMap(r => Object.entries(r.subs).filter(([k, s]) => k !== 'Textile Mill' && (s.trading || s.demand_level)).map(([k, s]) => `<tr><td class="l">${k}</td>${['trading', 'demand_level', 'supplies', 'foreign_inquiries'].map(f => `<td>${s[f] ? `<span class="ar-lvl" style="${lvlCol(s[f])}">${s[f]}</span>` : '–'}</td>`).join('')}</tr>`)).join('')}</table></div></div>
      <div class="card" style="margin-top:12px"><h2>Spot quotations (¢/lb)</h2><div class="tbl"><table><tr><th class="l">Grade</th>${mk.map(m => `<th>${m}</th>`).join('')}</tr>
        ${last ? `<tr><td class="l">41-4-34, ${last.date}</td>${mk.map(m => `<td>${n(last[m])}</td>`).join('')}</tr><tr><td class="l note">change since ${first.date}</td>${mk.map(m => `<td>${sg(last[m] - first[m])}</td>`).join('')}</tr>` : ''}
        ${g31 ? `<tr><td class="l">31-3-36, ${g31.date}</td>${mk.map(m => `<td>${n(g31[m])}</td>`).join('')}</tr><tr><td class="l note">31-3-36 premium over 41-4-34</td>${mk.map(m => `<td>${last ? sg(g31[m] - last[m]) : '–'}</td>`).join('')}</tr>` : ''}</table></div>
        ${(D.futures || []).length ? `<h3>ICE futures and A Index during the week</h3><div class="tbl"><table><tr><th class="l">Day</th>${(D.futures_months || []).map(m => `<th>${m}</th>`).join('')}<th>7-mkt spot</th><th>A Index</th></tr>
          ${D.futures.map(r => `<tr><td class="l">${r.date}</td>${r.futures.map(v => `<td>${n(v)}</td>`).join('')}<td>${n(r.spot_7mkt)}</td><td>${n(r.a_index)}</td></tr>`).join('')}</table></div>` : ''}</div>
      <div class="card" style="margin-top:12px"><h2>Reported spot trades</h2><div class="tbl"><table><tr><th class="l">Region</th><th class="l">Area</th><th>Price (¢/lb)</th><th>Color</th><th>Volume</th><th class="l">Lot</th></tr>
        ${regs.flatMap(r => r.trades.filter(t => t.lo != null).map(t => `<tr><td class="l">${r.region.split(' (')[0]}</td><td class="l">${t.area || '–'}</td><td><b>${n(t.lo)}${t.hi != null && t.hi !== t.lo ? '–' + n(t.hi) : ''}</b></td><td>${t.color || '–'}</td><td>${t.volume || '–'}</td><td class="l note">${t.text}</td></tr>`)).join('') || '<tr><td colspan="6" class="note">No trades reported.</td></tr>'}</table></div></div>
      ${fcR ? `<div class="card" style="margin-top:12px"><h2>Grower forward contracting <span class="note">AMS Forward Contracting Report, as of ${fcR.as_of}: share of planted Upland acres contracted</span></h2>
        <div class="tbl"><table><tr><th class="l">State / region</th><th>${fcR.crop_year}</th><th>${fcR.crop_year - 1}</th><th>${fcR.crop_year - 2}</th><th>5-season avg</th><th>vs avg</th><th>Planted (k ac)</th></tr>
        ${fcR.rows.map(r => { const p5 = r.prior.slice(0, 5).filter(v => v != null && v <= 100); const a5 = p5.length ? p5.reduce((x, y) => x + y, 0) / p5.length : null;
          return `<tr style="${r.region ? 'font-weight:700' : ''}"><td class="l">${r.loc}</td><td>${r.pct == null ? '–' : r.pct + '%'}</td><td>${r.prior[0] == null ? '–' : r.prior[0] + '%'}</td><td>${r.prior[1] == null ? '–' : r.prior[1] + '%'}</td><td>${a5 == null ? '–' : a5.toFixed(0) + '%'}</td><td>${a5 == null || r.pct == null ? '–' : sg(r.pct - a5, 0)}</td><td>${r.acres ? Math.round(r.acres / 1000).toLocaleString() : '–'}</td></tr>`; }).join('')}</table></div>
        <p class="note">More forward contracting means more of the crop is priced and hedged early, so less grower selling is left for later in the season. 5-season average leaves out values above 100% (data errors in the source).</p></div>` : ''}
      ${ser.length > 1 ? `<div class="card" style="margin-top:12px"><h2>Week by week</h2><div class="tbl"><table><tr><th class="l">Report</th><th>Spot 7-mkt</th><th>Dec</th><th>Basis (pts)</th><th>A Index</th><th>AWP</th><th class="l">Export demand</th><th class="l">Export inquiries from</th></tr>
        ${ser.slice().reverse().slice(0, 26).map(s => `<tr><td class="l">${s.date}</td><td>${n(s.spot)}</td><td>${n(s.dec)}</td><td>${s.spot != null && s.dec != null ? Math.round((s.spot - s.dec) * 100) : '–'}</td><td>${n(s.a_index)}</td><td>${n(s.awp)}</td><td class="l">${s.export_demand || '–'}</td><td class="l">${(s.countries || []).join(', ') || '–'}</td></tr>`).join('')}</table></div></div>` : ''}
      <p class="note">Source: USDA AMS Cotton and Tobacco Market News, Weekly Cotton Market Review (published Fridays) and Forward Contracting Report (monthly). Crop and demand lines are taken from the regional reporters' notes; harvest percentages are NASS figures as quoted in the review.</p>
    </div>`;
  }
  return { mount };
})();
