#!/usr/bin/env python3
"""
fetch_cot_data.py — BCOM COT Data Fetcher & Analyzer
======================================================
Downloads CFTC Disaggregated COT data for all 23 BCOM constituent commodities
from 2006 to present (Futures & Options Combined endpoint).

Outputs:
  data/bcom_cot_master.csv   — Full history, all commodities, all categories,
                                with derived metrics and percentile columns.
  data/cotton_cot.csv        — Cotton-only extract of the master (all crop_types,
                                all columns). Lightweight (~5 MB vs 60+ MB) for client-side
                                dashboards that only need cotton.
  data/latest_summary.json   — Latest-week snapshot with pre-calculated
                                percentiles over 1yr/3yr/5yr/10yr/full
                                history, historical extremes with dates.
"""

import json, os, sys, time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from dateutil import tz

sys.path.insert(0, str(Path(__file__).resolve().parent))
import web_data  # noqa: E402

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
ROOT_DIR    = SCRIPT_DIR.parent
DATA_DIR    = ROOT_DIR / "data"
CSV_PATH    = DATA_DIR / "bcom_cot_master.csv"
COTTON_PATH = DATA_DIR / "cotton_cot.csv"
JSON_PATH   = DATA_DIR / "latest_summary.json"
DATA_DIR.mkdir(exist_ok=True)

# ── CFTC Socrata API ───────────────────────────────────────────────────────
ENDPOINT = "https://publicreporting.cftc.gov/resource/kh3c-gbw2.json"
API_LIMIT = 10000
REQUEST_DELAY = 1.2

# ── Timezone ────────────────────────────────────────────────────────────────
ET = tz.gettz('US/Eastern')

# ── Check if manual run (skip strict validation) ───────────────────────────
SKIP_FRESH_CHECK = os.getenv('SKIP_FRESH_CHECK', 'false').lower() == 'true'

# ── BCOM 2026 Constituents ─────────────────────────────────────────────────
# "code" is the CFTC contract market code. Market *names* change over time
# (e.g. WTI, Nat Gas and Brent were renamed in Feb 2022, which silently froze
# those series); codes are stable across renames, so we query by code and only
# fall back to the name if a code returns nothing.
# Not reported by the CFTC (LME / ICE Europe venues): Zinc, Nickel, Lead and
# Low Sulphur Gas Oil — they are listed in NOT_REPORTED for the UI.
BCOM = {
    "Brent Crude Oil":    {"ticker":"CO", "sector":"Energy",           "code":"06765T", "cftc":"BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE",          "crop":False},
    "Natural Gas":        {"ticker":"NG", "sector":"Energy",           "code":"023651", "cftc":"NAT GAS NYME - NEW YORK MERCANTILE EXCHANGE",            "crop":False},
    "WTI Crude Oil":      {"ticker":"CL", "sector":"Energy",           "code":"067651", "cftc":"WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",            "crop":False},
    "ULS Diesel":         {"ticker":"HO", "sector":"Energy",           "code":"022651", "cftc":"NY HARBOR ULSD - NEW YORK MERCANTILE EXCHANGE",          "crop":False},
    "RBOB Gasoline":      {"ticker":"XB", "sector":"Energy",           "code":"111659", "cftc":"GASOLINE RBOB - NEW YORK MERCANTILE EXCHANGE",           "crop":False},
    "Corn":               {"ticker":"C",  "sector":"Grains",           "code":"002602", "cftc":"CORN - CHICAGO BOARD OF TRADE",                          "crop":True},
    "Soybeans":           {"ticker":"S",  "sector":"Grains",           "code":"005602", "cftc":"SOYBEANS - CHICAGO BOARD OF TRADE",                      "crop":True},
    "Soybean Meal":       {"ticker":"SM", "sector":"Grains",           "code":"026603", "cftc":"SOYBEAN MEAL - CHICAGO BOARD OF TRADE",                  "crop":True},
    "Soybean Oil":        {"ticker":"BO", "sector":"Grains",           "code":"007601", "cftc":"SOYBEAN OIL - CHICAGO BOARD OF TRADE",                   "crop":True},
    "Wheat SRW":          {"ticker":"W",  "sector":"Grains",           "code":"001602", "cftc":"WHEAT-SRW - CHICAGO BOARD OF TRADE",                     "crop":True},
    "HRW Wheat":          {"ticker":"KW", "sector":"Grains",           "code":"001612", "cftc":"WHEAT-HRW - CHICAGO BOARD OF TRADE",                     "crop":True},
    "Copper":             {"ticker":"HG", "sector":"Industrial Metals","code":"085692", "cftc":"COPPER- #1 - COMMODITY EXCHANGE INC.",                   "crop":False},
    # COMEX outright Aluminum (191691) stopped being reported in Jun 2026; use the
    # US Midwest Premium contract, which the CFTC still publishes weekly.
    "Aluminum MWP":       {"ticker":"ALI","sector":"Industrial Metals","code":"191693", "cftc":"ALUMINUM MWP - COMMODITY EXCHANGE INC.",                 "crop":False},
    "Gold":               {"ticker":"GC", "sector":"Precious Metals",  "code":"088691", "cftc":"GOLD - COMMODITY EXCHANGE INC.",                         "crop":False},
    "Silver":             {"ticker":"SI", "sector":"Precious Metals",  "code":"084691", "cftc":"SILVER - COMMODITY EXCHANGE INC.",                       "crop":False},
    "Sugar":              {"ticker":"SB", "sector":"Softs",            "code":"080732", "cftc":"SUGAR NO. 11 - ICE FUTURES U.S.",                        "crop":False},
    "Coffee":             {"ticker":"KC", "sector":"Softs",            "code":"083731", "cftc":"COFFEE C - ICE FUTURES U.S.",                            "crop":True},
    "Cocoa":              {"ticker":"CC", "sector":"Softs",            "code":"073732", "cftc":"COCOA - ICE FUTURES U.S.",                               "crop":True},
    "Cotton":             {"ticker":"CT", "sector":"Softs",            "code":"033661", "cftc":"COTTON NO. 2 - ICE FUTURES U.S.",                        "crop":True},
    "Live Cattle":        {"ticker":"LC", "sector":"Livestock",        "code":"057642", "cftc":"LIVE CATTLE - CHICAGO MERCANTILE EXCHANGE",              "crop":False},
    "Lean Hogs":          {"ticker":"LH", "sector":"Livestock",        "code":"054642", "cftc":"LEAN HOGS - CHICAGO MERCANTILE EXCHANGE",                "crop":True},
}
NOT_REPORTED = ["Zinc", "Nickel", "Lead", "Low Sulphur Gas Oil"]

TRADER_CATS = ["managed_money", "swap_dealers", "prod_merc", "other_rept"]

# ── EXACT Socrata field names ───────────────────────────────────────────────
FIELDS = {
    "all": {
        "oi":    "open_interest_all",
        "mm_l":  "m_money_positions_long_all",
        "mm_s":  "m_money_positions_short_all",
        "mm_sp": "m_money_positions_spread",
        "mm_tl": "traders_m_money_long_all",
        "mm_ts": "traders_m_money_short_all",
        "sd_l":  "swap_positions_long_all",
        "sd_s":  "swap__positions_short_all",
        "sd_sp": "swap__positions_spread_all",
        "sd_tl": "traders_swap_long_all",
        "sd_ts": "traders_swap_short_all",
        "pm_l":  "prod_merc_positions_long",
        "pm_s":  "prod_merc_positions_short",
        "pm_tl": "traders_prod_merc_long_all",
        "pm_ts": "traders_prod_merc_short_all",
        "or_l":  "other_rept_positions_long",
        "or_s":  "other_rept_positions_short",
        "or_sp": "other_rept_positions_spread",
        "or_tl": "traders_other_rept_long_all",
        "or_ts": "traders_other_rept_short",
    },
    "old": {
        "oi":    "open_interest_old",
        "mm_l":  "m_money_positions_long_old",
        "mm_s":  "m_money_positions_short_old",
        "mm_sp": "m_money_positions_spread_1",
        "mm_tl": "traders_m_money_long_old",
        "mm_ts": "traders_m_money_short_old",
        "sd_l":  "swap_positions_long_old",
        "sd_s":  "swap__positions_short_old",
        "sd_sp": "swap__positions_spread_old",
        "sd_tl": "traders_swap_long_old",
        "sd_ts": "traders_swap_short_old",
        "pm_l":  "prod_merc_positions_long_1",
        "pm_s":  "prod_merc_positions_short_1",
        "pm_tl": "traders_prod_merc_long_old",
        "pm_ts": "traders_prod_merc_short_old",
        "or_l":  "other_rept_positions_long_1",
        "or_s":  "other_rept_positions_short_1",
        "or_sp": "other_rept_positions_spread_1",
        "or_tl": "traders_other_rept_long_old",
        "or_ts": "traders_other_rept_short_1",
    },
    "other": {
        "oi":    "open_interest_other",
        "mm_l":  "m_money_positions_long_other",
        "mm_s":  "m_money_positions_short_other",
        "mm_sp": "m_money_positions_spread_2",
        "mm_tl": "traders_m_money_long_other",
        "mm_ts": "traders_m_money_short_other",
        "sd_l":  "swap_positions_long_other",
        "sd_s":  "swap__positions_short_other",
        "sd_sp": "swap__positions_spread_other",
        "sd_tl": "traders_swap_long_other",
        "sd_ts": "traders_swap_short_other",
        "pm_l":  "prod_merc_positions_long_2",
        "pm_s":  "prod_merc_positions_short_2",
        "pm_tl": "traders_prod_merc_long_other",
        "pm_ts": "traders_prod_merc_short_other",
        "or_l":  "other_rept_positions_long_2",
        "or_s":  "other_rept_positions_short_2",
        "or_sp": "other_rept_positions_spread_2",
        "or_tl": "traders_other_rept_long_other",
        "or_ts": "traders_other_rept_short_2",
    }
}

CAT_PREFIX = {
    "managed_money": "mm",
    "swap_dealers":  "sd",
    "prod_merc":     "pm",
    "other_rept":    "or",
}

# ── Helpers ────────────────────────────────────────────────────────────────
def pct_of_score(series, score):
    """Percentile rank of score within series (0-100)."""
    s = pd.Series(series).dropna()
    if len(s) == 0:
        return 50.0
    below  = (s < score).sum()
    equal  = (s == score).sum()
    return round(((below + 0.5 * equal) / len(s)) * 100, 1)

def si(val):
    """Safe int parse."""
    try:
        v = int(val)
        return 0 if pd.isna(v) else v
    except (TypeError, ValueError):
        return 0

def get_expected_report_date():
    """Calculate the expected Tuesday report date for current week."""
    today = datetime.now(ET)
    days_since_tuesday = (today.weekday() - 1) % 7
    tuesday = today - timedelta(days=days_since_tuesday)
    return tuesday.strftime("%Y-%m-%d")

def validate_fresh_data(df, expected_date=None):
    """Validate that fetched data contains the expected report date."""
    if df.empty:
        return False, None, "No data fetched"
    
    latest_date = df["date"].max()
    
    if expected_date:
        if expected_date not in df["date"].values:
            latest_dt = pd.to_datetime(latest_date)
            expected_dt = pd.to_datetime(expected_date)
            days_diff = (expected_dt - latest_dt).days
            
            if days_diff > 7:
                return False, latest_date, f"Data stale: latest is {latest_date}, expected {expected_date}"
            else:
                return True, latest_date, f"Using data from {latest_date} (expected {expected_date}, diff: {days_diff} days)"
    
    return True, latest_date, f"Latest data: {latest_date}"

# ── Fetch from CFTC API ────────────────────────────────────────────────────
def _get(where):
    url = (f"{ENDPOINT}?$where={where}"
           f"&$order=report_date_as_yyyy_mm_dd ASC&$limit={API_LIMIT}")
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  (attempt {attempt+1}) error: {e}", end=" ")
            time.sleep(3 * (attempt + 1))
    return []


def fetch_commodity(meta, since_date="2006-01-01"):
    """Fetch all records for a commodity since a date — by contract code
    (stable across CFTC renames), falling back to the market name."""
    date_clause = f" AND report_date_as_yyyy_mm_dd >= '{since_date}'"
    if meta.get("code"):
        data = _get(f"cftc_contract_market_code='{meta['code']}'" + date_clause)
        if data:
            return data
    enc = meta["cftc"].replace("'", "''")
    return _get(f"market_and_exchange_names='{enc}'" + date_clause)

# ── Process raw API records into flat rows ─────────────────────────────────
def process_records(raw, commodity_name, meta, crop_type="all"):
    """Convert list of raw API dicts into a list of flat row dicts."""
    fmap = FIELDS[crop_type]
    rows = []
    for rec in raw:
        date_str = rec.get("report_date_as_yyyy_mm_dd", "")[:10]
        if not date_str:
            continue

        oi = si(rec.get(fmap["oi"]))

        row = {
            "date":           date_str,
            "commodity":      commodity_name,
            "ticker":         meta["ticker"],
            "sector":         meta["sector"],
            "crop_type":      crop_type,
            "is_crop":        meta["crop"],
            "open_interest":  oi,
        }

        for cat, pfx in CAT_PREFIX.items():
            L  = si(rec.get(fmap[f"{pfx}_l"]))
            S  = si(rec.get(fmap[f"{pfx}_s"]))
            Sp = si(rec.get(fmap.get(f"{pfx}_sp",""))) if fmap.get(f"{pfx}_sp") else 0
            TL = si(rec.get(fmap[f"{pfx}_tl"]))
            TS = si(rec.get(fmap[f"{pfx}_ts"]))

            net    = L - S
            lp     = (L / oi * 100) if oi > 0 else 0.0
            sp_pct = (S / oi * 100) if oi > 0 else 0.0
            np_pct = lp - sp_pct
            ppt_l  = (L / TL) if TL > 0 else 0.0
            ppt_s  = (S / TS) if TS > 0 else 0.0

            prefix = f"{cat}"
            row[f"{prefix}_long"]          = L
            row[f"{prefix}_short"]         = S
            row[f"{prefix}_spread"]        = Sp
            row[f"{prefix}_net"]           = net
            row[f"{prefix}_traders_long"]  = TL
            row[f"{prefix}_traders_short"] = TS
            row[f"{prefix}_long_pct_oi"]   = round(lp, 3)
            row[f"{prefix}_short_pct_oi"]  = round(sp_pct, 3)
            row[f"{prefix}_net_pct_oi"]    = round(np_pct, 3)
            row[f"{prefix}_per_trader_l"]  = round(ppt_l, 1)
            row[f"{prefix}_per_trader_s"]  = round(ppt_s, 1)

        rows.append(row)
    return rows

# ── Percentile calculation ─────────────────────────────────────────────────
WINDOWS = {
    "1yr":  52,
    "3yr":  156,
    "5yr":  260,
    "10yr": 520,
    "full": None,
}

PCTILE_COLS = [
    "managed_money_net",      "managed_money_long",     "managed_money_short",
    "managed_money_net_pct_oi","managed_money_long_pct_oi","managed_money_short_pct_oi",
    "managed_money_per_trader_l","managed_money_per_trader_s",
    "swap_dealers_net",       "swap_dealers_long",      "swap_dealers_short",
    "swap_dealers_net_pct_oi",
    "prod_merc_net",          "prod_merc_long",         "prod_merc_short",
    "prod_merc_net_pct_oi",
    "other_rept_net",         "other_rept_long",        "other_rept_short",
    "other_rept_net_pct_oi",
    "open_interest",
]

def _rolling_midrank(x, windows):
    """Percentile (mid-rank) of each x[i] within its trailing window x[i-w+1..i].
    Vectorised with an n×n comparison — n is ~1,000 weekly rows per series."""
    n = len(x)
    valid = ~np.isnan(x)
    xi = x[:, None]; xj = x[None, :]
    less = (xj < xi) & valid[None, :]
    eq = (xj == xi) & valid[None, :]
    idx = np.arange(n)
    out = {}
    for name, w in windows.items():
        m = idx[None, :] <= idx[:, None]
        if w:
            m &= idx[None, :] > (idx[:, None] - w)
        cnt = (m & valid[None, :]).sum(1)
        r = ((less & m).sum(1) + 0.5 * (eq & m).sum(1)) / np.where(cnt > 0, cnt, 1) * 100
        r = np.round(r, 1)
        r[~valid | (cnt == 0)] = np.nan
        out[name] = r
    return out


def add_percentiles(df):
    """Recompute percentile columns over each series' FULL history.

    The previous incremental version ranked new rows only against the other
    new rows (a ~3-row "history"), which produced nonsense like Cotton net
    long at the 12.5th percentile when it was actually ~82nd. Done vectorised,
    the full recompute takes seconds, so we simply always do it."""
    print("  Calculating percentiles (full history)...")
    df = df[[c for c in df.columns if not c.startswith("pctile_")]].copy()
    df = df.sort_values(["commodity", "crop_type", "date"]).reset_index(drop=True)
    new_cols = {}
    for (comm, ct), idx in df.groupby(["commodity", "crop_type"]).groups.items():
        g = df.loc[idx]
        for col in PCTILE_COLS:
            if col not in g.columns:
                continue
            res = _rolling_midrank(pd.to_numeric(g[col], errors="coerce").to_numpy(float), WINDOWS)
            for win_name, vals in res.items():
                key = f"pctile_{col}_{win_name}"
                new_cols.setdefault(key, pd.Series(np.nan, index=df.index))
                new_cols[key].loc[idx] = vals
    return pd.concat([df, pd.DataFrame(new_cols)], axis=1)

# ── Historical extremes ────────────────────────────────────────────────────
def extremes(series, dates, windows=(260, 520)):
    """Return min/max values and their dates for different windows."""
    result = {}
    for w in windows:
        tag = f"{w//52}yr"
        s = series.iloc[-w:] if len(series) > w else series
        d = dates.iloc[-w:] if len(dates) > w else dates
        if len(s) == 0:
            continue
        mn_idx = s.idxmin(); mx_idx = s.idxmax()
        result[f"{tag}_min"] = int(s[mn_idx])
        result[f"{tag}_min_date"] = str(d[mn_idx])[:10]
        result[f"{tag}_max"] = int(s[mx_idx])
        result[f"{tag}_max_date"] = str(d[mx_idx])[:10]
    mn_idx = series.idxmin(); mx_idx = series.idxmax()
    result["full_min"] = int(series[mn_idx])
    result["full_min_date"] = str(dates[mn_idx])[:10]
    result["full_max"] = int(series[mx_idx])
    result["full_max_date"] = str(dates[mx_idx])[:10]
    return result

# ── Build summary JSON ─────────────────────────────────────────────────────
def build_summary(df):
    """Build compact summary dict."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    latest_date = df["date"].max()

    summary = {
        "report_date":   latest_date,
        "generated":     now,
        "data_from":     df["date"].min(),
        "total_records": len(df),
        "description":   "BCOM COT Data — CFTC Disaggregated Futures & Options Combined.",
        "commodities": []
    }

    for comm_name, meta in BCOM.items():
        cd = df[df["commodity"] == comm_name].sort_values("date")
        if cd.empty:
            continue

        crop_types = ["all", "old", "other"] if meta["crop"] else ["all"]
        comm_entry = {
            "name":    comm_name,
            "ticker":  meta["ticker"],
            "sector":  meta["sector"],
            "is_crop": meta["crop"],
            "variants": []
        }

        for ct in crop_types:
            ctd = cd[cd["crop_type"] == ct].sort_values("date")
            if ctd.empty:
                continue

            latest = ctd.iloc[-1]
            prev   = ctd.iloc[-2] if len(ctd) > 1 else latest

            variant = {
                "crop_type":    ct,
                "date":         str(latest["date"])[:10],
                "open_interest": int(latest.get("open_interest", 0)),
                "categories":   {}
            }

            for cat in TRADER_CATS:
                net   = int(latest.get(f"{cat}_net", 0))
                lng   = int(latest.get(f"{cat}_long", 0))
                shrt  = int(latest.get(f"{cat}_short", 0))
                sprd  = int(latest.get(f"{cat}_spread", 0))
                pnet  = float(latest.get(f"{cat}_net_pct_oi", 0))
                plng  = float(latest.get(f"{cat}_long_pct_oi", 0))
                pshrt = float(latest.get(f"{cat}_short_pct_oi", 0))
                tl    = int(latest.get(f"{cat}_traders_long", 0))
                ts    = int(latest.get(f"{cat}_traders_short", 0))
                ptl   = float(latest.get(f"{cat}_per_trader_l", 0))
                pts   = float(latest.get(f"{cat}_per_trader_s", 0))

                chg_net  = net  - int(prev.get(f"{cat}_net", net))
                chg_long = lng  - int(prev.get(f"{cat}_long", lng))
                chg_shrt = shrt - int(prev.get(f"{cat}_short", shrt))

                def gp(col, win="full"):
                    return float(latest.get(f"pctile_{col}_{win}", -1))

                pctiles = {
                    "net_full":      gp(f"{cat}_net"),
                    "net_1yr":       gp(f"{cat}_net","1yr"),
                    "net_3yr":       gp(f"{cat}_net","3yr"),
                    "net_5yr":       gp(f"{cat}_net","5yr"),
                    "net_10yr":      gp(f"{cat}_net","10yr"),
                    "long_full":     gp(f"{cat}_long"),
                    "long_10yr":     gp(f"{cat}_long","10yr"),
                    "short_full":    gp(f"{cat}_short"),
                    "short_10yr":    gp(f"{cat}_short","10yr"),
                    "net_pctoi_full":gp(f"{cat}_net_pct_oi"),
                    "net_pctoi_10yr":gp(f"{cat}_net_pct_oi","10yr"),
                }

                net_series  = ctd[f"{cat}_net"].reset_index(drop=True)
                lng_series  = ctd[f"{cat}_long"].reset_index(drop=True)
                shrt_series = ctd[f"{cat}_short"].reset_index(drop=True)
                date_series = ctd["date"].reset_index(drop=True)

                hist = {
                    "net":   extremes(net_series,  date_series),
                    "long":  extremes(lng_series,  date_series),
                    "short": extremes(shrt_series, date_series),
                }

                variant["categories"][cat] = {
                    "net":              net,
                    "long":             lng,
                    "short":            shrt,
                    "spread":           sprd,
                    "net_pct_oi":       round(pnet, 2),
                    "long_pct_oi":      round(plng, 2),
                    "short_pct_oi":     round(pshrt, 2),
                    "traders_long":     tl,
                    "traders_short":    ts,
                    "per_trader_long":  round(ptl, 1),
                    "per_trader_short": round(pts, 1),
                    "wk_chg_net":       chg_net,
                    "wk_chg_long":      chg_long,
                    "wk_chg_short":     chg_shrt,
                    "pctiles":          pctiles,
                    "historical":       hist,
                }

            comm_entry["variants"].append(variant)
        summary["commodities"].append(comm_entry)

    return summary


# ── Main ───────────────────────────────────────────────────────────────────
def save_cotton_extract(df: "pd.DataFrame") -> None:
    """Write the cotton-only extract of the master dataframe.

    Keeps every column and every crop_type row so downstream dashboards can use
    it as a drop-in replacement for the 60+ MB master when they only need cotton.
    """
    cotton = df[df["commodity"] == "Cotton"]
    if cotton.empty:
        print("WARNING: no Cotton rows found - cotton_cot.csv not written")
        return
    cotton = cotton.sort_values(["crop_type", "date"]).reset_index(drop=True)
    cotton.to_csv(COTTON_PATH, index=False)
    sz = COTTON_PATH.stat().st_size / 1024
    print(f"Saved: {COTTON_PATH.name} ({sz:.1f} KB, {len(cotton):,} rows)")


def main():
    print("=" * 65)
    print("BCOM COT Data Fetcher")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 65)

    old_df = None
    last_by_comm = {}
    if CSV_PATH.exists():
        old_df = pd.read_csv(CSV_PATH, low_memory=False)
        old_df = old_df[[c for c in old_df.columns if not c.startswith("pctile_")]]
        last_by_comm = (old_df[old_df["crop_type"] == "all"]
                        .groupby("commodity")["date"].max().to_dict())
        print(f"Existing CSV: {len(old_df):,} rows, latest {old_df['date'].max()}")

    # Per-commodity incremental window: 2-week overlap from that commodity's
    # own last date, or full history for markets we have never fetched / that
    # froze (e.g. after a CFTC rename). Self-healing backfill.
    all_rows, fetched = [], {}
    for i, (comm_name, meta) in enumerate(BCOM.items(), 1):
        last = last_by_comm.get(comm_name)
        since = ((pd.to_datetime(last) - timedelta(days=14)).strftime("%Y-%m-%d")
                 if last else "2006-01-01")
        print(f"  [{i:2d}/{len(BCOM)}] {comm_name:20s} since {since} ...", end=" ", flush=True)
        raw = fetch_commodity(meta, since_date=since)
        if not raw:
            print("no data")
            time.sleep(REQUEST_DELAY)
            continue
        rows = process_records(raw, comm_name, meta, crop_type="all")
        if meta["crop"]:
            for ct in ["old", "other"]:
                if FIELDS[ct]["mm_l"] in raw[-1]:
                    rows += process_records(raw, comm_name, meta, crop_type=ct)
        all_rows.extend(rows)
        fetched[comm_name] = min(r["date"] for r in rows)
        print(f"{len(raw)} records, latest {raw[-1].get('report_date_as_yyyy_mm_dd','')[:10]}")
        time.sleep(REQUEST_DELAY)

    if not all_rows and old_df is None:
        print("ERROR: No data fetched and no existing CSV. Exiting.")
        sys.exit(1)

    new_df = pd.DataFrame(all_rows)
    if not new_df.empty:
        new_df["date"] = pd.to_datetime(new_df["date"]).dt.strftime("%Y-%m-%d")

    # Merge: for each refreshed commodity drop old rows from its cutoff onward
    if old_df is not None:
        keep = old_df.copy()
        for comm, cutoff in fetched.items():
            keep = keep[~((keep["commodity"] == comm) & (keep["date"] >= cutoff))]
        df = pd.concat([keep, new_df], ignore_index=True)
    else:
        df = new_df
    meta_cols = ["date", "commodity", "ticker", "sector", "crop_type", "is_crop"]
    for col in df.columns:
        if col not in meta_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.drop_duplicates(["commodity", "crop_type", "date"], keep="last")
    df = df.sort_values(["commodity", "crop_type", "date"]).reset_index(drop=True)

    if not SKIP_FRESH_CHECK:
        is_valid, latest_date, msg = validate_fresh_data(df, get_expected_report_date())
        print(f"\n[Validator] {msg}")
        if not is_valid:
            # Not fatal: a later scheduled retry will pick the report up. We
            # still write any backfilled markets; unchanged files aren't committed.
            print("NOTE: this week's CFTC report isn't out yet — writing what we have.")

    df = add_percentiles(df)
    df.to_csv(CSV_PATH, index=False)
    print(f"Saved: {CSV_PATH.name} ({CSV_PATH.stat().st_size/1024:.0f} KB, {len(df):,} rows)")

    save_cotton_extract(df)

    summary = build_summary(df)
    summary["not_reported"] = NOT_REPORTED
    with open(JSON_PATH, "w") as f:
        json.dump(summary, f, separators=(",", ":"))
    print(f"Saved: {JSON_PATH.name}")

    man = web_data.build(df, BCOM)
    print(f"Saved: data/web/ (manifest, snapshot, {len(man['commodities'])} series files)")
    stale = [c["name"] for c in man["commodities"] if c["stale"]]
    if stale:
        print(f"Stale markets (excluded from cross-sectional views): {stale}")
    print(f"Done. Latest report date: {summary['report_date']}")

if __name__ == "__main__":
    main()
