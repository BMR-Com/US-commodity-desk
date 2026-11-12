"""Backup desk read for the Overview tab, run by GitHub Actions (.github/workflows/desk_read_bot.yml).

The primary read is written by Claude's intraday task (07:41, 11:41 and 14:41 CT on weekdays): own-words notes in
data/overview/notes.json and a desk alert message. This script only steps in when that task has not committed an
"Overview desk read" for BACKUP_AFTER_H hours (e.g. the Claude subscription lapsed or a run failed):

  1. notes  — for every market, a rule-based read from the news feed (data/news/news.json): the top recent
              headlines with their outlets, a supply/price tone count, and (sugar, coffee, cocoa only) a small
              tone-based fund_score blended with the last one. Entries are marked "by": "bot" so the page shows
              them as an automatic read, and Claude's next run simply overwrites them.
  2. alerts — after the overview rebuild, new key-level breaks and colour-band view changes versus
              data/overview/alert_state.json are written to data/overview/bot_alert.md; the workflow opens a
              GitHub issue from it (GitHub e-mails / notifies repository watchers).

Usage: python models/desk_read_bot.py check|notes|alerts
  check  → prints "backup" or "claude" (whether the backup should run)
"""
import json, os, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
CT = ZoneInfo("America/Chicago")
BACKUP_AFTER_H = float(os.environ.get("BACKUP_AFTER_H", "5"))
NOTES_P, STATE_P, OV_P, ALERT_P = (D / "overview" / "notes.json", D / "overview" / "alert_state.json",
                                   D / "overview" / "overview.json", D / "overview" / "bot_alert.md")
MODEL_SOFTS = {"sugar", "coffee", "cocoa"}  # no full fundamental model on the desk: the read carries a fund_score

# tone words: what the headline says about supply/demand (not the day's price move)
TIGHT = r"drought|dry(ness)?\b|frost|heat ?wave|el ni[nñ]o|la ni[nñ]a|deficit|shortage|tight|lower (output|production|crop|stocks)|" \
        r"(output|production|crop|harvest|stocks|arrivals|supply|supplies) (could |may |to )?(fall|drop|decline|cut|slump|lag|trail|shrink)|" \
        r"cuts? (output|production|crop|forecast|estimate)|disease|outbreak|screwworm|hpai|bird flu|swine fever|strike|disrupt|" \
        r"sanction|export ban|export curbs|force majeure|outage|attack|cold (snap|spell|blast)|strong (demand|sales|exports)|record (demand|sales|exports)"
LOOSE = r"surplus|(rising|higher|record|large|larger|bigger|abundant|ample|global) (\w+ )?(stocks|inventor\w*|supplies|supply|output|production|arrivals)|(stocks|inventor\w*|supplies|supply) (weigh|build)|bumper|record (crop|harvest|output|production)|ample|abundant|glut|oversuppl|(rising|higher|record|large|bigger) (stocks|inventor|supplies|supply|output|production|arrivals)|" \
        r"(stocks|inventor\w*|supplies|output|production|arrivals) (rise|rising|climb|build|jump|surge|grow|outpace)|stock ?build|" \
        r"rains? (help|boost|benefit|improve)|favou?rable weather|good rains|tariff cut|lifts? sanctions|ceasefire|peace|weak (demand|sales|exports)|slow (demand|sales)"
UP = r"\b(rise|rises|rose|rall(y|ies|ied)|jump|climb|surge|soar|gain|higher|up|firm|rebound|bounce)"
DN = r"\b(fall|falls|fell|drop|slide|slump|sink|sank|plunge|tumble|lower|down|weak|retreat|slip)"


def J(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def now_ct():
    return datetime.now(CT)


def hours_since_claude():
    """Hours since the last commit by Claude's intraday task (message 'Overview desk read ...')."""
    try:
        t = subprocess.run(["git", "log", "-1", "--grep=Overview desk read", "--format=%ct", "--", "data/overview/notes.json"],
                           cwd=ROOT, capture_output=True, text=True, timeout=30).stdout.strip()
        return (time.time() - int(t)) / 3600 if t else 1e9
    except Exception:
        return 1e9


def news_items(key, hours):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import overview as ov  # reuse the tile's own news matching (tags, regexes, tier sort, de-dup)
    return ov.events(key, n=8, days=hours / 24)


def tone(titles):
    t = sum(1 for s in titles if re.search(TIGHT, s, re.I))
    l = sum(1 for s in titles if re.search(LOOSE, s, re.I))
    u = sum(1 for s in titles if re.search(UP, s, re.I))
    d = sum(1 for s in titles if re.search(DN, s, re.I))
    return t, l, u, d


def bot_read(key, old, hours):
    its = news_items(key, hours)
    titles = [i["title"] for i in its]
    n = {"date": now_ct().strftime("%Y-%m-%d"), "by": "bot", "time": now_ct().strftime("%H:%M CT")}
    # remember when Claude last read this market, so a stale analyst fund_score can be dropped
    n["claude_date"] = old.get("claude_date") if old.get("by") == "bot" else old.get("date")
    if not its:
        n["fundamental"] = f"No new headlines for this market in the last {hours:.0f} hours."
        n["events"] = [e for e in (old.get("events") or [])][:3]
    else:
        t, l, u, d = tone(titles)
        lean = ("leans supportive (supply risks or firm demand outnumber bearish supply news)" if t > l else
                "leans bearish (bigger supplies or weaker demand outnumber supply risks)" if l > t else
                "is mixed on supply and demand" if t else "has no clear supply or demand signal")
        px = "prices mostly reported higher" if u > d else "prices mostly reported lower" if d > u else "price reports mixed"
        n["fundamental"] = (f"{len(its)} headline{'s' if len(its) > 1 else ''} in the last {hours:.0f} hours; the news flow {lean}, "
                            f"{px} ({t} supply-tight, {l} supply-loose, {u} up, {d} down by keyword).")
        n["events"] = [f"{i['title']} ({i['source']}, {i['date']})" for i in its[:3]]
    # fund_score: only for the markets without a full model, tone-based and blended with the last analyst score
    prev = old.get("fund_score")
    # base = the last analyst (Claude) score, so hourly bot runs do not compound on their own output
    base_sc = old.get("claude_fund_score") if old.get("by") == "bot" else prev
    if base_sc is not None:
        n["claude_fund_score"] = base_sc
    cd = n.get("claude_date")
    fresh = cd and (now_ct().date() - datetime.strptime(cd, "%Y-%m-%d").date()).days <= 2
    if key in MODEL_SOFTS:
        t, l = (tone(titles)[:2] if its else (0, 0))
        news_sc = 0.3 * (t - l) / max(t + l, 1)
        base = base_sc if base_sc is not None else 0.0
        sc = 0.5 * base + 0.5 * news_sc if (t or l) else base
        n["fund_score"] = round(max(-1, min(1, sc)), 2)
    elif base_sc is not None and fresh:
        n["fund_score"] = base_sc
    return n


def do_notes():
    notes = J(NOTES_P) or {"about": "", "markets": {}}
    ov = J(OV_P) or {}
    keys = [m["key"] for m in ov.get("markets", [])] or list(notes.get("markets", {}))
    hours = 76 if now_ct().weekday() == 0 else 30  # Monday: since Friday
    for k in keys:
        notes["markets"][k] = bot_read(k, notes["markets"].get(k) or {}, hours)
    notes["updated"] = now_ct().strftime("%Y-%m-%d")
    notes["bot_note"] = f"Automatic backup read (GitHub Actions) at {now_ct():%Y-%m-%d %H:%M} CT: Claude's desk read had not run for {BACKUP_AFTER_H:.0f}+ hours."
    NOTES_P.write_text(json.dumps(notes, indent=2, ensure_ascii=False) + "\n")
    print("notes: bot read for", len(keys), "markets")


def do_alerts():
    ov = J(OV_P) or {}
    st = J(STATE_P) or {"views": {}, "alerts": {}, "news": []}
    lines, views, alerts = [], {}, {}
    for m in ov.get("markets", []):
        k = m["key"]
        views[k] = {"view": m.get("view"), "shade": m.get("shade"), "score": m.get("score")}
        alerts[k] = [a["text"] for a in (m.get("alerts") or [])]
        px = (m.get("live") or {}).get("last") or (m.get("price") or {}).get("last")
        ctr = (m.get("price") or {}).get("contract", "")
        old = st.get("views", {}).get(k)
        if old and old.get("shade") != m.get("shade"):
            lines.append(f"- **{m['name']}** ({ctr}): view {old.get('view')} → {m.get('view')} (score {m.get('score')}), last {px}")
        for a in m.get("alerts") or []:
            if a["text"] not in (st.get("alerts", {}).get(k) or []) and (a.get("new") or a["text"].startswith("Broke")):
                lines.append(f"- **{m['name']}** ({ctr}): {a['text']}, last {px}")
    STATE_P.write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "by": "bot",
                                   "views": views, "alerts": alerts, "news": st.get("news", [])}, indent=1) + "\n")
    if lines:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        ALERT_P.write_text(f"Automatic backup alert (Claude's desk read has not run for {BACKUP_AFTER_H:.0f}+ hours).\n\n" + "\n".join(lines) +
                           "\n\nhttps://bmr-com.github.io/Brazil--trade/#overview\nhttps://bmr-com.github.io/US-commodity-desk/#overview\n"
                           + (f"\nRepo: {repo}\n" if repo else ""))
    elif ALERT_P.exists():
        ALERT_P.unlink()
    print("alerts:", len(lines))


if __name__ == "__main__":
    cmd = (sys.argv[1:] or ["check"])[0]
    if cmd == "check":
        h = hours_since_claude()
        print("backup" if h >= BACKUP_AFTER_H or os.environ.get("FORCE_BACKUP") == "1" else "claude", file=sys.stdout)
        print(f"hours since Claude's desk read: {h:.1f}", file=sys.stderr)
    elif cmd == "notes":
        do_notes()
    elif cmd == "alerts":
        do_alerts()
