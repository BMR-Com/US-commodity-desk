// Trade playbook renderer (shared by dairy and meats): <div data-playbook="data/.../playbook.json"></div>
const Playbook = (() => {
  const n = (v, d = 2) => v == null ? '–' : (+v).toFixed(d);
  const usd = v => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v < 0 ? '-' : ''}$${Math.abs(Math.round(v)).toLocaleString()}</span>`;
  const side = s => /^(long|buy)/.test(s) ? `<b class="up">${s}</b>` : `<b class="dn">${s}</b>`;
  const T = (head, rows) => `<div class="tbl"><table class="bt-t"><tr>${head.map((h, i) => `<th class="${i < 2 ? 'l' : ''}">${h}</th>`).join('')}</tr>${rows.join('')}</table></div>`;
  function statLine(s) {
    if (!s) return '';
    if (s.sharpe == null) return `<p class="note">Track record: right ${n(s.hit, 0)}% of the time, ${usd(s.avg_usd_per_class_contract)} average per Class contract, ${s.months ?? '–'} months.</p>`;
    return `<p class="note">Track record (one lot per signal, after costs): Sharpe <b>${n(s.sharpe)}</b> (${s.sharpe_2012_19 != null ? `2012-19 ${n(s.sharpe_2012_19)}, ` : ''}2020-23 ${n(s.sharpe_2020_23)}, 2024-26 ${n(s.sharpe_2024_26)}) · right ${n(s.hit, 0)}% · average win ${usd(s.avg_win_usd)} vs loss ${usd(s.avg_loss_usd)} · ${usd(s.ann_usd)} a year · worst drawdown ${usd(s.maxdd_usd)} · worst week ${usd(s.worst_week_usd)} · ${s.trades} trades${s.avg_lots ? `, ${s.avg_lots} lots open on average` : ''}</p>`;
  }
  function posTable(P) {
    if (!P.length) return '<p><b>Now:</b> no position. Nothing meets the entry rule today.</p>';
    const keys = [['contract', 'Contract'], ['side', 'Trade'], ['futures', 'Futures'], ['estimate', 'Settlement estimate'], ['edge_usd', 'Edge $/lot'], ['cost_usd', 'Cost $/lot'],
      ['gap_cwt', 'Gap $/cwt'], ['chg_4w_pct', '4-week %'], ['entry_date', 'Entered'], ['entry_price', 'Entry'], ['stop', 'Stop'], ['open_pnl_usd', 'Open $/lot'],
      ['weeks_published', 'Weeks published'], ['settles', 'Settles'], ['legs_per_10', 'Legs (per 10)'], ['exit_signal', 'Exit when'], ['note', '']]
      .filter(([k]) => P.some(p => p[k] != null && p[k] !== ''));
    return `<p><b>Now:</b> ${P.length} position${P.length > 1 ? 's' : ''}${P[0].unit ? '' : ''}.</p>` + T(keys.map(k => k[1]), P.map(p => `<tr>${keys.map(([k], i) => {
      const v = p[k]; let h = v ?? '';
      if (k === 'side') h = side(v); else if (/usd/.test(k)) h = usd(v); else if (k === 'futures' || k === 'estimate') h = `${v} <span class="note">${p.unit || ''}</span>`;
      else if (k === 'chg_4w_pct') h = `<span class="${v > 0 ? 'up' : 'dn'}">${v > 0 ? '+' : ''}${v}%</span>`;
      return `<td class="${i < 2 ? 'l' : ''}">${h}</td>`; }).join('')}</tr>`));
  }
  function card(t, i) {
    const live = t.positions.length;
    return `<details class="card" style="margin-top:10px"${i < 2 || live ? ' open' : ''}><summary><h3 style="display:inline">${t.name}</h3> <span class="note">${t.type}${t.stats?.sharpe != null ? ` · Sharpe ${n(t.stats.sharpe)}` : ''} · ${live ? `<b>${live} live</b>` : 'flat'}</span></summary>
      <p>${t.thesis}</p>
      <ul class="read"><li><b>Entry.</b> ${t.entry}</li><li><b>Exit.</b> ${t.exit}</li><li><b>Risk.</b> ${t.risk}</li>
      <li><b>What to track.</b> ${t.track.join(' · ')}</li></ul>
      ${t.levels ? `<p class="note">Levels on ${t.levels.month} as of ${t.levels.date}: close ${n(t.levels.close, 3)} · buy above ${n(t.levels.buy_above, 3)} · sell below ${n(t.levels.sell_below, 3)} · long exit below ${n(t.levels.exit_long_below, 3)} · short exit above ${n(t.levels.exit_short_above, 3)}</p>` : ''}
      ${posTable(t.positions)}${statLine(t.stats)}</details>`;
  }
  const sg = v => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${(+v).toFixed(2)}</span>`;
  function gridHtml(G) {
    if (!G || !G.length) return '';
    return `<details><summary>Every variant tested, best first (ranked by the weakest of 2012-19, 2020-23, 2024-26)</summary>${T(['Variant', 'Family', 'Sharpe', '2012-19', '2020-23', '2024-26', 'Hit', 'Win / loss', '$ / year', 'Worst drawdown', 'Avg lots'],
      G.map(g => `<tr><td class="l">${g.key}</td><td class="l">${g.group}</td><td><b>${sg(g.sharpe)}</b></td><td>${sg(g.sharpe_2012_19)}</td><td>${sg(g.sharpe_2020_23)}</td><td>${sg(g.sharpe_2024_26)}</td><td>${n(g.hit, 0)}%</td><td>${n(g.payoff)}</td><td>${usd(g.ann_usd)}</td><td>${usd(g.maxdd_usd)}</td><td>${n(g.avg_lots, 1)}</td></tr>`))}</details>`;
  }
  function accHtml(A) {
    if (!A) return '';
    return Object.entries(A).map(([s, a]) => `<p class="note">How well each method predicts the final settlement (${s}, mean abs error, % of price): ${Object.entries(a).map(([h, x]) => `${h.replace('le_', '≤')}: futures ${x.futures_mae_pct}%, cash ${x.rw_mae_pct}%, cash + seasonal ${x.sea_mae_pct}%, model ${x.ridge_mae_pct}%, model + futures ${x.ridge_b_mae_pct}%`).join(' · ')}. Futures are the best single forecast at every horizon.</p>`).join('');
  }
  async function mount(el) {
    const d = await getJSON(el.dataset.playbook).catch(() => null);
    if (!d) { el.innerHTML = ''; return; }
    const live = d.trades.filter(t => t.positions.length);
    el.innerHTML = `<div class="card"><h2>Trade playbook <span class="note">positions as of ${d.as_of} settlements (updated nightly); track records refreshed ${d.stats_generated || "–"}, tested from ${d.stats_since || '–'}</span></h2>
      <p>Every strategy the desk has tested, written as a trade: when to get in, when to get out, the risk, and what to watch. ${live.length ? `Live today: ${live.map(t => `<b>${t.name}</b> (${t.positions.length})`).join(', ')}.` : 'No strategy has a live signal today.'}</p>
      ${d.intro ? `<p>${d.intro}</p>` : ''}${accHtml(d.accuracy)}${gridHtml(d.grid)}</div>${d.trades.map(card).join('')}
      <p class="note">Research only, not advice. Results assume fills at settlement for one lot per signal after half a bid-ask per side; these markets are thin, so larger size moves prices. Check live quotes before acting.</p>`;
  }
  const run = () => document.querySelectorAll('[data-playbook]').forEach(el => el.dataset.mounted || (el.dataset.mounted = 1, mount(el)));
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', run) : run();
  return { mount };
})();
