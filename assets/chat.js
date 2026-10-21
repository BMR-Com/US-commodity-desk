// Ask the desk: a chatbot over the desk's own numbers (data/ai/context.json + the text of the open tab), answered by
// Groq (free tier). The Groq key is pasted once and kept only in this browser (localStorage), sent only to api.groq.com.
const Chat = (() => {
  const MODELS = [['llama-3.3-70b-versatile', 'Llama 3.3 70B (best)'], ['meta-llama/llama-4-scout-17b-16e-instruct', 'Llama 4 Scout (more context)'],
                  ['openai/gpt-oss-120b', 'GPT-OSS 120B'], ['llama-3.1-8b-instant', 'Llama 3.1 8B (fastest)']];
  const TAB_SYMS = { grains: ['ZC', 'ZS', 'ZM', 'ZL', 'ZW', 'KE'], dairy: ['DC', 'GDK', 'CSC', 'CB', 'GNF', 'DY'], hogs: ['HE'], cattle: ['LE', 'GF'], cotton: ['CT'],
                     energy: ['NG', 'CL', 'HO', 'RB'], cotfull: [], markets: [], summary: [], signals: [], options: [] };
  const BUDGET = 16000;   // characters of desk cards per question (~4k tokens; the free tier allows 6-30k tokens a minute)
  const LS = { get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) {} } };
  let CTX = null, hist = [], lastIds = [], busy = false, PROXY;
  const proxy = async () => { if (PROXY === undefined) PROXY = await getJSON('data/ai/proxy.json').then(j => j && j.url ? j : null).catch(() => null); return PROXY; };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const md = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/^#{1,4} (.*)$/gm, '<b>$1</b>').replace(/^\s*[-*] (.*)$/gm, '• $1').replace(/\n/g, '<br>');
  function activeTab() { const b = document.querySelector('nav.comm button.on'); return b ? b.dataset.c : 'summary'; }
  function pageText() {
    const t = activeTab(), sec = document.getElementById(t);
    if (!sec) return '';
    let txt = '';
    const fr = sec.querySelector('iframe');
    try { txt = fr ? fr.contentDocument.body.innerText : sec.innerText; } catch (e) { txt = sec.innerText; }
    return txt.replace(/[ \t]+/g, ' ').replace(/\n{2,}/g, '\n').trim().slice(0, 3500);
  }
  function pick(q) {
    const ql = ' ' + q.toLowerCase().replace(/[^a-z0-9/&.%-]+/g, ' ') + ' ';
    const tabSyms = TAB_SYMS[activeTab()] || [];
    const hs = (location.hash.split('/')[1] || '').toUpperCase();
    const score = CTX.cards.map(c => {
      let s = 0;
      for (const a of c.aliases || []) {
        const hit = a.length <= 3 ? ql.includes(' ' + a + ' ') : ql.includes(a);
        if (hit) s += a.length > 4 ? 3 : 2;
      }
      if (c.kind === 'market' && (tabSyms.includes(c.id) || c.id === hs)) s += 1.5;
      if (lastIds.includes(c.id)) s += 1;
      return [s, c];
    }).filter(x => x[0] > 0).sort((a, b) => b[0] - a[0]);
    const always = ['overview', 'table'].map(id => CTX.cards.find(c => c.id === id)).filter(Boolean);
    const out = [...always]; let n = always.reduce((a, c) => a + c.text.length, 0);
    for (const [, c] of score) { if (out.includes(c)) continue; if (n + c.text.length > BUDGET) continue; out.push(c); n += c.text.length; }
    return out;
  }
  async function ask(q) {
    const P = await proxy();
    const key = LS.get('groqApiKey'), user = LS.get('deskUser'), code = LS.get('deskCode');
    if (P && !(user && code)) { settings(true); add('bot', 'Enter your desk user name and access code in the settings above (ask the desk owner for one).'); return; }
    if (!P && !key) { settings(true); add('bot', 'Paste your Groq API key in the settings above first (free at console.groq.com/keys). It stays in this browser only.'); return; }
    if (!CTX) CTX = await getJSON('data/ai/context.json').catch(() => null);
    if (!CTX) { add('bot', 'The desk context file is not built yet (data/ai/context.json).'); return; }
    const cards = pick(q); lastIds = cards.map(c => c.id);
    const page = pageText();
    const sys = `You are the assistant of the BMR-Com US Ags Desk, a research site on US agricultural and energy futures (grains, oilseeds, cotton, livestock, dairy, energy).
Answer ONLY from the DATA below: the desk's cards (built ${CTX.generated}, market data as of ${CTX.data_date}) and the text of the tab the user has open.
Rules: quote numbers with units, contract and date; if the data does not contain the answer, say so plainly and name the tab where it may be (Summary, Markets & macro, Options pricer, Signals, Dairy, Grains & oilseeds, Cotton, Lean hogs, Live & feeder cattle, COT (full), Energy). Never invent numbers. Be concise: short paragraphs or bullets. Explain jargon briefly when helpful. This is research, not investment advice; describe the desk's own views and signals rather than giving personal trade recommendations.`;
    const data = cards.map(c => `### ${c.title}\n${c.text}`).join('\n\n') + (page ? `\n\n### Text of the open tab (${activeTab()})\n${page}` : '');
    const msgs = [{ role: 'system', content: sys + '\n\nDATA:\n' + data }, ...hist.slice(-6), { role: 'user', content: q }];
    const thinking = add('bot', '…');
    const order = [LS.get('groqModel') || MODELS[0][0], ...MODELS.map(m => m[0])].filter((m, i, a) => a.indexOf(m) === i);
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
        if (r.status === 429 || r.status === 413 || r.status === 400 || r.status === 404 || r.status >= 500) { err = `${model}: HTTP ${r.status}`; continue; }
        const j = await r.json();
        txt = j.choices?.[0]?.message?.content; used = model;
        if (txt) break;
      } catch (e) { err = String(e); }
    }
    thinking.remove();
    if (!txt) { add('bot', 'No answer: ' + (err || 'unknown error') + '. On the free tier, wait a minute if you hit the per-minute limit.'); return; }
    hist.push({ role: 'user', content: q }, { role: 'assistant', content: txt });
    add('bot', txt, `${used.split('/').pop()}${usage ? ` · ${usage.used}/${usage.limit} today` : ''} · sources: ${cards.map(c => c.title).join(', ')}${page ? ', open tab' : ''}`);
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
          <p class="note" id="chat-note">Free key: console.groq.com/keys. Kept only in this browser and sent only to Groq. Free-tier limits are per minute; the bot falls back to another model when one is busy.</p></div>
        <div id="chat-msgs"><div class="chat-m chat-bot">Ask about any number on the desk, for example:<div class="chat-sugg">
          ${['Why is corn rated strongly bearish?', 'Which markets have crowded fund positioning?', 'Compare carry and trend for soybeans and soy oil', 'What does the options market imply for Class III milk?', 'Summarize this tab'].map(s => `<button class="chat-s">${s}</button>`).join('')}</div></div></div>
        <form id="chat-f"><textarea id="chat-q" rows="2" placeholder="Ask about prices, fundamentals, COT, options, signals…"></textarea><button type="submit">Send</button></form></div>`;
    document.body.appendChild(el);
    const panel = document.getElementById('chat-panel');
    document.getElementById('chat-btn').onclick = () => { panel.style.display = panel.style.display === 'none' ? '' : 'none'; if (!LS.get('groqApiKey') && !LS.get('deskCode')) settings(true); document.getElementById('chat-q').focus(); };
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
