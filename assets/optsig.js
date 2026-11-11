// Options & open-interest read: current vol and skew vs history, active tested signals and a trade idea per market.
// Data: data/optsig/optsig.json (refreshed weekly). OptSig.card(el, syms) for a commodity tab; OptSig.show() for the Trade ideas tab.
const OptSig = (() => {
  let D = null;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const n = (v, d = 1) => v == null ? '–' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const sg = (v, d = 1) => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${n(v, d)}</span>`;
  const ord = v => v == null ? '–' : `${v}${v % 100 >= 10 && v % 100 <= 20 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[v % 10] || 'th')}`;
  const bar = p => p == null ? '' : `<span style="display:inline-block;width:64px;height:7px;background:#e6e6e0;border-radius:4px;vertical-align:middle;position:relative"><i style="position:absolute;left:0;top:0;height:7px;border-radius:4px;width:${Math.max(3, p)}%;background:${p >= 80 ? '#c0392b' : p <= 20 ? '#2e8b3e' : '#b59a2a'}"></i></span> <span class="note">${ord(p)}</span>`;
  const load = () => D ? Promise.resolve(D) : fetch('data/optsig/optsig.json?v=' + Date.now().toString().slice(0, 8)).then(r => r.json()).then(d => (D = d)).catch(() => null);
  const LEAN = { bullish: ['#d7efd5', '#2e8b3e'], bearish: ['#fbe1dc', '#c0392b'], neutral: ['#fff7d1', '#d4ac0d'] };

  function block(sym, m) {
    const I = m.idea, R = m.read, V = m.vol, U = m.us_vol, [bg, bd] = LEAN[I.lean] || LEAN.neutral;
    const act = m.active.length ? `<ul style="margin:4px 0 0 18px;padding:0">${m.active.map(a => `<li><span class="${a.lean > 0 ? 'up' : 'dn'}">${a.lean > 0 ? '▲' : '▼'}</span> ${esc(a.text)} <span class="note">(${a.strength})</span></li>`).join('')}</ul>` : '<p class="note" style="margin:4px 0">No tested signal is active.</p>';
    const vol = V ? `<h3 style="margin-top:12px">Implied vol and skew vs history</h3><div class="tbl"><table>
        <tr><th class="l">Tenor</th><th>ATM</th><th>90%</th><th>110%</th><th>110−90 skew</th><th class="l">vs 1 yr</th><th class="l">vs 3 yrs</th><th class="l">vs all (2005–)</th><th>Same-month median</th></tr>
        ${V.tenors.map(t => `<tr><td class="l">${t.tenor}</td><td><b>${n(t.atm)}</b></td><td>${n(t.p90)}</td><td>${n(t.c110)}</td><td>${sg(t.skew)}</td><td class="l">${bar(t.pct_1y)}</td><td class="l">${bar(t.pct_3y)}</td><td class="l">${bar(t.pct_all)}</td><td>${n(t.month_median)}</td></tr>`).join('')}</table></div>
        <div class="tbl"><table><tr><th class="l">Measure</th><th>Now</th><th class="l">vs 3 yrs</th><th class="l">Reading</th></tr>
        <tr><td class="l">1m implied − 20-day realized (${n(V.rv20)}%)</td><td>${sg(V.iv_minus_rv)}</td><td class="l">${bar(V.iv_minus_rv_pct)}</td><td class="l note">${V.iv_minus_rv_pct >= 80 ? 'options expensive vs recent movement' : V.iv_minus_rv_pct <= 20 ? 'options cheap vs recent movement' : 'normal'}</td></tr>
        <tr><td class="l">1m 25-delta risk reversal (call ${n(V.c25)} − put ${n(V.p25)})</td><td>${sg(V.rr25)}</td><td class="l">${bar(V.rr25_pct_3y)}</td><td class="l note">${V.rr25_pct_3y >= 80 ? 'calls rich' : V.rr25_pct_3y <= 20 ? 'puts rich' : 'normal'} · ${ord(V.rr25_pct_all)} pct of all history</td></tr>
        <tr><td class="l">3m skew (110% − 90%)</td><td></td><td class="l">${bar(V.sk3m_pct_3y)}</td><td class="l note">${V.sk3m_pct_3y >= 80 ? 'upside bid' : V.sk3m_pct_3y <= 20 ? 'downside bid' : 'normal'}</td></tr>
        <tr><td class="l">Term structure: 1m − 6m ATM</td><td>${sg(V.term_1m_6m)}</td><td class="l">${bar(V.term_pct)}</td><td class="l note">${V.term_1m_6m > 0 ? 'front above back (stress priced now)' : 'front below back'}</td></tr>
        <tr><td class="l">1m implied vol change</td><td>${sg(V.iv_chg_1w)} 1w · ${sg(V.iv_chg_1m)} 1m</td><td></td><td></td></tr></table></div>` :
      U && U.atm ? `<p style="margin:8px 0 0"><b>Vol:</b> ${esc(U.label || 'front')} ATM implied ${n(U.atm)}% vs 20-day realized ${n(U.rv20)}%${U.pct_hist != null ? ` (${ord(U.pct_hist)} pct of the desk's ${U.hist_days}-day CME history)` : ''}${U.rr25 != null ? ` · 25-delta risk reversal ${sg(U.rr25, 2)}` : ''}.</p>` : '';
    return `<div style="border:1px solid var(--line);border-left:6px solid ${bd};background:${bg};border-radius:8px;padding:10px 14px;margin:8px 0">
        <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap"><b style="font-size:15px">${esc(m.name)} — ${I.lean}</b><span class="note">data to ${m.asof}</span></div>
        <p style="margin:6px 0"><b>Idea:</b> ${esc(I.structure)}</p>
        ${I.why.length ? `<ul style="margin:2px 0 0 18px;padding:0">${I.why.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}
        <p style="margin:8px 0 0"><b>Active signals</b></p>${act}
        <p style="margin:8px 0 0"><b>Positioning:</b> ${esc(R.quadrant)} over 20 days — price ${sg(R.r20)}%, futures open interest ${sg(R.oi_chg20)}% (${ord(R.oi_chg20_pct)} pct). Calls are ${n(R.call_share)}% of option open interest (${ord(R.call_share_pct)} pct of 3 yrs; ${esc(R.scope)}); 20-day change calls ${sg(R.call_oi_chg20)}%, puts ${sg(R.put_oi_chg20)}%; calls ${n(R.call_vol_share)}% of the week's option volume.</p>
        ${vol}${I.risk ? `<p class="note" style="margin:8px 0 0">${esc(I.risk)}</p>` : ''}</div>`;
  }
  async function card(el, syms) {
    const d = await load(); if (!d) return;
    const ms = syms.filter(s => d.markets[s]); if (!ms.length) return;
    el.innerHTML = `<div class="card"><h2>Options &amp; open interest: weekly read and trade idea</h2>${ms.map(s => block(s, d.markets[s])).join('')}<p class="note">${esc(d.note)} Updated ${esc(d.generated)}.</p></div>`;
  }
  async function show() {
    const el = document.getElementById('optsig'); history.replaceState(null, '', '#ideas');
    el.innerHTML = '<div class="card"><p class="note">Loading…</p></div>';
    const d = await load(); if (!d) { el.innerHTML = '<div class="card"><p class="note">Not built yet.</p></div>'; return; }
    const ks = Object.keys(d.markets), rank = { bullish: 0, bearish: 0, neutral: 1 };
    ks.sort((a, b) => rank[d.markets[a].idea.lean] - rank[d.markets[b].idea.lean] || Math.abs(d.markets[b].score) - Math.abs(d.markets[a].score));
    el.innerHTML = `<div style="max-width:1200px;margin:0 auto;padding:12px 16px"><div class="card"><h2>Trade ideas from options and open interest</h2>
      <div class="tbl"><table><tr><th class="l">Market</th><th class="l">Lean</th><th class="l">Idea</th><th class="l">Active signals</th><th>Data to</th></tr>
      ${ks.map(s => { const m = d.markets[s]; return `<tr><td class="l"><b>${esc(m.name)}</b></td><td class="l ${m.idea.lean === 'bullish' ? 'up' : m.idea.lean === 'bearish' ? 'dn' : ''}">${m.idea.lean}</td><td class="l">${esc(m.idea.structure)}</td><td class="l note">${m.active.map(a => esc(a.text.split(':')[0])).join('; ') || '–'}</td><td>${m.asof}</td></tr>`; }).join('')}</table></div>
      <p class="note">${esc(d.note)} Updated ${esc(d.generated)}.</p></div>${ks.map(s => block(s, d.markets[s])).join('')}</div>`;
  }
  return { card, show, load };
})();
