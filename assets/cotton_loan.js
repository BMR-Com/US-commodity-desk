// Cotton > Loan: cotton in the CCC marketing loan (FSA PSL-61R weekly/monthly, PSL-43R maturity, weekly state snapshots).
// Data: data/cotton_loan/loan.json (models/cotton_loan.py). Self-contained: a failure here does not touch other tabs.
const CottonLoan = (() => {
  const k = v => v == null ? '–' : !v ? '–' : Math.abs(v) < 10000 ? fmt(v / 1000, 1) + 'k' : fmt(v / 1000, 0) + 'k';
  const mkey = s => { const m = String(s).replace(',', '').match(/([A-Za-z]{3}) (\d{4})/); return m ? +m[2] * 12 + MON.indexOf(m[1]) : 0; };
  const kpi = (l, v, s2) => `<div class="card kpi"><div class="lbl">${l}</div><div class="val">${v}</div><div class="sub">${s2}</div></div>`;
  const STN = { AL: 'Alabama', AZ: 'Arizona', AR: 'Arkansas', CA: 'California', FL: 'Florida', GA: 'Georgia', KS: 'Kansas', LA: 'Louisiana', MS: 'Mississippi', MO: 'Missouri', NM: 'New Mexico', NC: 'North Carolina', OK: 'Oklahoma', SC: 'South Carolina', TN: 'Tennessee', TX: 'Texas', VA: 'Virginia', IL: 'Illinois' };
  async function mount(el) {
    el.innerHTML = '<div class="card"><p class="note">Loading cotton loan…</p></div>';
    const D = await getJSON('data/cotton_loan/loan.json').catch(() => null);
    if (!D || !D.series) { el.innerHTML = '<div class="card"><p class="note">Cotton loan data not built yet.</p></div>'; return; }
    const up = D.series.filter(s => s.com === 'COTTON-UP'), last = up[up.length - 1], Y = D.yoy, M = D.maturity || {}, S = D.state || {};
    const ms = M.summary || {}, oc = ms[String(last.crop_year - 1)] || {};
    el.innerHTML = `
      <div class="card"><h2>Cotton in the loan</h2>${(D.brief || []).map(b => `<p><b>${b.h}.</b> ${b.t}</p>`).join('')}
        <p class="note">Updated ${D.generated}. FSA State Office Reporting System: PSL-61R loan activity (weekly, as of Mondays; monthly), PSL-43R warehouse cotton maturity (monthly), state reports captured weekly.
        Year-on-year comparisons use the monthly reports, the only ones FSA keeps for a year; weekly history builds from Oct 2026. Upland unless stated. Bales.</p></div>
      <div class="grid g4" style="margin-top:12px">
        ${kpi(`${last.crop_year} crop entered`, k(last.put), `as of ${last.date} · ${k(last.repaid)} repaid · ${k(last.out)} outstanding`)}
        ${kpi(`${last.crop_year - 1} crop still in`, k(last.prior_crop_out), `of ${fmt(last.prior_crop_put / 1e6, 2)}m that entered`)}
        ${kpi('Year on year (monthly)', Y ? k(Y.now.put) : '–', Y ? `${Y.now.date} vs ${k(Y.year_ago.put)} at ${Y.year_ago.date}` : 'needs a year of reports')}
        ${kpi('Form G share (old crop)', oc.made ? fmt(oc.G_made / oc.made * 100, 0) + '%' : '–', 'loans made through loan servicing agents; rest Form A (county office)')}
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Current crop: entered and outstanding</h2><div class="chart"><canvas id="cLnSer"></canvas></div>
          <p class="note">Dots: monthly reports; line: weekly. Year-ago points are the previous crop at the same date (monthly reports; FSA skipped Oct 2025).</p></div>
        <div class="card"><h2>Loans outstanding by maturity month (PSL-43R, ${M.as_of || '–'})</h2><div class="chart"><canvas id="cLnMat"></canvas></div>
          <p class="note">Loans run 9 months from disbursement. Grey: same report a year earlier (${M.year_ago?.as_of || '–'}). All cotton, Form A + G.</p></div>
      </div>
      <div class="card" style="margin-top:12px"><h2>By state (as of ${S.as_of || '–'})</h2><div class="tbl"><table>
        <tr><th>State</th><th>${S.crop_year} entered</th><th>repaid</th><th>outstanding</th><th>entered at ${S.monthly_as_of}</th><th>year earlier (${S.monthly_year_ago || '–'})</th><th>${S.crop_year - 1} crop entered</th><th>${S.crop_year - 1} still in</th></tr>
        ${(S.rows || []).filter(r => r.put || r.old_out || r.old_put).map(r => `<tr><td class="l">${STN[r.st] || r.st}</td><td>${k(r.put)}</td><td>${k(r.repaid)}</td><td>${k(r.out)}</td><td>${k(r.m_put)}</td><td>${r.m_put_ly == null ? '–' : k(r.m_put_ly)}</td><td>${k(r.old_put)}</td><td>${k(r.old_out)}</td></tr>`).join('')}
      </table></div></div>
      <div class="card" style="margin-top:12px"><h2>Outstanding by state and maturity (${D.maturity_state?.week || '–'})</h2><div class="tbl" id="lnMatSt"></div></div>`;
    try {
      const mo = up.filter(s => s.kind === 'monthly'), wk = up.filter(s => s.kind === 'weekly');
      const shift = d => { const t = new Date(d); t.setFullYear(t.getFullYear() + 1); return t.toISOString().slice(0, 10); };
      chart('cLnSer', { type: 'line', data: { datasets: [
        { label: 'Entered (weekly)', data: wk.map(s => ({ x: s.date, y: s.put / 1e3 })), borderColor: PAL[0], pointRadius: 2 },
        { label: 'Outstanding (weekly)', data: wk.map(s => ({ x: s.date, y: s.out / 1e3 })), borderColor: PAL[2], pointRadius: 2 },
        { label: 'Entered (monthly)', data: mo.filter(s => s.crop_year === last.crop_year).map(s => ({ x: s.date, y: s.put / 1e3 })), borderColor: PAL[0], showLine: false, pointRadius: 4 },
        { label: 'Previous crop, a year earlier', data: mo.filter(s => s.crop_year === last.crop_year - 1).map(s => ({ x: shift(s.date), y: s.put / 1e3 })), borderColor: '#999', borderDash: [4, 3], pointRadius: 3 }] },
        options: { parsing: true, scales: { x: { type: 'category', labels: [...new Set([...mo, ...wk].filter(s => s.crop_year === last.crop_year).map(s => s.date).concat(mo.filter(s => s.crop_year === last.crop_year - 1).map(s => shift(s.date))))].sort() }, y: { title: { display: true, text: 'thousand bales' } } } } });
      const agg = rows => { const o = {}; (rows || []).forEach(r => { const key = `${r.matures} (${r.crop_year})`; o[key] = (o[key] || 0) + r.out; }); return o; };
      const srt = o => Object.fromEntries(Object.entries(o).sort((x, y) => mkey(x[0]) - mkey(y[0])));
      const a = srt(agg(M.rows)), b = srt(agg(M.year_ago?.rows));
      chart('cLnMat', { type: 'bar', data: { labels: Object.keys(a), datasets: [{ label: M.as_of, data: Object.values(a).map(v => v / 1e3), backgroundColor: PAL[2] }] },
        options: { scales: { y: { title: { display: true, text: 'thousand bales' } } } } });
      const yb = Object.entries(b);
      if (yb.length) $('#cLnMat').closest('.card').insertAdjacentHTML('beforeend', `<p class="note">A year earlier: ${yb.map(([kk, v]) => `${kk} ${k(v)}`).join(' · ')}</p>`);
      const R = D.maturity_state?.rows || [], mats = [...new Set(R.map(r => `${r.matures} (${r.cy})`))].sort((x, y) => mkey(x) - mkey(y));
      const sts = [...new Set(R.map(r => r.st))];
      $('#lnMatSt').innerHTML = `<table><tr><th>State</th>${mats.map(m => `<th>${m}</th>`).join('')}</tr>${sts.map(s => `<tr><td class="l">${STN[s] || s}</td>${mats.map(m => { const x = R.filter(r => r.st === s && `${r.matures} (${r.cy})` === m).reduce((t, r) => t + r.qty, 0); return `<td>${x ? k(x) : ''}</td>`; }).join('')}</tr>`).join('')}</table>`;
    } catch (e) { console.warn('cotton loan charts', e); }
  }
  return { mount };
})();
