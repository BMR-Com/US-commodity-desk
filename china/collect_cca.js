// China Cotton Association (china-cotton.org) collector. Run in a tab on https://www.china-cotton.org/ (any page).
// It opens the association's own pages in a hidden same-origin frame and reads what they display: the CCIndex and
// Cotlook A tables (newest pages until it reaches KNOWN dates), the latest quotes and balance sheet, the national
// production table and NBS table, yearly cotton imports, and new production-monitoring survey articles
// (sowing, growth, output, picking and selling progress). Nothing is posted to the site.
// Evaluate as: window.__cca = <this file without the trailing semicolon>(KNOWN); KNOWN = {cc_last, cl_last, urls:[...]}
// It resolves to a gzip+base64 JSON string for `python china/ingest.py <file>`.
(async (KNOWN = {}) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const tick = () => fetch('/favicon.ico', { cache: 'no-store' }).catch(() => {});   // not throttled in hidden tabs, unlike timers
  const until = async (fn, ms = 15000) => { const t0 = performance.now(); while (performance.now() - t0 < ms) { try { const v = fn(); if (v) return v; } catch (e) {} await tick(); } return null; };
  const F = document.createElement('iframe');
  F.style.cssText = 'width:1300px;height:1000px;position:fixed;left:-6000px;top:0';
  document.body.appendChild(F);
  const load = async (url, ready) => { F.src = 'about:blank'; await until(() => F.contentDocument?.location.href === 'about:blank', 3000); F.src = url;
    return until(() => { const d = F.contentDocument; return d && d.location.href.includes(url.split('?')[0]) && ready(d) ? d : null; }, 20000); };
  const out = { collected_at: new Date().toISOString(), errors: [] };
  const table = d => d.querySelector('.count .arco-table tbody');
  const rowsOf = d => [...table(d).querySelectorAll('tr')].map(tr => [...tr.cells].map(c => c.innerText.trim()));
  // page a data table until a row's first cell is <= stop (dates) or maxPages
  const pageTable = async (key, stop, maxPages) => {
    const d = await load(`/data?key=${key}`, d => { const t = table(d); return t && t.querySelector('tr td') && !t.innerText.includes('暂无数据') && d.body.innerText.includes('最新统计'); });
    if (!d) throw new Error('table ' + key + ' did not load');
    const rows = [];
    for (let p = 0; p < maxPages; p++) {
      const before = table(d).innerText;
      const r = rowsOf(d); rows.push(...r);
      if (stop && r.some(x => x[0] <= stop)) break;
      const nx = d.querySelector('.count .arco-pagination-item-next');
      if (!nx || nx.classList.contains('arco-pagination-item-disabled')) break;
      nx.click();
      if (!await until(() => table(d)?.innerText !== before, 10000)) break;
    }
    return { rows, text: d.body.innerText };
  };
  try { const r = await pageTable('1', KNOWN.cc_last || '2013-01-01', KNOWN.cc_last ? 40 : 400); out.ccindex = r.rows;
    const t = r.text, i = t.indexOf('最新统计'), j = t.indexOf('中国棉花供求平衡表');
    out.quotes_text = i >= 0 ? t.slice(i, i + 700) : ''; out.balance_text = j >= 0 ? t.slice(j, j + 400) : ''; } catch (e) { out.errors.push('ccindex ' + e); }
  try { out.cotlook = (await pageTable('4', KNOWN.cl_last || '2000-01-01', KNOWN.cl_last ? 20 : 120)).rows; } catch (e) { out.errors.push('cotlook ' + e); }
  for (const [k, name] of [['6-1', 'nbs'], ['6-2', 'cca_prod'], ['9-1', 'imports_yearly']]) {
    try { out[name] = (await pageTable(k, null, 1)).rows; } catch (e) { out.errors.push(name + ' ' + e); }
  }
  // production-monitoring list: newest items; capture the article links the list would open
  try {
    const d = await load('/newsList?id=6', d => [...d.querySelectorAll('button')].some(b => b.innerText.includes('查看更多')));
    const W = F.contentWindow, cap = []; W.open = u => { cap.push(String(u)); return null; };
    const X = d.evaluate("//main//*[string-length(normalize-space(text()))>8]", d, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
    const list = [];
    for (let i = 0; i < X.snapshotLength; i++) { const e = X.snapshotItem(i); if (e.childElementCount || /^\d{4}-\d\d-\d\d$/.test(e.innerText.trim())) continue;
      const n0 = cap.length; e.click(); if (cap.length > n0) list.push([e.innerText.trim(), '', cap[cap.length - 1]]); }
    out.list = list;
    const known = new Set(KNOWN.urls || []); out.art = {};
    for (const [t, , u] of list) {
      if (known.has(u)) continue;
      const a = await load(u, d => { const s = d.querySelector('main')?.innerText || ''; return s.includes('出处') && s.length > 300; });
      if (!a) { out.errors.push('article ' + u); continue; }
      await sleep(300);
      const s = a.querySelector('main').innerText, i = s.indexOf('出处'), j = s.indexOf('最新更新');
      out.art[u] = { t, body: s.slice(i, j > 0 ? j : undefined) };
    }
  } catch (e) { out.errors.push('articles ' + e); }
  F.remove();
  const buf = new Uint8Array(await new Response(new Blob([JSON.stringify(out)]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
  let b = ''; for (let i = 0; i < buf.length; i += 0x8000) b += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  return btoa(b);
})
