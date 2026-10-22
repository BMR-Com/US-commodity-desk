#!/usr/bin/env python3
"""Dairy trade playbook for the Outlook tab: every tested strategy as a trade card with today's positions, entry and
exit rules, risk, and what to track. Runs nightly (after models/dairy_arb.py refreshes the spot nowcast and the
per-contract settlements); the track records come from models/dairy_ideas.py (weekly).
Writes data/dairy/derived/playbook.json.
"""
import json, math, sys
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
from futures_io import load_contracts  # noqa: E402
from dairy_class import load_class_prices  # noqa: E402
from dairy_arb import targets  # noqa: E402
import dairy_ideas as DI  # noqa: E402

D = ROOT / "data" / "dairy" / "derived"
SPEC = DI.SPEC
NAME = {s: v[4] for s, v in SPEC.items()}
UNIT = {"DC": "$/cwt", "GDK": "$/cwt", "CSC": "$/lb", "CB": "¢/lb", "GNF": "¢/lb", "DY": "¢/lb"}


def J(p):
    try:
        return json.loads((D / p).read_text())
    except Exception:
        return {}


def stat(I, key):
    x = next((i for i in I if i["key"] == key), None)
    if not x:
        return None
    return {k: x.get(k) for k in ("sharpe", "sharpe_2020_23", "sharpe_2024_26", "hit", "payoff", "ann_usd", "maxdd_usd", "calmar", "avg_win_usd", "avg_loss_usd", "trades", "avg_lots", "worst_week_usd")}


def main():
    ideas, arb, lab = J("dairy_ideas.json"), J("dairy_arb.json"), J("dairy_lab.json")
    I = ideas.get("ideas", [])
    T = targets(load_class_prices())
    F = {s: load_contracts(s) for s in SPEC}
    today = max(f.date.max() for f in F.values())
    live = arb.get("live", [])
    # 4-week futures trend per open month, from settlements (nightly)
    trend = {}
    for s, f in F.items():
        st = f.pivot_table(index="date", columns="m", values="close").sort_index().ffill()
        now, ago = st.iloc[-1], st.loc[:today - pd.Timedelta(days=28)].iloc[-1]
        cur = today.to_period("M")
        for h in range(0, 6):
            m = cur + h
            if m in T.index and pd.notna(T.loc[m, "ann"]) and T.loc[m, "ann"] <= today:
                continue
            if m in st.columns and pd.notna(now.get(m)) and pd.notna(ago.get(m)) and ago[m] > 0:
                trend[(s, str(m))] = {"futures": float(now[m]), "chg": float(math.log(now[m] / ago[m])), "cost": SPEC[s][3] / float(now[m])}
    ann_date = lambda m: (str(T.loc[pd.Period(m, "M"), "ann"].date()) if pd.Period(m, "M") in T.index and pd.notna(T.loc[pd.Period(m, "M"), "ann"]) else
                          f"~{(pd.Period(m, 'M') + 1).start_time + pd.offsets.Week(weekday=2):%Y-%m-%d}")
    def conv_rows(syms, hmax=2, need_trend=False, late=False):
        out = []
        for r in live:
            s = r["sym"]
            if s not in syms:
                continue
            h = (pd.Period(r["month"], "M") - today.to_period("M")).n
            if h < 0 or h > hmax or r.get("nowcast") is None:
                continue
            if late and not (h == 0 and today.day >= 8):
                continue
            gap = r["nowcast"] - r["futures"]
            if abs(r["gap_usd"]) <= r["cost_usd"]:
                continue
            side = 1 if gap > 0 else -1
            tr = trend.get((s, r["month"]))
            if need_trend and (tr is None or np.sign(tr["chg"]) != side):
                continue
            out.append({"contract": f"{NAME[s]} {pd.Period(r['month'], 'M').strftime('%b %Y')}", "sym": s, "month": r["month"], "side": "long" if side > 0 else "short",
                        "futures": r["futures"], "estimate": round(r["nowcast"], 3), "unit": UNIT[s], "edge_usd": abs(int(r["gap_usd"])), "cost_usd": r["cost_usd"],
                        "weeks_published": f"{r['known_weeks']} of {r['weeks']}", "settles": ann_date(r["month"]),
                        "note": f"futures last traded {r.get('last_trade') or '–'}"})
        return out
    trades = []
    # 1 convergence core
    trades.append({"key": "conv_core", "name": "Cash convergence: butter and dry whey", "type": "Cash arbitrage", "stats": stat(I, "conv_butter_whey"),
        "thesis": "Butter and whey futures settle on USDA's monthly average of the weekly plant survey, which follows CME spot with a 1-2 week lag. When spot has moved and the futures have not, the futures have to converge toward the spot-based estimate by settlement.",
        "entry": "On Wednesday, after the 11:00 am CT USDA weekly report (NDPSR) and the CME spot session: for each butter and whey contract up to 2 months out, if the desk's estimate of the settlement is above the futures by more than the round-trip cost (shown below), buy one lot; if below, sell one. Enter near the settlement price.",
        "exit": "Re-check every Wednesday. Close when the estimate-vs-futures gap shrinks below the round-trip cost or flips sign, or hold to final settlement (the USDA announcement in the first days of the following month; the contract stops trading the day before).",
        "risk": "No stop was used in the test. Size so the historical worst drawdown is tolerable; a large unexpected move in CME spot during the month is the main risk, so it falls as more weeks are published.",
        "track": ["CME spot butter and dry whey closes (daily, about 11:10 am CT)", "USDA NDPSR weekly prices and volumes (Wednesday 11:00 am CT)", "The gap on this page (updated nightly)", "USDA class and product price announcement (first Wednesday of the month)"],
        "positions": conv_rows(("CB", "DY"))})
    trades.append({"key": "conv_trend", "name": "Cash convergence confirmed by the futures trend (all six)", "type": "Cash arbitrage + trend", "stats": stat(I, "conv_trend"),
        "thesis": "Same convergence logic across all six contracts, but only when the futures have already moved the same way over the last 4 weeks. Fewer trades, better return per unit of drawdown than the plain version.",
        "entry": "Wednesday, after the USDA weekly report: estimate above futures by more than the cost AND the contract up at least the cost over the last 4 weeks (or the mirror for shorts). Contracts up to 2 months out.",
        "exit": "Wednesday re-check: close if either condition fails, or hold to settlement.",
        "risk": "Class III and cheese are efficiently priced on their own; the trend filter is what keeps them from losing.",
        "track": ["CME spot cheese blocks and barrels, butter, nonfat, whey (daily)", "USDA NDPSR (Wednesday)", "4-week change of each contract (this page, nightly)"],
        "positions": conv_rows(tuple(SPEC), need_trend=True)})
    trades.append({"key": "conv_late", "name": "Spot-month lock-in (lowest risk)", "type": "Cash arbitrage", "stats": stat(I, "conv_late"),
        "thesis": "Once the first weekly prints of the month are published, part of the monthly average is locked and the rest follows spot already seen. The remaining risk is small, so this is the closest to a true arbitrage; edges are small and frequent.",
        "entry": "From the 8th of the month: current-month contract only, all six; trade the direction of the estimate-vs-futures gap when it exceeds the round-trip cost.",
        "exit": "Hold to final settlement, or close if the gap falls below cost at a Wednesday check.",
        "risk": "Liquidity in the expiring month is thin; work orders near the settlement.",
        "track": ["Weekly prints published so far this month", "CME spot since the last print", "The gap on this page"],
        "positions": conv_rows(tuple(SPEC), hmax=0, late=True)})
    # trend
    tpos = [{"contract": f"{NAME[s]} {pd.Period(m, 'M').strftime('%b %Y')}", "sym": s, "month": m, "side": "long" if v["chg"] > 0 else "short", "futures": v["futures"], "unit": UNIT[s],
             "chg_4w_pct": round(v["chg"] * 100, 2), "settles": ann_date(m)} for (s, m), v in sorted(trend.items()) if abs(v["chg"]) > v["cost"]]
    trades.append({"key": "trend4", "name": "4-week futures trend (all six, up to 5 months out)", "type": "Trend / persistence", "stats": stat(I, "trend4"),
        "thesis": "Dairy settlement prices are averages of slow-moving survey prices, so moves persist for weeks; futures inherit part of that persistence.",
        "entry": "Weekly (Wednesday): hold one lot per contract month in the direction of its change over the last 4 weeks, when that change is larger than the round-trip cost.",
        "exit": "Flip or flatten when the 4-week change reverses or falls below the cost at the weekly check.",
        "risk": "Largest drawdowns of all the ideas (many positions); run it smaller than the convergence trades.",
        "track": ["4-week change of each contract (this page)", "CME spot direction"],
        "positions": tpos})
    # breakouts with stops (state from the daily rule)
    bstate = {}
    for s in ("CB", "GDK", "GNF"):
        DI.daily_breakout(F, T, s)
        bstate[s] = DI.daily_breakout.state.get(s, {})
    for s in ("CB", "GDK", "GNF"):
        st = bstate[s]
        pos = []
        if st.get("pos"):
            pos.append({"contract": f"{NAME[s]} {pd.Period(st['month'], 'M').strftime('%b %Y')}", "sym": s, "month": st["month"], "side": "long" if st["pos"] > 0 else "short",
                        "entry_price": round(st["entry"], 4), "entry_date": st["entry_date"], "futures": round(st["close"], 4), "stop": round(st["stop"], 4), "unit": UNIT[s],
                        "open_pnl_usd": st["open_pnl_usd"],
                        "exit_signal": (f"close if it settles below {st['exit_long_below']:.3f} (10-day low) or the stop {st['stop']:.3f}" if st["pos"] > 0 else
                                        f"close if it settles above {st['exit_short_above']:.3f} (10-day high) or the stop {st['stop']:.3f}")})
        trades.append({"key": f"breakout_{s}", "name": f"Breakout with trailing stop: {NAME[s]}", "type": "Trend, low drawdown", "stats": stat(I, f"breakout_{s}"),
            "thesis": "Right less than half the time, but stops keep losers small while the occasional long dairy trend runs; small drawdowns per lot.",
            "entry": f"Daily on the contract about 2 months out ({st.get('month', '–')}): buy when it settles above its 20-day high (now {st.get('buy_above', float('nan')):.3f}); sell when it settles below its 20-day low (now {st.get('sell_below', float('nan')):.3f}).",
            "exit": "Long: close on a settle below the 10-day low or the trailing stop (2x the 20-day average daily move below the best close). Short: the mirror. Also close 10 days before the USDA announcement.",
            "risk": f"Average daily move {st.get('atr', float('nan')):.3f} {UNIT[s]}; stop distance about {2 * st.get('atr', float('nan')):.3f}.",
            "track": ["Daily settlement vs the 20-day high/low and the stop (this page, nightly)"],
            "levels": {k: st.get(k) for k in ("date", "month", "close", "buy_above", "sell_below", "exit_long_below", "exit_short_above", "atr")},
            "positions": pos})
    # formula arbitrage
    fa = arb.get("formula_arb", {})
    fpos = []
    for k, lab_ in (("class3", "Class III"), ("class4", "Class IV")):
        for r in fa.get(k, {}).get("now", []):
            if abs(r["gap"]) >= 0.20:
                hr = fa.get("hedge_per_10", {}).get(k, {})
                legs = ", ".join(f"{'buy' if r['gap'] < 0 else 'sell'} {v} {sym}" for sym, v in hr.items())
                fpos.append({"contract": f"{lab_} {pd.Period(r['month'], 'M').strftime('%b %Y')}", "side": ("sell" if r["gap"] > 0 else "buy") + f" {lab_}", "futures": r["futures"],
                             "estimate": round(r["implied"], 2), "gap_cwt": r["gap"], "legs_per_10": legs})
    t3 = next((t for t in fa.get("class3", {}).get("trades", []) if t["threshold"] == 0.2), {})
    trades.append({"key": "formula_arb", "name": "Formula arbitrage: Class III / IV vs component futures", "type": "Relative value",
        "stats": {"hit": t3.get("hit"), "avg_usd_per_class_contract": t3.get("avg_usd"), "months": t3.get("months")},
        "thesis": "Class III is a fixed formula of the cheese, butter and whey averages (Class IV: butter and nonfat); the class contract and its components settle on the same USDA numbers, so a price gap between them must close by expiry.",
        "entry": "When the Class futures differ from the price implied by the component futures of the same month by more than $0.20/cwt: sell the dear side, buy the cheap side in the hedge ratio shown (per 10 Class contracts).",
        "exit": "Hold to settlement, or close when the gap is back under about $0.05.",
        "risk": "Four thin legs; quotes can be stale, so check live bids and offers before acting.",
        "track": ["Class vs implied gap (this page, nightly)", "Live quotes on all legs"],
        "positions": fpos})
    out = {"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "as_of": str(today.date()), "stats_since": ideas.get("start"),
           "stats_generated": ideas.get("generated"), "trades": trades}
    (D / "playbook.json").write_text(json.dumps(out, default=lambda o: None if (isinstance(o, float) and math.isnan(o)) else str(o)))
    for t in trades:
        print(t["name"], len(t["positions"]))


if __name__ == "__main__":
    main()
