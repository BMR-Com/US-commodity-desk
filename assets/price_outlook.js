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
        <div><h3>Scenarios (balance sheet → history)</h3><div class="tbl"><table><tr><th class="l">Case</th><th>US stocks/use</th><th>vs USDA</th><th>May at expiry</th><th>Range (±1 sd)</th><th>Jul/Dec in June</th></tr>
          ${['bull', 'base', 'bear', 'usda'].map(k => `<tr${k === 'base' ? ' style="font-weight:600"' : ''}><td class="l">${lab[k]}</td><td>${f(S[k].su)}%</td><td>${s(S[k].dsu, 1)}</td><td>${f(S[k].may)} <span class="note">(${s(S[k].may_pct, 1)}%)</span></td><td>${f(S[k].may_lo)}–${f(S[k].may_hi)}</td><td>${s(S[k].jul_dec, 1)}</td></tr>`).join('')}</table></div>
          <p class="note">Taking merchant hedging into account as well, the base case is ${f(S.base.may_hedge)} (${s(S.base.may_hedge_pct, 1)}%).</p></div>
        <div><h3>Simulation (${fmt(M.n, 0)} balance-sheet outcomes, ${fmt(M.paths, 0)} price paths)</h3><div class="tbl"><table><tr><th class="l">10th / median / 90th percentile</th><th>Value</th></tr>
          <tr><td class="l">May at expiry (${D.expiry})</td><td><b>${pr(M.may_expiry)}</b></td></tr>
          <tr><td class="l">Highest May trades before expiry</td><td>${pr(M.may_high)}</td></tr>
          <tr><td class="l">Lowest May trades before expiry</td><td>${pr(M.may_low)}</td></tr>
          <tr><td class="l">Chance May trades at or above</td><td>${Object.entries(M.p_above).map(([k, v]) => `${k}: ${v}%`).join(' · ')}</td></tr>
          <tr><td class="l">Chance May trades at or below</td><td>${Object.entries(M.p_below).map(([k, v]) => `${k}: ${v}%`).join(' · ')}</td></tr>
          <tr><td class="l">Mar/May near expiry</td><td>${pr(M.mar_may)} <span class="note">(inverse ${M.p_hk_inverse}%)</span></td></tr>
          <tr><td class="l">May/Jul near expiry</td><td>${pr(M.may_jul)} <span class="note">(inverse ${M.p_kn_inverse}%)</span></td></tr>
          <tr><td class="l">Jul/Dec in June</td><td>${pr(M.jul_dec)}</td></tr></table></div></div>
      </div>
      ${D.fair ? `<div style="margin-top:8px"><h3>Fair value from the level of US stocks/use</h3>
        <div class="tbl"><table><tr><th class="l">Case</th><th>US stocks/use</th><th>Fair May (Nov–Apr average), 2007/08 on excl. 2010/11</th><th>2013/14 on</th><th>All seasons</th></tr>
        ${['usda', 'bear', 'base', 'bull'].map(k => `<tr${k === 'base' ? ' style="font-weight:600"' : ''}><td class="l">${lab[k]}</td><td>${f(D.fair.scen[k].su)}%</td><td>${f(D.fair.scen[k].ex_2010)}</td><td>${f(D.fair.scen[k].since_2013)}</td><td>${f(D.fair.scen[k].all)}</td></tr>`).join('')}</table></div>
        <p>May at ${f(P.K, 2)} already implies US stocks/use of <b>${f(D.fair.implied_su.ex_2010)}–${f(D.fair.implied_su.all)}%</b> against USDA's ${f(D.usda_su)}%: the market is pricing close to the desk base case, not USDA's. What it is not pricing is the tight tail: the bullish case (${f(D.fair.scen.bull.su)}%) is below the lowest US stocks/use since 2007/08 (${f(D.fair.min_su_hist)}% in ${D.fair.min_su_my}, when May averaged ${f(D.fair.px_at_min)} with a world shortage). Simulated fair value: ${pr(D.fair.sim)}.</p></div>` : ''}
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
