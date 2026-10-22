#!/usr/bin/env python3
"""Contract specifications for every desk market: available contracts (standard, mini, micro), size, tick value,
contract value in dollars at today's price, exchange maintenance margin and what it covers.

Prices: front contract's latest close from data/technicals/<SYM>.json. Margins: data/specs/margins.json (CME Group
outright maintenance margins, refreshed by the Mac collector via cme/collect_margins.js). Writes data/specs/specs.json.
"""
import json, math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# group -> list of contracts. price: desk symbol whose front price applies; usd: $ value of 1 quoted unit for one contract
# ratio: fraction of the parent contract (for minis / micros priced off the parent)
C = {
    "grains": [
        dict(sym="ZC", name="Corn", ex="CBOT", code="C", size="5,000 bu", quote="¢/bu", tick="0.25¢ = $12.50", usd=50, price="ZC", months="Mar, May, Jul, Sep, Dec", settle="Physical (shipping certificates, Illinois River)", options="Yes, incl. weeklies and short-dated new crop"),
        dict(sym="XC", name="Mini corn", ex="CBOT", code="YC", size="1,000 bu", quote="¢/bu", tick="0.125¢ = $1.25", usd=10, price="ZC", months="as corn", settle="Physical", options="No"),
        dict(sym="MZC", name="Micro corn", ex="CBOT", code="MZC", size="500 bu", quote="¢/bu", tick="0.50¢ = $2.50", usd=5, price="ZC", months="as corn", settle="Cash-settled to the corn future", options="No"),
        dict(sym="ZS", name="Soybeans", ex="CBOT", code="S", size="5,000 bu", quote="¢/bu", tick="0.25¢ = $12.50", usd=50, price="ZS", months="Jan, Mar, May, Jul, Aug, Sep, Nov", settle="Physical (shipping certificates)", options="Yes"),
        dict(sym="XK", name="Mini soybeans", ex="CBOT", code="YK", size="1,000 bu", quote="¢/bu", tick="0.125¢ = $1.25", usd=10, price="ZS", months="as soybeans", settle="Physical", options="No"),
        dict(sym="MZS", name="Micro soybeans", ex="CBOT", code="MZS", size="500 bu", quote="¢/bu", tick="0.50¢ = $2.50", usd=5, price="ZS", months="as soybeans", settle="Cash-settled to the soybean future", options="No"),
        dict(sym="ZM", name="Soybean meal", ex="CBOT", code="06", size="100 short tons", quote="$/short ton", tick="$0.10 = $10", usd=100, price="ZM", months="Jan, Mar, May, Jul, Aug, Sep, Oct, Dec", settle="Physical (shipping certificates)", options="Yes"),
        dict(sym="MZM", name="Micro soybean meal", ex="CBOT", code="MZM", size="10 short tons", quote="$/short ton", tick="$0.20 = $2", usd=10, price="ZM", months="as meal", settle="Cash-settled", options="No"),
        dict(sym="ZL", name="Soybean oil", ex="CBOT", code="07", size="60,000 lb", quote="¢/lb", tick="0.01¢ = $6", usd=600, price="ZL", months="Jan, Mar, May, Jul, Aug, Sep, Oct, Dec", settle="Physical (warehouse receipts)", options="Yes"),
        dict(sym="MZL", name="Micro soybean oil", ex="CBOT", code="MZL", size="6,000 lb", quote="¢/lb", tick="0.02¢ = $1.20", usd=60, price="ZL", months="as oil", settle="Cash-settled", options="No"),
        dict(sym="ZW", name="Chicago SRW wheat", ex="CBOT", code="W", size="5,000 bu", quote="¢/bu", tick="0.25¢ = $12.50", usd=50, price="ZW", months="Mar, May, Jul, Sep, Dec", settle="Physical (shipping certificates)", options="Yes"),
        dict(sym="XW", name="Mini wheat", ex="CBOT", code="YW", size="1,000 bu", quote="¢/bu", tick="0.125¢ = $1.25", usd=10, price="ZW", months="as wheat", settle="Physical", options="No"),
        dict(sym="MZW", name="Micro wheat", ex="CBOT", code="MZW", size="500 bu", quote="¢/bu", tick="0.50¢ = $2.50", usd=5, price="ZW", months="as wheat", settle="Cash-settled", options="No"),
        dict(sym="KE", name="KC HRW wheat", ex="CBOT", code="KW", size="5,000 bu", quote="¢/bu", tick="0.25¢ = $12.50", usd=50, price="KE", months="Mar, May, Jul, Sep, Dec", settle="Physical", options="Yes"),
        dict(sym="MKC", name="Mini KC HRW wheat", ex="CBOT", code="MKC", size="1,000 bu", quote="¢/bu", tick="0.125¢ = $1.25", usd=10, price="KE", months="as KC wheat", settle="Physical", options="No"),
    ],
    "cotton": [
        dict(sym="CT", name="Cotton No. 2", ex="ICE US", code=None, size="50,000 lb", quote="¢/lb", tick="0.01¢ = $5", usd=500, price="CT", months="Mar, May, Jul, Oct, Dec", settle="Physical (certificated cotton at ICE warehouses)", options="Yes", margin_note="ICE margin: see ICE Clear US (risk-based, not published as a flat rate)"),
    ],
    "hogs": [
        dict(sym="HE", name="Lean hogs", ex="CME", code="LN", size="40,000 lb", quote="¢/lb", tick="0.025¢ = $10", usd=400, price="HE", months="Feb, Apr, May, Jun, Jul, Aug, Oct, Dec", settle="Cash-settled to the CME Lean Hog Index", options="Yes"),
        dict(sym="PRK", name="Pork cutout", ex="CME", code="PRK", size="40,000 lb", quote="¢/lb", tick="0.025¢ = $10", usd=400, price=None, months="as lean hogs", settle="Cash-settled to the CME Pork Cutout Index", options="Yes (thin)"),
    ],
    "cattle": [
        dict(sym="LE", name="Live cattle", ex="CME", code="48", size="40,000 lb", quote="¢/lb", tick="0.025¢ = $10", usd=400, price="LE", months="Feb, Apr, Jun, Aug, Oct, Dec", settle="Physical delivery or certificate", options="Yes, incl. weeklies"),
        dict(sym="GF", name="Feeder cattle", ex="CME", code="62", size="50,000 lb", quote="¢/lb", tick="0.025¢ = $12.50", usd=500, price="GF", months="Jan, Mar, Apr, May, Aug, Sep, Oct, Nov", settle="Cash-settled to the CME Feeder Cattle Index", options="Yes"),
    ],
    "dairy": [
        dict(sym="DC", name="Class III milk", ex="CME", code="DA", size="200,000 lb (2,000 cwt)", quote="$/cwt", tick="$0.01 = $20", usd=2000, price="DC", months="24 consecutive months", settle="Cash-settled to USDA Class III price", options="Yes"),
        dict(sym="GDK", name="Class IV milk", ex="CME", code="DK", size="200,000 lb (2,000 cwt)", quote="$/cwt", tick="$0.01 = $20", usd=2000, price="GDK", months="24 consecutive months", settle="Cash-settled to USDA Class IV price", options="Yes"),
        dict(sym="CSC", name="Cash-settled cheese", ex="CME", code="CSC", size="20,000 lb", quote="$/lb", tick="$0.001 = $20", usd=20000, price="CSC", months="24 consecutive months", settle="Cash-settled to USDA monthly cheese price", options="Yes"),
        dict(sym="CB", name="Cash-settled butter", ex="CME", code="CB", size="20,000 lb", quote="¢/lb", tick="0.025¢ = $5", usd=200, price="CB", months="24 consecutive months", settle="Cash-settled to USDA monthly butter price", options="Yes"),
        dict(sym="GNF", name="Nonfat dry milk", ex="CME", code="NF", size="44,000 lb", quote="¢/lb", tick="0.025¢ = $11", usd=440, price="GNF", months="24 consecutive months", settle="Cash-settled to USDA monthly NDM price", options="Yes"),
        dict(sym="DY", name="Dry whey", ex="CME", code="DY", size="44,000 lb", quote="¢/lb", tick="0.025¢ = $11", usd=440, price="DY", months="24 consecutive months", settle="Cash-settled to USDA monthly dry whey price", options="Yes"),
    ],
    "energy": [
        dict(sym="CL", name="WTI crude oil", ex="NYMEX", code="CL", size="1,000 barrels", quote="$/bbl", tick="$0.01 = $10", usd=1000, price="CL", months="Every month, about 10 years out", settle="Physical delivery at Cushing, Oklahoma", options="Yes, incl. weeklies"),
        dict(sym="QM", name="E-mini crude oil", ex="NYMEX", code="QM", size="500 barrels", quote="$/bbl", tick="$0.025 = $12.50", usd=500, price="CL", months="Every month", settle="Cash-settled to CL", options="No"),
        dict(sym="MCL", name="Micro WTI crude oil", ex="NYMEX", code="MCL", size="100 barrels", quote="$/bbl", tick="$0.01 = $1", usd=100, price="CL", months="Every month", settle="Cash-settled to CL", options="Yes"),
        dict(sym="NG", name="Henry Hub natural gas", ex="NYMEX", code="NG", size="10,000 MMBtu", quote="$/MMBtu", tick="$0.001 = $10", usd=10000, price="NG", months="Every month, about 12 years out", settle="Physical delivery at Henry Hub, Louisiana", options="Yes, incl. weeklies"),
        dict(sym="QG", name="E-mini natural gas", ex="NYMEX", code="QG", size="2,500 MMBtu", quote="$/MMBtu", tick="$0.005 = $12.50", usd=2500, price="NG", months="Every month", settle="Cash-settled to NG", options="No"),
        dict(sym="MNG", name="Micro Henry Hub natural gas", ex="NYMEX", code="MNG", size="1,000 MMBtu", quote="$/MMBtu", tick="$0.001 = $1", usd=1000, price="NG", months="Every month", settle="Cash-settled to NG", options="No"),
        dict(sym="HO", name="NY Harbor ULSD (heating oil)", ex="NYMEX", code="HO", size="42,000 gal (1,000 bbl)", quote="$/gal", tick="$0.0001 = $4.20", usd=42000, price="HO", months="Every month", settle="Physical delivery in New York Harbor", options="Yes"),
        dict(sym="MHO", name="Micro NY Harbor ULSD", ex="NYMEX", code="MHO", size="4,200 gal", quote="$/gal", tick="$0.0001 = $0.42", usd=4200, price="HO", months="Every month", settle="Cash-settled to HO", options="No"),
        dict(sym="RB", name="RBOB gasoline", ex="NYMEX", code="RB", size="42,000 gal (1,000 bbl)", quote="$/gal", tick="$0.0001 = $4.20", usd=42000, price="RB", months="Every month", settle="Physical delivery in New York Harbor", options="Yes"),
        dict(sym="MRB", name="Micro RBOB gasoline", ex="NYMEX", code="MRB", size="4,200 gal", quote="$/gal", tick="$0.0001 = $0.42", usd=4200, price="RB", months="Every month", settle="Cash-settled to RB", options="No"),
    ],
}
# quoted unit -> dollars per quoted unit (¢ quotes need /100)
CENTS = {"¢/bu", "¢/lb"}


def front(sym):
    p = ROOT / "data" / "technicals" / f"{sym}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    ser = [x for x in d["series"] if x.get("ticker") == d.get("default")] or d["series"][1:2] or d["series"]
    bars = ser[0]["bars"]
    closes = [b[4] for b in bars[-61:] if b[4]]
    rets = [math.log(b / a) for a, b in zip(closes[:-1], closes[1:]) if a > 0 and b > 0][-20:]
    hv = (sum(r * r for r in rets) / len(rets)) ** 0.5 * math.sqrt(252) if len(rets) > 5 else None
    return {"contract": ser[0].get("label"), "ticker": d.get("default"), "date": bars[-1][0], "last": bars[-1][4], "hv20": hv}


def pick(rows, ticker):
    """Margin row whose period covers the front contract month (ticker like DCX2026); else the first row."""
    if ticker:
        code, yr = ticker[-5], int(ticker[-4:])
        mo = "FGHJKMNQUVXZ".index(code) + 1
        key = yr * 12 + mo
        for r in rows:
            a, _, b = r["period"].partition("-")
            ka = int(a[3:]) * 12 + int(a[:2]); kb = int(b[3:]) * 12 + int(b[:2]) if b else ka
            if ka <= key <= kb:
                return r
        later = [r for r in rows if int(r["period"][3:7]) * 12 + int(r["period"][:2]) >= key]
        if later:
            return later[0]
    return rows[0]


def money(x):
    return None if x is None else int(round(x))


def main():
    mg = json.loads((ROOT / "data" / "specs" / "margins.json").read_text())
    by = {}
    for r in mg["rows"]:
        by.setdefault(r["code"], []).append(r)
    num = lambda s: float(s.replace(",", "").split()[0]) if s and s[0].isdigit() else None
    out = {"generated": date.today().isoformat(), "margins_asof": mg.get("asof"), "groups": {}}
    for g, rows in C.items():
        res = []
        for c in rows:
            px = front(c["price"]) if c.get("price") else None
            r = dict(c); r["of"] = c.get("price")
            if px:
                notional = px["last"] * c["usd"]            # usd = dollars per 1.00 quoted unit (1¢ for cent quotes)
                r.update(front_contract=px["contract"], price=px["last"], price_date=px["date"], notional=money(notional),
                         day_move=money(notional * px["hv20"] / math.sqrt(252)) if px["hv20"] else None, hv20=round(px["hv20"] * 100, 1) if px["hv20"] else None)
            m = by.get(c.get("code") or "", [])
            if m:
                x = pick(m, px["ticker"] if px else None)
                maint = num(x.get("maint")) or max(filter(None, [num(x.get("maint_long")), num(x.get("maint_short"))]), default=None)
                r.update(margin_period=x["period"], maint=money(maint), initial=money(maint * 1.1) if maint else None,
                         margin_long=money(num(x.get("maint_long"))) if x.get("maint_long") else None, margin_short=money(num(x.get("maint_short"))) if x.get("maint_short") else None,
                         margin_all=[{"period": y["period"], "maint": money(num(y.get("maint")) or num(y.get("maint_long")))} for y in m])
                if r.get("notional") and maint:
                    r["margin_pct"] = round(maint / r["notional"] * 100, 1)
                    r["leverage"] = round(r["notional"] / maint, 1)
                if r.get("day_move") and maint:
                    r["days_covered"] = round(maint / r["day_move"], 1)
            if r.get("maint") is None and r.get("day_move"):
                # no published flat rate (ICE): SPAN-style estimate = 99% two-day move (2.33 x sqrt 2 x daily move);
                # on CME contracts this rule lands within about 20% of the exchange number
                r["maint_est"] = money(2.33 * math.sqrt(2) * r["day_move"])
                r["margin_pct"] = round(r["maint_est"] / r["notional"] * 100, 1)
                r["leverage"] = round(r["notional"] / r["maint_est"], 1)
            res.append(r)
        out["groups"][g] = res
    (ROOT / "data" / "specs" / "specs.json").write_text(json.dumps(out, indent=0))
    for g, rows in out["groups"].items():
        for r in rows:
            print(g, r["sym"], r.get("price"), r.get("notional"), r.get("maint"), r.get("margin_pct"), r.get("day_move"))


if __name__ == "__main__":
    main()
