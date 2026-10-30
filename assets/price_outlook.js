// Cotton > Outlook: price and spread outlook to May expiry from the desk balance-sheet scenarios and their simulation, with merchant hedging.
// Data: data/derived/ct_price_outlook.json (models/cotton_price_outlook.py).
const PriceOutlook = (() => {
  const f = (v, d = 1) => v == null || Number.isNaN(+v) ? '–' : fmt(v, d);
  const s = (v, d = 2) => v == null ? '–' : `${v > 0 ? '+' : ''}${fmt(v, d)}`;
  async function mount(el) {
    if (!el) return;
    const D = await getJSON('data/derived/ct_price_outlook.json').catch(() => null);
    if (!D) { el.innerHTML = ''; return; }
    const S = D.scenarios, M = D.mc, Hd = D.hedge, P = D.prices, SP = D.spreads;
    const lab = { bull: 'Bullish', base: 'Base', bear: 'Bearish', usda: 'USDA' };
    const pr = o => `${f(o[10])} / ${f(o[50])} / ${f(o[90])}`;
    el.innerHTML = `<div class="card"><h2>Price and spread outlook to May expiry <span class="note">as of ${D.asof} · built ${D.built}</span></h2>
      <p>May settled <b>${f(P.K, 2)}</b> (Mar ${f(P.H, 2)}, Jul ${f(P.N, 2)}, Dec ${f(P.Z_old, 2)}, new-crop Dec ${f(P.Z_new, 2)}). Spreads: Dec/Mar ${s(SP.ZH)}, Mar/May ${s(SP.HK)}, May/Jul ${s(SP.KN)}, Jul/Dec ${s(SP.NZ)}.</p>
      <div class="grid g2">
        <div><h3>Simulation to mid-March (${fmt(M.n, 0)} balance-sheet outcomes, ${fmt(M.paths, 0)} price paths)</h3>
          <p class="note">Every combination: crop × exports × India's duty path (the balance-sheet simulation) × which history the market follows (four fits drawn equally) × that fit's typical miss; stocks/use is not capped. Simulated USDA March stocks/use: ${pr(M.su_pct)}%. Median May by fit: ${Object.entries(M.by_fit).map(([k, v]) => `${{ex_short: 'excl. shortage years', ex_2010: 'excl. 2010/11', since_2013: 'since 2013/14', all: 'all seasons'}[k]} ${f(v, 0)}`).join(', ')}.</p><div class="tbl"><table><tr><th class="l">10th / median / 90th percentile</th><th>Value</th></tr>
          <tr><td class="l">May, February–March average</td><td><b>${pr(M.may_feb_mar)}</b> <span class="note">(above today ${M.p_may_above_now}%)</span></td></tr>
          <tr><td class="l">Highest May trades by mid-March</td><td>${pr(M.may_high)}</td></tr>
          <tr><td class="l">Lowest May trades by mid-March</td><td>${pr(M.may_low)}</td></tr>
          <tr><td class="l">Chance May trades at or above</td><td>${Object.entries(M.p_above).map(([k, v]) => `${k}: ${v}%`).join(' · ')}</td></tr>
          <tr><td class="l">Chance May trades at or below</td><td>${Object.entries(M.p_below).map(([k, v]) => `${k}: ${v}%`).join(' · ')}</td></tr>
          <tr><td class="l">May/Jul, February–March</td><td>${pr(M.may_jul)} <span class="note">(inverse ${M.p_kn_inverse}%)</span></td></tr>
          <tr><td class="l">Jul/Dec, February–March</td><td>${pr(M.jul_dec)} <span class="note">(above today ${M.p_nz_above_now}%)</span></td></tr>
          <tr><td class="l">Mar/May near its expiry</td><td>${pr(M.mar_may)} <span class="note">(history; inverse ${M.p_hk_inverse}%)</span></td></tr></table></div></div>
      </div>
      ${D.fair ? `<div style="margin-top:8px"><h3>Fair value in February–March, when USDA's numbers settle</h3>
        <div class="tbl"><table><tr><th class="l">If USDA's March US stocks/use is</th><th>Fair May</th><th>Fair Mar/May (Jan–Feb, Jan USDA)</th><th>Fair May/Jul</th><th>Fair Jul/Dec</th></tr>
        ${['usda', 'bear', 'base', 'bull'].map(k => { const F = D.fair.scen[k]; return `<tr${k === 'base' ? ' style="font-weight:600"' : ''}><td class="l">${f(F.su)}% (${lab[k]}${k === 'bull' ? ', beyond history' : k === 'base' ? ', just below the lowest outside 2010/11' : ''})</td><td>${f(F.px.ex_short, 0)}–${f(F.px.ex_2010, 0)}</td><td>${F.hk ? `${s(F.hk.ex_short)} to ${s(F.hk.ex_2010)}` : '–'}</td><td>${s(F.kn.ex_short)} to ${s(F.kn.ex_2010)}</td><td>${s(F.nz.ex_short, 1)} to ${s(F.nz.ex_2010, 1)}</td></tr>`; }).join('')}
        <tr><td class="l">Today</td><td>${f(P.K, 2)}</td><td>${s(SP.HK)}</td><td>${s(SP.KN)}</td><td>${s(SP.NZ)}</td></tr>
        <tr><td class="l">USDA stocks/use implied by today's price</td><td>${f(D.fair.implied_su.px.ex_short, 0)}–${f(D.fair.implied_su.px.ex_2010, 0)}%</td><td>${D.fair.implied_su.hk?.ex_2010 ? f(D.fair.implied_su.hk.ex_2010, 0) + '%' : '–'}</td><td>${f(D.fair.implied_su.kn.ex_short, 0)}–${f(D.fair.implied_su.kn.ex_2010, 0)}%</td><td>${f(D.fair.implied_su.nz.ex_short, 0)}–${f(D.fair.implied_su.nz.ex_2010, 0)}%</td></tr>
        <tr><td class="l">Fit (R², excl. world-shortage seasons → excl. 2010/11 → all)</td><td>${f(D.fair.fit.px.ex_short.r2, 2)} → ${f(D.fair.fit.px.ex_2010.r2, 2)} → ${f(D.fair.fit.px.all.r2, 2)}</td><td>${D.fair.fit.hk ? `${f(D.fair.fit.hk.ex_short.r2, 2)} → ${f(D.fair.fit.hk.ex_2010.r2, 2)} → ${f(D.fair.fit.hk.all.r2, 2)}` : '–'}</td><td>${f(D.fair.fit.kn.ex_short.r2, 2)} → ${f(D.fair.fit.kn.ex_2010.r2, 2)} → ${f(D.fair.fit.kn.all.r2, 2)}</td><td>${f(D.fair.fit.nz.ex_short.r2, 2)} → ${f(D.fair.fit.nz.ex_2010.r2, 2)} → ${f(D.fair.fit.nz.all.r2, 2)}</td></tr></table></div>
        <p>Ranges: fitted without the two world-shortage seasons (2010/11, 2021/22) and without 2010/11 only. Today's prices imply USDA's March US stocks/use near ${f(D.fair.implied_su.px.ex_2010, 0)}% for May and ${f(D.fair.implied_su.nz.ex_2010, 0)}% for Jul/Dec, between USDA's ${f(D.usda_su)}% now and the desk base ${f(D.fair.scen.base.su)}%. If USDA moves to the desk base by March, May, May/Jul and Jul/Dec are all cheap; the bullish case is below any March number since 2007/08 (lowest ${f(D.fair.min_su_hist)}%, ${D.fair.min_su_my}), so treat its values as direction, not level.</p></div>` : ''}
      ${D.options ? (() => { const O = D.options; const bins = Object.keys(O.rn);
        return `<div style="margin-top:8px"><h3>What the May options price (${O.date}, futures ${f(O.F, 2)})</h3>
        <p>At-the-money implied vol ${f(O.atm)}% (${O.iv_hist ? `${f(O.iv_hist.pct, 0)}th percentile of late-October May vol since 2000, median ${f(O.iv_hist.median)}%` : ''}); 25-delta risk reversal <b>${s(O.rr25)}</b> vol (calls ${f(O.iv25c)}% at ${f(O.k25c, 0)} over puts ${f(O.iv25p)}% at ${f(O.k25p, 0)}). Largest open interest: ${O.top_oi.map(t => `${f(t.k, 0)} ${t.cp === 'C' ? 'calls' : 'puts'} ${fmt(t.oi, 0)}`).join(', ')}.</p>
        <div class="tbl"><table><tr><th class="l">May at option expiry</th>${bins.map(b => `<th>${b.replace('0-70', '<70').replace('140-999', '>140')}</th>`).join('')}</tr>
          <tr><td class="l">Options market (from the smile)</td>${bins.map(b => `<td>${f(O.rn[b], 0)}%</td>`).join('')}</tr>
          <tr><td class="l">Desk, conservative</td>${bins.map(b => `<td>${f(O.desk_cons[b], 0)}%</td>`).join('')}</tr>
          <tr><td class="l">Desk, every combination</td>${bins.map(b => `<td>${f(O.desk[b], 0)}%</td>`).join('')}</tr></table></div>
        <div class="tbl" style="margin-top:6px"><table><tr><th class="l">May option</th>${O.options.map(o => `<th>${f(o.k, 0)}${o.cp}</th>`).join('')}</tr>
          <tr><td class="l">Market</td>${O.options.map(o => `<td>${f(o.mkt, 2)}</td>`).join('')}</tr>
          <tr><td class="l">Desk value, conservative</td>${O.options.map(o => `<td class="${o.desk_cons > o.mkt * 1.15 ? 'up' : o.desk_cons < o.mkt * 0.85 ? 'dn' : ''}">${f(o.desk_cons, 2)}</td>`).join('')}</tr>
          <tr><td class="l">Desk value, every combination</td>${O.options.map(o => `<td class="${o.desk > o.mkt * 1.15 ? 'up' : o.desk < o.mkt * 0.85 ? 'dn' : ''}">${f(o.desk, 2)}</td>`).join('')}</tr></table></div>
        <p class="note">Market probabilities from the settlement smile (no discounting). Desk distributions: the February–March simulation carried to option expiry at historical vol; "conservative" holds stocks/use at the lowest March number outside 2010/11. Green: desk value at least 15% above market; red: at least 15% below. Not advice.</p></div>`; })() : ''}
      <div class="grid g2" style="margin-top:8px">
        <div><h3>Merchant hedging vs hedgeable supply</h3><p>Producer/merchant shorts ${f(Hd.pm_short_m, 1)} m bales (${Hd.date}) = <b>${f(Hd.pct)}% of world exports</b>, rank ${Hd.rank} at this point of the season since 2010/11 (median ${f(Hd.median_pct)}%). Open interest ${f(Hd.oi_m, 1)} m bales; managed money net ${s(Hd.mm_net_m, 1)} m.
          In seasons when merchants were this heavily hedged (38%+), May rose ${s(Hd.high_mean, 1)}% on average to expiry; in lightly hedged ones (below 30%) ${s(Hd.low_mean, 1)}%.
          Net of their longs merchants are short ${f(Hd.net_pct)}% of world exports (rank ${Hd.net_rank}); in the seasons May rallied 12%+ the net averaged ${f(Hd.net_bull_avg)}% (${(Hd.bull_eps || []).map(e => `${e.my} ${f(e.net_pct, 0)}%`).join(', ')}).</p>
          ${D.oncall ? `<p>On-call (${D.oncall.oncall_date}): old-crop unfixed call sales ${fmt(D.oncall.S_old / 1000, 1)}k lots (${f(D.oncall.S_old_seas_pct, 0)}th percentile of the last five seasons), unfixed purchases ${fmt(D.oncall.P_old / 1000, 1)}k (${f(D.oncall.P_old_seas_pct, 0)}th); mills still have to fix a net ${fmt(D.oncall.N_old / 1000, 1)}k lots. Commercials' old-crop long/short ratio is ${f(D.oncall.ls_old, 2)} (${f(D.oncall.ls_old_pct, 0)}th percentile of three years): little long cover, so mill fixing has to buy in the market.</p>` : ''}</div>
        <div><h3>Seasons when USDA's October balance sheet was too loose</h3><div class="tbl"><table><tr><th class="l">Season</th><th>Oct stocks/use</th><th>Final</th><th>May, late Oct → expiry</th><th>Merchant shorts</th><th>Jul/Dec in June</th></tr>
          ${D.analog.map(a => `<tr><td class="l">${a.my}${['2010/11', '2021/22'].includes(a.my) ? '*' : ''}</td><td>${f(a.su_oct)}%</td><td>${f(a.su_fin)}%</td><td>${s(a.may_chg, 1)}%</td><td>${f(a.pm_short_pct, 0)}%</td><td>${s(a.jul_dec_june, 1)}</td></tr>`).join('')}</table></div>
          <p class="note">* World-shortage seasons, when old-crop spreads inverted (Mar/May ${Object.entries(D.typical.shortage).map(([k, v]) => `${k} ${s(v.hk, 1)}`).join(', ')}); in other seasons Mar/May ended near ${s(D.typical.hk_feb)} and May/Jul near ${s(D.typical.kn_apr)}.</p></div>
      </div>
      <p class="note"><b>Variables used:</b> ${D.vars.join('; ')}. A guide to likely ranges, not a forecast or advice.</p></div>`;
  }
  return { mount };
})();
