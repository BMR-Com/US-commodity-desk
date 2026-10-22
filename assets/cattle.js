// Live & feeder cattle section.
const Cattle = (() => {
  const L = 'data/livestock/derived/';
  let built = false, tab = 'c-primer', C, F, BIAS, CS;
  function shell() {
    $('#cattle').innerHTML = `<nav class="tabs" id="cTabs"><button data-t="c-primer" class="on">1 · Primer</button><button data-t="c-geo">Where it's produced, trade &amp; weather</button><button data-t="c-sd">2 · Supply &amp; demand</button>
      <button data-t="c-flows">3 · Futures, options &amp; COT</button><button data-t="c-outlook">4 · Outlook</button></nav><main><div id="cBody"></div></main>`;
    $$('#cTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; $$('#cTabs button').forEach(x => x.classList.toggle('on', x === b)); render(); });
  }
  async function show() {
    if (!built) { shell(); [C, F, BIAS, CS] = await Promise.all([getJSON(L + 'cattle.json'), getJSON(L + 'flows.json').catch(() => null), getJSON('data/derived/convergence_bias.json').catch(() => null), getJSON(L + 'cattle_sd.json').catch(() => null)]); built = true; }
    const h = location.hash.slice(1); if (/^c-/.test(h)) { tab = h; $$('#cTabs button').forEach(x => x.classList.toggle('on', x.dataset.t === tab)); }
    render();
  }
  function render() { history.replaceState(null, '', '#' + tab); ({ 'c-primer': primer, 'c-geo': () => Geo.mount($('#cBody'), 'beef'), 'c-sd': sd, 'c-flows': flows, 'c-outlook': outlook })[tab](); }
  const body = h => { $('#cBody').innerHTML = h; };

  function primer() {
    body(Specs.slot('cattle') + `<div class="grid g2">
      <div class="card"><h2>The contracts</h2><div class="tbl"><table><tr><th></th><th class="l">Live cattle (LE)</th><th class="l">Feeder cattle (GF)</th></tr>
        <tr><td>Size</td><td class="l">40,000 lb</td><td class="l">50,000 lb</td></tr><tr><td>Quote</td><td class="l">¢/lb; 0.025¢ = $10</td><td class="l">¢/lb; 0.025¢ = $12.50</td></tr>
        <tr><td>Months</td><td class="l">Feb, Apr, Jun, Aug, Oct, Dec</td><td class="l">Jan, Mar, Apr, May, Aug, Sep, Oct, Nov</td></tr>
        <tr><td>Settlement</td><td class="l">Physical delivery of 1,050–1,500 lb steers (USDA Choice/Select mix) at approved yards, or by certificate</td><td class="l">Cash-settled to the CME Feeder Cattle Index (7-day weighted average of 700–899 lb feeder steer auction prices in 12 states)</td></tr></table></div>
        <h3>Convergence</h3><p>Live cattle converge to the 5-area fed steer cash price through the delivery mechanism, so the relevant cash series is USDA's 5-area weekly weighted average (LM_CT150). Feeder cattle converge exactly to the CME index. The desk's test of every expired live cattle contract since 2010 finds futures have settled 2–3% above where they traded 20–60 business days earlier, in both 2010–17 and 2018–26 (see Outlook): a persistent premium for being long, consistent with heavy short hedging by feedlots.</p></div>
      <div class="card"><h2>How each supply-and-demand line moves price</h2><div class="tbl"><table><tr><th class="l">Line</th><th class="l">Mechanism</th><th class="l">Watch</th></tr>
        <tr><td class="l">Beef cow herd</td><td class="l">The cattle cycle (~10 years). Heifer retention to rebuild the herd cuts beef supply first, then raises it 2–3 years later.</td><td class="l">January Cattle inventory, July report</td></tr>
        <tr><td class="l">Placements</td><td class="l">Cattle entering feedlots now are marketed 4–6 months later (lighter placements take longer).</td><td class="l">Monthly Cattle on Feed by weight</td></tr>
        <tr><td class="l">Marketings and weights</td><td class="l">Current-ness: slow marketings and rising carcass weights mean a backlog of fed cattle, bearish for cash.</td><td class="l">COF marketings, carcass weights</td></tr>
        <tr><td class="l">Boxed beef</td><td class="l">Packers bid cattle off the cutout; the cutout-minus-cattle spread is their margin.</td><td class="l">LM_XB403 Choice/Select</td></tr>
        <tr><td class="l">Feeder supply</td><td class="l">Calf crop and pasture conditions; drought forces early placements and cow culling.</td><td class="l">Drought, auction volumes</td></tr>
        <tr><td class="l">Corn price</td><td class="l">Feed cost: higher corn lowers what feedlots can pay for feeders (feeder prices fall vs live).</td><td class="l">Corn futures</td></tr></table></div></div></div>
      <div class="card" style="margin-top:12px"><h2>Feeding margin calculator</h2><div class="grid g2"><div>
        <div class="slider"><label>Feeder $/cwt</label><input type="range" id="fmF" min="200" max="450" step="0.5" value="340"><output id="ofmF"></output></div>
        <div class="slider"><label>Live $/cwt</label><input type="range" id="fmL" min="150" max="300" step="0.5" value="230"><output id="ofmL"></output></div>
        <div class="slider"><label>Corn $/bu</label><input type="range" id="fmC" min="3" max="8" step="0.05" value="4.5"><output id="ofmC"></output></div>
        <p class="note">750 lb feeder in, 1,400 lb out, ~6.5 lb gain per bushel of corn-equivalent feed and $0.55/lb non-feed cost of gain; a teaching tool for how corn and feeder prices set what a feedlot can bid, not a costing model.</p></div>
        <div><div class="bigout"><div><div class="note">Margin $/head</div><div class="v" id="ofmM"></div></div><div><div class="note">Breakeven live $/cwt</div><div class="v" id="ofmB"></div></div></div></div></div></div>`);
    const lf = C.curve_le?.settle?.[1], gf = C.curve_gf?.settle?.[0];
    if (lf) $('#fmL').value = lf; if (gf) $('#fmF').value = gf;
    const calc = () => { const fp = +$('#fmF').value, lp = +$('#fmL').value, cp = +$('#fmC').value, gain = 650;
      const feed = gain / 6.5 * cp, other = gain * 0.55, cost = 7.5 * fp + feed + other, rev = 14 * lp;
      $('#ofmF').textContent = fp.toFixed(1); $('#ofmL').textContent = lp.toFixed(1); $('#ofmC').textContent = cp.toFixed(2);
      $('#ofmM').innerHTML = sgn(rev - cost, 0); $('#ofmB').textContent = '$' + (cost / 14).toFixed(2); };
    $$('#cBody input').forEach(i => i.oninput = calc); calc();
  }

  function sd() {
    const cof = C.cof;
    const last = k => { const y = cof[k].yoy; const m = Object.keys(y).at(-1); return [m, y[m], cof[k].k_head.at(-1)]; };
    body(`<div class="grid g4">${[['on_feed', 'On feed (1,000+ head lots)'], ['placements', 'Placements'], ['marketings', 'Marketings']].map(([k, n]) => { const [m, y, v] = last(k);
      return `<div class="card kpi"><div class="lbl">${n} · ${m}</div><div class="val">${sgn(y, 1, '%')}</div><div class="sub">${fmt(v, 0)} thousand head, y/y</div></div>`; }).join('')}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>5-area fed steer price (weekly)</h2><div class="chart"><canvas id="c5"></canvas></div></div>
        <div class="card"><h2>Boxed beef cutout (600–900 lb)</h2><div class="chart"><canvas id="cBB"></canvas></div></div>
        <div class="card"><h2>Choice cutout − dressed steer ($/cwt)</h2><div class="chart"><canvas id="cSpr"></canvas></div><p class="note">Packer margin proxy (ignores hide/offal value and costs).</p></div>
        <div class="card"><h2>Cattle on feed y/y %</h2><div class="chart"><canvas id="cCof"></canvas></div></div></div>`);
    const f = C.five_area; chart('c5', { type: 'line', data: { labels: f.date, datasets: [{ label: 'Live FOB', data: f.live_fob, borderColor: PAL[0], pointRadius: 0 }, { label: 'Dressed delivered', data: f.dressed, borderColor: PAL[2], pointRadius: 0, yAxisID: 'y1' }] }, options: { scales: { y1: { position: 'right', grid: { display: false } } } } });
    const b = C.boxed_beef; chart('cBB', { type: 'line', data: { labels: b.date, datasets: [{ label: 'Choice', data: b.choice, borderColor: PAL[1], pointRadius: 0 }, { label: 'Select', data: b.select, borderColor: PAL[3], pointRadius: 0 }] } });
    const s = C.cutout_minus_dressed; chart('cSpr', { type: 'line', data: { labels: s.date, datasets: [{ label: 'spread', data: s.spread, borderColor: PAL[2], pointRadius: 0 }] } });
    const ks = Object.keys(cof.on_feed.yoy); chart('cCof', { type: 'bar', data: { labels: ks, datasets: ['on_feed', 'placements', 'marketings'].map((k, i) => ({ label: k.replace('_', ' '), data: ks.map(m => cof[k].yoy[m] ?? null), backgroundColor: PAL[i] })) } });
  }

  function flows() {
    const parts = ['LE', 'GF'].filter(s => F?.cot?.[s]);
    body(`<div id="cCotDesk" style="margin-bottom:12px"></div><div class="card"><h2>Positioning (secondary)</h2><div class="tbl"><table><tr><th>Contract</th><th>Report</th><th>Open int.</th><th>MM net</th><th>w/w</th><th>Pctl 3y</th><th>Prod/merch</th><th>Swap</th></tr>
      ${parts.map(s => { const x = F.cot[s].summary; return `<tr><td>${s === 'LE' ? 'Live cattle' : 'Feeder cattle'}</td><td>${x.date}</td><td>${fmt(x.oi, 0)}</td><td>${sgn(x.mm_net, 0)}</td><td>${sgn(x.mm_net_wow, 0)}</td><td>${fmt(x.mm_net_percentile_3y, 0)}</td><td>${sgn(x.pm_net, 0)}</td><td>${sgn(x.sw_net, 0)}</td></tr>`; }).join('')}</table></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h3>Live cattle curve vs ${C.curve_le?.cash_label ?? 'cash'}</h3><div class="chart"><canvas id="cLe"></canvas></div></div>
        <div class="card"><h3>Feeder cattle curve vs ${C.curve_gf?.cash_label ?? 'index'}</h3><div class="chart"><canvas id="cGf"></canvas></div></div>
        <div class="card"><h3>Live cattle front month</h3><div class="chart"><canvas id="cLePx"></canvas></div></div>
        <div class="card"><h3>Live cattle: managed money vs producer/merchant</h3><div class="chart"><canvas id="cLeCot"></canvas></div></div></div>`);
    const cv = (id, x) => x && chart(id, { type: 'bar', data: { labels: x.month, datasets: [{ type: 'line', label: 'settle', data: x.settle, borderColor: PAL[0], pointRadius: 2, yAxisID: 'y' }, { label: 'vs cash', data: x.vs_cash, backgroundColor: x.vs_cash.map(v => v >= 0 ? 'rgba(31,122,58,.5)' : 'rgba(179,38,30,.5)'), yAxisID: 'y1' }] }, options: { scales: { y1: { position: 'right', grid: { display: false } } } } });
    cv('cLe', C.curve_le); cv('cGf', C.curve_gf);
    const px = F?.prices?.LE; if (px) chart('cLePx', { type: 'line', data: { labels: px.date.slice(-750), datasets: [{ label: 'Live cattle ¢/lb', data: px.c1.slice(-750), borderColor: PAL[0], pointRadius: 0 }] } });
    const s = F?.cot?.LE?.series; if (s) chart('cLeCot', { type: 'line', data: { labels: s.date.slice(-260), datasets: [{ label: 'Managed money', data: s.mm_net.slice(-260), borderColor: PAL[1], pointRadius: 0 }, { label: 'Producer/merchant', data: s.pm_net.slice(-260), borderColor: PAL[2], pointRadius: 0 }] } });
    CotDesk.mount($('#cCotDesk'), ['LE', 'GF']);
  }

  function outlook() {
    const le = C.curve_le, gf = C.curve_gf, cof = C.cof, b = BIAS?.LE, g = BIAS?.GF, Lr = [];
    if (le) Lr.push(`<b>Live cattle vs cash:</b> ${le.cash_label} $${fmt(le.cash)}; ${le.month.slice(0, 3).map((m, i) => `${m} ${sgn(le.vs_cash[i], 2)}`).join(', ')}.`);
    if (gf) Lr.push(`<b>Feeders vs index:</b> ${gf.cash_label} $${fmt(gf.cash)}; ${gf.month.slice(0, 3).map((m, i) => `${m} ${sgn(gf.vs_cash[i], 2)}`).join(', ')}.`);
    const yo = k => { const y = cof[k].yoy, m = Object.keys(y).at(-1); return `${k.replace('_', ' ')} ${sgn(y[m], 1, '%')} (${m})`; };
    Lr.push(`<b>Cattle on feed:</b> ${yo('on_feed')}, ${yo('placements')}, ${yo('marketings')}.`);
    if (b && b.h20) Lr.push(`<b>Structural edge (tested):</b> live cattle futures have finished ${sgn(b.h20.mean_pct, 1, '%')} above their 20-day-out price and ${sgn(b.h60.mean_pct, 1, '%')} above their 60-day-out price on average since 2010 (${Math.round(100 * b.h60.up_share)}% of contracts), robust across 2010–17 and 2018–26. Feeder cattle show no comparable bias (${g?.h60 ? sgn(g.h60.mean_pct, 1, '%') : '–'} from 60 days).`);
    const x = F?.cot?.LE?.summary; if (x) Lr.push(`<b>Positioning (secondary):</b> managed money ${x.mm_net >= 0 ? 'long' : 'short'} ${fmt(Math.abs(x.mm_net), 0)} (${fmt(x.mm_net_percentile_3y, 0)} pctl 3y); producer/merchant ${sgn(x.pm_net, 0)}.`);
    body(`<div id="cattlePlaybook" data-playbook="data/livestock/derived/playbook_cattle.json" style="margin-bottom:12px"></div><div id="cTech" style="margin-bottom:12px"></div><div class="grid g2"><div class="card"><h2>Cattle desk readout</h2><ul class="read">${Lr.map(v => `<li>${v}</li>`).join('')}</ul><p class="note">What the numbers say, not a trade recommendation.</p></div>
      <div class="card"><h2>What has been tested</h2><div class="tbl"><table><tr><th>Contract</th><th>From 20 bdays</th><th>From 60</th><th>From 120</th></tr>
        ${[['Live cattle', b], ['Feeder cattle', g]].map(([n, v]) => v && v.h20 ? `<tr><td>${n} (${v.n_contracts})</td>${['h20', 'h60', 'h120'].map(h => `<td>${sgn(v[h].mean_pct, 2, '%')} · ${Math.round(100 * v[h].up_share)}% up</td>`).join('')}</tr>` : '').join('')}</table></div>
        <p class="note">Futures vs their own final price for every expired contract since 2010. The live cattle premium held in both halves of the sample (quarter-clustered t 2.3–3.2), but it coincides with a long cattle-cycle bull market, so treat it as a risk premium that can vanish in a herd-liquidation bear phase. </p>${CS ? `<h3>Placements → marketings pipeline</h3><p>Forecasting monthly fed-cattle marketings from placements by weight with fixed days on feed: mean abs error ${CS.test.mape_pipeline}% vs ${CS.test.mape_naive}% for the trailing marketings trend; the pipeline wins only ${Math.round(100 * CS.test.pipeline_beats_naive)}% of months (n=${CS.test.n}). Days on feed vary too much with feed costs, heifer share and weather for a fixed-lag pipeline; it is shown for context only. Implied y/y marketings from placements already reported: ${CS.forward.map(f => `${f.month} ${sgn(f.yoy_pct, 1, '%')}`).join(', ')}.</p>` : ''}</div></div>`);
    Playbook.mount($('#cattlePlaybook')); Tech.mount($('#cTech'), ['LE', 'GF']);
  }
  return { show };
})();
