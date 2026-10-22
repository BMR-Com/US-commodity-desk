// Contract specs card for the primers: available contracts, size, tick, contract value at today's price, margins.
const Specs = (() => {
  let D = null, P = null;
  const usd = v => v == null ? '–' : '$' + Math.round(v).toLocaleString();
  async function load() { if (!P) P = getJSON('data/specs/specs.json').then(d => (D = d)).catch(() => null); return P; }
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
      <p class="note">Contract value = front-month price × contract size. Typical daily move = one standard deviation of daily price changes over the last 20 days, in dollars per contract. Maintenance margin is the exchange minimum for the front month (CME Group, outright, speculative accounts); initial margin is 110% of it, and brokers often ask for more. Margins change with volatility and are higher close to expiry for some contracts.${anyEst ? ' *ICE does not publish a flat margin for cotton; the figure is an estimate (99% two-day move), so check ICE Clear US or your broker.' : ''}${rows.some(r => /Mini|Micro|E-mini/.test(r.name)) ? ' Mini, e-mini and micro contracts trade a half, a fifth or a tenth of the full size, with margin to match.' : ''}</p></div>`;
  }
  function fill() {
    document.querySelectorAll('.specs-slot').forEach(el => { if (D) el.innerHTML = html(el.dataset.g, el.dataset.only ? el.dataset.only.split(',') : null); });
  }
  // placeholder that fills itself once the specs file is loaded
  function slot(group, only) { setTimeout(() => load().then(fill), 0); return `<div class="specs-slot" data-g="${group}" data-only="${(only || []).join(',')}"></div>`; }
  return { load, html, slot, fill };
})();
