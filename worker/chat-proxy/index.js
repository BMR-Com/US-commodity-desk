// Chat proxy for the BMR-Com US Ags Desk: keeps the Groq API key server-side (Worker secret GROQ_API_KEY),
// checks a per-user access code (secret DESK_USERS = "name:code;name2:code2") and counts questions per user per
// UTC day in a Durable Object; above DAILY_LIMIT it answers 429. The page never sees the Groq key.
const MODELS = new Set(['llama-3.3-70b-versatile', 'meta-llama/llama-4-scout-17b-16e-instruct', 'openai/gpt-oss-120b', 'llama-3.1-8b-instant']);

export class Counter {
  constructor(state) { this.state = state; }
  async fetch(req) {
    const url = new URL(req.url);
    let n = (await this.state.storage.get('n')) || 0;
    if (url.pathname === '/hit') {
      const limit = +url.searchParams.get('limit');
      if (n >= limit) return Response.json({ ok: false, n });
      n += 1; await this.state.storage.put('n', n);
      return Response.json({ ok: true, n });
    }
    return Response.json({ ok: true, n });
  }
}

function users(env) {
  const m = new Map();
  for (const p of String(env.DESK_USERS || '').split(/[;,\n]/)) {
    const i = p.indexOf(':'); if (i > 0) m.set(p.slice(0, i).trim().toLowerCase(), p.slice(i + 1).trim());
  }
  return m;
}
function cors(env, req) {
  const o = req.headers.get('Origin') || '', ok = String(env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).includes(o);
  return { 'Access-Control-Allow-Origin': ok ? o : 'https://bmr-com.github.io', 'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
           'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '86400', Vary: 'Origin' };
}
const json = (h, body, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...h, 'Content-Type': 'application/json' } });

export default {
  async fetch(req, env) {
    const h = cors(env, req);
    if (req.method === 'OPTIONS') return new Response(null, { headers: h });
    const url = new URL(req.url);
    const limit = +(env.DAILY_LIMIT || 500), day = new Date().toISOString().slice(0, 10);
    let body = {};
    if (req.method === 'POST') { try { body = await req.json(); } catch (e) { return json(h, { error: 'bad JSON' }, 400); } }
    else body = Object.fromEntries(url.searchParams);
    const user = String(body.user || '').trim().toLowerCase(), code = String(body.code || '').trim();
    const U = users(env);
    if (!user || !U.has(user) || U.get(user) !== code) return json(h, { error: 'Unknown user or wrong access code.' }, 401);
    const stub = env.COUNTER.get(env.COUNTER.idFromName(`${user}|${day}`));
    if (url.pathname.endsWith('/usage')) { const u = await (await stub.fetch('https://c/get')).json(); return json(h, { user, day, used: u.n, limit }); }
    if (!url.pathname.endsWith('/chat') || req.method !== 'POST') return json(h, { error: 'POST /chat' }, 404);
    if (!env.GROQ_API_KEY) return json(h, { error: 'The proxy has no GROQ_API_KEY secret yet.' }, 503);
    const msgs = Array.isArray(body.messages) ? body.messages : [];
    const size = JSON.stringify(msgs).length;
    if (!msgs.length || size > 90000) return json(h, { error: `messages missing or too large (${size} chars)` }, 413);
    const hit = await (await stub.fetch(`https://c/hit?limit=${limit}`)).json();
    if (!hit.ok) return json(h, { error: `Daily limit reached: ${limit} questions per user per day (resets 00:00 UTC).`, used: hit.n, limit }, 429);
    const first = MODELS.has(body.model) ? body.model : 'llama-3.3-70b-versatile';
    let r, j;   // fall back to the other models when Groq's per-minute limit or an outage hits one (one count per question)
    for (const model of [first, ...[...MODELS].filter(m => m !== first)]) {
      r = await fetch('https://api.groq.com/openai/v1/chat/completions', { method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + env.GROQ_API_KEY },
        body: JSON.stringify({ model, messages: msgs, temperature: Math.min(+body.temperature || 0.2, 1), max_tokens: Math.min(+body.max_tokens || 900, 1500) }) });
      const t = await r.text();
      try { j = JSON.parse(t); } catch (e) { j = { error: t.slice(0, 300) }; }
      j.model = j.model || model;
      if (r.ok || ![413, 429, 500, 502, 503, 504].includes(r.status)) break;
    }
    j.desk_usage = { used: hit.n, limit, day };
    return json(h, j, r.status);
  },
};
