// USDA FAS export sales announcements (daily "flash" sales). Run in a fas.usda.gov tab (same-origin fetch).
// Reads the newest PAGES listing pages of the Export Sales Announcement type, fetches the full text of any
// truncated teaser, and returns gzip+base64 JSON [{t, title, href, text, full}] for pipelines/flash.py.
(async (PAGES = 3) => {
  const rows = {};
  for (let pg = 0; pg < PAGES; pg++) {
    const h = await fetch(`/newsroom/search?news%5B0%5D=news_type%3A10106&page=${pg}`).then(r => r.text());
    const d = new DOMParser().parseFromString(h, 'text/html');
    for (const c of d.querySelectorAll('.c-card__body-content')) {
      const href = c.querySelector('a.c-card__url')?.getAttribute('href');
      if (!href) continue;
      rows[href] = { t: c.querySelector('time')?.getAttribute('datetime'), title: c.querySelector('.c-card__title')?.textContent.trim(), href,
        text: c.querySelector('.c-card__content')?.textContent.replace(/\s+/g, ' ').trim() };
    }
  }
  for (const r of Object.values(rows)) {
    if (r.text && !/\.\.\.$|…$/.test(r.text)) continue;
    const h = await fetch(r.href).then(x => x.text());
    const b = new DOMParser().parseFromString(h, 'text/html').querySelector('.l-story__body-inner');
    if (b) { r.text = b.textContent.replace(/\s+/g, ' ').split('###')[0].trim(); r.full = 1; }
  }
  const s = JSON.stringify(Object.values(rows));
  const buf = new Uint8Array(await new Response(new Blob([s]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
  let b = ''; for (let i = 0; i < buf.length; i += 8192) b += String.fromCharCode(...buf.subarray(i, i + 8192));
  return btoa(b);
})();
