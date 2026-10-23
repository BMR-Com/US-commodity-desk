// China customs (GACC) monthly bulletin collector: table (14) "Major Import Commodities in Quantity and Value" and
// table (13) exports, English site. Run in a tab on http://english.customs.gov.cn/statics/report/monthly.html.
// Evaluate as: window.__gaccp = <this file without the trailing semicolon>(KNOWN); KNOWN = {have: ['M|2026|Aug', ...]}
// Resolves to gzip+base64 JSON {rows: [[flow, year, mon, commodity, unit, m_qty, m_val, ytd_qty, ytd_val, pct_qty]]}.
(async (KNOWN = {}) => {
  const have = new Set(KNOWN.have || []);
  const P = s => new DOMParser().parseFromString(s, 'text/html');
  const keep = /cotton|yarn|grain|cereal|soya|wheat|maize|barley|sorghum|rice|rape|edible|meat|beans|sugar|textile|wool|dairy|milk|powdered|bovine|swine|poultry|agricultur|fertil|palm|oil/i;
  const out = { collected_at: new Date().toISOString(), rows: [], log: [] };
  const y0 = new Date().getFullYear();
  for (const y of [y0 - 1, y0]) {
    let h = await fetch(`/statics/report/monthly${y}.html`).then(r => r.ok ? r.text() : '').catch(() => '');
    if (!h && y === y0) h = await fetch('/statics/report/monthly.html').then(r => r.text());
    const d = P(h);
    for (const [tag, flow] of [['Major Import Commodities', 'M'], ['Major Export Commodities', 'X']]) {
      const row = [...d.querySelectorAll('tr')].find(tr => tr.textContent.includes(tag));
      if (!row) { out.log.push(`${y} no ${tag}`); continue; }
      for (const a of row.querySelectorAll('a')) {
        const m = a.textContent.trim().replace('.', '');
        if (have.has(`${flow}|${y}|${m}`)) continue;
        try {
          const t = P(await fetch(a.getAttribute('href').replace(/^https?:\/\/[^/]+/, '')).then(r => r.text()));
          let n = 0;
          for (const tr of t.querySelectorAll('tr')) { const c = [...tr.cells].map(x => x.textContent.trim().replace(/\s+/g, ' '));
            if (c.length >= 7 && keep.test(c[0])) { out.rows.push([flow, y, m, ...c.slice(0, 7)]); n++; } }
          out.log.push(`${flow} ${y} ${m} ${n}`);
        } catch (e) { out.log.push(`${flow} ${y} ${m} ${e}`); }
        await new Promise(r => setTimeout(r, 300));
      }
    }
  }
  const buf = new Uint8Array(await new Response(new Blob([JSON.stringify(out)]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
  let b = ''; for (let i = 0; i < buf.length; i += 0x8000) b += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  return btoa(b);
})
