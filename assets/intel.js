// News headlines, key-events calendar and weather watch panels.
const Intel = (() => {
  const C = {};
  const load = async n => C[n] ?? (C[n] = await getJSON(`data/${n}/${n}.json`).catch(() => null));
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ago = t => { const h = (Date.now() - new Date(t.replace('Z', ':00Z')).getTime()) / 36e5; return h < 1 ? 'now' : h < 24 ? `${Math.round(h)}h` : `${Math.round(h / 24)}d`; };
  const MK = { ZC: 'corn', ZS: 'soybeans', ZM: 'meal', ZL: 'oil', ZW: 'wheat', KE: 'wheat', HE: 'hogs', LE: 'cattle', GF: 'cattle', CT: 'cotton', DC: 'dairy', GDK: 'dairy' };
  const TAGLAB = { corn: 'Corn', soybeans: 'Soybeans', meal: 'Meal', oil: 'Oil', wheat: 'Wheat', hogs: 'Hogs', cattle: 'Cattle', cotton: 'Cotton', dairy: 'Dairy', south_america: 'S. America', usda: 'USDA' };

  async function news(el, { tags = null, n = 25, chips = true } = {}) {
    const D = await load('news');
    if (!D) { el.innerHTML = '<p class="note">Headlines not loaded yet.</p>'; return; }
    let sel = tags;
    const draw = () => {
      const items = D.items.filter(i => !sel || i.tags.some(t => sel.includes(t))).slice(0, n);
      el.innerHTML = (chips ? `<div class="tbar"><div class="grp"><span class="lab">Filter</span>${[['', 'All'], ...Object.entries(TAGLAB)].map(([k, l]) => `<button class="chip ${(sel || []).join() === k || (!sel && !k) ? 'on' : ''}" data-t="${k}">${l}</button>`).join('')}</div></div>` : '') +
        `<ul class="news">${items.map(i => `<li><a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(i.title)}</a> <span class="note">${esc(i.source)} · ${ago(i.time)}</span></li>`).join('') || '<li class="note">No recent headlines.</li>'}</ul>
        ${chips ? `<p class="note">Headlines and links only, from major outlets' public RSS (Reuters, Bloomberg, Dow Jones/WSJ, DTN, Farm Progress, Brownfield and others via Google News). Updated every 3 hours; ${D.generated}.</p>` : ''}`;
      el.querySelectorAll('[data-t]').forEach(b => b.onclick = () => { sel = b.dataset.t ? [b.dataset.t] : null; draw(); });
    };
    draw();
  }

  async function calendar(el, { markets = null, days = 21, minImp = 1, cats = null } = {}) {
    const D = await load('calendar');
    if (!D) { el.innerHTML = '<p class="note">Calendar not loaded yet.</p>'; return; }
    const today = new Date().toISOString().slice(0, 10), end = new Date(Date.now() + days * 864e5).toISOString().slice(0, 10);
    const ev = D.events.filter(e => e.date >= today && e.date <= end && e.importance >= minImp && (!cats || cats.includes(e.cat)) && (!markets || e.markets.includes('ALL') || e.markets.some(m => markets.includes(m))));
    const byDay = {}; ev.forEach(e => (byDay[e.date] = byDay[e.date] || []).push(e));
    const dname = d => new Date(d + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    el.innerHTML = `<div class="tbl"><table class="cal">${Object.entries(byDay).map(([d, es]) => `<tr><td class="cal-d">${dname(d)}</td><td class="l">${es.map(e => `<div class="cal-e imp${e.importance}">${e.time ? `<span class="note">${e.time}</span> ` : ''}${e.link ? `<a href="${esc(e.link)}" target="_blank" rel="noopener">${esc(e.event)}</a>` : esc(e.event)}${e.estimated ? ' <span class="note">(est.)</span>' : ''} <span class="note">${e.markets.includes('ALL') ? '' : e.markets.join(' ')}</span></div>`).join('')}</td></tr>`).join('') || '<tr><td class="note">No events in range.</td></tr>'}</table></div>
      <p class="note">Bold = market-moving (WASDE, Crop Production, Grain Stocks, Hogs and Pigs, Cattle on Feed, class prices, first notice). NASS dates from the NASS calendar; WASDE 2026 dates official; contract dates rule-based (est.). Times US Central.</p>`;
  }

  async function weather(el, { countries = null, markets = null } = {}) {
    const D = await load('weather');
    if (!D) { el.innerHTML = '<p class="note">Weather not loaded yet.</p>'; return; }
    const rs = D.regions.filter(r => (!countries || countries.includes(r.country)) && (!markets || r.markets.some(m => markets.includes(m)))).sort((a, b) => b.risk - a.risk || b.sensitivity - a.sensitivity);
    const fl = (f, obs, nrm) => `<span class="wx wx-${f}">${obs} mm</span> <span class="note">vs ${nrm ?? '–'}</span>`;
    el.innerHTML = `<div class="tbl"><table><tr><th>Region</th><th class="l">Crop stage now</th><th>Last 30 days</th><th>Next 16 days</th><th>Max temp next 16d</th><th>Watch</th></tr>
      ${rs.map(r => { const st = r.stages.map(s => `${s.crop}: <b>${s.stage}</b>`).join('; '), mat = r.stages.filter(s => s.sensitivity >= 2).map(s => s.matters).join('; ');
        const w = r.risk >= 3 ? '<span class="wx wx-dry">High</span>' : r.risk >= 1 ? '<span class="wx wx-wet">Watch</span>' : '<span class="note">–</span>';
        return `<tr><td>${esc(r.region)} <span class="note">${r.country}</span></td><td class="l sv-w">${st || '<span class="note">off-season</span>'}${mat ? `<br><span class="note">${esc(mat)}</span>` : ''}</td>
          <td>${fl(r.past30_flag, r.past30_mm, r.past30_normal)}</td><td>${fl(r.next16_flag, r.next16_mm, r.next16_normal)}</td>
          <td>${r.tmax_next16}°C <span class="note">${r.tmax_anom == null ? '' : (r.tmax_anom > 0 ? '+' : '') + r.tmax_anom + ' vs normal'}</span></td><td>${w}</td></tr>`; }).join('')}</table></div>
      <p class="note">Open-Meteo forecast and reanalysis; "normal" = 2006–2025 average for the same dates. Red = below the 20th percentile of past years (dry), blue = above the 80th (wet). Watch flags weight dryness, heat and harvest rain by how sensitive the crop stage is this month. ${D.generated}.</p>`;
  }
  return { news, calendar, weather, MK };
})();
