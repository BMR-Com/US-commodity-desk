// Energy geography: world production map, trade-flow arrows, US production by state, US export destinations,
// US LNG export terminals (bubble map) and refining capacity. Data: data/energy/geo/<key>.json (models/energy_geo.py).
const EnergyGeo = (() => {
  const LIB = ['https://cdn.jsdelivr.net/npm/d3@7.8.5/dist/d3.min.js', 'https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js'];
  const KEYS = [['crude', 'Crude oil'], ['natgas', 'Natural gas & LNG'], ['products', 'Diesel & gasoline']];
  let libs = null, world = null, us = null, key = 'crude';
  const cache = {};
  const load = src => new Promise((ok, no) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = no; document.head.appendChild(s); });
  async function ready() {
    if (!libs) libs = (async () => { for (const s of LIB) if (!(s.includes('/d3@') ? window.d3 : window.topojson)) await load(s); })();
    await libs;
    if (!world) world = await fetch('https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json').then(r => r.json());
    if (!us) us = await fetch('https://cdn.jsdelivr.net/npm/us-atlas@3.0.1/states-10m.json').then(r => r.json());
  }
  const n0 = v => v == null ? '–' : Math.round(v).toLocaleString();
  const n1 = v => v == null ? '–' : (+v).toLocaleString(undefined, { maximumFractionDigits: 1 });
  const pct = (a, b) => a == null || !b ? '–' : `${a / b * 100 - 100 > 0 ? '+' : ''}${(a / b * 100 - 100).toFixed(0)}%`;
  const cls = v => v > 0 ? 'up' : v < 0 ? 'dn' : '';
  const shade = t => d3.interpolateRgb('#fde9c8', '#8a3b06')(Math.max(0, Math.min(1, t)));
  function worldMap(svgEl, prod) {
    const W = 960, H = 470, svg = d3.select(svgEl).attr('viewBox', `0 0 ${W} ${H}`);
    const feats = topojson.feature(world, world.objects.countries).features.filter(f => f.id !== '010');
    const proj = d3.geoNaturalEarth1().fitSize([W, H], { type: 'FeatureCollection', features: feats }), path = d3.geoPath(proj);
    const by = {}; for (const p of prod || []) if (p.mapped && p.iso) by[+p.iso] = p;
    const max = Math.max(1, ...(prod || []).map(p => p.share));
    svg.append('g').selectAll('path').data(feats).join('path').attr('d', path).attr('fill', f => by[+f.id] ? shade(by[+f.id].share / max) : '#eceee9')
      .attr('stroke', '#fff').attr('stroke-width', .5).append('title').text(f => by[+f.id] ? `${by[+f.id].country}: ${n1(by[+f.id].value)} (${by[+f.id].share}%)` : f.properties.name);
    const lab = svg.append('g');
    for (const p of (prod || []).filter(p => p.mapped && p.iso)) { const f = feats.find(f => +f.id === +p.iso); if (!f) continue; const [x, y] = path.centroid(f);
      lab.append('text').attr('x', x).attr('y', y).attr('text-anchor', 'middle').attr('class', 'geo-lbl').text(`${p.short || p.country} ${p.share}%`); }
    return { feats, path };
  }
  function flowMap(svgEl, flows) {
    const m = worldMap(svgEl, []), svg = d3.select(svgEl);
    const cen = iso => { const f = m.feats.find(f => +f.id === +iso); return f ? m.path.centroid(f) : null; };
    const fl = flows.filter(f => f.from_iso && f.to_iso).sort((a, b) => b.t - a.t).slice(0, 32), max = Math.max(...fl.map(f => f.t), 1);
    const exps = [...new Set(fl.map(f => f.from))];
    const col = d3.scaleOrdinal(exps, ['#b8452f', '#2f6db3', '#c48a1c', '#3a8a5a', '#7a4fa0', '#6b6b6b', '#1f9e9e', '#8c564b', '#e377c2']);
    svg.append('defs').selectAll('marker').data(exps).join('marker').attr('id', (d, i) => 'egArr' + i).attr('viewBox', '0 0 10 10').attr('refX', 9).attr('refY', 5)
      .attr('markerUnits', 'userSpaceOnUse').attr('markerWidth', 11).attr('markerHeight', 11).attr('orient', 'auto').append('path').attr('d', 'M0,0L10,5L0,10z').attr('fill', d => col(d));
    const g = svg.append('g'); let nl = 0;
    for (const f of fl) { const a = cen(f.from_iso), b = cen(f.to_iso); if (!a || !b || isNaN(a[0]) || isNaN(b[0])) continue;
      const dr = Math.hypot(b[0] - a[0], b[1] - a[1]) * 1.2;
      g.append('path').attr('d', `M${a[0]},${a[1]}A${dr},${dr} 0 0,1 ${b[0]},${b[1]}`).attr('fill', 'none').attr('stroke', col(f.from)).attr('stroke-opacity', .75)
        .attr('stroke-width', 1 + 7 * Math.sqrt(f.t / max)).attr('marker-end', `url(#egArr${exps.indexOf(f.from)})`).append('title').text(`${f.from} → ${f.to}: ${n0(f.t)} kt (${f.year}), $${n0(f.usd / 1e6)}m`);
      if (f.t >= max * .3 && nl++ < 6) g.append('text').attr('x', (a[0] + b[0]) / 2).attr('y', (a[1] + b[1]) / 2 - 4).attr('class', 'geo-flow').text(`${n0(f.t / 1000)} Mt`); }
    return exps.map(e => `<span class="geo-key"><i style="background:${col(e)}"></i>${e}</span>`).join(' ');
  }
  function usMap(svgEl, S, pts) {
    const W = 960, H = 560, svg = d3.select(svgEl).attr('viewBox', `0 0 ${W} ${H}`);
    const feats = topojson.feature(us, us.objects.states).features;
    const proj = d3.geoAlbersUsa().fitSize([W, H], { type: 'FeatureCollection', features: feats }), path = d3.geoPath(proj);
    const by = Object.fromEntries((S ? S.states : []).map(s => [s.fips, s])), max = Math.max(1, ...(S ? S.states : []).map(s => s.share));
    svg.append('g').selectAll('path').data(feats).join('path').attr('d', path).attr('fill', f => by[f.id] ? shade(Math.sqrt(by[f.id].share / max)) : '#eceee9')
      .attr('stroke', '#fff').attr('stroke-width', .7).append('title').text(f => by[f.id] ? `${by[f.id].state}: ${n0(by[f.id].value)} ${S.unit} (${by[f.id].share}%)` : f.properties.name);
    const lab = svg.append('g');
    for (const f of feats) { const s = by[f.id]; if (!s || s.share < 3) continue; const [x, y] = path.centroid(f); if (isNaN(x)) continue;
      lab.append('text').attr('x', x).attr('y', y).attr('text-anchor', 'middle').attr('class', 'geo-lbl').text(`${s.abbr} ${s.share}%`); }
    if (pts && pts.length) {
      const pmax = Math.max(1, ...pts.map(p => p.value || 0)), g = svg.append('g');
      for (const p of pts) { const xy = proj([p.lon, p.lat]); if (!xy) continue;
        g.append('circle').attr('cx', xy[0]).attr('cy', xy[1]).attr('r', 4 + 18 * Math.sqrt((p.value || 0) / pmax)).attr('fill', 'rgba(47,109,179,.55)').attr('stroke', '#1d4f8a')
          .append('title').text(`${p.name}: ${n1(p.value)} ${p.unit || ''}`);
        g.append('text').attr('x', xy[0] + 8).attr('y', xy[1] - 6).attr('class', 'geo-lbl').attr('text-anchor', 'start').text(p.short || p.name); }
    }
  }
  const tbl = (head, rows) => `<div class="tbl"><table><tr>${head.map((h, i) => `<th class="${i ? '' : 'l'}">${h}</th>`).join('')}</tr>${rows.join('')}</table></div>`;
  async function render(el) {
    el.innerHTML = '<p class="note">Loading maps…</p>';
    try { await ready(); } catch (e) { el.innerHTML = '<p class="note">Map libraries could not load.</p>'; return; }
    const G = cache[key] || (cache[key] = await getJSON(`data/energy/geo/${key}.json`).catch(() => null));
    if (!G) { el.innerHTML = '<p class="note">Energy geography not built yet (runs weekly; first build pending).</p>'; return; }
    const prod = G.production || [];
    el.innerHTML = `
      <div class="card"><h2>${G.prod_title || `Where ${G.name.toLowerCase()} is produced`} <span class="note">${G.prod_source}, ${G.year}, ${G.unit}</span></h2>
        <div class="geo-wrap"><svg class="geo-map" id="egW"></svg><div><p class="note">Shaded: countries with at least ${G.threshold}% of the world total (darker = larger). World ${n1(G.world)} ${G.unit}.</p>
        ${tbl(['Country', 'Production', 'Share', 'vs last yr', 'vs 5-yr avg'], prod.map(p => `<tr class="${p.mapped ? '' : 'note'}"><td class="l">${p.mapped ? '<b>' + p.country + '</b>' : p.country}</td><td>${n1(p.value)}</td><td>${p.share}%</td><td class="${cls(p.value - p.prev)}">${pct(p.value, p.prev)}</td><td class="${cls(p.value - p.avg5)}">${pct(p.value, p.avg5)}</td></tr>`))}</div></div></div>
      ${G.us_states ? `<div class="card" style="margin-top:12px"><h2>United States: ${G.us_states.what} <span class="note">${G.us_states.source}, ${G.us_states.period}</span></h2>
        <div class="geo-wrap"><svg class="geo-map" id="egU"></svg><div>${tbl(['State', G.us_states.unit, 'Share', 'vs year ago'], G.us_states.states.slice(0, 14).map(s => `<tr><td class="l">${s.state}</td><td>${n0(s.value)}</td><td>${s.share}%</td><td class="${cls(s.value - s.prev)}">${pct(s.value, s.prev)}</td></tr>`))}
        <p class="note">US total ${n0(G.us_states.total)} ${G.us_states.unit}${G.us_states.offshore ? `; Federal offshore Gulf ${n0(G.us_states.offshore)} (not shown on the map)` : ''}.</p></div></div></div>` : ''}
      ${G.terminals ? `<div class="card" style="margin-top:12px"><h2>US LNG export terminals <span class="note">EIA exports by point of exit, last 12 months to ${G.terminals.through}, Bcf (bubble size)</span></h2>
        <div class="geo-wrap"><svg class="geo-map" id="egL"></svg><div>${tbl(['Terminal', 'Last 12 m (Bcf)', 'Latest month (Bcf)', 'Share', 'Top buyers (12 m)'], G.terminals.rows.map(t => `<tr><td class="l"><b>${t.name}</b></td><td>${n1(t.value)}</td><td>${n1(t.last)}</td><td>${t.share}%</td><td class="l note">${t.top.join(', ')}</td></tr>`))}
        <p class="note">Total LNG exports, last 12 months: ${n1(G.terminals.total)} Bcf (≈${n1(G.terminals.total / 365)} Bcf/d). ${G.terminals.note || ''}</p></div></div>
        ${G.pipeline ? `<h3>Pipeline exports by border crossing (last 12 months, Bcf)</h3>${tbl(['Crossing', 'To', 'Bcf'], G.pipeline.slice(0, 10).map(p => `<tr><td class="l">${p.name}</td><td>${p.to}</td><td>${n1(p.value)}</td></tr>`))}` : ''}</div>` : ''}
      ${G.refining ? `<div class="card" style="margin-top:12px"><h2>US refining capacity by state <span class="note">EIA operable atmospheric crude distillation capacity, Jan 1 ${G.refining.period}, thousand b/d</span></h2>
        <div class="geo-wrap"><svg class="geo-map" id="egR"></svg><div>${tbl(['State', 'Capacity (kb/d)', 'Share'], G.refining.states.slice(0, 14).map(s => `<tr><td class="l">${s.state}</td><td>${n0(s.value)}</td><td>${s.share}%</td></tr>`))}
        <p class="note">US total ${n0(G.refining.total)} kb/d. The Gulf Coast (Texas, Louisiana) holds over half of US capacity, so hurricanes there move diesel and gasoline cracks.</p></div></div></div>` : ''}
      <div class="card" style="margin-top:12px"><h2>Trade flows <span class="note">${G.flows_label || ''}</span></h2>
        ${G.flows && G.flows.length ? `<svg class="geo-map" id="egF"></svg><div id="egFK" class="note"></div>` : '<p class="note">Bilateral flow data loading (UN Comtrade is rate-limited; filled in over the next weekly runs).</p>'}
        <div class="grid g2" style="margin-top:8px"><div><h3>Main exporters <span class="note">${G.exporters_label || ''}</span></h3>
          ${tbl(['Exporter', 'Exports', 'Year'], (G.exporters || []).map(e => `<tr><td class="l">${e.country}</td><td>${n0(e.value)} ${e.unit || ''}</td><td>${e.year}</td></tr>`))}</div>
          <div>${(G.us_dest || []).map(d => `<h3>${d.title} <span class="note">${d.source}, ${d.period}, ${d.unit}</span></h3>${tbl(['#', 'Destination', 'Quantity', 'Share'], d.top.map((x, i) => `<tr><td class="l">${i + 1}</td><td class="l">${x.country}</td><td>${n1(x.value)}</td><td>${x.share}%</td></tr>`))}`).join('') || '<p class="note">US destination data loading.</p>'}</div></div></div>
      <div class="card" style="margin-top:12px"><h2>Websites to track</h2><ul>${(G.links || []).map(l => `<li><a href="${l.url}" target="_blank" rel="noopener">${l.name}</a> <span class="note">${l.what}</span></li>`).join('')}</ul>
        <p class="note">${G.sources || ''} Built ${G.generated}.</p></div>`;
    worldMap(el.querySelector('#egW'), prod);
    if (G.us_states) usMap(el.querySelector('#egU'), G.us_states);
    if (G.terminals) usMap(el.querySelector('#egL'), null, G.terminals.rows);
    if (G.refining) usMap(el.querySelector('#egR'), G.refining);
    if (G.flows && G.flows.length) el.querySelector('#egFK').innerHTML = flowMap(el.querySelector('#egF'), G.flows);
  }
  function mount(el) {
    el.innerHTML = `<div class="mk-bar" style="margin:0 0 8px">${KEYS.map(k => `<button data-g="${k[0]}" class="${k[0] === key ? 'on' : ''}">${k[1]}</button>`).join('')}</div><div id="egBody"></div>`;
    const body = el.querySelector('#egBody');
    el.querySelectorAll('[data-g]').forEach(b => b.onclick = () => { key = b.dataset.g; el.querySelectorAll('[data-g]').forEach(x => x.classList.toggle('on', x === b)); render(body); });
    render(body);
  }
  return { mount };
})();
