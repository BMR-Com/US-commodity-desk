// Cotton > Where it's grown: Australia section. Desk crop estimate from dam storage, planting rain and price; storages and
// rain at the cotton towns against history; crop history; published forecasts. Data: data/australia/australia.json
// (models/australia_cotton.py). Isolated: a failure here only blanks this section.
const AusCotton = (() => {
  let D = null;
  const md = s => String(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  const f = (v, d = 2) => v == null || Number.isNaN(v) ? '–' : fmt(v, d);
  const pc = v => v == null ? '–' : `${v > 0 ? '+' : ''}${fmt(v, 0)}%`;
  const pcl = v => v == null ? '–' : `${fmt(v, 0)}%`;
  const rcls = v => v == null ? '' : v < 80 ? 'dn' : v > 120 ? 'up' : '';
  const kpi = (l, v, s2) => `<div class="card kpi"><div class="lbl">${l}</div><div class="val">${v}</div><div class="sub">${s2}</div></div>`;
  const a = (u, l) => u ? `<a href="${u}" target="_blank" rel="noopener">${l} ↗</a>` : l;

  async function mount(el) {
    el.innerHTML = '<div class="card"><p class="note">Loading Australian cotton…</p></div>';
    D = await getJSON('data/australia/australia.json').catch(() => null);
    if (!D || !D.projection) { el.innerHTML = '<div class="card"><h2>Australia</h2><p class="note">Australian cotton data not built yet.</p></div>'; return; }
    const P = D.projection, dr = P.drivers, B = P.backtest;
    el.innerHTML = `
      <div class="card"><h2>Australia: desk crop estimate ${P.season}</h2>
        ${(D.brief || []).map(b => `<p><b>${b.h}.</b> ${md(b.t)}</p>`).join('')}
        <p class="note">Updated ${D.built}; drivers as of ${P.asof}. Sources: ${D.sources.join('; ')}. 1 bale = 480 lb (217.7 kg) lint. Research use only.</p></div>
      <div class="grid g4" style="margin-top:12px">
        ${kpi(`Desk crop ${P.season}`, `${f(P.m480)} m bales`, `range ${f(P.lo_m480)}–${f(P.hi_m480)} · ${f(P.lint_kt, 0)} kt lint · last season ${f(P.last_m480)} m`)}
        ${kpi('Area', `${f(P.area_kha, 0)} kha`, `last season ${f(P.last_area_kha, 0)} kha · yield ${f(P.yield_bpha, 1)} bales/ha (${f(P.yield_kg_ha, 0)} kg/ha)`)}
        ${kpi('Water in cotton dams', dr.gl != null ? `${f(dr.gl, 0)} GL` : '–', `a year ago ${f(dr.gl_last, 0)} GL · 10-season average for this date ${f(dr.gl_avg10, 0)} GL`)}
        ${kpi('Rain since 1 Aug, northern towns', dr.plant_pct != null ? pcl(dr.plant_pct) : '–', `of the ${D.rain_normal.period} average for this date · April–July ${pcl(dr.fallow_pct)}`)}
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Estimates for ${P.season}</h2><div class="tbl" id="auOthers"></div>
          <p class="note">ABARES and Cotton Australia figures are entered by hand from their releases (ABARES files sit behind a bot check). Lint converted at 217.7 kg per 480-lb bale.</p></div>
        <div class="card"><h2>Production by season (m 480-lb bales)</h2><div class="chart"><canvas id="cAuProd"></canvas></div>
          <p class="note">Cotton Australia (season ending in the year shown on its site) and USDA for seasons it has not posted. Last bar: desk estimate; whiskers in the tooltip.</p></div>
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Dam storage in the cotton valleys</h2><div class="tbl" id="auDams"></div>
          <p class="note">BOM Water Data Online, daily mean volume. % of high mark: today's volume against the 98th percentile of the dam's record since 1990 (close to full supply). * in the model's total (dams with a complete record).</p></div>
        <div class="card"><h2>Rain at the cotton towns</h2><div class="tbl" id="auRain"></div>
          <p class="note">Open-Meteo (ERA5 reanalysis, about 5 days behind) against the ${D.rain_normal.period} average for the same dates; next 16 days from the Open-Meteo forecast. Rank: 1 = driest of the seasons since 1990. North = towns where dryland cotton is grown and rain changes planting.</p></div>
      </div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Area vs water in storage at this date</h2><div class="chart"><canvas id="cAuScat"></canvas></div>
          <p class="note">Each dot is a season: dam storage on today's date that season (GL) against the area planted. Red: this season at the desk area.</p></div>
        <div class="card"><h2>How the model did: estimate at this date vs final crop</h2><div class="chart"><canvas id="cAuBt"></canvas></div><p class="note" id="auBtNote"></p></div>
      </div>
      <div class="card" style="margin-top:12px"><h2>Crop history and drivers</h2><div class="tbl" id="auHist" style="max-height:420px;overflow:auto"></div>
        <p class="note">Area: hectares planted (Cotton Australia); where marked USDA, area harvested. Drivers measured on today's date in each season.</p></div>`;
    [others, prodChart, dams, rain, scatter, backtest, hist].forEach(fn => { try { fn(); } catch (e) { console.error('australia', fn.name, e); } });
  }

  function others() {
    const P = D.projection;
    const rows = [{ source: 'Desk model', report: `as of ${P.asof}`, region: 'Australia', area_kha: P.area_kha, m480: P.m480, lint_kt: P.lint_kt, remark: `range ${f(P.lo_m480)}–${f(P.hi_m480)}` }].concat(D.others || []);
    document.getElementById('auOthers').innerHTML = `<table><tr><th class="l">Source</th><th class="l">Date</th><th class="l">Region</th><th>Area kha</th><th>Lint kt</th><th>m bales</th><th class="l">Note</th></tr>
      ${rows.map(r => `<tr><td class="l">${a(r.url, r.source)}</td><td class="l">${r.date || r.report || ''}</td><td class="l">${r.region}</td><td>${f(r.area_kha, 0)}</td><td>${f(r.lint_kt ?? (r.m480 ? r.m480 * 217.72 : null), 0)}</td><td><b>${f(r.m480)}</b></td><td class="l note">${r.remark || ''}</td></tr>`).join('')}</table>`;
  }

  function prodChart() {
    const H = D.history.filter(h => +h.season.slice(0, 4) >= 1995), P = D.projection;
    const lab = H.map(h => h.season).concat([P.season]);
    chart('cAuProd', { type: 'bar', data: { labels: lab, datasets: [
      { label: 'Production', data: H.map(h => h.m480).concat([null]), backgroundColor: '#8aa4c8' },
      { label: 'Desk estimate', data: H.map(() => null).concat([P.m480]), backgroundColor: '#c0504d' }] },
      options: { plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { afterBody: it => it[0].dataIndex === lab.length - 1 ? `Range ${f(P.lo_m480)}–${f(P.hi_m480)}` : '' } } } } });
  }

  function dams() {
    document.getElementById('auDams').innerHTML = `<table><tr><th class="l">Dam</th><th class="l">Valley</th><th>GL</th><th>% of high mark</th><th>Year ago</th><th>10-yr avg</th></tr>
      ${D.storage.map(s => `<tr><td class="l">${s.dam}${s.in_model ? '*' : ''}</td><td class="l">${s.valley || ''} <span class="note">${s.state || ''}</span></td><td><b>${f(s.gl, 0)}</b></td>
        <td class="${s.pct_high < 40 ? 'dn' : s.pct_high > 80 ? 'up' : ''}">${pcl(s.pct_high)}</td><td>${f(s.ly_gl, 0)}</td><td>${f(s.avg10_gl, 0)}</td></tr>`).join('')}
      <tr><td class="l note" colspan="6">Latest reading ${D.storage.map(s => s.date).sort().pop()}</td></tr></table>`;
  }

  function rain() {
    document.getElementById('auRain').innerHTML = `<table><tr><th class="l">Town</th><th class="l">Valley</th><th>Since 1 Aug</th><th>% avg</th><th>Rank</th><th>Last 30 d</th><th>Next 16 d</th></tr>
      ${D.rain.map(r => `<tr><td class="l">${r.label}${r.north ? '' : ' <span class="note">(south)</span>'}</td><td class="l">${r.valley || ''} <span class="note">${r.state || ''}</span></td>
        <td>${f(r.since_aug_mm, 0)} mm</td><td class="${rcls(r.since_aug_pct)}">${pcl(r.since_aug_pct)}</td><td>${r.rank ?? '–'} of ${r.years}</td>
        <td><span class="${rcls(r.last30_pct)}">${f(r.last30_mm, 0)} mm</span> <span class="note">${pcl(r.last30_pct)}</span></td>
        <td>${r.fc16_mm != null ? `${f(r.fc16_mm, 0)} mm <span class="note">${pcl(r.fc16_pct)}</span>` : '–'}</td></tr>`).join('')}
      <tr><td class="l note" colspan="7">Archive through ${D.rain.map(r => r.through).sort()[0]}</td></tr></table>`;
  }

  function scatter() {
    const H = D.history.filter(h => h.gl != null), P = D.projection;
    chart('cAuScat', { type: 'scatter', data: { datasets: [
      { label: 'Past seasons', data: H.map(h => ({ x: h.gl, y: h.area_kha, s: h.season })), backgroundColor: '#6f9fcf' },
      { label: P.season + ' (desk)', data: [{ x: P.drivers.gl, y: P.area_kha, s: P.season }], backgroundColor: '#c0504d', pointRadius: 6 }] },
      options: { plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: c => `${c.raw.s}: ${f(c.raw.x, 0)} GL, ${f(c.raw.y, 0)} kha` } } },
        scales: { x: { type: 'logarithmic', title: { display: true, text: 'GL in storage on this date' } }, y: { title: { display: true, text: 'kha planted' } } } } });
  }

  function backtest() {
    const B = D.projection.backtest, R = B.rows;
    chart('cAuBt', { type: 'bar', data: { labels: R.map(r => r.season), datasets: [
      { label: 'Final crop', data: R.map(r => r.act_m), backgroundColor: '#8aa4c8' },
      { label: 'Model at this date (season left out)', type: 'line', data: R.map(r => r.est_m), borderColor: '#c0504d', pointRadius: 3, showLine: false }] },
      options: { plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { afterBody: it => `miss ${pc(R[it[0].dataIndex].err_pct)}` } } } } });
    const A = D.projection.area_model, Y = D.projection.yield_model, N = D.names;
    document.getElementById('auBtNote').innerHTML = `Each season is estimated from a model fitted without it, using only what was known on today's date that season. Average miss ${f(B.mape_pct, 0)}% (same as last season: ${f(B.naive_mape_pct, 0)}%); 80% of misses between ${pc(B.q10_pct)} and ${pc(B.q90_pct)}, which sets the range.
      Area variables: ${A.vars.map(v => N[v]).join(', ')} (${A.n} seasons; alternatives tried: ${A.alternatives.map(x => `${x.vars.map(v => N[v]).join(' + ')} ${f(x.loo_rmse_log * 100, 0)}%`).join('; ')}).
      Yield variables: ${Y.vars.map(v => N[v]).join(', ')} (miss ${f(Y.loo_rmse, 2)} bales/ha).`;
  }

  function hist() {
    const H = D.history.slice().reverse();
    document.getElementById('auHist').innerHTML = `<table><tr><th class="l">Season</th><th>Area kha</th><th>m bales</th><th>Bales/ha</th><th>USDA m bales</th><th>Dams GL</th><th>Rain since 1 Aug</th><th>Apr–Jul rain</th><th class="l">Source</th></tr>
      ${H.map(h => `<tr><td class="l">${h.season}</td><td>${f(h.area_kha, 0)}</td><td><b>${f(h.m480)}</b></td><td>${f(h.yield_bpha, 1)}</td><td>${f(h.psd_m480)}</td><td>${f(h.gl, 0)}</td>
        <td class="${rcls(h.plant_pct)}">${pcl(h.plant_pct)}</td><td class="${rcls(h.fallow_pct)}">${pcl(h.fallow_pct)}</td><td class="l note">${h.src || ''}</td></tr>`).join('')}</table>`;
  }

  return { mount };
})();
