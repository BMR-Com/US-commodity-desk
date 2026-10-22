// Contract specs card for the primers: available contracts, size, tick, contract value at today's price, margins.
const Specs = (() => {
  let D = null, P = null, CAL = null;
  const usd = v => v == null ? '–' : '$' + Math.round(v).toLocaleString();
  async function load() { if (!P) P = Promise.all([getJSON('data/specs/specs.json').then(d => (D = d)).catch(() => null), getJSON('data/specs/calendar.json').then(d => (CAL = d)).catch(() => null)]); return P; }
  function html(group, only) {
    if (!D || !D.groups[group]) return '';
    let rows = D.groups[group];
    if (only) rows = rows.filter(r => only.includes(r.of) || only.includes(r.sym));
    const anyEst = rows.some(r => r.maint_est != null);
    return `<div class="card" style="margin-top:12px"><h2>Contracts, size and margin <span class="note">prices ${rows.find(r => r.price_date)?.price_date || ''}; exchange margins as of ${D.margins_asof}</span></h2>
      <div class="tbl"><table class="bt-t"><tr><th class="l">Contract</th><th class="l">Exchange · code</th><th class="l">Size</th><th class="l">Tick</th><th>Front month</th><th>Price</th><th>Contract value</th><th>Typical daily move</th><th>Maintenance margin</th><th>Initial (≈110%)</th><th>Margin % of value</th><th>Leverage</th><th class="l">Settlement</th><th class="l">Options</th></tr>
      ${rows.map(r => {
        const m = r.maint ?? r.maint_est, est = r.maint == null && r.maint_est != null;
        const ls = r.margin_long && r.margin_short ? ` <span class="note">(long ${usd(r.margin_long)} / short ${usd(r.margin_short)})</span>` : '';
        return `<tr><td class="l"><b>${r.name}</b></td><td class="l">${r.ex} · ${r.sym}</td><td class="l">${r.size}</td><td class="l">${r.tick}</td><td>${r.front_contract || '–'}</td><td>${r.price ?? '–'} <span class="note">${r.quote}</span></td>
          <td><b>${usd(r.notional)}</b></td><td>${usd(r.day_move)}</td><td>${m == null ? '–' : usd(m) + (est ? '*' : '')}${ls}</td><td>${m == null ? '–' : usd(m * 1.1) + (est ? '*' : '')}</td><td>${r.margin_pct ?? '–'}%</td><td>${r.leverage ? r.leverage + 'x' : '–'}</td>
          <td class="l note">${r.settle}</td><td class="l note">${r.options}</td></tr>`; }).join('')}</table></div>
      ${calHtml([...new Set(rows.map(r => r.of).filter(Boolean))])}
      <p class="note">Contract value = front-month price × contract size. Typical daily move = one standard deviation of daily price changes over the last 20 days, in dollars per contract. Maintenance margin is the exchange minimum for the front month (CME Group, outright, speculative accounts); initial margin is 110% of it, and brokers often ask for more. Margins change with volatility and are higher close to expiry for some contracts.${anyEst ? ' *ICE does not publish a flat margin for cotton; the figure is an estimate (99% two-day move), so check ICE Clear US or your broker.' : ''}${rows.some(r => /Mini|Micro|E-mini/.test(r.name)) ? ' Mini, e-mini and micro contracts trade a half, a fifth or a tenth of the full size, with margin to match.' : ''}</p></div>`;
  }
  function calHtml(syms) {
    if (!CAL) return '';
    const S = syms.filter(s => CAL.markets[s]);
    if (!S.length) return '';
    const E = CAL.explain, d = v => v ? v.slice(5) : '–';
    const urgent = c => c.days_to_out <= 5 ? 'dn' : c.days_to_out <= 15 ? 'warn' : '';
    return `<h3>Key dates: when to roll <span class="note">updated ${CAL.generated}; from the exchange rules</span></h3>
      ${Object.values(S.reduce((g, s) => { const m = CAL.markets[s], k = m.rule + JSON.stringify(m.contracts.map(c => [c.month, c.fpd, c.fnd, c.ltd, c.out_by]));
          (g[k] = g[k] || []).push(s); return g; }, {})).map(G => { const s = G[0], m = CAL.markets[s], phys = m.settle === 'physical', hasFpd = m.contracts.some(c => c.fpd), hasFnd = m.contracts.some(c => c.fnd), ck = CAL.check?.[s];
        const many = G.length > 1, mon = c => new Date(c.month + '-15').toLocaleString('en-US', { month: 'short', year: 'numeric' });
        return `<p><b>${G.map(x => CAL.markets[x].name).join(', ')}</b> · ${phys ? '<b class="dn">physical delivery</b>' : '<b class="up">cash-settled</b>'}. ${m.roll.startsWith('As ') ? CAL.markets[Object.keys(CAL.markets).find(x => !CAL.markets[x].roll.startsWith('As ') && CAL.markets[x].rule === m.rule)]?.roll || m.roll : m.roll}${many ? ` Same dates for ${G.join(', ')}.` : ''}</p>
        <div class="tbl"><table class="bt-t"><tr><th class="l">${many ? 'Contract month' : 'Contract'}</th>${hasFpd ? '<th title="' + E.fpd + '">First position day</th>' : ''}${hasFnd ? '<th title="' + E.fnd + '">First notice day</th>' : ''}<th title="${E.ltd}">Last trading day</th>${m.contracts.some(c => c.settles) ? '<th>USDA price (final settlement)</th>' : ''}<th title="${E.out_by}"><b>Roll / exit by</b></th><th>Business days left</th></tr>
        ${m.contracts.map(c => `<tr><td class="l">${many ? `${mon(c)} <span class="note">(${c.contract.slice(s.length, s.length + 1)}${c.contract.slice(-2)})</span>` : c.contract}</td>${hasFpd ? `<td>${c.fpd || '–'}</td>` : ''}${hasFnd ? `<td>${c.fnd || '–'}</td>` : ''}<td>${c.ltd}</td>${c.settles ? `<td>${c.settles}</td>` : (m.contracts.some(x => x.settles) ? '<td></td>' : '')}<td><b>${c.out_by}</b></td><td class="${urgent(c)}">${c.days_to_out}</td></tr>`).join('')}</table></div>
        <p class="note">Rule: ${m.rule}${ck ? ` Checked against ${ck.checked} expired contracts: ${ck.exact} exact${ck.checked > ck.exact ? '; the others are final-settlement prices posted a day or two later, or exchange one-offs' : ''}.` : ''}</p>`; }).join('')}
      <p class="note">${E.out_by} Holidays follow the US exchange calendar; early closes and one-off changes are not modelled, so confirm a delivery-sensitive date on the exchange calendar or with your broker.</p>`;
  }
  function fill() {
    document.querySelectorAll('.specs-slot').forEach(el => { if (D) el.innerHTML = html(el.dataset.g, el.dataset.only ? el.dataset.only.split(',') : null); });
  }
  // placeholder that fills itself once the specs file is loaded
  function slot(group, only) { setTimeout(() => load().then(fill), 0); return `<div class="specs-slot" data-g="${group}" data-only="${(only || []).join(',')}"></div>`; }
  return { load, html, slot, fill };
})();
