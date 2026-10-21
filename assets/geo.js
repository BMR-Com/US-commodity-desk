// Geography, trade & weather primer: world and US production maps, trade-flow map, export tables,
// crop-region weather vs history, US drought, and weather websites. Geo.mount(el, ['corn']) or several keys (picker).
const Geo = (() => {
  const LIB = ['https://cdn.jsdelivr.net/npm/d3@7.8.5/dist/d3.min.js', 'https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js'];
  let libs = null, world = null, us = null, WX = null;
  const cache = {};
  const load = src => new Promise((ok, no) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = no; document.head.appendChild(s); });
  async function ready() {
    if (!libs) libs = (async () => { for (const s of LIB) if (!(s.includes('/d3@') ? window.d3 : window.topojson)) await load(s); })();
    await libs;
    if (!world) world = await fetch('https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json').then(r => r.json());
    if (!us) us = await fetch('https://cdn.jsdelivr.net/npm/us-atlas@3.0.1/states-10m.json').then(r => r.json());
    if (!WX) WX = await getJSON('data/geo/weather.json').catch(() => ({ regions: [] }));
  }
  const n0 = v => v == null ? '–' : Math.round(v).toLocaleString();
  const n1 = v => v == null ? '–' : (+v).toLocaleString(undefined, { maximumFractionDigits: 1 });
  const pct = (a, b) => a == null || !b ? '–' : `${a / b * 100 - 100 > 0 ? '+' : ''}${(a / b * 100 - 100).toFixed(0)}%`;
  const cls = v => v > 0 ? 'up' : v < 0 ? 'dn' : '';
  const ord = v => v == null ? '–' : v + (v % 100 >= 11 && v % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[v % 10] || 'th'));
  const pcol = p => p == null ? '' : p <= 20 ? 'dn' : p >= 80 ? 'up' : '';
  const green = t => d3.interpolateRgb('#dcefdc', '#0f5a2a')(Math.max(0, Math.min(1, t)));

  function worldMap(svgEl, G) {
    const W = 960, H = 470, svg = d3.select(svgEl).attr('viewBox', `0 0 ${W} ${H}`);
    const feats = topojson.feature(world, world.objects.countries).features.filter(f => f.id !== '010');
    const proj = d3.geoNaturalEarth1().fitSize([W, H], { type: 'FeatureCollection', features: feats }), path = d3.geoPath(proj);
    const share = {}, info = {};
    for (const p of G.production) if (p.mapped) for (const id of [].concat(p.iso || [])) { share[+id] = p.share; info[+id] = p; }
    const max = Math.max(...G.production.map(p => p.share));
    svg.append('g').selectAll('path').data(feats).join('path').attr('d', path).attr('fill', f => share[+f.id] != null ? green(share[+f.id] / max) : '#eceee9')
      .attr('stroke', '#fff').attr('stroke-width', .5).append('title').text(f => info[+f.id] ? `${info[+f.id].country}: ${n1(info[+f.id].value)} (${info[+f.id].share}% of world)` : (f.properties.name));
    // labels for mapped producers
    const lab = svg.append('g');
    for (const p of G.production.filter(p => p.mapped)) {
      const ids = [].concat(p.iso || []).map(Number); const f = feats.find(f => +f.id === (p.country === 'European Union' ? 276 : ids[0])); if (!f) continue;
      const [x, y] = path.centroid(f);
      lab.append('text').attr('x', x).attr('y', y).attr('text-anchor', 'middle').attr('class', 'geo-lbl').text(`${p.country === 'European Union' ? 'EU' : p.country} ${p.share}%`);
    }
    return { proj, path, feats };
  }
  function flowMap(svgEl, G) {
    const m = worldMap(svgEl, { production: [] }), svg = d3.select(svgEl);
    const cen = iso => { const ids = [].concat(iso || []).map(Number); const id = ids.length > 1 ? 276 : ids[0]; const f = m.feats.find(f => +f.id === id); return f ? m.path.centroid(f) : null; };
    const fl = G.flows.filter(f => f.from_iso && f.to_iso).sort((a, b) => b.t - a.t).slice(0, 30);
    const max = Math.max(...fl.map(f => f.t), 1);
    const exps = [...new Set(fl.map(f => f.from))];
    const col = d3.scaleOrdinal(exps, ['#2f6db3', '#c48a1c', '#b8452f', '#3a8a5a', '#7a4fa0', '#6b6b6b']);
    svg.append('defs').selectAll('marker').data(exps).join('marker').attr('id', (d, i) => 'geoArr' + i).attr('viewBox', '0 0 10 10').attr('refX', 9).attr('refY', 5)
      .attr('markerUnits', 'userSpaceOnUse').attr('markerWidth', 11).attr('markerHeight', 11).attr('orient', 'auto').append('path').attr('d', 'M0,0L10,5L0,10z').attr('fill', d => col(d));
    const g = svg.append('g');
    let nl = 0;
    for (const f of fl) {
      const a = cen(f.from_iso), b = cen(f.to_iso); if (!a || !b) continue;
      const dx = b[0] - a[0], dy = b[1] - a[1], dr = Math.hypot(dx, dy) * 1.2;
      g.append('path').attr('d', `M${a[0]},${a[1]}A${dr},${dr} 0 0,1 ${b[0]},${b[1]}`).attr('fill', 'none').attr('stroke', col(f.from)).attr('stroke-opacity', .75)
        .attr('stroke-width', 1 + 7 * Math.sqrt(f.t / max)).attr('marker-end', `url(#geoArr${exps.indexOf(f.from)})`)
        .append('title').text(`${f.from} → ${f.to}: ${n0(f.t / 1000)} kt (${f.year}), $${n0(f.usd / 1e6)}m`);
      if (f.t >= max * 0.25 && nl++ < 6) g.append('text').attr('x', (a[0] + b[0]) / 2).attr('y', (a[1] + b[1]) / 2 - 4).attr('class', 'geo-flow').text(`${n0(f.t / 1000)} kt`);
    }
    for (const e of exps) { const c = cen(fl.find(f => f.from === e).from_iso); if (c) g.append('circle').attr('cx', c[0]).attr('cy', c[1]).attr('r', 5).attr('fill', col(e)).attr('stroke', '#fff'); }
    return exps.map(e => `<span class="geo-key"><i style="background:${col(e)}"></i>${e}</span>`).join(' ');
  }
  function usMap(svgEl, S) {
    const W = 960, H = 560, svg = d3.select(svgEl).attr('viewBox', `0 0 ${W} ${H}`);
    const feats = topojson.feature(us, us.objects.states).features;
    const proj = d3.geoAlbersUsa().fitSize([W, H], { type: 'FeatureCollection', features: feats }), path = d3.geoPath(proj);
    const by = Object.fromEntries(S.states.map(s => [s.fips, s])), max = Math.max(...S.states.map(s => s.share));
    svg.append('g').selectAll('path').data(feats).join('path').attr('d', path).attr('fill', f => by[f.id] ? green(Math.sqrt(by[f.id].share / max)) : '#eceee9')
      .attr('stroke', '#fff').attr('stroke-width', .7).append('title').text(f => by[f.id] ? `${by[f.id].state}: ${n0(by[f.id].value)} (${by[f.id].share}%)` : f.properties.name);
    const lab = svg.append('g');
    for (const f of feats) { const s = by[f.id]; if (!s || s.share < 3) continue; const [x, y] = path.centroid(f); if (isNaN(x)) continue;
      lab.append('text').attr('x', x).attr('y', y).attr('text-anchor', 'middle').attr('class', 'geo-lbl').text(`${s.abbr} ${s.share}%`); }
  }
  function wxRow(r) {
    const pn = (v, n, p) => v == null ? '–' : `${n0(v)} mm${n ? ` <span class="note">(${pct(v, n)} vs avg)</span>` : ''}${p != null ? ` <span class="${pcol(p)}">${ord(p)} pct</span>` : ''}`;
    return `<tr><td class="l"><b>${r.name}</b><br><span class="note">${r.country} · ${r.note}</span></td>
      <td>${pn(r.r30, r.r30_n, r.r30_p)}</td><td>${pn(r.r60, r.r60_n, r.r60_p)}</td><td>${pn(r.rstd, r.rstd_n, r.rstd_p)}<br><span class="note">since ${r.season_from.slice(5)}</span></td>
      <td>${r.wb60 == null ? '–' : n0(r.wb60) + ' mm'}${r.wb60_p != null ? ` <span class="${pcol(r.wb60_p)}">${ord(r.wb60_p)}</span>` : ''}</td>
      <td>${r.tmax30 == null ? '–' : r.tmax30.toFixed(1) + '°C'}${r.tmax30_n != null ? ` <span class="${(r.tmax30 - r.tmax30_n) > 1.5 ? 'dn' : ''}">(${(r.tmax30 - r.tmax30_n > 0 ? '+' : '') + (r.tmax30 - r.tmax30_n).toFixed(1)})</span>` : ''}<br><span class="note">${r.hot30} hot days${r.hot30_n != null ? ` (avg ${r.hot30_n.toFixed(0)})` : ''}</span></td>
      <td>${r.sm100_p != null ? `<span class="${pcol(r.sm100_p)}">${ord(r.sm100_p)} pct</span>` : '–'}<br><span class="note">top 7 cm ${r.sm7_p != null ? ord(r.sm7_p) : '–'}</span></td>
      <td>${pn(r.f16_rain, r.f16_rain_n, r.f16_rain_p)}<br><span class="note">Tmax ${r.f16_tmax == null ? '–' : r.f16_tmax.toFixed(1) + '°C'}</span></td>
      <td class="l">${r.history ? (r.flags.join('; ') || 'near normal') : '<span class="note">15-year history loading (added a few regions a day)</span>'}</td></tr>`;
  }
  function wxCharts(el, regs) {
    if (!window.Chart) return;
    el.innerHTML = regs.filter(r => r.chart_rain || r.chart_sm).map(r => `<div class="geo-ch"><h4>${r.name} <span class="note">${r.country}</span></h4><canvas id="gr-${r.id}" height="150"></canvas><canvas id="gs-${r.id}" height="120"></canvas></div>`).join('') || '<p class="note">Charts appear once a region\'s history has loaded.</p>';
    for (const r of regs) {
      if (r.chart_rain) { const c = r.chart_rain, lb = c.weeks.map(w => 'wk ' + (w + 1));
        new Chart(el.querySelector('#gr-' + r.id), { type: 'line', data: { labels: lb, datasets: [
          { label: 'this season', data: c.cur, borderColor: '#2f6db3', borderWidth: 2, pointRadius: 0 },
          { label: 'average', data: c.mean, borderColor: '#8a8984', borderDash: [4, 3], pointRadius: 0 },
          { label: '10th pct', data: c.p10, borderColor: 'rgba(184,69,47,.5)', pointRadius: 0, borderWidth: 1 },
          { label: '90th pct', data: c.p90, borderColor: 'rgba(58,138,90,.5)', pointRadius: 0, borderWidth: 1, fill: '-1', backgroundColor: 'rgba(138,137,132,.12)' }] },
          options: { plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } }, title: { display: true, text: `cumulative rain since ${r.season_from} (mm)`, font: { size: 11 } } }, scales: { x: { ticks: { maxTicksLimit: 8 } } } } }); }
      if (r.chart_sm) { const c = r.chart_sm;
        new Chart(el.querySelector('#gs-' + r.id), { type: 'line', data: { labels: c.dates, datasets: [
          { label: 'root-zone soil moisture', data: c.cur, borderColor: '#7a4fa0', borderWidth: 2, pointRadius: 0 },
          { label: 'p10', data: c.p10, borderColor: 'rgba(138,137,132,.4)', pointRadius: 0, borderWidth: 1 },
          { label: 'p90', data: c.p90, borderColor: 'rgba(138,137,132,.4)', pointRadius: 0, borderWidth: 1, fill: '-1', backgroundColor: 'rgba(138,137,132,.12)' }] },
          options: { plugins: { legend: { display: false }, title: { display: true, text: '28–100 cm soil moisture (m³/m³), last 52 weeks vs 2011–25 10th–90th pct', font: { size: 11 } } }, scales: { x: { ticks: { maxTicksLimit: 6 } } } } }); }
    }
  }
  async function render(el, key) {
    el.innerHTML = '<p class="note">Loading maps…</p>';
    try { await ready(); } catch (e) { el.innerHTML = '<p class="note">Map libraries could not load.</p>'; return; }
    const G = cache[key] || (cache[key] = await getJSON(`data/geo/${key}.json`).catch(() => null));
    if (!G) { el.innerHTML = '<p class="note">Geography data not built yet for this commodity.</p>'; return; }
    const regs = WX.regions.filter(r => G.weather_regions.includes(r.id));
    const unit = (G.unit || '').replace(/[()]/g, '');
    const usd = G.us_dest;
    const destTbl = (d, lbl) => !d ? '' : `<h3>${lbl} <span class="note">${d.measure}${d.my ? `, marketing year ${d.my - 1}/${String(d.my).slice(2)}` : ''}${d.week ? ` (week ending ${d.week})` : ''}${d.year ? `, ${d.year}` : ''}</span></h3>
      <div class="tbl"><table><tr><th class="l">#</th><th class="l">Destination</th><th>Quantity</th><th>Share</th></tr>${d.top.map((x, i) => `<tr><td class="l">${i + 1}</td><td class="l">${x.country}</td><td>${n0(x.value)}</td><td>${x.share ?? '–'}%</td></tr>`).join('')}
      ${d.unknown ? `<tr><td></td><td class="l note">Unknown destinations</td><td class="note">${n0(d.unknown)}</td><td class="note">${n1(d.unknown / d.total * 100)}%</td></tr>` : ''}</table></div>`;
    el.innerHTML = `
      <div class="card"><h2>Where ${G.name.toLowerCase()} is produced <span class="note">USDA PSD, market year ${G.my}/${String(G.my + 1).slice(2)}, ${unit}</span></h2>
        <div class="geo-wrap"><svg class="geo-map" id="geoW"></svg>
        <div><p class="note">Shaded: countries with at least ${G.threshold}% of world output (darker = larger share). World total ${n1(G.world)} ${unit}.</p>
        <div class="tbl"><table><tr><th class="l">Country</th><th>Production</th><th>Share</th><th>vs last yr</th><th>vs 5-yr avg</th></tr>
        ${G.production.map(p => `<tr class="${p.mapped ? '' : 'note'}"><td class="l">${p.mapped ? '<b>' + p.country + '</b>' : p.country}</td><td>${n1(p.value)}</td><td>${p.share}%</td><td class="${cls(p.value - p.prev)}">${pct(p.value, p.prev)}</td><td class="${cls(p.value - p.avg5)}">${pct(p.value, p.avg5)}</td></tr>`).join('')}</table></div></div></div></div>
      ${G.us_states ? `<div class="card" style="margin-top:12px"><h2>United States by state <span class="note">USDA NASS ${G.us_states.year}: ${G.us_states.what.toLowerCase()}</span></h2>
        <div class="geo-wrap"><svg class="geo-map" id="geoU"></svg><div class="tbl"><table><tr><th class="l">State</th><th>${G.us_states.unit.toLowerCase()}</th><th>Share</th></tr>
        ${G.us_states.states.slice(0, 12).map(s => `<tr><td class="l">${s.state}</td><td>${n0(s.value)}</td><td>${s.share}%</td></tr>`).join('')}</table></div></div></div>` : ''}
      <div class="card" style="margin-top:12px"><h2>Trade flows <span class="note">top exporters' shipments by destination, UN Comtrade ${G.flows_year || ''}, thousand tonnes</span></h2>
        ${G.flows.length ? `<svg class="geo-map" id="geoF"></svg><div id="geoFK" class="note"></div>` : (key === 'milk' ? '<p class="note">Fluid milk is hardly traded across borders; see Cheese, Butter and Nonfat dry milk for dairy trade flows.</p>' : '<p class="note">Bilateral flow data loading (UN Comtrade is rate-limited; filled in over the next runs).</p>')}
        <div class="grid g2" style="margin-top:8px"><div><h3>Top 5 exporters <span class="note">PSD ${G.my}/${String(G.my + 1).slice(2)}, ${unit}</span></h3><div class="tbl"><table><tr><th class="l">Exporter</th><th>Exports</th><th>Share of world</th><th>Last yr</th></tr>
          ${G.exporters.map(e => `<tr><td class="l">${e.country}</td><td>${n1(e.value)}</td><td>${e.share}%</td><td>${n1(e.prev)}</td></tr>`).join('')}</table></div>
          <h3>Top importers</h3><div class="tbl"><table><tr><th class="l">Importer</th><th>Imports</th><th>Share</th><th>Last yr</th></tr>
          ${G.importers.map(e => `<tr><td class="l">${e.country}</td><td>${n1(e.value)}</td><td>${e.share}%</td><td>${n1(e.prev)}</td></tr>`).join('')}</table></div></div>
          <div>${usd ? destTbl(usd.last_my, 'US exports: top 10 destinations') + destTbl(usd.current_my, 'US current season: top 10 buyers') + destTbl(usd.comtrade, 'US exports: top 10 destinations') : '<p class="note">US destination data not available yet.</p>'}
          ${usd && (usd.last_my || usd.current_my) ? '<p class="note">Source: USDA FAS weekly Export Sales. Units: metric tons (cotton: running bales).</p>' : ''}</div></div></div>
      <div class="card" style="margin-top:12px"><h2>Weather in the regions that matter <span class="note">Open-Meteo; vs ${WX.history || '2011–2025'}; data through ${regs[0] ? regs[0].data_through : '–'}</span></h2>
        <p class="note">Countries with at least ${G.threshold}% of world output or a top-5 export share. Percentiles rank this year against the same dates in 2011–2025 (10th = drier/lower than 9 in 10 years). Water balance = rain minus reference evapotranspiration. Irrigated areas (Xinjiang, Punjab) depend more on heat and water supply than on rain.</p>
        <div class="tbl"><table><tr><th class="l">Region</th><th>Rain 30 d</th><th>Rain 60 d</th><th>Season to date</th><th>Water bal. 60 d</th><th>Max temp 30 d (anom)</th><th>Soil moisture</th><th>Next 16 d rain</th><th class="l">Read</th></tr>
        ${regs.map(wxRow).join('') || '<tr><td colspan="9" class="note">Weather data loading.</td></tr>'}</table></div>
        <details style="margin-top:8px"><summary><b>Charts: season rain and soil moisture vs history</b></summary><div class="geo-chs" id="geoCh"></div></details></div>
      ${G.usdm ? `<div class="card" style="margin-top:12px"><h2>United States: drought in the producing states <span class="note">U.S. Drought Monitor, % of state area</span></h2>
        <div class="grid g2"><div class="tbl"><table><tr><th class="l">State</th><th>D1+ now</th><th>D2+ now</th><th>D1+ month ago</th></tr>
        ${Object.entries(G.usdm.latest).map(([s, r]) => `<tr><td class="l">${s}</td><td class="${r[3] > 30 ? 'dn' : ''}">${n1(r[3])}%</td><td>${n1(r[4])}%</td><td>${n1(G.usdm.month_ago[s][3])}%</td></tr>`).join('')}
        ${G.usdm.conus ? `<tr><td class="l note">Lower 48</td><td>${n1(G.usdm.conus[3])}%</td><td>${n1(G.usdm.conus[4])}%</td><td></td></tr>` : ''}</table>
        <p class="note">Week of ${Object.values(G.usdm.latest)[0]?.[0] || ''}. D1 moderate, D2 severe drought.</p></div>
        <div><img class="geo-img" src="https://droughtmonitor.unl.edu/data/png/current/current_usdm.png" alt="Current US Drought Monitor map" loading="lazy">
        <img class="geo-img" src="https://www.cpc.ncep.noaa.gov/products/predictions/814day/814prcp.new.gif" alt="CPC 8-14 day precipitation outlook" loading="lazy">
        <img class="geo-img" src="https://www.cpc.ncep.noaa.gov/products/Soilmst_Monitoring/Figures/daily/curr.w.anom.daily.gif" alt="CPC soil moisture anomaly" loading="lazy">
        <p class="note">Live images from the Drought Monitor and NOAA CPC (8–14 day rain outlook, soil moisture anomaly).</p></div></div></div>` : ''}
      <div class="card" style="margin-top:12px"><h2>Weather and crop websites to track</h2><div class="grid g2">
        ${G.links.map(c => `<div><h3>${c.country}</h3><ul>${c.links.map(l => `<li><a href="${l.url}" target="_blank" rel="noopener">${l.name}</a> <span class="note">${l.what}</span></li>`).join('')}</ul></div>`).join('')}
        <div><h3>Global</h3><ul>${G.links_common.map(l => `<li><a href="${l.url}" target="_blank" rel="noopener">${l.name}</a> <span class="note">${l.what}</span></li>`).join('')}</ul></div></div>
        <p class="note">${G.sources}. Built ${G.generated}.</p></div>`;
    worldMap(el.querySelector('#geoW'), G);
    if (G.us_states) usMap(el.querySelector('#geoU'), G.us_states);
    if (G.flows.length) el.querySelector('#geoFK').innerHTML = flowMap(el.querySelector('#geoF'), G);
    const det = el.querySelector('details'); det.addEventListener('toggle', () => { if (det.open && !det.dataset.done) { det.dataset.done = 1; wxCharts(el.querySelector('#geoCh'), regs); } });
  }
  function mount(el, keys, labels) {
    keys = [].concat(keys);
    if (keys.length === 1) return render(el, keys[0]);
    el.innerHTML = `<div class="mk-bar" style="margin:0 0 8px">${keys.map((k, i) => `<button data-g="${k}" class="${i ? '' : 'on'}">${(labels || keys)[i]}</button>`).join('')}</div><div id="geoBody"></div>`;
    const body = el.querySelector('#geoBody');
    el.querySelectorAll('[data-g]').forEach(b => b.onclick = () => { el.querySelectorAll('[data-g]').forEach(x => x.classList.toggle('on', x === b)); render(body, b.dataset.g); });
    render(body, keys[0]);
  }
  return { mount };
})();
