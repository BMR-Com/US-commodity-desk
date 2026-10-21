// Trader tools: the trader sheet (Summary page) and the per-market spreads / crush / volatility / report-day view.
const RVView = (() => {
  const G = 'data/grains/derived/';
  const f = (v, d = 2) => v == null || isNaN(v) ? '–' : (+v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const sg = (v, d = 1, suf = '') => v == null || isNaN(v) ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${f(v, d)}${suf}</span>`;
  const ord = v => { if (v == null) return '–'; const n = Math.round(v); return n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th')); };
  const k = v => v == null ? '–' : (v >= 0 ? '+' : '') + (Math.abs(v) >= 1000 ? (v / 1000).toFixed(0) + 'k' : v.toFixed(0));
  const usd = v => v == null ? '–' : '$' + Math.round(v).toLocaleString('en-US');
  const spark = (a, w = 90, h = 22) => { if (!a || a.length < 2) return ''; const mn = Math.min(...a), mx = Math.max(...a), r = mx - mn || 1;
    return `<svg width="${w}" height="${h}" class="spark"><polyline fill="none" stroke="#2f6b3a" stroke-width="1.4" points="${a.map((v, i) => `${(i / (a.length - 1) * w).toFixed(1)},${(h - 2 - (v - mn) / r * (h - 4)).toFixed(1)}`).join(' ')}"/></svg>`; };
  const TIL = { bull: 'up', bear: 'dn', neutral: '' };

  // ── trader sheet ──
  async function sheet(el) {
    const S = await getJSON('data/summary/sheet.json').catch(() => null);
    if (!S) { el.innerHTML = '<p class="note">Trader sheet not built yet.</p>'; return; }
    const R = S.rows;
    el.innerHTML = `<div class="tbl"><table class="ts">
      <tr><th class="l">Market</th><th>Last · 1d<br>1w · 1m</th><th>Technicals<br>support · resistance</th><th>Curve</th><th>Funds (MM) · 10y pct<br>CTA flip ▲ / ▼</th><th>Exports vs norm<br>WASDE read</th><th>Vol · 1σ day</th><th class="l">Next catalyst · typical move</th><th>View</th></tr>
      ${R.map(r => `<tr><td class="l"><b>${r.name}</b><br><span class="note">${r.contract || ''}</span></td>
        <td><b>${f(r.last, r.last > 100 ? 2 : 3)}</b> ${sg(r.chg, 2)}<br>${sg(r.r1w, 1, '%')} · ${sg(r.r1m, 1, '%')}</td>
        <td>${r.rating || '–'} <span class="note">RSI ${f(r.rsi, 0)}</span><br><span class="note">${f(r.sup)} · ${f(r.res)}</span></td>
        <td>${r.spread ? `${r.spread} <b>${f(r.spread_v)}</b><br><span class="note">${r.pct_full != null ? `${r.pct_full}% full carry · ` : ''}${r.spread_pct != null ? `${ord(r.spread_pct)} pct` : ''}</span>` : '–'}</td>
        <td>${k(r.mm_net)} <span class="note">(${k(r.mm_dn)}) · ${ord(r.mm_pct10)}</span><br><span class="note">${r.cta_up ? `▲ ${f(r.cta_up)} / ▼ ${f(r.cta_dn)}` : r.driver || ''}</span></td>
        <td>${r.esr_pace ? `${Math.round(r.esr_pace * 100)}% vs ${Math.round(r.esr_norm * 100)}%` : '–'}<br><span class="note">${r.wasde || ''}</span></td>
        <td>${f(r.hv20, 0)}% <span class="note">${ord(r.hv_pct)}</span><br>±${f(r.day_move)} <span class="note">${usd(r.day_move_usd)}</span></td>
        <td class="l">${r.event ? `<b>${r.event_date?.slice(5)}</b> ${r.event.replace('NASS ', '').replace('USDA ', '')}${r.event_move != null ? `<br><span class="note">±${f(r.event_move)} (${usd(r.event_move_usd)}/ct, ${f(r.event_ratio, 1)}× normal; 1-in-10 ±${f(r.event_p90)})</span>` : ''}` : '–'}</td>
        <td>${r.view ? `<span class="${/bull/.test(r.view) ? 'up' : /bear/.test(r.view) ? 'dn' : ''}">${r.view}</span>` : '–'}</td></tr>
        ${r.flags.length ? `<tr class="ts-f"><td></td><td colspan="8" class="l">${r.flags.map(x => `<span class="flag ${TIL[x.tilt]}">${x.text}</span>`).join('')}</td></tr>` : ''}`).join('')}</table></div>
      <div class="grid g2" style="margin-top:10px"><div><h3>Cross-market</h3><div class="tbl"><table><tr><th class="l">Relationship</th><th>Now</th><th>10-yr median</th><th>10-yr pct</th><th>20-day chg</th></tr>
        ${S.crush ? `<tr><td class="l">Board crush (front, $/bu)</td><td>${f(S.crush.crush)}</td><td>${f(S.crush.crush_med10)}</td><td>${ord(S.crush.crush_pct10)}</td><td>–</td></tr>
        <tr><td class="l">Oil share of crush value (%)</td><td>${f(S.crush.oil_share, 1)}</td><td>${f(S.crush.share_med10, 1)}</td><td>${ord(S.crush.share_pct10)}</td><td>–</td></tr>` : ''}
        ${S.ratios.map(x => `<tr><td class="l">${x.name} <span class="note">${x.unit}</span></td><td>${f(x.now, x.unit === 'ratio' ? 2 : 1)}</td><td>${f(x.med10, x.unit === 'ratio' ? 2 : 1)}</td><td>${ord(x.pct10)}</td><td>${sg(x.chg_20d, x.unit === 'ratio' ? 2 : 1)}</td></tr>`).join('')}</table></div></div>
        <div><h3>How to read it</h3><p class="note">Curve: nearest spread with % of full carry (storage at the CBOT tariff 0.165¢/bu/day plus interest at the ${S.rate}% T-bill) and its percentile vs the same spread at the same point in the last 15 years. Near full carry = the market is paying to store (ample supply); inverted = nearby scarcity. Funds: managed-money net and weekly change (futures only), 10-year percentile. CTA triggers: price levels where trend-following signals flip. Vol: 20-day realized volatility (percentile vs 10 years) and the 1-σ daily move. Typical catalyst move: median absolute move on that report day since 2006, with the 90th percentile. Flags are rule-based prompts for a closer look, not trade calls. ${S.generated}.</p></div></div>`;
  }

  // ── per-market view ──
  async function mount(el, sym) {
    const [R, X] = await Promise.all([getJSON(G + 'rv.json').catch(() => null), getJSON(G + 'report_reaction.json').catch(() => null)]);
    const M = R?.markets?.[sym], E = X?.markets?.[sym];
    if (!M && !E) { el.innerHTML = '<div class="card"><p class="note">Relative-value data not built yet.</p></div>'; return; }
    const V = M?.vol, U = M?.unit || '';
    const crush = (sym === 'ZS' || sym === 'ZM' || sym === 'ZL') && R.crush;
    el.innerHTML = `
      <div class="card"><h2>Calendar spreads${M?.spreads?.some(s => s.pct_full != null) ? ' and carry' : ''}</h2><div class="tbl"><table>
        <tr><th class="l">Spread</th><th>Now (${U})</th><th>$/contract</th><th>Last 60 days</th><th>5-day chg</th>${M?.spreads?.some(s => s.pct_full != null) ? '<th>Full carry</th><th>% of full carry</th><th>Hist. median % FC</th>' : ''}<th>15-yr range, same point</th><th>Percentile</th><th class="l">Read</th></tr>
        ${(M?.spreads || []).map(s => `<tr><td class="l"><b>${s.pair}</b></td><td>${f(s.spread)}</td><td>${s.usd == null ? '–' : (s.usd < 0 ? '-$' : '$') + Math.abs(s.usd).toLocaleString()}</td><td>${spark(s.path)}</td><td>${sg(s.chg_5d, 2)}</td>
          ${s.full_carry != null ? `<td>${f(s.full_carry)}</td><td><b>${s.pct_full}%</b></td><td>${s.hist_pf_med ?? '–'}%</td>` : (M.spreads.some(x => x.pct_full != null) ? '<td></td><td></td><td></td>' : '')}
          <td>${f(s.hist_min)} … ${f(s.hist_med)} … ${f(s.hist_max)}</td><td>${ord(s.pctile)}</td><td class="l sv-w">${s.read || ''}</td></tr>`).join('')}</table></div>
        <p class="note">Spread = near minus deferred. Percentile ranks today's spread against the same contract pair at the same number of days before the near contract's expiry in each of the last 15 years (higher = tighter / more inverted). ${M?.spreads?.some(s => s.pct_full != null) ? `Full carry = storage (${R.storage?.[sym] ?? 0.165}¢/bu/day, CBOT tariff; wheat at the variable-rate floor) + interest on the near price at ${R.rate}% for the days between delivery months.` : ''}</p></div>
      ${crush ? `<div class="grid g2" style="margin-top:12px"><div class="card"><h2>Board crush</h2><div class="tbl"><table><tr><th class="l">Months</th><th>Crush $/bu</th><th>Oil share</th></tr>
          ${crush.curve.map(c => `<tr><td class="l">${c.label}</td><td><b>${f(c.crush)}</b></td><td>${f(c.oil_share, 1)}%</td></tr>`).join('')}</table></div>
          <p class="note">Crush = soybean oil ¢/lb × 0.11 + meal $/st × 0.022 − soybeans $/bu. Front month ${f(crush.front.crush)} $/bu is at the ${ord(crush.front.crush_pct10)} percentile of 10 years (median ${f(crush.front.crush_med10)}); oil share ${f(crush.front.oil_share, 1)}% (${ord(crush.front.share_pct10)} pct, median ${f(crush.front.share_med10, 1)}%). Wide margins pull in crush, adding meal and oil supply and supporting bean demand.</p></div>
        <div class="card"><h2>Crush and oil share, 5 years (weekly)</h2><div style="height:260px"><canvas id="rvCrush"></canvas></div></div></div>` : ''}
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Volatility</h2>${V ? `<p>20-day realized vol <b>${V.hv20}%</b> (${ord(V.hv20_pct10)} percentile of 10 years), 60-day ${V.hv60}%. One-σ daily move ≈ <b>${f(V.day_move)} ${U}</b> (${usd(V.day_move_usd)}/contract), weekly ≈ ${f(V.week_move)} ${U}. Next month's seasonal median: ${V.next_month_med}%.</p>
          <div class="tbl"><table><tr><th>Window</th><th>Now</th><th>10th pct</th><th>Median</th><th>90th pct</th></tr>${Object.entries(V.cone).map(([n, c]) => `<tr><td>${n}-day</td><td><b>${c.now}%</b></td><td>${c.p10}%</td><td>${c.p50}%</td><td>${c.p90}%</td></tr>`).join('')}</table></div>
          <div style="height:200px;margin-top:8px"><canvas id="rvVol"></canvas></div>
          <p class="note">Vol cone: today's realized vol against its 10-year distribution for each window. Bars: median 20-day vol by calendar month (the seasonal vol curve options price); line: this year. Realized vol near the bottom of the cone into a big report has historically made owning options cheap relative to the move.</p>` : '<p class="note">Not enough history.</p>'}</div>
      </div>
        <div class="card" style="margin-top:12px"><h2>Report-day playbook</h2>${E ? `<div class="tbl"><table><tr><th class="l">Report</th><th>Since</th><th>n</th><th>Median move</th><th>× normal day</th><th>1-in-10</th><th>Typical now</th><th>Up days</th><th class="l">Last three</th></tr>
          ${Object.entries(E.reports).map(([t, x]) => `<tr><td class="l"><b>${t}</b></td><td>${x.since}</td><td>${x.n}</td><td>${x.abs_med}%</td><td><b>${x.ratio}×</b></td><td>${x.p90}%</td><td>±${f(x.exp_move)} <span class="note">${usd(x.exp_move_usd)}</span></td><td>${Math.round(x.up_share * 100)}%</td>
            <td class="l">${x.last.slice(0, 3).map(l => `${l.date.slice(2)} ${sg(l.ret, 1, '%')}`).join(' · ')}</td></tr>`).join('')}</table></div>
          ${E.wasde_sensitivity ? `<p><b>WASDE days:</b> ${E.wasde_sensitivity.note} (correlation ${E.wasde_sensitivity.corr}, ${E.wasde_sensitivity.n} reports). The surprise that moves price is vs the trade estimate, so this USDA-vs-USDA measure understates it.</p>` : ''}
          <p class="note">Close-to-close move of the front contract on each release day (next day for reports released after the livestock close), dates from USDA's report text as released. A normal day's median move is ${E.normal_abs_med}%.</p>` : '<p class="note">Not built yet.</p>'}</div>`;
    if (crush) chart('rvCrush', { type: 'line', data: { labels: crush.hist.date, datasets: [{ label: 'Crush $/bu', data: crush.hist.crush, borderColor: '#2f6b3a', borderWidth: 1.6, pointRadius: 0, yAxisID: 'y' },
      { label: 'Oil share %', data: crush.hist.share, borderColor: '#d68910', borderWidth: 1.4, pointRadius: 0, yAxisID: 'y2' }] },
      options: { scales: { y: { title: { display: true, text: '$/bu' } }, y2: { position: 'right', grid: { display: false }, title: { display: true, text: 'oil share %' } } } } });
    if (V) {
      const yr = V.hist.date.at(-1).slice(0, 4), cur = Array(12).fill(null);
      V.hist.date.forEach((d, i) => { if (d.startsWith(yr)) cur[+d.slice(5, 7) - 1] = V.hist.hv20[i]; });
      chart('rvVol', { data: { labels: MON, datasets: [{ type: 'bar', label: '10-yr median 20d vol', data: V.seasonal, backgroundColor: 'rgba(47,107,58,.25)' }, { type: 'line', label: yr, data: cur, borderColor: '#c0392b', pointRadius: 2, borderWidth: 2 }] },
        options: { scales: { y: { title: { display: true, text: '% annualized' } } } } });
    }
  }
  return { sheet, mount };
})();
