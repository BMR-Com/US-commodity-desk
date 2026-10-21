#!/usr/bin/env python3
"""Pre-written AI reads for the desk chatbot, generated in GitHub Actions with the GROQ_API_KEY secret.

For the overview and each market card in data/ai/context.json, ask Groq for a short desk read and answers to a few
standard questions, using only the card's numbers. The chatbot shows these to anyone (no key needed); live questions
still need a key in the browser. Paced for the Groq free tier (per-minute token limits). Writes data/ai/daily.json.
"""
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "ai"
KEY = os.environ.get("GROQ_API_KEY", "")
PREF = ["gpt-oss-120b", "llama-4-maverick", "llama-4-scout", "llama-3.3-70b", "qwen3-32b", "kimi-k2", "gpt-oss-20b", "llama-3.1-8b"]
MODELS = []


def models():
    """Chat models this key can use now (Groq retires models), in preference order; saved for the chatbot."""
    global MODELS
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": "Bearer " + KEY}, timeout=30)
        ids = [m["id"] for m in r.json().get("data", []) if m.get("active", True)]
    except Exception as e:
        print("models list failed", e); ids = []
    ids = [i for i in ids if not any(x in i for x in ("whisper", "guard", "tts", "playai", "orpheus", "prompt", "compound", "distil"))]
    rank = lambda i: next((k for k, p in enumerate(PREF) if p in i), len(PREF))
    MODELS = sorted(ids, key=rank)
    print("models:", MODELS)
    (D / "models.json").write_text(json.dumps({"checked": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "models": MODELS}))
QUESTIONS = {
    "market": ["What is the desk's view and why?", "What are funds (COT) doing?", "What are the key levels and next catalysts?", "What do the fundamentals say?"],
    "overview": ["What matters most today?", "What is the macro backdrop for ags?"],
}
SYS = ("You are the analyst of the BMR-Com US Ags Desk. Use ONLY the DATA given; quote numbers with units and dates; never invent numbers; "
       "if something is missing say so. Plain English, concise. Research, not investment advice.")


def ask(messages, max_tokens=900):
    for m in MODELS:
        for attempt in range(3):
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": "Bearer " + KEY},
                                  json={"model": m, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}, timeout=90)
            except Exception as e:
                print("  err", e); time.sleep(10); continue
            if r.status_code == 200:
                txt = r.json()["choices"][0]["message"]["content"] or ""
                a, b = txt.find("{"), txt.rfind("}")
                if a >= 0 and b > a:
                    try:
                        json.loads(txt[a:b + 1]); return m, txt[a:b + 1]
                    except Exception:
                        pass
                print("  ", m, "no JSON in reply"); break
            print("  ", m, r.status_code, r.text[:160])
            if r.status_code == 401:
                sys.exit("GROQ_API_KEY rejected (401)")
            if r.status_code == 429:
                time.sleep(25 * (attempt + 1)); continue
            break
    return None, None


def main():
    if not KEY:
        print("ai_daily: no GROQ_API_KEY secret")
        return
    models()
    if not MODELS:
        sys.exit("no Groq models available for this key")
    C = json.loads((D / "context.json").read_text())
    cards = [c for c in C["cards"] if c["kind"] in ("overview", "market")]
    only = set(sys.argv[1:])
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "data_date": C.get("data_date"), "items": {}}
    for c in cards:
        if only and c["id"] not in only:
            continue
        qs = QUESTIONS["overview" if c["kind"] == "overview" else "market"]
        prompt = (f"DATA ({c['title']}):\n{c['text']}\n\nReply with ONLY a JSON object, no other text: {{\"read\": \"3-5 sentence desk read of {c['title']}\", "
                  f"\"faq\": [{{\"q\": question, \"a\": answer of 2-5 sentences}}] for these questions: {json.dumps(qs)}}}")
        m, txt = ask([{"role": "system", "content": SYS}, {"role": "user", "content": prompt}], 1200)
        if not txt:
            print(c["id"], "no answer"); continue
        try:
            j = json.loads(txt)
        except Exception:
            print(c["id"], "bad JSON"); continue
        out["items"][c["id"]] = {"title": c["title"], "model": m, "read": j.get("read"), "faq": [x for x in j.get("faq", []) if x.get("q") and x.get("a")]}
        print(c["id"], m, (j.get("read") or "")[:100], flush=True)
        time.sleep(20)   # stay under the free tier's tokens-per-minute (6-8k tokens a minute on most models)
    D.mkdir(parents=True, exist_ok=True)
    (D / "daily.json").write_text(json.dumps(out, ensure_ascii=False, indent=0))
    print(len(out["items"]), "items")


if __name__ == "__main__":
    main()
