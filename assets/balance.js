// US balance sheet with desk scenarios (data/derived/balance_sheets.json; models/balance_sheets.py).
// BalanceSheet.mount(el, key) — key: cotton, corn, soybeans, meal, oil, wheat, kc
const BalanceSheet = (() => {
  const css = `<style id="bsCss">
    .bs table td,.bs table th{text-align:right;white-space:nowrap}
    .bs table td:first-child,.bs table th:first-child{text-align:left}
    .bs tr.k td{font-weight:700}
    .bs tr.end td{border-top:2px solid var(--line)}
    .bs th.sc,.bs td.sc{background:rgba(42,120,214,.06)}
    .bs th.sc.bear,.bs td.sc.bear{background:rgba(179,38,30,.06)}
    .bs th.sc.bull,.bs td.sc.bull{background:rgba(31,122,58,.07)}
    .bs th.cur,.bs td.cur{border-right:2px solid var(--line)}
    .bs .bs-sum{margin:6px 0 10px;line-height:1.5}
    .bs .bs-sum b.dn{color:var(--dn,#b3261e)} .bs .bs-sum b.up{color:var(--up,#1f7a3a)}
  </style>`;
  const fmt = (v, d) => v == null || isNaN(v) ? '' : (+v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  function dec(label, m) {
    if (/Stocks \/ use/.test(label)) return 1;
    if (/area/.test(label)) return 1;
    if (/Yield/.test(label)) return m.dec ? 0 : 1;
    if (/Farm price/.test(label)) return 2;
    return m.dec;
  }
  async function mount(el, key) {
    if (!document.getElementById('bsCss')) document.head.insertAdjacentHTML('beforeend', css);
    el.innerHTML = '<div class="card bs"><p class="note">Loading balance sheet…</p></div>';
    const D = await getJSON('data/derived/balance_sheets.json').catch(() => null);
    const m = D && D.markets && D.markets[key];
    if (!m) { el.innerHTML = ''; return; }
    const yrs = m.years, cur = m.cur, u = m.unit, d = m.dec;
    const S = m.summary, us = m.usda_end, prodOnly = m.product;
    const diff = v => `${v - us >= 0 ? '+' : '−'}${fmt(Math.abs(v - us), d)}`;
    let sum = '';
    if (!prodOnly) {
      const b = S.base, dir = b.end < us ? 'tighter' : 'looser';
      sum = `<p class="bs-sum">Desk base case: ${m.cur} ending stocks <b class="${b.end < us ? 'up' : 'dn'}">${fmt(b.end, d)}</b> ${u} vs USDA's ${fmt(us, d)} (${diff(b.end)}; ${dir} than USDA), stocks/use ${fmt(b.su, 1)}% vs ${fmt(m.usda_su, 1)}%. `
        + `Bearish ${fmt(S.bear.end, d)} · bullish ${fmt(S.bull.end, d)}. `
        + `Production ${fmt(b.prod, d)} vs USDA ${fmt(m.prod_usda, d)}; exports ${fmt(b.exports, d)} vs USDA ${fmt(m.exp_usda, d)}.</p>`;
      const cap = m.capped || {};
      if (Object.keys(cap).length) {
        sum += `<p class="note">${Object.entries(cap).map(([s, c]) => `${({ base: 'Base', bear: 'Bearish', bull: 'Bullish' })[s]}: export sales point to ${fmt(c.projected, d)}, but supply only allows about ${fmt(c.allowed, d)} before stocks hit ${fmt(m.floor, d)}, the tightest USDA has carried since 2007/08 (${m.floor_my}). The gap has to be rationed by price.`).join(' ')}</p>`;
      }
    }
    const H = `<tr><th>${u}</th>${yrs.map(y => `<th class="${y === cur ? 'cur' : ''}">${y}${y === cur ? `<br><span class="note">USDA ${m.report.split(' ')[0].slice(0, 3)}</span>` : ''}</th>`).join('')}
      <th class="sc">Base</th><th class="sc bear">Bearish</th><th class="sc bull">Bullish</th></tr>`;
    const R = m.rows.map(r => {
      const dd = dec(r.label, m), end = r.label === 'Ending stocks';
      return `<tr class="${r.key ? 'k' : ''} ${end ? 'end' : ''}"><td>${r.label}</td>${yrs.map(y => `<td class="${y === cur ? 'cur' : ''}">${fmt(r.usda[y], dd)}</td>`).join('')}
        <td class="sc">${prodOnly ? '–' : fmt(r.base, dd)}</td><td class="sc bear">${prodOnly ? '–' : fmt(r.bear, dd)}</td><td class="sc bull">${prodOnly ? '–' : fmt(r.bull, dd)}</td></tr>`;
    }).join('');
    const notes = prodOnly
      ? `<p class="note">USDA's last three seasons and its ${cur} forecast. No desk scenarios here: meal and oil come out of the soybean crush, so an export miss changes how much is crushed rather than piling up as stocks. See the soybean balance sheet for the crush.</p>`
      : `<p class="note"><b>Production:</b> ${m.prod_src}. <b>Exports:</b> ${m.exp_src}${m.exp_miss != null ? `; at this point of the season the export projection has missed USDA's final by about ${fmt(m.exp_miss, 0)}% on average${m.exp_miss >= 10 ? ', so treat the export side as an early read' : ''}` : ''}. Beginning stocks, imports and domestic use stay at USDA's ${m.report} numbers. Bearish = bigger crop and weaker exports; bullish = smaller crop and stronger exports.</p>`;
    el.innerHTML = `<div class="card bs"><h2>US balance sheet — ${m.name} <span class="note">USDA ${yrs[0]}–${cur} and desk scenarios · built ${D.generated}</span></h2>
      ${sum}<div class="tbl"><table>${H}${R}</table></div>${notes}</div>`;
  }
  return { mount };
})();
