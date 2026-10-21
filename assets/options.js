// Options pricer: Black-76 on futures, realized-vol stats, strategy builder, interactive payoff and Greeks.
const Options = (() => {
  let V = null, built = false, sym = 'ZC', S = null, charts = {};
  const N = x => { const t = 1 / (1 + .2316419 * Math.abs(x)), d = .3989423 * Math.exp(-x * x / 2), p = d * t * (.3193815 + t * (-.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return x > 0 ? 1 - p : p; };
  const n = x => Math.exp(-x * x / 2) / Math.sqrt(2 * Math.PI);
  // Black-76: price and Greeks for one option on a futures price F. vol and r in decimals, T in years.
  function b76(type, F, K, T, vol, r) {
    if (type === 'F') return { px: F, delta: 1, gamma: 0, theta: 0, vega: 0 };
    const df = Math.exp(-r * T);
    if (T <= 1e-6 || vol <= 0) { const iv = type === 'C' ? Math.max(F - K, 0) : Math.max(K - F, 0); return { px: iv, delta: type === 'C' ? (F > K ? 1 : 0) : (F < K ? -1 : 0), gamma: 0, theta: 0, vega: 0 }; }
    const s = vol * Math.sqrt(T), d1 = (Math.log(F / K) + vol * vol * T / 2) / s, d2 = d1 - s;
    const call = df * (F * N(d1) - K * N(d2)), put = df * (K * N(-d2) - F * N(-d1));
    const px = type === 'C' ? call : put;
    return { px, delta: type === 'C' ? df * N(d1) : -df * N(-d1), gamma: df * n(d1) / (F * s),
      theta: (-F * df * n(d1) * vol / (2 * Math.sqrt(T)) + r * px) / 365, vega: F * df * n(d1) * Math.sqrt(T) / 100 };
  }
  const STRATS = {
    'Long call': w => [['C', 1, 0]], 'Long put': w => [['P', 1, 0]], 'Short call': w => [['C', -1, 0]], 'Short put': w => [['P', -1, 0]],
    'Long straddle': w => [['C', 1, 0], ['P', 1, 0]], 'Short straddle': w => [['C', -1, 0], ['P', -1, 0]],
    'Long strangle': w => [['C', 1, w], ['P', 1, -w]], 'Short strangle': w => [['C', -1, w], ['P', -1, -w]],
    'Bull call spread': w => [['C', 1, 0], ['C', -1, w]], 'Bear put spread': w => [['P', 1, 0], ['P', -1, -w]],
    'Bull put spread (credit)': w => [['P', -1, 0], ['P', 1, -w]], 'Bear call spread (credit)': w => [['C', -1, 0], ['C', 1, w]],
    'Risk reversal (long call, short put)': w => [['C', 1, w], ['P', -1, -w]], 'Fence / collar on long futures': w => [['F', 1, 0], ['P', 1, -w], ['C', -1, w]],
    'Hedger: long futures + long put': w => [['F', 1, 0], ['P', 1, -w]], 'Covered call (long futures, short call)': w => [['F', 1, 0], ['C', -1, w]],
    'Short hedge: short futures + long call': w => [['F', -1, 0], ['C', 1, w]],
    'Long call butterfly': w => [['C', 1, -w], ['C', -2, 0], ['C', 1, w]], 'Long put butterfly': w => [['P', 1, w], ['P', -2, 0], ['P', 1, -w]],
    'Iron condor (short)': w => [['P', 1, -2 * w], ['P', -1, -w], ['C', -1, w], ['C', 1, 2 * w]],
    'Call ratio spread 1x2': w => [['C', 1, 0], ['C', -2, w]], 'Put ratio spread 1x2': w => [['P', 1, 0], ['P', -2, -w]],
    'Three-way (put spread, short call)': w => [['P', 1, 0], ['P', -1, -2 * w], ['C', -1, 2 * w]],
    'Long futures': w => [['F', 1, 0]], 'Short futures': w => [['F', -1, 0]],
  };
  const fx = (v, d = 2) => v == null || isNaN(v) ? '–' : (+v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  const usd = v => v == null || isNaN(v) ? '–' : (v < 0 ? '−$' : '$') + (Math.abs(v) < 10 ? Math.abs(v).toFixed(2) : Math.abs(Math.round(v)).toLocaleString());
  const round = (x, st) => Math.round(x / st) * st;
  function newState() {
    const m = V.markets[sym], c = m.contracts[0];
    S = { c: c ? c.code : null, F: c ? c.last : 0, vol: c ? (c.vol || 20) : 20, r: (V.rate || 4) , exp: c ? c.expiry : '', strat: 'Long straddle', w: 2, qty: 1, days: 0, vshift: 0, legs: [] };
    build();
  }
  const contract = () => V.markets[sym].contracts.find(c => c.code === S.c);
  const T0 = () => Math.max(0, (new Date(S.exp + 'T13:30:00') - new Date()) / 864e5);
  function build() {
    const m = V.markets[sym], atm = round(S.F, m.step);
    S.legs = STRATS[S.strat](S.w).map(([t, q, k]) => ({ t, q: q * S.qty, K: t === 'F' ? S.F : +(atm + k * m.step).toFixed(4), vol: null }));
  }
  function value(F, daysLeft, volShift) {
    const m = V.markets[sym], T = Math.max(daysLeft, 0) / 365, r = S.r / 100;
    let px = 0, g = { delta: 0, gamma: 0, theta: 0, vega: 0 };
    for (const L of S.legs) {
      const v = Math.max(((L.vol ?? S.vol) + volShift) / 100, .001);
      if (L.t === 'F') { px += L.q * (F - L.K); g.delta += L.q; continue; }
      const o = b76(L.t, F, L.K, T, v, r);
      px += L.q * o.px; for (const k in g) g[k] += L.q * o[k];
    }
    return { px, ...g };
  }
  function entryCost() { const m = V.markets[sym], T = T0() / 365; return S.legs.reduce((a, L) => a + (L.t === 'F' ? 0 : L.q * b76(L.t, S.F, L.K, T, (L.vol ?? S.vol) / 100, S.r / 100).px), 0); }
  function render() {
    const el = document.getElementById('options'), m = V.markets[sym], dte = T0();
    const groups = [...new Set(Object.values(V.markets).map(x => x.group))];
    el.innerHTML = `<main>
      <div class="card"><div class="mk-bar">${groups.map(g => `<span class="note" style="margin-left:6px">${g}:</span>` + Object.entries(V.markets).filter(([, x]) => x.group === g).map(([k, x]) => `<button data-s="${k}" class="${k === sym ? 'on' : ''}">${x.name}</button>`).join('')).join(' ')}</div>
        <h2>${m.name} options <span class="note">${m.unit}; 1 contract = $${m.mult.toLocaleString()} per 1 ${m.unit.split('/')[0]}; options expire ${m.expiry_rule}</span></h2></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Volatility</h2>
          <p>Front-month 20-day realized vol <b>${fx(m.hv20_front, 1)}%</b>: ${m.hv20_pct1y ?? '–'}th percentile of the last year, ${m.hv20_pct5y ?? '–'}th of 5 years. ${(() => { const mo = new Date().getMonth(); const sv = m.seasonal[mo]; return sv ? `Typical 20-day vol this month: ${fx(sv, 1)}%.` : ''; })()}</p>
          <div class="tbl"><table><tr><th class="l">Contract</th><th>Last</th><th>Option expiry</th><th>Days</th><th>HV10</th><th>HV20</th><th>HV30</th><th>HV60</th><th>HV90</th><th>Parkinson 20</th></tr>
          ${m.contracts.map(c => `<tr class="${c.code === S.c ? 'mk-today' : ''}"><td class="l">${c.label}</td><td>${fx(c.last, m.dp)}</td><td>${c.expiry}</td><td>${c.dte}</td>${['hv10', 'hv20', 'hv30', 'hv60', 'hv90', 'park20'].map(k => `<td>${fx(c[k], 1)}</td>`).join('')}</tr>`).join('')}</table></div>
          <div class="grid g2"><div><canvas id="opCone" height="190"></canvas></div><div><canvas id="opSeas" height="190"></canvas></div></div>
          <canvas id="opHist" height="110"></canvas>
          <p class="note">${V.note} Realized vol from daily closes; the continuous series drops roll gaps. Implied vol usually trades above realized before reports (WASDE, Hogs &amp; Pigs, Cattle on Feed) and in the growing season.</p></div>
        <div class="card"><h2>Pricer <span class="note">Black-76, European approximation of CME/ICE American options on futures</span></h2>
          <div class="op-in">
            <label>Contract<select id="opC">${m.contracts.map(c => `<option value="${c.code}" ${c.code === S.c ? 'selected' : ''}>${c.label} (${c.expiry})</option>`).join('')}</select></label>
            <label>Futures<input id="opF" type="number" step="${m.step / 2}" value="${S.F}"></label>
            <label>Vol %<input id="opV" type="number" step="0.5" value="${S.vol}"></label>
            <label>Rate %<input id="opR" type="number" step="0.05" value="${fx(S.r, 2)}"></label>
            <label>Expiry<input id="opE" type="date" value="${S.exp}"></label>
            <label>Strategy<select id="opS">${Object.keys(STRATS).map(k => `<option ${k === S.strat ? 'selected' : ''}>${k}</option>`).join('')}</select></label>
            <label>Width (strikes)<input id="opW" type="number" min="1" step="1" value="${S.w}"></label>
            <label>Lots<input id="opQ" type="number" min="1" step="1" value="${S.qty}"></label></div>
          <div class="mk-bar" style="margin-top:6px"><span class="note">Vol presets:</span>${(() => { const c = contract() || {}; return [['HV10', c.hv10], ['HV20', c.hv20], ['HV30', c.hv30], ['HV60', c.hv60], ['Parkinson', c.park20], ['5-yr median', (m.cone.find(x => x.n === 20) || {}).p50]].filter(x => x[1]).map(([l, v]) => `<button data-v="${v}">${l} ${fx(v, 1)}</button>`).join(''); })()}</div>
          <div class="tbl"><table id="opLegs"><tr><th class="l">Leg</th><th>Lots (+ buy / − sell)</th><th>Strike</th><th>Vol %</th><th>Premium</th><th>$ / lot</th><th>Delta</th><th>Gamma</th><th>Theta $/day</th><th>Vega $/vol pt</th><th></th></tr></table></div>
          <div class="mk-bar"><button id="opAddC">+ call</button><button id="opAddP">+ put</button><button id="opAddF">+ futures</button></div>
          <div id="opSum"></div></div></div>
      <div class="card" style="margin-top:12px"><h2>Payoff</h2>
        <div class="op-in"><label>Days passed <b id="opDl">0</b> of ${Math.round(dte)}<input id="opD" type="range" min="0" max="${Math.max(1, Math.round(dte))}" value="${Math.min(S.days, Math.round(dte))}"></label>
          <label>Vol shift <b id="opVsl">${S.vshift > 0 ? '+' : ''}${S.vshift}</b> pts<input id="opVs" type="range" min="-15" max="15" step="1" value="${S.vshift}"></label>
          <label>Show Greek<select id="opG"><option value="delta">Delta</option><option value="gamma">Gamma</option><option value="theta">Theta $/day</option><option value="vega">Vega $/vol pt</option></select></label></div>
        <div class="grid g2"><div><canvas id="opPay" height="230"></canvas></div><div><canvas id="opGk" height="230"></canvas></div></div>
        <p class="note">Blue: profit/loss per position at expiry. Orange: today's value after the chosen days pass, with the vol shift applied. P&amp;L in dollars for ${S.qty} lot(s) at $${m.mult.toLocaleString()} per price unit, net of the premium paid or received at today's model prices. Commissions and the early-exercise premium of American options are ignored.</p></div></main>`;
    el.querySelectorAll('[data-s]').forEach(b => b.onclick = () => { sym = b.dataset.s; newState(); render(); });
    el.querySelectorAll('[data-v]').forEach(b => b.onclick = () => { S.vol = +b.dataset.v; S.legs.forEach(L => L.vol = null); render(); });
    const on = (id, f) => el.querySelector(id).onchange = e => { f(e.target.value); render(); };
    on('#opC', v => { S.c = v; const c = contract(); S.F = c.last; S.vol = c.vol || S.vol; S.exp = c.expiry; build(); });
    on('#opF', v => { S.F = +v; }); on('#opV', v => { S.vol = +v; }); on('#opR', v => { S.r = +v; }); on('#opE', v => { S.exp = v; });
    on('#opS', v => { S.strat = v; build(); }); on('#opW', v => { S.w = Math.max(1, +v); build(); }); on('#opQ', v => { S.qty = Math.max(1, +v); build(); });
    el.querySelector('#opAddC').onclick = () => { S.legs.push({ t: 'C', q: 1, K: round(S.F, m.step), vol: null }); render(); };
    el.querySelector('#opAddP').onclick = () => { S.legs.push({ t: 'P', q: 1, K: round(S.F, m.step), vol: null }); render(); };
    el.querySelector('#opAddF').onclick = () => { S.legs.push({ t: 'F', q: 1, K: S.F, vol: null }); render(); };
    el.querySelector('#opD').oninput = e => { S.days = +e.target.value; el.querySelector('#opDl').textContent = S.days; drawPay(); };
    el.querySelector('#opVs').oninput = e => { S.vshift = +e.target.value; el.querySelector('#opVsl').textContent = (S.vshift > 0 ? '+' : '') + S.vshift; drawPay(); };
    el.querySelector('#opG').onchange = () => drawPay();
    legs(); drawVol(); drawPay();
  }
  function legs() {
    const m = V.markets[sym], T = T0() / 365, tb = document.getElementById('opLegs');
    tb.querySelectorAll('tr.leg').forEach(r => r.remove());
    S.legs.forEach((L, i) => {
      const v = (L.vol ?? S.vol), o = L.t === 'F' ? { px: 0, delta: 1, gamma: 0, theta: 0, vega: 0 } : b76(L.t, S.F, L.K, T, v / 100, S.r / 100);
      const tr = document.createElement('tr'); tr.className = 'leg';
      tr.innerHTML = `<td class="l">${L.t === 'C' ? 'Call' : L.t === 'P' ? 'Put' : 'Futures'}</td><td><input type="number" step="1" value="${L.q}" data-k="q" style="width:60px"></td>
        <td><input type="number" step="${m.step}" value="${L.K}" data-k="K" style="width:80px"></td><td>${L.t === 'F' ? '–' : `<input type="number" step="0.5" value="${v}" data-k="vol" style="width:60px">`}</td>
        <td>${L.t === 'F' ? '–' : fx(o.px, m.dp + 1)}</td><td>${L.t === 'F' ? '–' : usd(o.px * m.mult * L.q)}</td><td>${fx(o.delta * L.q, 2)}</td><td>${fx(o.gamma * L.q, 4)}</td>
        <td>${usd(o.theta * L.q * m.mult)}</td><td>${usd(o.vega * L.q * m.mult)}</td><td><button data-x="${i}" class="op-x">✕</button></td>`;
      tb.appendChild(tr);
      tr.querySelectorAll('input').forEach(inp => inp.onchange = e => { const k = inp.dataset.k; L[k] = +e.target.value; render(); });
      tr.querySelector('[data-x]').onclick = () => { S.legs.splice(i, 1); render(); };
    });
    // summary
    const tot = value(S.F, T0(), 0), cost = entryCost(), lo = S.F * .02, hi = S.F * 2, xs = [];
    for (let i = 0; i <= 600; i++) xs.push(lo + (hi - lo) * i / 600);
    S.legs.forEach(L => xs.push(L.K)); xs.sort((a, b) => a - b);  // include kinks so max/min are exact
    const pay = xs.map(x => (value(x, 0, 0).px - cost) * m.mult);
    const be = []; for (let i = 1; i < xs.length; i++) if (Math.sign(pay[i]) !== Math.sign(pay[i - 1]) && pay[i] !== 0) be.push(xs[i - 1] + (xs[i] - xs[i - 1]) * (0 - pay[i - 1]) / (pay[i] - pay[i - 1]));
    const slopeR = S.legs.filter(L => L.t !== 'P').reduce((a, L) => a + L.q, 0);  // calls + futures decide the upside
    const maxP = slopeR > 0 ? 'unlimited' : usd(Math.max(...pay)), maxL = slopeR < 0 ? 'unlimited' : usd(Math.min(...pay));
    const sd = S.F * S.vol / 100 * Math.sqrt(T0() / 365);
    document.getElementById('opSum').innerHTML = `<div class="grid g2"><div class="tbl"><table>
      <tr><td class="l">Net premium</td><td>${cost >= 0 ? 'pay' : 'receive'} ${fx(Math.abs(cost), m.dp + 1)} ${m.unit} = <b>${usd(Math.abs(cost) * m.mult)}</b></td></tr>
      <tr><td class="l">Max profit at expiry</td><td>${maxP}</td></tr><tr><td class="l">Max loss at expiry</td><td>${maxL}</td></tr>
      <tr><td class="l">Breakevens at expiry</td><td>${be.map(b => fx(b, m.dp)).join(' · ') || '–'}</td></tr>
      <tr><td class="l">Expected 1σ move to expiry</td><td>±${fx(sd, m.dp)} (${fx(S.F - sd, m.dp)}–${fx(S.F + sd, m.dp)})</td></tr></table></div>
      <div class="tbl"><table><tr><th class="l">Position Greeks</th><th>Units</th><th>$</th></tr>
      <tr><td class="l">Delta (futures-equivalent lots)</td><td>${fx(tot.delta, 2)}</td><td>${usd(tot.delta * m.mult)} per 1 ${m.unit.split('/')[0]}</td></tr>
      <tr><td class="l">Gamma (delta change per 1 ${m.unit.split('/')[0]})</td><td>${fx(tot.gamma, 4)}</td><td></td></tr>
      <tr><td class="l">Theta (per calendar day)</td><td>${fx(tot.theta, 4)}</td><td>${usd(tot.theta * m.mult)}</td></tr>
      <tr><td class="l">Vega (per 1 vol point)</td><td>${fx(tot.vega, 4)}</td><td>${usd(tot.vega * m.mult)}</td></tr></table></div></div>`;
  }
  function chart(id, cfg) { if (charts[id]) charts[id].destroy(); const c = document.getElementById(id); if (!c || !window.Chart) return; charts[id] = new Chart(c, cfg); }
  function drawPay() {
    const m = V.markets[sym], dte = T0(), sd = Math.max(S.F * S.vol / 100 * Math.sqrt(Math.max(dte, 5) / 365), S.F * .03);
    const lo = Math.max(S.F - 3.2 * sd, S.F * .2), hi = S.F + 3.2 * sd, xs = []; for (let i = 0; i <= 160; i++) xs.push(lo + (hi - lo) * i / 160);
    const cost = entryCost(), left = Math.max(dte - S.days, 0);
    const exp = xs.map(x => ({ x, y: (value(x, 0, 0).px - cost) * m.mult }));
    const now = xs.map(x => ({ x, y: (value(x, left, S.vshift).px - cost) * m.mult }));
    const G = document.getElementById('opG').value;
    const gk = xs.map(x => { const v = value(x, left, S.vshift); return { x, y: G === 'delta' ? v.delta : G === 'gamma' ? v.gamma : v[G] * m.mult }; });
    const base = { type: 'line', options: { animation: false, interaction: { mode: 'index', intersect: false }, scales: { x: { type: 'linear', title: { display: true, text: `${m.name} futures (${m.unit})` } } },
      plugins: { legend: { position: 'bottom' } } } };
    chart('opPay', { ...base, data: { datasets: [
      { label: 'at expiry', data: exp, borderColor: '#2f6db3', borderWidth: 2, pointRadius: 0 },
      { label: `after ${S.days} day(s)${S.vshift ? `, vol ${S.vshift > 0 ? '+' : ''}${S.vshift}` : ''}`, data: now, borderColor: '#c48a1c', borderWidth: 2, pointRadius: 0, borderDash: [5, 3] },
      { label: 'current futures', data: [{ x: S.F, y: Math.min(...exp.map(p => p.y), ...now.map(p => p.y)) }, { x: S.F, y: Math.max(...exp.map(p => p.y), ...now.map(p => p.y)) }], borderColor: '#8a8984', borderWidth: 1, pointRadius: 0 }] },
      options: { ...base.options, scales: { ...base.options.scales, y: { title: { display: true, text: 'P&L ($)' } } } } });
    chart('opGk', { ...base, data: { datasets: [{ label: `${G} after ${S.days} day(s)`, data: gk, borderColor: '#7a4fa0', borderWidth: 2, pointRadius: 0 }] },
      options: { ...base.options, scales: { ...base.options.scales, y: { title: { display: true, text: G === 'delta' ? 'lots' : G === 'gamma' ? 'per unit' : '$' } } } } });
  }
  function drawVol() {
    const m = V.markets[sym];
    chart('opCone', { type: 'line', data: { labels: m.cone.map(c => c.n + 'd'), datasets: [
      { label: 'now', data: m.cone.map(c => c.now), borderColor: '#b8452f', borderWidth: 2 }, { label: 'median', data: m.cone.map(c => c.p50), borderColor: '#8a8984', borderDash: [4, 3] },
      { label: '10th', data: m.cone.map(c => c.p10), borderColor: 'rgba(47,109,179,.5)', pointRadius: 0 }, { label: '90th', data: m.cone.map(c => c.p90), borderColor: 'rgba(47,109,179,.5)', pointRadius: 0, fill: '-1', backgroundColor: 'rgba(47,109,179,.08)' }] },
      options: { plugins: { title: { display: true, text: 'Vol cone (front month, 5 years, %)' }, legend: { labels: { boxWidth: 10 } } } } });
    chart('opSeas', { type: 'bar', data: { labels: ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'], datasets: [{ label: 'median 20-day vol', data: m.seasonal, backgroundColor: m.seasonal.map((v, i) => i === new Date().getMonth() ? '#c48a1c' : '#9bb7d9') }] },
      options: { plugins: { title: { display: true, text: 'Seasonality of 20-day vol (%)' }, legend: { display: false } } } });
    chart('opHist', { type: 'line', data: { labels: m.hv20_hist.map(r => r[0]), datasets: [{ label: '20-day realized vol, front month', data: m.hv20_hist.map(r => r[1]), borderColor: '#2f6db3', pointRadius: 0, borderWidth: 1.5 }] },
      options: { plugins: { legend: { display: false }, title: { display: true, text: '20-day realized vol, last year (%)' } }, scales: { x: { ticks: { maxTicksLimit: 6 } } } } });
  }
  async function show() {
    if (!built) { V = await getJSON('data/vol/vol.json').catch(() => null); built = true; if (V && !V.markets[sym]) sym = Object.keys(V.markets)[0]; if (V) newState(); }
    history.replaceState(null, '', '#options');
    if (!V) { document.getElementById('options').innerHTML = '<main><div class="card"><p class="note">Volatility data not built yet.</p></div></main>'; return; }
    render();
  }
  return { show, b76 };
})();
