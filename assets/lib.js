// Shared helpers for the US Commodity Desk pages.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const fmt = (v, d = 2) => v == null || isNaN(v) ? '–' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const sgn = (v, d = 1, suf = '') => { if (v == null || isNaN(v)) return '–'; v = +(+v).toFixed(d) || 0; return `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${fmt(v, d)}${suf}</span>`; };
const cache = {};
async function getJSON(u) { if (!cache[u]) cache[u] = fetch(u + '?v=' + Date.now().toString().slice(0, 8)).then(r => r.json()); return cache[u]; }
async function getCSV(u) {
  if (!cache[u]) cache[u] = fetch(u + '?v=' + Date.now().toString().slice(0, 8)).then(r => r.text()).then(t => {
    const [h, ...rows] = t.trim().split(/\r?\n/); const cols = h.split(',');
    return rows.map(r => { const v = r.split(','); const o = {}; cols.forEach((c, i) => { const x = v[i]; o[c] = x === '' || x === undefined ? null : isNaN(+x) ? x : +x; }); return o; });
  });
  return cache[u];
}
const charts = {};
const PAL = ['#2f6b3a', '#c0392b', '#2c6fbb', '#d68910', '#7d3c98', '#17a589', '#7f8c8d', '#a04000'];
function chart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  const base = { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
    plugins: { legend: { labels: { boxWidth: 10, font: { size: 11 } } }, tooltip: { bodyFont: { size: 11 } } },
    scales: { x: { ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 12 }, grid: { display: false } },
              y: { ticks: { font: { size: 10 } }, grid: { color: '#eee' } } } };
  cfg.options = deepMerge(base, cfg.options || {});
  charts[id] = new Chart(document.getElementById(id), cfg);
  return charts[id];
}
function deepMerge(a, b) { const o = Array.isArray(a) ? [...a] : { ...a }; for (const k in b) o[k] = b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) && a[k] && typeof a[k] === 'object' ? deepMerge(a[k], b[k]) : b[k]; return o; }
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// seasonal view: series {month:['2024-01',...], vals:[...]} -> datasets this year, last year, 5y min/max/avg
function seasonal(months, vals) {
  const by = {}; months.forEach((m, i) => { const [y, mm] = m.split('-').map(Number); (by[y] ||= Array(12).fill(null))[mm - 1] = vals[i]; });
  const yrs = Object.keys(by).map(Number).sort(); const cy = yrs.at(-1);
  const prev5 = yrs.filter(y => y < cy).slice(-5);
  const stat = f => Array.from({ length: 12 }, (_, i) => { const xs = prev5.map(y => by[y][i]).filter(v => v != null); return xs.length ? f(xs) : null; });
  return { cy, by, min: stat(x => Math.min(...x)), max: stat(x => Math.max(...x)), avg: stat(x => x.reduce((a, b) => a + b, 0) / x.length), prev5 };
}
function seasonalDatasets(s, label = '') {
  return [
    { label: `5y range`, data: s.max, borderWidth: 0, backgroundColor: 'rgba(47,107,58,.12)', fill: '+1', pointRadius: 0 },
    { label: '_min', data: s.min, borderWidth: 0, pointRadius: 0, fill: false },
    { label: `5y avg`, data: s.avg, borderColor: '#999', borderDash: [4, 3], borderWidth: 1.2, pointRadius: 0 },
    { label: `${s.cy - 1}`, data: s.by[s.cy - 1], borderColor: '#2c6fbb', borderWidth: 1.5, pointRadius: 0 },
    { label: `${s.cy}`, data: s.by[s.cy], borderColor: '#c0392b', borderWidth: 2.4, pointRadius: 2 },
  ];
}
const legendNoMin = { labels: { filter: i => !i.text.startsWith('_'), boxWidth: 10, font: { size: 11 } } };
function tabs(root, onShow) {
  $$('nav.tabs button', root).forEach(b => b.onclick = () => {
    $$('nav.tabs button', root).forEach(x => x.classList.toggle('on', x === b));
    $$('.panel', root).forEach(p => p.classList.toggle('on', p.id === b.dataset.tab));
    history.replaceState(null, '', '#' + b.dataset.tab); onShow && onShow(b.dataset.tab);
  });
}
