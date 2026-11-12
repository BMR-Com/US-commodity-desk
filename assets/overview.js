// Overview tab: one coloured tile per commodity (red = bearish, yellow = neutral, green = bullish) from data/overview/overview.json.
const Overview = (() => {
  let D = null;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const f = (v, d = 2) => v == null || isNaN(v) ? '–' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const pc = (v, d = 1) => v == null || isNaN(v) ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${f(v, d)}%</span>`;
  const LAB = { fundamental: 'Fund', technical: 'Tech', cot: 'COT', seasonal: 'Seas' };
  const css = `
  .ov-grp{font-size:15px;font-weight:600;color:var(--acc);margin:18px 0 8px}
  .ov-grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr))}
  .ov-grid.big{grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr))}
  .ov-tile{border-radius:10px;border:1px solid var(--line);border-left:7px solid #999;padding:12px 14px;background:#fff;display:flex;flex-direction:column;gap:6px;min-height:100%}
  .ov-grid.big .ov-tile{min-height:560px}
  .ov-tile.bear3{background:#f6d0cb;border-left-color:#8e1b14}.ov-tile.bear2{background:#fbe1dc;border-left-color:#c0392b}
  .ov-tile.bear1{background:#fdebd6;border-left-color:#e07b22}.ov-tile.neutral{background:#fff7d1;border-left-color:#d4ac0d}
  .ov-tile.bull1{background:#eaf6dd;border-left-color:#8bc34a}.ov-tile.bull2{background:#d7efd5;border-left-color:#2e8b3e}
  .ov-tile.bull3{background:#bfe5c2;border-left-color:#1b5e20}.ov-tile.na{background:#f3f3f1;border-left-color:#aaa}
  .ov-hd{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
  .ov-hd h2{font-size:16px;margin:0}.ov-hd .px{font-size:13px;color:#333}.ov-hd .px b{font-size:17px}
  .ov-badge{font-size:12px;font-weight:700;padding:3px 9px;border-radius:999px;background:rgba(255,255,255,.75);white-space:nowrap;text-transform:capitalize}
  .ov-parts{display:flex;gap:5px;flex-wrap:wrap}
  .ov-parts span{font-size:11px;padding:1px 7px;border-radius:999px;background:rgba(255,255,255,.7);border:1px solid rgba(0,0,0,.08)}
  .ov-parts span.p{color:var(--up);font-weight:600}.ov-parts span.n{color:var(--dn);font-weight:600}
  .ov-sec{font-size:12.5px;line-height:1.42;color:#222}
  .ov-sec h4{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#555;margin:4px 0 1px;font-weight:700}
  .ov-sec ul{margin:2px 0 0 16px;padding:0}.ov-sec li{margin:1px 0}
  .ov-sec a{color:#1d4f91}
  .ov-lv{display:flex;gap:4px;flex-wrap:wrap;align-items:center;margin-top:2px}
  .ov-lv span{font-size:11.5px;padding:1px 6px;border-radius:5px;background:rgba(255,255,255,.75)}
  .ov-lv .s{color:var(--up)}.ov-lv .r{color:var(--dn)}.ov-lv .l{font-weight:700}
  .ov-rng{position:relative;height:6px;background:rgba(0,0,0,.1);border-radius:3px;margin:6px 0 2px}
  .ov-rng i{position:absolute;top:-3px;width:3px;height:12px;background:#111;border-radius:1px}
  .ov-key{display:flex;gap:6px;flex-wrap:wrap;align-items:center;font-size:11.5px;margin:4px 0 2px}
  .ov-key span{padding:2px 8px;border-radius:999px;border:1px solid rgba(0,0,0,.08)}
  .ov-alert{font-size:12px;font-weight:600;padding:4px 8px;border-radius:6px;background:rgba(255,255,255,.85)}
  .ov-alert.up{color:var(--up);border:1px solid #9ad29f}.ov-alert.dn{color:var(--dn);border:1px solid #e6a49e}
  .ov-alert b{font-size:10px;background:#111;color:#fff;border-radius:4px;padding:0 4px;margin-right:4px}
  .ov-live{font-size:11.5px;color:#333}
  .ov-more{font-size:11.5px;cursor:pointer;color:#1d4f91;background:none;border:0;padding:0;text-align:left}`;

  function legend() {
    const k = [['bear3', 'Strongly bearish'], ['bear2', 'Bearish'], ['bear1', 'Mildly bearish'], ['neutral', 'Neutral'], ['bull1', 'Mildly bullish'], ['bull2', 'Bullish'], ['bull3', 'Strongly bullish']];
    return `<div class="ov-key">${k.map(([c, l]) => `<span class="ov-tile ${c}" style="display:inline-block;min-height:0;padding:2px 8px;border-left-width:5px">${l}</span>`).join('')}</div>`;
  }

  function levels(m) {
    const L = m.levels, p = m.price;
    if (!L || !p) return '';
    const dp = p.dp ?? 2;
    const chips = [...(L.support || []).slice().reverse().map((v, i) => `<span class="s">S${L.support.length - i} ${f(v, dp)}</span>`),
      `<span class="l">${f(p.last, dp)}</span>`, ...(L.resistance || []).map((v, i) => `<span class="r">R${i + 1} ${f(v, dp)}</span>`)];
    const trig = m.cot && m.cot.triggers ? [m.cot.triggers.up && `<span class="r">Fund buy trigger ${f(m.cot.triggers.up.lvl, dp)}</span>`, m.cot.triggers.dn && `<span class="s">Fund sell trigger ${f(m.cot.triggers.dn.lvl, dp)}</span>`].filter(Boolean) : [];
    let rng = '';
    if (L.lo52 != null && L.hi52 != null && L.hi52 > L.lo52) {
      const x = Math.max(0, Math.min(100, 100 * (p.last - L.lo52) / (L.hi52 - L.lo52)));
      rng = `<div class="ov-rng" title="52-week range"><i style="left:calc(${x}% - 1px)"></i></div><div class="note" style="display:flex;justify-content:space-between"><span>52-wk low ${f(L.lo52, dp)}</span><span>${x.toFixed(0)}% of range</span><span>high ${f(L.hi52, dp)}</span></div>`;
    }
    return `<div class="ov-lv">${chips.join('')}</div>${trig.length ? `<div class="ov-lv">${trig.join('')}</div>` : ''}${rng}`;
  }

  function sec(t, body) { return body ? `<div class="ov-sec"><h4>${t}</h4>${body}</div>` : ''; }

  function tile(m) {
    if (m.error) return `<div class="ov-tile na"><div class="ov-hd"><h2>${esc(m.name)}</h2></div><p class="note">Not available this run.</p></div>`;
    const p = m.price;
    const parts = Object.entries(m.parts || {}).map(([k, v]) => `<span class="${v == null ? '' : v >= 0.07 ? 'p' : v <= -0.07 ? 'n' : ''}" title="score ${v ?? 'n/a'}">${LAB[k]} ${v == null ? '–' : (v > 0 ? '+' : '') + v.toFixed(2)}</span>`).join('');
    const ev = [...(m.events || []).map(e => `<li>${esc(e.text)}</li>`), ...(m.headlines || []).map(h => `<li><a href="${esc(h.link)}" target="_blank" rel="noopener">${esc(h.title)}</a> <span class="note">${esc(h.source)} · ${esc(h.date)}</span></li>`)];
    const fv = m.fair ? esc(m.fair.text) + (m.fair.gap_pct != null ? ` <b>${m.fair.gap_pct > 0 ? 'Below' : 'Above'} fair by ${Math.abs(m.fair.gap_pct).toFixed(1)}%.</b>` : '') : '<span class="note">No fundamental fair-value model for the outright yet.</span>';
    const fund = esc(m.fundamental?.text || '');
    const short = fund.length > 520 ? fund.slice(0, 500).replace(/\s\S*$/, '') + '…' : null;
    return `<div class="ov-tile ${m.shade}" id="ov-${m.key}">
      <div class="ov-hd"><div><h2>${esc(m.name)}</h2>${p ? `<div class="px">${esc(p.contract)} <b>${f(p.last, p.dp)}</b> ${esc(p.unit)} · 1w ${pc(p.chg_1w)} · 1m ${pc(p.chg_1m)}</div>` : ''}</div>
        <div class="ov-badge">${esc(m.view)}${m.conviction ? ` · ${m.conviction}` : ''}</div></div>
      ${m.live ? `<div class="ov-live">Intraday ${f(m.live.last, p?.dp)} (${pc(m.live.vs_close_pct, 2)} vs the close the levels use) · ${esc(m.live.time)}, delayed</div>` : ''}
      ${(m.alerts || []).map(a => `<div class="ov-alert ${a.side}">${a.new ? '<b>NEW</b>' : ''}${esc(a.text)}</div>`).join('')}
      <div class="ov-parts">${parts}</div>
      ${sec('Fundamental outlook', short ? `<span class="ov-f">${short}</span> <button class="ov-more" data-full="${fund.replace(/"/g, '&quot;')}">more</button>` : fund)}
      ${sec('Fair value (fundamentals, outright)', fv)}
      ${sec('Recent events & news flow' + (m.notes_date ? ` <span class="note" style="text-transform:none">${m.notes_by === 'bot' ? 'auto read (GitHub backup)' : 'desk read'} ${esc(m.notes_date)}</span>` : ''), ev.length ? `<ul>${ev.slice(0, 7).join('')}</ul>` : '<span class="note">Nothing new picked up.</span>')}
      ${sec('Technicals & key levels', (m.technical ? esc(m.technical.text) : '<span class="note">No price data.</span>') + levels(m))}
      ${sec(m.vol && m.vol.kind === 'realized' ? 'Volatility (realized)' : 'Implied volatility', m.vol ? esc(m.vol.text) : '<span class="note">Not available.</span>')}
      ${sec('Seasonality', m.seasonal ? esc(m.seasonal.text) : '<span class="note">Not available.</span>')}
      ${m.optsig ? sec('Options & open interest idea', `<b class="${m.optsig.lean === 'bullish' ? 'up' : m.optsig.lean === 'bearish' ? 'dn' : ''}">${esc(m.optsig.lean)}</b>: ${esc(m.optsig.structure)}${m.optsig.signals && m.optsig.signals.length ? ` <span class="note">(${m.optsig.signals.map(esc).join('; ')})</span>` : ''} <span class="note">data to ${esc(m.optsig.asof)}</span>`) : ''}
      ${sec('COT', m.cot ? esc(m.cot.text) + (m.cot.date ? ` <span class="note">(${esc(m.cot.date)})</span>` : '') : '<span class="note">Not available.</span>')}
    </div>`;
  }

  async function show() {
    const el = document.getElementById('overview');
    if (!document.getElementById('ov-css')) { const s = document.createElement('style'); s.id = 'ov-css'; s.textContent = css; document.head.appendChild(s); }
    history.replaceState(null, '', '#overview');
    if (!D) {
      el.innerHTML = '<div class="card"><p class="note">Loading…</p></div>';
      D = await fetch('data/overview/overview.json?v=' + Date.now().toString().slice(0, 8)).then(r => r.json()).catch(() => null);
    }
    if (!D) { el.innerHTML = '<div class="card"><p class="note">Overview not built yet.</p></div>'; return; }
    const big = D.desk === 'softs';
    const W = D.weights || {};
    el.innerHTML = `<div style="max-width:1400px;margin:0 auto;padding:12px 16px">
      <div class="card"><b>Overview</b> — one tile per market. Colour = overall read, a weighted blend of fundamentals (${(100 * (W.fundamental || 0)).toFixed(0)}%), technicals (${(100 * (W.technical || 0)).toFixed(0)}%), COT positioning (${(100 * (W.cot || 0)).toFixed(0)}%) and seasonality (${(100 * (W.seasonal || 0)).toFixed(0)}%), each scored −1 to +1 by the desk's own models; missing parts are left out of the blend.
        ${legend()}<p class="note">Rule-based read built ${esc(D.generated)} from the desk's data; recent events from the whole news feed (major outlets, trade press, broker and bank research); intraday quotes and key-level alerts refresh hourly in trading hours. Research only, not investment advice.</p></div>
      ${D.groups.map(g => { const ms = D.markets.filter(m => m.group === g); return ms.length ? `${D.groups.length > 1 ? `<div class="ov-grp">${esc(g)}</div>` : ''}<div class="ov-grid ${big ? 'big' : ''}">${ms.map(tile).join('')}</div>` : ''; }).join('')}
    </div>`;
    el.querySelectorAll('.ov-more').forEach(b => b.onclick = () => { b.previousElementSibling.textContent = b.dataset.full; b.remove(); });
  }
  function tileInto(el, m) {
    if (!document.getElementById('ov-css')) { const st = document.createElement('style'); st.id = 'ov-css'; st.textContent = css; document.head.appendChild(st); }
    el.innerHTML = `<div class="ov-grid big">${tile(m)}</div>`;
    el.querySelectorAll('.ov-more').forEach(b => b.onclick = () => { b.previousElementSibling.textContent = b.dataset.full; b.remove(); });
  }
  return { show, tileInto };
})();
