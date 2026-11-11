// Price strip fixed at the bottom of every page: the latest Yahoo / US Treasury snapshot (data/markets/markets.json,
// pipelines/markets.py) for commodities, yields, currencies and stock indices, with each exchange's delay.
// Isolated: any failure here leaves the page untouched.
(() => {
  try {
    const ORDER = ['Grains & oilseeds', 'Softs', 'Livestock & dairy', 'Energy', 'Metals', 'Commodity indices', 'US rates', 'Currencies', 'US stocks', 'World stocks'];
    const SHORT = { 'Grains & oilseeds': 'GRAINS', 'Softs': 'SOFTS', 'Livestock & dairy': 'LIVESTOCK & DAIRY', 'Energy': 'ENERGY', 'Metals': 'METALS',
      'Commodity indices': 'INDEX', 'US rates': 'US YIELDS', 'Currencies': 'FX', 'US stocks': 'US STOCKS', 'World stocks': 'WORLD STOCKS' };
    const css = `
      #pxStrip{position:fixed;left:0;right:0;bottom:0;z-index:999;background:#111;color:#e8e6e1;font:12px/1.2 system-ui,-apple-system,"Segoe UI",sans-serif;border-top:1px solid #333}
      #pxStrip .row{display:flex;align-items:center;gap:8px;height:26px;overflow:hidden}
      #pxStrip .lane{flex:1;overflow:hidden;white-space:nowrap;mask-image:linear-gradient(90deg,transparent,#000 2%,#000 98%,transparent)}
      #pxStrip .track{display:inline-block;padding-left:100%;animation:pxScroll var(--dur,240s) linear infinite}
      #pxStrip:hover .track{animation-play-state:paused}
      @keyframes pxScroll{from{transform:translateX(0)}to{transform:translateX(-100%)}}
      #pxStrip .g{color:#d9a441;font-weight:600;margin:0 6px 0 14px}
      #pxStrip .it{margin:0 9px;cursor:default}
      #pxStrip .up{color:#4cc38a}#pxStrip .dn{color:#ff6b6b}#pxStrip .st{color:#8a8984}
      #pxStrip .meta{flex:none;padding:0 10px;color:#9a988f;font-size:11px;border-left:1px solid #333;cursor:pointer;white-space:nowrap}
      #pxStrip .note{display:none;padding:6px 12px 8px;color:#bdbab2;font-size:11px;line-height:1.5;border-top:1px solid #333}
      #pxStrip.open .note{display:block}
      body{padding-bottom:30px}`;
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const bar = document.createElement('div'); bar.id = 'pxStrip';
    bar.innerHTML = '<div class="row"><div class="lane"><div class="track">Loading prices…</div></div><div class="meta" title="Delays and sources">…</div></div><div class="note"></div>';
    document.body.appendChild(bar);
    bar.querySelector('.meta').onclick = () => bar.classList.toggle('open');

    const ct = s => { const d = new Date(s.replace(' UTC', 'Z').replace(' ', 'T')); return isNaN(d) ? null : d; };
    const tCT = d => d.toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit' });
    const dCT = d => d.toLocaleDateString('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric' });
    const num = (v, u) => { const a = Math.abs(v); const dp = /¢/.test(u || '') ? 2 : a >= 1000 ? 1 : a >= 10 ? 2 : a >= 1 ? 3 : 4;
      return v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp }); };
    const delayTxt = i => i.delay_min == null ? 'delay depends on exchange (often 15 min)' : i.delay_min === 0 ? 'real time' : `delayed ~${i.delay_min} min`;

    function draw(M) {
      const items = (M.items || []).filter(i => i.last != null && (i.age_min == null || i.age_min < 4 * 1440));   // drop series not updated for 4+ days
      const groups = ORDER.map(g => [g, items.filter(i => i.group === g)]).filter(([, a]) => a.length);
      const html = groups.map(([g, a]) => `<span class="g">${SHORT[g] || g}</span>` + a.map(i => {
        const ch = i.d1 == null ? '' : i.kind === 'yield' ? `${i.d1 > 0 ? '+' : ''}${i.d1.toFixed(1)} bp` : `${i.d1 > 0 ? '+' : ''}${i.d1.toFixed(2)}%`;
        const cls = i.d1 == null || Math.abs(i.d1) < 1e-9 ? 'st' : i.d1 > 0 ? 'up' : 'dn';
        const t = ct(i.time || '');
        const tip = `${i.name}${i.contract ? ' ' + i.contract : ''} ${i.unit || ''} · last trade ${t ? dCT(t) + ' ' + tCT(t) + ' CT' : '?'} · ${delayTxt(i)}${i.exch ? ' (' + i.exch + ')' : ''}`;
        return `<span class="it" title="${tip.replace(/"/g, '&quot;')}">${i.name} <b>${num(i.last, i.unit)}${i.kind === 'yield' ? '%' : ''}</b> <span class="${cls}">${ch}</span></span>`;
      }).join('')).join('');
      const tr = bar.querySelector('.track');
      tr.innerHTML = html || 'No prices in the snapshot.';
      tr.style.setProperty('--dur', Math.max(90, Math.round(items.length * 3.2)) + 's');
      const g = ct(M.generated || '');
      const age = g ? Math.round((Date.now() - g) / 60000) : null;
      bar.querySelector('.meta').innerHTML = g ? `Snapshot ${dCT(g)} ${tCT(g)} CT${age != null && age < 600 ? ` (${age} min ago)` : ''} · delays ⓘ` : 'Delays ⓘ';
      bar.querySelector('.note').innerHTML = `<b>Not live.</b> Prices are a snapshot taken by the desk ${g ? 'at ' + dCT(g) + ' ' + tCT(g) + ' CT' : ''}, refreshed about hourly on weekdays (7 am–6 pm ET, Sunday evening).
        On top of that, each price was already delayed by its source when the snapshot was taken: CBOT/CME futures (grains, livestock, dairy, T-notes, S&P futures) ~10 min;
        ICE US softs, NYMEX and COMEX (cotton, sugar, coffee, cocoa, energy, metals) ~30 min; Treasury yield indices ~15 min; currencies real time; US cash stock indices real time;
        other stock exchanges usually 15 min. Change is vs the previous settlement / close (yields in basis points). Hover a price for its last trade time and delay.
        Sources: Yahoo Finance, US Treasury. Research use only.`;
    }
    const load = () => fetch('data/markets/markets.json?' + Date.now()).then(r => r.ok ? r.json() : Promise.reject(r.status)).then(draw)
      .catch(() => { bar.querySelector('.track').textContent = 'Price snapshot not available.'; });
    load();
    setInterval(load, 5 * 60 * 1000);
  } catch (e) { /* the page stays as it is */ }
})();
