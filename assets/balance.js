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
      const cap = m.capped || {}, SN = { base: 'Base', bear: 'Bearish', bull: 'Bullish' }, t = m.trade;
      const cn = Object.entries(cap).map(([s, c]) => {
        const p = [];
        if (c.trade) p.push(`export sales point to ${fmt(c.trade.projected, d)}, but the US share of world trade limits it to about ${fmt(c.trade.allowed, d)}`);
        if (c.supply) p.push(`${c.trade ? 'and ' : 'export sales point to ' + fmt(c.supply.projected, d) + ', but '}supply only allows about ${fmt(c.supply.allowed, d)} before stocks reach pipeline minimum (${fmt(m.floor, d)}) — the rest would have to be rationed by price`);
        return `<b>${SN[s]}:</b> ${p.join(' ')}.`;
      });
      if (cn.length) sum += `<p class="note">${cn.join(' ')}</p>`;
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
      : `<p class="note"><b>Variables used:</b> ${m.vars.join('; ')}. Beginning stocks, imports and domestic use are USDA's ${m.report} numbers.${m.exp_miss != null && m.exp_miss >= 10 ? ` Export sales are only ${m.exp_week} weeks into the season, so the export side is an early read.` : ''} Bearish = larger crop, bullish = smaller crop with strong demand; exports stay within available supply and the US share of world trade. Production and exports as of ${D.generated}.</p>`;
    el.innerHTML = `<div class="card bs"><h2>US balance sheet — ${m.name} <span class="note">USDA ${yrs[0]}–${cur} and desk scenarios · built ${D.generated}</span></h2>
      ${sum}<div class="tbl"><table>${H}${R}</table></div>${notes}</div>`;
  }
  return { mount };
})();

// Outlook in brief (data/derived/outlook_brief.json; models/outlook_brief.py): crop, exports, ending stocks, COT, technicals, options, bottom line.
// OutlookBrief.mount(el, key) on a market's Outlook tab; OutlookBrief.inline(el, sym) on the Summary tab.
const OutlookBrief = (() => {
  const css = `<style id="obCss">.ob ul{margin:4px 0 0;padding-left:18px}.ob li{margin:4px 0;line-height:1.45}.ob li.bl{list-style:none;margin-left:-18px;margin-top:8px;padding:8px 10px;background:rgba(42,120,214,.06);border-radius:6px}</style>`;
  const li = it => `<li class="${it.h === 'Bottom line' ? 'bl' : ''}"><b>${it.h}:</b> ${it.t}</li>`;
  async function data() { return getJSON('data/derived/outlook_brief.json').catch(() => null); }
  async function mount(el, key) {
    if (!el) return;
    if (!document.getElementById('obCss')) document.head.insertAdjacentHTML('beforeend', css);
    const D = await data(); const m = D && D.markets && D.markets[key];
    if (!m) { el.innerHTML = ''; return; }
    el.innerHTML = `<div class="card ob"><h2>Outlook in brief — ${m.name} <span class="note">built ${D.generated}</span></h2><ul>${m.items.map(li).join('')}</ul>
      <p class="note">Built automatically from the crop model, export sales, the balance sheet below, CFTC positioning, price technicals and options data. Research, not investment advice.</p></div>`;
  }
  async function inline(el, sym) {
    if (!el) return;
    if (!document.getElementById('obCss')) document.head.insertAdjacentHTML('beforeend', css);
    const D = await data(); const m = D && Object.values(D.markets || {}).find(x => x.sym === sym);
    el.innerHTML = m ? `<div class="ob"><h3>Outlook in brief</h3><ul>${m.items.map(li).join('')}</ul></div>` : '';
  }
  return { mount, inline };
})();
