#!/usr/bin/env python3
"""Morning brief track record: a permanent log of every daily call, scored against what prices did next.

1. Log. Each brief build adds one row per market to data/brief/calls.csv: brief date, contract, price at the time of
   the call, rating, desk view and conviction, RSI, support/resistance, trend-follower triggers, ATR, fund positioning
   and the macro view/score. One row per market per brief date: the latest run before the grain open (13:30 UTC)
   wins; a run after the open never replaces a morning call (it saw part of the session). The file is append-only
   history and is not touched by pipelines/retention.py (which only prunes dated folders and dated .md files).
   `--backfill` rebuilds rows for past dates from the git history of data/brief/latest.json (needs a full clone).

2. Score. Each call is marked against the same contract's settlements (data/contracts/<SYM>.csv, final close =
   settlement) 1, 5 and 20 trading days later, starting with the settle of the call day (calls are made before the
   open). Entry = the price in the brief. Weekend/holiday briefs that repeat the prior call (same contract, same
   price) are dropped so a call is not counted twice. Results go to data/brief/scorecard.json:
   - desk view and technical rating: hit rate on directional calls, the base rate (share of that market's h-day moves in the
     called direction over the 3 years before logging began, i.e. what always calling that direction would score), edge = hit - base, average
     signed move in % and in ATRs, an overlap-adjusted t-stat, and the rank correlation of view strength with the move;
   - support/resistance: share of calls where no settle broke the level within 5 days;
   - trend-follower triggers: signed move after the price is through a trigger;
   - macro score: correlation of the score with the average ag move (in ATRs) over the next 5 days.
   Overlapping windows and same-day calls: n_eff = distinct call dates / horizon (conservative: it ignores the
   diversification across markets on the same day). Groups with n_eff < 10 are marked "too few"; read nothing into them.
"""
import csv, json, math, subprocess, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
OUT = D / "brief"
CALLS = OUT / "calls.csv"
SCORE = OUT / "scorecard.json"
HORIZONS = (1, 5, 20)
MIN_EFF = 10
PRE_OPEN_UTC = "13:30"
MONTH = {"Jan": "F", "Feb": "G", "Mar": "H", "Apr": "J", "May": "K", "Jun": "M", "Jul": "N", "Aug": "Q", "Sep": "U", "Oct": "V", "Nov": "X", "Dec": "Z"}
VIEW = {"strongly bearish": -3, "bearish": -2, "mildly bearish": -1, "neutral": 0, "mildly bullish": 1, "bullish": 2, "strongly bullish": 3}
RATING = {"strong sell": -2, "sell": -1, "neutral": 0, "buy": 1, "strong buy": 2}
COLS = ["date", "generated", "prices_from", "sym", "name", "group", "contract", "code", "last", "chg", "atr", "rating", "trend", "rsi",
        "sup", "res", "cta_up", "cta_dn", "mm_net", "mm_pct3", "view", "conviction", "macro_view", "macro_score"]


def code(sym, contract):
    """'Dec 26' -> ZCZ2026 (the naming in data/contracts)."""
    try:
        mon, yy = (contract or "").split()
        return f"{sym}{MONTH[mon[:3]]}20{int(yy):02d}"
    except Exception:
        return ""


def rows_from_brief(B, macro=None):
    mac = B.get("macro") if isinstance(B.get("macro"), dict) else {}
    if mac.get("score") is None and macro:
        mac = macro
    out = []
    for m in B.get("markets", []):
        out.append({"date": B["date"], "generated": B.get("generated", ""), "prices_from": B.get("prices_from", ""), "sym": m["sym"],
                    "name": m.get("name"), "group": m.get("group"), "contract": m.get("contract"), "code": code(m["sym"], m.get("contract")),
                    "last": m.get("last"), "chg": m.get("chg"), "atr": m.get("atr"), "rating": m.get("rating"), "trend": m.get("trend"),
                    "rsi": m.get("rsi"), "sup": m.get("sup"), "res": m.get("res"), "cta_up": m.get("cta_up"), "cta_dn": m.get("cta_dn"),
                    "mm_net": m.get("mm_net"), "mm_pct3": m.get("mm_pct3"), "view": m.get("view"), "conviction": m.get("conviction"),
                    "macro_view": mac.get("view"), "macro_score": mac.get("score")})
    return out


def read_calls():
    if not CALLS.exists():
        return []
    with open(CALLS) as f:
        return list(csv.DictReader(f))


def pre_open(gen):
    return (gen or "")[11:16] < PRE_OPEN_UTC


def merge(calls, new):
    """Upsert by (date, sym): a pre-open run replaces an earlier one; a post-open run only fills a missing date."""
    idx = {(c["date"], c["sym"]): i for i, c in enumerate(calls)}
    for r in new:
        r = {k: "" if r.get(k) is None else r[k] for k in COLS}
        k = (r["date"], r["sym"])
        if k not in idx:
            idx[k] = len(calls)
            calls.append(r)
            continue
        old = calls[idx[k]]
        if old["generated"] == r["generated"] or (pre_open(r["generated"]) and (not pre_open(old["generated"]) or r["generated"] > old["generated"])):
            calls[idx[k]] = r
    calls.sort(key=lambda c: (c["date"], c["sym"]))
    return calls


def write_calls(calls):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(CALLS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(calls)


def backfill():
    git = lambda *a: subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout
    shas = git("log", "--reverse", "--format=%H", "--", "data/brief/latest.json").split()
    calls = read_calls()
    for sha in shas:
        try:
            B = json.loads(git("show", f"{sha}:data/brief/latest.json"))
        except Exception:
            continue
        try:
            macro = json.loads(git("show", f"{sha}:data/macro/macro.json"))
        except Exception:
            macro = None
        calls = merge(calls, rows_from_brief(B, macro))
    write_calls(calls)
    print("backfill:", len(shas), "brief versions,", len({c["date"] for c in calls}), "dates,", len(calls), "calls")


# ---------- scoring ----------

def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def settles(syms):
    """{contract code: (sorted dates, closes)} from data/contracts/<SYM>.csv."""
    out = {}
    for s in syms:
        p = D / "contracts" / f"{s}.csv"
        if not p.exists():
            continue
        by = defaultdict(list)
        with open(p) as f:
            for r in csv.DictReader(f):
                c = num(r.get("close"))
                if c is not None:
                    by[r["contract"]].append((r["date"], c))
        for k, v in by.items():
            v.sort()
            out[k] = ([d for d, _ in v], [c for _, c in v])
    return out


def base_rates(syms, first, years=3):
    cut = f"{int(first[:4]) - years}{first[4:]}"
    out = {}
    for s in syms:
        p = D / "contracts" / f"{s}.csv"
        if not p.exists():
            continue
        by = defaultdict(list)
        with open(p) as f:
            for r in csv.DictReader(f):
                c, v = num(r.get("close")), num(r.get("volume"))
                if c is not None and r["date"] < first:
                    by[r["contract"]].append((r["date"], c, v or 0))
        out[s] = {}
        for h in HORIZONS:
            up = dn = n = 0
            for v in by.values():
                v.sort()
                for i in range(1, len(v) - h + 1):
                    if v[i][0] < cut or v[i][2] <= 0:
                        continue
                    x = v[i + h - 1][1] - v[i - 1][1]
                    n += 1
                    up += x > 0
                    dn += x < 0
            if n:
                out[s][h] = {1: up / n, -1: dn / n}
    return out


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def rank(xs):
    o = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and xs[o[j + 1]] == xs[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def corr(a, b):
    if len(a) < 3:
        return None
    ma, mb = mean(a), mean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return None if sa == 0 or sb == 0 else sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def stats(rows, h, key):
    """rows carry 'dir' (call sign), 'score' (strength) and fwd returns; directional stats for one horizon."""
    rs = [r for r in rows if r["fwd"].get(h) is not None]
    dirn = [r for r in rs if r[key] != 0]
    n = len(dirn)
    eff = len({r["date"] for r in dirn}) / h  # same-day calls move together: count independent dates, not calls
    out = {"n": n, "n_eff": round(eff, 1), "too_few": eff < MIN_EFF}
    if not n:
        return out
    sgn = lambda r: 1 if r[key] > 0 else -1
    hits = [1 if sgn(r) * r["fwd"][h]["pct"] > 0 else 0 for r in dirn]
    base = [r["base"][h][sgn(r)] for r in dirn if r["base"].get(h)]
    sp = [sgn(r) * r["fwd"][h]["pct"] for r in dirn]
    sa = [sgn(r) * r["fwd"][h]["atr"] for r in dirn if r["fwd"][h]["atr"] is not None]
    sd = math.sqrt(sum((x - mean(sp)) ** 2 for x in sp) / (n - 1)) if n > 1 else None
    t = mean(sp) / (sd / math.sqrt(max(eff, 1))) if sd else None
    ic = corr(rank([r[key] for r in rs]), rank([r["fwd"][h]["atr"] if r["fwd"][h]["atr"] is not None else r["fwd"][h]["pct"] for r in rs]))
    out.update({"hit": round(100 * mean(hits), 1), "base": None if not base else round(100 * mean(base), 1),
                "edge": None if not base else round(100 * (mean(hits) - mean(base)), 1),
                "avg_pct": round(mean(sp), 2), "avg_atr": None if not sa else round(mean(sa), 2),
                "t": None if t is None else round(t, 2), "rank_ic": None if ic is None else round(ic, 3)})
    return out


def score():
    calls = read_calls()
    if not calls:
        print("scorecard: no calls logged")
        return
    S = settles({c["sym"] for c in calls})
    # drop repeats: a brief that shows the same contract at the same price as the previous call (weekend, holiday)
    by_sym = defaultdict(list)
    for c in sorted(calls, key=lambda c: c["date"]):
        prev = by_sym[c["sym"]][-1] if by_sym[c["sym"]] else None
        if prev and prev["code"] == c["code"] and prev["last"] == c["last"]:
            continue
        by_sym[c["sym"]].append(c)
    rows = []
    for sym, cs in by_sym.items():
        for c in cs:
            last, atr = num(c["last"]), num(c["atr"])
            ser = S.get(c["code"])
            if last is None or not ser:
                continue
            dates, px = ser
            i0 = bisect_left(dates, c["date"]) if pre_open(c["generated"]) else bisect_left(dates, c["date"] + "~")
            fwd, path = {}, px[i0:i0 + max(HORIZONS)]
            for h in HORIZONS:
                j = i0 + h - 1
                if j < len(px):
                    fwd[h] = {"pct": 100 * (px[j] / last - 1), "atr": (px[j] - last) / atr if atr else None, "date": dates[j]}
            rows.append({"c": c, "sym": sym, "date": c["date"], "last": last, "fwd": fwd, "path": path,
                         "view": VIEW.get((c["view"] or "").lower(), 0), "rating": RATING.get((c["rating"] or "").lower(), 0),
                         "trig": 1 if num(c["cta_up"]) is not None and last > num(c["cta_up"]) else -1 if num(c["cta_dn"]) is not None and last < num(c["cta_dn"]) else 0,
                         "macro": num(c["macro_score"])})
    # base rate per market and horizon: share of up / down h-day settle-to-settle moves in that market's traded
    # contracts over the 3 years before the first call (what always calling up, or always down, would have scored)
    base = base_rates(by_sym, min(c["date"] for c in calls))
    for r in rows:
        r["base"] = base.get(r["sym"], {})

    def block(rs, key):
        return {f"{h}d": stats(rs, h, key) for h in HORIZONS}

    names = {r["sym"]: r["c"]["name"] for r in rows}
    out = {"generated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "first_call": min(c["date"] for c in calls),
           "last_call": max(c["date"] for c in calls), "calls_logged": len(calls), "calls_scored": {f"{h}d": sum(h in r["fwd"] for r in rows) for h in HORIZONS},
           "min_eff": MIN_EFF, "method": __doc__.split("2. Score.")[1].strip(),
           "view": {"all": block(rows, "view"), "by_market": {}, "by_view": {}},
           "rating": {"all": block(rows, "rating"), "by_rating": {}},
           "triggers": block(rows, "trig"), "levels": {}, "macro": {}, "by_market_rows": []}
    for sym in sorted(by_sym, key=lambda s: names.get(s, s)):
        rs = [r for r in rows if r["sym"] == sym]
        if rs:
            out["view"]["by_market"][sym] = {"name": names[sym], **block(rs, "view")}
    for v, s in VIEW.items():
        rs = [r for r in rows if r["view"] == s]
        if rs and s:
            out["view"]["by_view"][v] = block([dict(r, one=s) for r in rs], "one")
    for v, s in RATING.items():
        rs = [r for r in rows if r["rating"] == s]
        if rs and s:
            out["rating"]["by_rating"][v] = block([dict(r, one=s) for r in rs], "one")
    # support / resistance: did any settle in the next 5 days break the level?
    for side, k, brk in (("support", "sup", lambda p, l: p < l), ("resistance", "res", lambda p, l: p > l)):
        rs = [(r, num(r["c"][k])) for r in rows if num(r["c"][k]) is not None and len(r["path"]) >= 5]
        rs = [(r, l) for r, l in rs if (l < r["last"] if side == "support" else l > r["last"])]
        held = [0 if any(brk(p, l) for p in r["path"][:5]) else 1 for r, l in rs]
        dist = [abs(r["last"] - l) / num(r["c"]["atr"]) for r, l in rs if num(r["c"]["atr"])]
        de = len({r["date"] for r, _ in rs}) / 5
        out["levels"][side] = {"n": len(held), "n_eff": round(de, 1), "too_few": de < MIN_EFF,
                               "held_5d": None if not held else round(100 * mean(held), 1), "avg_dist_atr": None if not dist else round(mean(dist), 2)}
    # macro score vs the average ag move (ATRs, unsigned by market) over the next 5 days
    by_date = defaultdict(list)
    for r in rows:
        if r["macro"] is not None and 5 in r["fwd"] and r["fwd"][5]["atr"] is not None:
            by_date[r["date"]].append((r["macro"], r["fwd"][5]["atr"]))
    pts = [(v[0][0], mean([x for _, x in v])) for v in by_date.values()]
    out["macro"] = {"n_days": len(pts), "n_eff": round(len(pts) / 5, 1), "too_few": len(pts) / 5 < MIN_EFF,
                    "corr_5d": None if len(pts) < 3 else (lambda c: None if c is None else round(c, 3))(corr([a for a, _ in pts], [b for _, b in pts])),
                    "avg_move_atr_when": {k: (lambda xs: None if not xs else round(mean(xs), 2))([b for a, b in pts if f(a)])
                                          for k, f in (("positive", lambda a: a > 0), ("zero", lambda a: a == 0), ("negative", lambda a: a < 0))}}
    # weak records: enough independent 5-day calls and a negative edge / wrong-way average
    weak = []
    for sym, b in out["view"]["by_market"].items():
        s5 = b["5d"]
        if not s5.get("too_few", True) and s5.get("hit") is not None and ((s5.get("edge") or 0) < -5 or s5["avg_pct"] < 0):
            weak.append({"sym": sym, "name": b["name"], "hit": s5["hit"], "edge": s5.get("edge"), "n": s5["n"]})
    out["weak"] = weak
    a5 = out["view"]["all"]["5d"]
    out["line"] = (f"Desk-view track record (5-day, {a5['n']} directional calls since {out['first_call']}): hit {a5['hit']}% vs base {a5['base']}%, "
                   f"avg {a5['avg_pct']:+.2f}% in the called direction (t {a5['t']})." if a5.get("hit") is not None and not a5["too_few"]
                   else f"Track record: {len(calls)} calls logged since {out['first_call']}; scoring needs about {MIN_EFF * 5} trading days of 5-day calls before the numbers mean anything.")
    SCORE.write_text(json.dumps(out, indent=1))
    print("scorecard:", out["line"])


def main():
    if "--backfill" in sys.argv:
        backfill()
    elif "--score-only" not in sys.argv:
        B = json.loads((OUT / "latest.json").read_text())
        write_calls(merge(read_calls(), rows_from_brief(B)))
        print("logged", B["date"], len(B.get("markets", [])), "calls")
    score()


if __name__ == "__main__":
    main()
