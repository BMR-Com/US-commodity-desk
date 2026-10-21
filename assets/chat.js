// Ask the desk: a chatbot over the desk's own numbers (data/ai/context.json + the text of the open tab), answered by
// Groq (free tier). The Groq key is pasted once and kept only in this browser (localStorage), sent only to api.groq.com.
const Chat = (() => {
  const MODELS = [['auto', 'Automatic (best available today)'], ['openai/gpt-oss-120b', 'GPT-OSS 120B'], ['openai/gpt-oss-20b', 'GPT-OSS 20B (fastest)']];
  const TAB_SYMS = { grains: ['ZC', 'ZS', 'ZM', 'ZL', 'ZW', 'KE'], dairy: ['DC', 'GDK', 'CSC', 'CB', 'GNF', 'DY'], hogs: ['HE'], cattle: ['LE', 'GF'], cotton: ['CT'],
                     energy: ['NG', 'CL', 'HO', 'RB'], cotfull: [], markets: [], summary: [], signals: [], options: [] };
  const BUDGET = 14000;   // characters of desk cards per question (~3.5k tokens; the free tier allows 6-30k tokens a minute)
  const LS = { get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) {} } };
  let CTX = null, hist = [], lastIds = [], busy = false, PROXY, LIVE = null;
  const CAP = 1000;   // questions per browser per day (own-key mode; the server proxy enforces its own limit per user)
  const dayKey = () => 'chatCount_' + new Date().toISOString().slice(0, 10);
  const count = () => +(LS.get(dayKey()) || 0);
  const proxy = async () => { if (PROXY === undefined) PROXY = await getJSON('data/ai/proxy.json').then(j => j && j.url ? j : null).catch(() => null); return PROXY; };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const md = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/^#{1,4} (.*)$/gm, '<b>$1</b>').replace(/^\s*[-*] (.*)$/gm, '• $1').replace(/\n/g, '<br>');
  function activeTab() { const b = document.querySelector('nav.comm button.on'); return b ? b.dataset.c : 'summary'; }
  function pageText(limit = 6000) {
    const t = activeTab(), sec = document.getElementById(t);
    if (!sec) return '';
    let txt = '';
    const fr = sec.querySelector('iframe');
    const vis = fr && fr.offsetParent !== null;
    try { txt = vis ? fr.contentDocument.body.innerText : sec.innerText; } catch (e) { txt = sec.innerText; }
    return txt.replace(/[ \t]+/g, ' ').replace(/\n{2,}/g, '\n').trim().slice(0, limit);
  }
  // Numbers behind the charts on the open tab (Chart.js), so questions about a chart can be answered.
  function chartText(limit = 3500) {
    const sec = document.getElementById(activeTab());
    if (!sec) return '';
    const wins = [window];
    const fr = sec.querySelector('iframe');
    try { if (fr && fr.offsetParent !== null && fr.contentWindow.Chart) wins.push(fr.contentWindow); } catch (e) {}
    const fmtv = v => v == null || isNaN(v) ? '–' : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : (+v).toFixed(Math.abs(v) < 10 ? 3 : 2).replace(/\.?0+$/, '');
    const out = [];
    for (const w of wins) {
      const insts = w.Chart && w.Chart.instances ? Object.values(w.Chart.instances) : [];
      for (const ch of insts) {
        const cv = ch.canvas;
        if (!cv || cv.offsetParent === null || !(w === window ? sec.contains(cv) : true)) continue;
        const card = cv.closest('.card') || cv.closest('.chart-section') || cv.parentElement?.parentElement;
        const head = ((ch.options?.plugins?.title?.text) || card?.querySelector('h2,h3,h4')?.innerText || '').toString().replace(/\s+/g, ' ').slice(0, 120);
        const labels = (ch.data.labels || []).map(String);
        const lines = [`Chart: ${head || 'untitled'}${labels.length ? ` (x: ${labels[0]} … ${labels[labels.length - 1]}, ${labels.length} points)` : ''}`];
        for (const ds of (ch.data.datasets || []).slice(0, 8)) {
          if (!ds.label || ds.label.startsWith('_')) continue;
          const pts = (ds.data || []).map((v, i) => [typeof v === 'object' && v !== null ? (v.x ?? labels[i]) : labels[i], typeof v === 'object' && v !== null ? v.y : v]).filter(p => p[1] != null && !isNaN(p[1]));
          if (!pts.length) continue;
          const last = pts[pts.length - 1], mx = pts.reduce((a, b) => b[1] > a[1] ? b : a), mn = pts.reduce((a, b) => b[1] < a[1] ? b : a);
          const step = Math.max(1, Math.ceil(pts.length / 8));
          const sample = pts.filter((_, i) => i % step === 0 || i === pts.length - 1).map(p => `${p[0]}: ${fmtv(p[1])}`).join(', ');
          lines.push(`- ${ds.label}: last ${fmtv(last[1])} (${last[0]}), high ${fmtv(mx[1])} (${mx[0]}), low ${fmtv(mn[1])} (${mn[0]}); points: ${sample}`);
        }
        if (lines.length > 1) out.push(lines.join('\n'));
      }
    }
    return out.join('\n').slice(0, limit);
  }
  function pick(q, budget = BUDGET, prefer = []) {
    const ql = ' ' + q.toLowerCase().replace(/[^a-z0-9/&.%-]+/g, ' ') + ' ';
    const tabSyms = TAB_SYMS[activeTab()] || [];
    const hs = (location.hash.split('/')[1] || '').toUpperCase();
    const STOP = new Set(['what', 'which', 'where', 'when', 'about', 'there', 'their', 'with', 'from', 'this', 'that', 'does', 'have', 'show', 'tell', 'much', 'many', 'price', 'prices', 'market', 'markets', 'today', 'week']);
    const qw = [...new Set(ql.split(' ').filter(w => w.length > 4 && !STOP.has(w)))];
    const score = CTX.cards.map(c => {
      let s = 0;
      for (const a of c.aliases || []) {
        const hit = a.length <= 3 ? ql.includes(' ' + a + ' ') : ql.includes(a);
        if (hit) s += a.length > 4 ? 3 : 2;
      }
      const al = s;
      if (c.kind === 'market' && (tabSyms.includes(c.id) || c.id === hs)) s += 1.5;
      const tl = c.text.toLowerCase(); let tw = 0;   // distinctive question words found in the card text
      for (const w of qw) if (tl.includes(w)) tw += 1;
      s += Math.min(tw, 4) * 0.6;
      if (lastIds.includes(c.id)) s += 1;
      return [s, c, al];
    }).filter(x => x[0] > 0).sort((a, b) => b[0] - a[0]);
    const always = ['overview', 'table'].map(id => CTX.cards.find(c => c.id === id)).filter(Boolean);
    const out = [...always]; let n = always.reduce((a, c) => a + c.text.length, 0);
    // first the best alias-matched card of each kind (so a question about corn and CPI gets both), then by score
    const seen = new Set(), share = Math.round(budget / 4);
    const put = (c, cap) => { const room = Math.min(cap, budget - n); if (room < 700 || out.some(o => o.id === c.id)) return; const t = c.text.length > room ? c.text.slice(0, room) + ' …' : c.text; out.push({ ...c, text: t }); n += t.length; };
    const firsts = prefer.map(id => CTX.cards.find(c => c.id === id)).filter(Boolean);
    firsts.forEach(c => seen.add(c.kind + ':' + c.id));
    for (const [, c, al] of [...score].sort((a, b) => b[2] - a[2] || b[0] - a[0])) { if (al < 2 || seen.has(c.kind) || (prefer.length && firsts.length >= prefer.length + 2)) continue; seen.add(c.kind); firsts.push(c); }
    const each = firsts.length ? Math.max(900, Math.floor((budget - n) / firsts.length)) : share;
    for (const c of firsts) put(c, each);
    for (const [, c] of score) put(c, 1e9);
    return out;
  }
  const PREF = ['gpt-oss-120b', 'llama-4-maverick', 'llama-4-scout', 'llama-3.3-70b', 'qwen3', 'kimi-k2', 'gpt-oss-20b', 'llama-3.1-8b'];
  async function liveModels(key) {   // the chat models this key can use today (Groq retires models)
    if (LIVE) return LIVE;
    try {
      const j = await fetch('https://api.groq.com/openai/v1/models', { headers: { Authorization: 'Bearer ' + key } }).then(r => r.json());
      const ids = (j.data || []).filter(m => m.active !== false).map(m => m.id).filter(i => !/whisper|guard|tts|playai|orpheus|prompt|compound|distil|allam/.test(i));
      const rank = i => { const k = PREF.findIndex(p => i.includes(p)); return k < 0 ? PREF.length : k; };
      LIVE = ids.sort((a, b) => rank(a) - rank(b));
    } catch (e) { LIVE = []; }
    return LIVE;
  }
  // Step 1: a fast model reads the catalogue of the desk's knowledge cards and picks the ones the question needs.
  async function route(q, key, models) {
    const fast = models.find(m => /gpt-oss-20b|8b|scout|qwen/.test(m)) || models[models.length - 1];
    if (!fast) return [];
    const cat = CTX.cards.map(c => `${c.id} | ${c.title} | ${c.text.split('\n')[0].slice(0, 90)}`).join('\n');
    const recent = hist.slice(-2).map(m => `${m.role}: ${m.content.slice(0, 300)}`).join('\n');
    try {
      const r = await fetch('https://api.groq.com/openai/v1/chat/completions', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key },
        body: JSON.stringify({ model: fast, temperature: 0, max_tokens: 300, messages: [
          { role: 'system', content: 'You route questions for a commodity research desk. Given a catalogue of knowledge cards (id | title | first line), return ONLY JSON {"ids": [up to 6 card ids, most useful first]}. Pick every card needed to answer fully, including for comparisons across markets, follow-up questions, history, macro, calendar or news. Return {"ids": []} if only the open web page is needed.' },
          { role: 'user', content: `Catalogue:\n${cat}\n\n${recent ? 'Conversation so far:\n' + recent + '\n\n' : ''}Question: ${q}` }] }) });
      if (!r.ok) return [];
      const t = (await r.json()).choices?.[0]?.message?.content || '';
      const j = JSON.parse(t.slice(t.indexOf('{'), t.lastIndexOf('}') + 1));
      const ok = new Set(CTX.cards.map(c => c.id));
      return (j.ids || []).filter(i => ok.has(i)).slice(0, 6);
    } catch (e) { return []; }
  }
  async function ask(q) {
    const P = await proxy();
    const key = LS.get('groqApiKey'), user = LS.get('deskUser'), code = LS.get('deskCode');
    if (P && !(user && code)) { settings(true); add('bot', 'Enter your desk user name and access code in the settings above (ask the desk owner for one).'); return; }
    if (!P && !key) { settings(true); add('bot', 'To ask questions, paste a free Groq API key in the settings above (console.groq.com/keys, about a minute to sign up). It stays in this browser only and is sent only to Groq.'); return; }
    if (!P && count() >= CAP) { add('bot', `Daily limit reached: ${CAP} questions a day in this browser (resets 00:00 UTC).`); return; }
    if (!CTX) CTX = await getJSON('data/ai/context.json').catch(() => null);
    if (!CTX) { add('bot', 'The desk context file is not built yet (data/ai/context.json).'); return; }
    const sys = `You are the assistant of the BMR-Com US Ags Desk, a research site on US agricultural and energy futures (grains, oilseeds, cotton, livestock, dairy, energy).
Answer ONLY from the DATA below: the desk's cards (built ${CTX.generated}, market data as of ${CTX.data_date}), the text of the tab the user has open, and the numbers behind the charts on that tab.
Rules: quote numbers with units, contract and date; if the data does not contain the answer, say so plainly and name the tab where it may be (Summary, Markets & macro, Options pricer, Signals, Dairy, Grains & oilseeds, Cotton, Lean hogs, Live & feeder cattle, COT (full), Energy). Never invent numbers. Reason like an analyst: compare, compute changes, spreads and ratios from the data (show the arithmetic briefly), connect fundamentals, positioning, technicals and macro, and point out conflicting signals. Be concise: short paragraphs or bullets. Explain jargon briefly when helpful. This is research, not investment advice; describe the desk's own views and signals rather than giving personal trade recommendations.`;
    let cards = [], page = '', charts = '';
    const thinking = add('bot', '…');
    const models = P ? [] : await liveModels(key);
    const routed = P ? [] : await route(q, key, models);
    const build = scale => {
      cards = pick(q, Math.round(BUDGET * scale), routed); lastIds = cards.map(c => c.id);
      page = pageText(Math.round(6000 * scale)); charts = chartText(Math.round(3500 * scale));
      const data = cards.map(c => `### ${c.title}\n${c.text}`).join('\n\n') + (page ? `\n\n### Text of the open tab (${activeTab()})\n${page}` : '') + (charts ? `\n\n### Numbers behind the charts on the open tab\n${charts}` : '');
      return [{ role: 'system', content: sys + '\n\nDATA:\n' + data }, ...hist.slice(-4).map(m => ({ role: m.role, content: m.content.slice(0, 1500) })), { role: 'user', content: q }];
    };
    let msgs = build(1);
    const avail = models;
    const pref = LS.get('groqModel');
    const order = [...(pref && pref !== 'auto' ? [pref] : []), ...avail, ...MODELS.map(m => m[0])].filter((m, i, a) => m !== 'auto' && a.indexOf(m) === i);
    let txt = null, used = null, err = '', usage = null;
    if (P) {
      try {
        const r = await fetch(P.url.replace(/\/$/, '') + '/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user, code, model: order[0], messages: msgs, temperature: 0.2, max_tokens: 900 }) });
        const j = await r.json();
        usage = j.desk_usage || (j.used != null ? { used: j.used, limit: j.limit } : null);
        if (r.ok) { txt = j.choices?.[0]?.message?.content; used = j.model || order[0]; }
        else err = j.error?.message || j.error || `HTTP ${r.status}`;
      } catch (e) { err = String(e); }
    }
    for (const model of (P ? [] : order)) {
      try {
        const r = await fetch('https://api.groq.com/openai/v1/chat/completions', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key },
          body: JSON.stringify({ model, messages: msgs, temperature: 0.2, max_tokens: 900 }) });
        if (r.status === 401) { err = 'Groq rejected the key (401). Check it at console.groq.com/keys.'; break; }
        if (r.status === 413 || r.status === 429) {   // too big for this model's per-minute budget: retry once with less context
          const t = await r.text(); err = `${model}: HTTP ${r.status}`;
          if (/token|too large|context|TPM/i.test(t) && !msgs.shrunk) { msgs = build(0.55); msgs.shrunk = true;
            const r2 = await fetch('https://api.groq.com/openai/v1/chat/completions', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key },
              body: JSON.stringify({ model, messages: msgs, temperature: 0.2, max_tokens: 900 }) });
            if (r2.ok) { const j2 = await r2.json(); txt = j2.choices?.[0]?.message?.content; used = model; if (txt) break; }
          }
          continue;
        }
        if (r.status === 400 || r.status === 404 || r.status >= 500) { err = `${model}: HTTP ${r.status}`; continue; }
        const j = await r.json();
        txt = j.choices?.[0]?.message?.content; used = model;
        if (txt) break;
      } catch (e) { err = String(e); }
    }
    thinking.remove();
    if (!txt) { add('bot', 'No answer: ' + (err || 'unknown error') + '. On the free tier, wait a minute if you hit the per-minute limit.'); return; }
    hist.push({ role: 'user', content: q }, { role: 'assistant', content: txt });
    if (!P) LS.set(dayKey(), String(count() + 1));
    if (!usage && !P) usage = { used: count(), limit: CAP };
    add('bot', txt, `${used.split('/').pop()}${usage ? ` · ${usage.used}/${usage.limit} today` : ''} · sources: ${cards.map(c => c.title).join(', ')}${page ? ', open tab' : ''}${charts ? ', charts on the tab' : ''}`);
  }
  function add(who, text, foot) {
    const box = document.getElementById('chat-msgs'), d = document.createElement('div');
    d.className = 'chat-m chat-' + who;
    d.innerHTML = (who === 'bot' ? md(text) : esc(text)) + (foot ? `<div class="chat-foot">${esc(foot)}</div>` : '');
    box.appendChild(d); box.scrollTop = box.scrollHeight;
    return d;
  }
  function settings(open) {
    const s = document.getElementById('chat-set');
    s.style.display = open == null ? (s.style.display === 'none' ? '' : 'none') : open ? '' : 'none';
    document.getElementById('chat-key').value = LS.get('groqApiKey') || '';
    document.getElementById('chat-user').value = LS.get('deskUser') || '';
    document.getElementById('chat-code').value = LS.get('deskCode') || '';
    proxy().then(P => { document.getElementById('chat-acc').style.display = P ? '' : 'none'; document.getElementById('chat-own').style.display = P ? 'none' : '';
      if (P) document.getElementById('chat-note').textContent = `The desk's own Groq key is used through the desk server; each user gets ${P.limit || 500} questions a day (resets 00:00 UTC).`; });
  }
  function build() {
    const el = document.createElement('div');
    el.innerHTML = `<button id="chat-btn" title="Ask questions about the numbers on this desk">💬 Ask the desk</button>
      <div id="chat-panel" style="display:none"><div class="chat-hd"><b>Ask the desk</b><span class="chat-sp"></span>
        <button id="chat-gear" title="Groq key and model">⚙</button><button id="chat-clear" title="New conversation">↺</button><button id="chat-x" title="Close">✕</button></div>
        <div id="chat-set" style="display:none"><div id="chat-acc"><label>User name <input id="chat-user" autocomplete="username"></label><label>Access code <input id="chat-code" type="password" autocomplete="current-password"></label></div>
          <div id="chat-own"><label>Groq API key <input id="chat-key" type="password" placeholder="gsk_…" autocomplete="off"></label></div>
          <label>Model <select id="chat-model">${MODELS.map(m => `<option value="${m[0]}">${m[1]}</option>`).join('')}</select></label>
          <div class="chat-row"><button id="chat-save">Save</button><button id="chat-forget">Sign out</button></div>
          <p class="note" id="chat-note">Paste a free Groq key (console.groq.com/keys) to ask anything about the desk. It is kept only in this browser and sent only to Groq; up to 1,000 questions a day.</p></div>
        <div id="chat-msgs"><div class="chat-m chat-bot">Ask about any number on the desk, for example:<div class="chat-sugg">
          ${['Why is corn rated strongly bearish?', 'Which markets have crowded fund positioning?', 'Compare carry and trend for soybeans and soy oil', 'What does the options market imply for Class III milk?', 'Summarize this tab'].map(s => `<button class="chat-s">${s}</button>`).join('')}</div></div></div>
        <form id="chat-f"><textarea id="chat-q" rows="2" placeholder="Ask about prices, fundamentals, COT, options, signals…"></textarea><button type="submit">Send</button></form></div>`;
    document.body.appendChild(el);
    const panel = document.getElementById('chat-panel');
    document.getElementById('chat-btn').onclick = () => { panel.style.display = panel.style.display === 'none' ? '' : 'none';  document.getElementById('chat-q').focus(); };
    document.getElementById('chat-x').onclick = () => panel.style.display = 'none';
    document.getElementById('chat-gear').onclick = () => settings();
    document.getElementById('chat-clear').onclick = () => { hist = []; lastIds = []; $$('#chat-msgs .chat-m').slice(1).forEach(x => x.remove()); };
    document.getElementById('chat-model').value = LS.get('groqModel') || MODELS[0][0];
    document.getElementById('chat-save').onclick = () => { const k = document.getElementById('chat-key').value.trim(); if (k) LS.set('groqApiKey', k);
      const u = document.getElementById('chat-user').value.trim(), c = document.getElementById('chat-code').value.trim(); if (u) LS.set('deskUser', u); if (c) LS.set('deskCode', c); LS.set('groqModel', document.getElementById('chat-model').value); settings(false); };
    document.getElementById('chat-forget').onclick = () => { ['groqApiKey', 'deskUser', 'deskCode'].forEach(k => LS.set(k, null)); ['chat-key', 'chat-user', 'chat-code'].forEach(i => document.getElementById(i).value = ''); };
    const send = async q => { if (!q || busy) return; busy = true; add('user', q); document.getElementById('chat-q').value = ''; try { await ask(q); } finally { busy = false; } };
    document.getElementById('chat-f').onsubmit = e => { e.preventDefault(); send(document.getElementById('chat-q').value.trim()); };
    document.getElementById('chat-q').onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(e.target.value.trim()); } };
    $$('.chat-s').forEach(b => b.onclick = () => send(b.textContent));
  }
  document.addEventListener('DOMContentLoaded', build);
  if (document.readyState !== 'loading') build();
  return { ask };
})();
