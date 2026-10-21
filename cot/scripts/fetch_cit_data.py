#!/usr/bin/env python3
"""
fetch_cit_data.py — CFTC Supplemental report (Commitments of Index Traders, CIT).

The CFTC publishes index-trader positions for 13 agricultural markets only
(futures + options combined, from January 2006). Index traders are the
long-only passive allocators (BCOM / S&P GSCI trackers, pension and
sovereign commodity mandates). Their positions move in three ways:
  1. annual reweights (January, roughly the 6th–10th business day),
  2. asset-allocation flows into or out of the commodity complex as a whole,
  3. slow drift with price (fixed notional means contracts fall as price rises).

Output:
  data/cit_master.csv — one row per market per week:
    index traders (CIT) long/short/net, traders, % of OI, and the rest of the
    report split ex-CIT (non-commercial, commercial, non-reportable).

Run:  python scripts/fetch_cit_data.py            (incremental, 2-week overlap)
      FULL_REBUILD=true python scripts/fetch_cit_data.py
"""
import os
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "cit_master.csv"
ENDPOINT = "https://publicreporting.cftc.gov/resource/4zgm-a668.json"
API_LIMIT = 10000
DELAY = 1.2

# Names match bcom_cot_master.csv so the two files join on (date, commodity).
CIT_MARKETS = {
    "Corn":          {"ticker": "C",  "sector": "Grains",    "code": "002602"},
    "Soybeans":      {"ticker": "S",  "sector": "Grains",    "code": "005602"},
    "Soybean Meal":  {"ticker": "SM", "sector": "Grains",    "code": "026603"},
    "Soybean Oil":   {"ticker": "BO", "sector": "Grains",    "code": "007601"},
    "Wheat SRW":     {"ticker": "W",  "sector": "Grains",    "code": "001602"},
    "HRW Wheat":     {"ticker": "KW", "sector": "Grains",    "code": "001612"},
    "Cotton":        {"ticker": "CT", "sector": "Softs",     "code": "033661"},
    "Sugar":         {"ticker": "SB", "sector": "Softs",     "code": "080732"},
    "Coffee":        {"ticker": "KC", "sector": "Softs",     "code": "083731"},
    "Cocoa":         {"ticker": "CC", "sector": "Softs",     "code": "073732"},
    "Live Cattle":   {"ticker": "LC", "sector": "Livestock", "code": "057642"},
    "Lean Hogs":     {"ticker": "LH", "sector": "Livestock", "code": "054642"},
    "Feeder Cattle": {"ticker": "FC", "sector": "Livestock", "code": "061641"},
}

# Socrata field names (lower-case; note the CFTC's own "postions" typo)
F = {
    "oi": "open_interest_all",
    "cit_l": "cit_positions_long_all", "cit_s": "cit_positions_short_all",
    "cit_tl": "traders_cit_long_all", "cit_ts": "traders_cit_short_all",
    "nc_l": "ncomm_postions_long_all_nocit", "nc_s": "ncomm_postions_short_all_nocit",
    "nc_sp": "ncomm_postions_spread_all_nocit",
    "nc_tl": "traders_noncomm_long_all_nocit", "nc_ts": "traders_noncomm_short_all_nocit",
    "cm_l": "comm_positions_long_all_nocit", "cm_s": "comm_positions_short_all_nocit",
    "cm_tl": "traders_comm_long_all_nocit", "cm_ts": "traders_comm_short_all_nocit",
    "nr_l": "nonrept_positions_long_all", "nr_s": "nonrept_positions_short_all",
}


def si(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def get(code, since):
    url = (f"{ENDPOINT}?$where=cftc_contract_market_code='{code}' AND "
           f"report_date_as_yyyy_mm_dd >= '{since}'"
           f"&$order=report_date_as_yyyy_mm_dd ASC&$limit={API_LIMIT}")
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            print(f"    retry {attempt + 1}: {e}")
            time.sleep(3 * (attempt + 1))
    return []


def rows_for(name, meta, raw):
    out = []
    for rec in raw:
        rec = {k.lower(): v for k, v in rec.items()}
        d = (rec.get("report_date_as_yyyy_mm_dd") or "")[:10]
        if not d:
            continue
        v = {k: si(rec.get(f)) for k, f in F.items()}
        oi = v["oi"]
        pct = (lambda x: round(x / oi * 100, 3) if oi > 0 else 0.0)
        out.append({
            "date": d, "commodity": name, "ticker": meta["ticker"], "sector": meta["sector"],
            "open_interest": oi,
            "cit_long": v["cit_l"], "cit_short": v["cit_s"], "cit_net": v["cit_l"] - v["cit_s"],
            "cit_traders_long": v["cit_tl"], "cit_traders_short": v["cit_ts"],
            "cit_long_pct_oi": pct(v["cit_l"]), "cit_net_pct_oi": pct(v["cit_l"] - v["cit_s"]),
            "cit_per_trader_l": round(v["cit_l"] / v["cit_tl"], 1) if v["cit_tl"] else 0.0,
            "noncomm_long": v["nc_l"], "noncomm_short": v["nc_s"], "noncomm_spread": v["nc_sp"],
            "noncomm_net": v["nc_l"] - v["nc_s"],
            "noncomm_traders_long": v["nc_tl"], "noncomm_traders_short": v["nc_ts"],
            "comm_long": v["cm_l"], "comm_short": v["cm_s"], "comm_net": v["cm_l"] - v["cm_s"],
            "comm_traders_long": v["cm_tl"], "comm_traders_short": v["cm_ts"],
            "nonrept_long": v["nr_l"], "nonrept_short": v["nr_s"],
        })
    return out


def main():
    full = os.getenv("FULL_REBUILD", "false").lower() == "true" or not CSV.exists()
    old = None if full else pd.read_csv(CSV, dtype={"date": str})
    new = []
    for i, (name, meta) in enumerate(CIT_MARKETS.items(), 1):
        since = "2006-01-01"
        if old is not None and (old.commodity == name).any():
            last = old.loc[old.commodity == name, "date"].max()
            since = (pd.to_datetime(last) - timedelta(days=14)).strftime("%Y-%m-%d")
        raw = get(meta["code"], since)
        rows = rows_for(name, meta, raw)
        print(f"  [{i:2d}/{len(CIT_MARKETS)}] {name:14s} since {since}: {len(rows)} rows")
        new.extend(rows)
        time.sleep(DELAY)
    if not new and old is None:
        raise SystemExit("No CIT data fetched.")
    df = pd.DataFrame(new)
    if old is not None:
        df = pd.concat([old, df], ignore_index=True)
    df = (df.drop_duplicates(["date", "commodity"], keep="last")
            .sort_values(["commodity", "date"]).reset_index(drop=True))
    # weekly flows (contracts and points of OI) per market
    g = df.groupby("commodity", sort=False)
    df["cit_net_chg_1w"] = g["cit_net"].diff()
    df["cit_net_chg_4w"] = g["cit_net"].diff(4)
    df["cit_net_pct_oi_chg_4w"] = g["cit_net_pct_oi"].diff(4).round(3)
    # January index reweight window (BCOM/GSCI rebalance in the first half of January)
    dt = pd.to_datetime(df["date"])
    df["rebalance_window"] = (dt.dt.month == 1) & (dt.dt.day <= 20)
    CSV.parent.mkdir(exist_ok=True)
    df.to_csv(CSV, index=False)
    print(f"Saved {CSV.relative_to(ROOT)}: {len(df)} rows, {df.commodity.nunique()} markets, "
          f"{df.date.min()} to {df.date.max()}")


if __name__ == "__main__":
    main()
