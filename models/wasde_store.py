"""Local WASDE store: the desk keeps every USDA WASDE report itself and builds the per-commodity JSON files the models
read, so it no longer waits for BMR-Com/wasde-analytics (kept only as a fallback).

Raw store: data/wasde/raw/<WasdeNumber>.csv.gz, one gzipped USDA report CSV each (pipelines/wasde.py writes them;
history was seeded once from wasde-analytics' master file). Built JSONs go to data/wasde/json/ (not committed; rebuilt
in seconds whenever the raw store is newer). JSON format and unit normalisation are copied from
BMR-Com/wasde-analytics/process.py so the models see identical files.

Use: from wasde_store import local_dir  ->  directory with <Commodity>.json, or None if the store is empty.
"""
import json, os, glob
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "wasde" / "raw"
JSON = ROOT / "data" / "wasde" / "json"
# commodities the desk reads (grains/oilseeds/cotton models, dairy balance, the cotton brief's short notes on others)
WANT = {"Corn", "Oilseed, Soybean", "Meal, Soybean", "Oil, Soybean", "Wheat", "Hard Red Winter", "Hard Red Spring", "Soft Red Winter",
        "Wheat, Hard Red Winter", "Wheat, Hard Red Spring", "Wheat, Soft Red Winter", "Wheat, White", "Wheat, Durum", "Cotton",
        "Milk", "Milk, Fat Basis", "Milk, Skim-Soild Basis", "Milk, Class III", "Milk, Class IV", "Cheese", "Butter", "Nonfat Dry Milk",
        "Dry Whey", "Rice", "Sugar", "Sorghum", "Beef", "Pork", "Broiler", "Steers", "Barrows and gilts"}

GRAIN_KEYWORDS = ["wheat","corn","maize","soybean","oilseed","rice","barley",
                  "oats","sorghum","rye","coarse grain","grain"]

MT_TO_BU = {
    "wheat":        36.7437,
    "corn":         39.3683,
    "maize":        39.3683,
    "soybean":      36.7437,
    "oilseed":      36.7437,
    "rice":         45.9296,
    "barley":       45.9296,
    "oats":         68.8944,
    "sorghum":      39.3683,
    "rye":          39.3683,
    "coarse grain": 39.3683,
}

def is_grain(commodity):
    cn = commodity.lower()
    return any(k in cn for k in GRAIN_KEYWORDS)

def get_mt_to_bu(commodity):
    cn = commodity.lower()
    for key, factor in MT_TO_BU.items():
        if key in cn:
            return factor
    return 36.7437

def unit_family(u):
    """Detect the measurement family from unit string."""
    u = u.strip().lower()
    if any(k in u for k in ["bushel"]): return "bushel"
    if any(k in u for k in ["metric ton", " mt", "mt "]): return "mt"
    if "bale" in u: return "bale"
    if "short ton" in u: return "ton"
    if "cwt" in u: return "cwt"
    if "hectare" in u: return "hectare"
    if "acre" in u: return "acre"
    return "other"

def unit_scale(u):
    """Detect numeric scale from unit string."""
    u = u.strip().lower()
    if "million" in u: return 1e6
    if "thousand" in u or "1,000" in u or "1000" in u: return 1e3
    return 1.0

def normalize_series_values(vals, units, commodity):
    """
    Given parallel lists of (value, unit_string) for a single
    (region, attribute, market_year) series sorted by WasdeNumber,
    return a list of (normalized_value, canonical_unit, ok) where
    all values are in the same unit.

    Strategy:
    1. Use unit strings to group by family and scale.
    2. Pick the most-recent unit as canonical.
    3. Convert all others to it.
    4. Run outlier detection: if any value is >50x or <0.02x the
       rolling median, try rescaling by known factors (1000, 0.001,
       MT_TO_BU, 1/MT_TO_BU) and pick the factor that minimizes
       variance in log-space.
    """
    if not vals:
        return []

    n = len(vals)
    # Step 1: determine canonical from most-recent 5 entries
    recent_units = units[max(0,n-5):]
    unit_counts  = {}
    for u in recent_units:
        u = u.strip()
        unit_counts[u] = unit_counts.get(u, 0) + 1
    canonical    = max(unit_counts, key=unit_counts.get) if unit_counts else ""
    canon_family = unit_family(canonical)
    canon_scale  = unit_scale(canonical)

    # Step 2: convert each value to canonical using unit strings
    result = []
    for v, u in zip(vals, units):
        u        = u.strip()
        uf       = unit_family(u)
        us       = unit_scale(u)

        if u.lower() == canonical.lower() or u == "":
            result.append((v, canonical, True))
            continue

        if uf == canon_family:
            # Same family, different scale
            if canon_scale > 0:
                result.append((round(v * us / canon_scale, 4), canonical, True))
            else:
                result.append((v, u, False))
        elif is_grain(commodity) and uf in ("mt","bushel") and canon_family in ("mt","bushel"):
            # Cross-family grain conversion
            mt_bu  = get_mt_to_bu(commodity)
            v_base = v * us   # raw units
            if uf == "mt":
                v_conv = v_base * mt_bu
            else:
                v_conv = v_base / mt_bu
            if canon_scale > 0:
                result.append((round(v_conv / canon_scale, 4), canonical, True))
            else:
                result.append((v, u, False))
        else:
            # Unknown conversion — keep raw, mark as potentially bad
            result.append((v, u, False))

    # Step 3: outlier detection on the normalized values
    # Check for suspicious >20x jumps between consecutive entries
    converted_vals = [r[0] for r in result]
    ok_flags       = [r[2] for r in result]

    # Compute median of all ok values for reference
    ok_vals = [v for v, ok in zip(converted_vals, ok_flags) if ok and v is not None]
    if len(ok_vals) < 2:
        return [(v, u, ok) for (v, u, ok) in result]

    median_val = float(np.median(ok_vals))
    if median_val == 0:
        return result

    # Candidate rescale factors to try for outliers
    mt_bu = get_mt_to_bu(commodity)
    rescale_candidates = [1000.0, 0.001, mt_bu, 1.0/mt_bu,
                          mt_bu/1000.0, 1000.0/mt_bu]

    fixed_result = []
    for i, (v, u, ok) in enumerate(result):
        if v is None or not ok:
            fixed_result.append((v, u, ok))
            continue
        ratio = v / median_val if median_val != 0 else 1.0
        if ratio > 50 or ratio < 0.02:
            # This value is an outlier — try rescaling
            best_factor = 1.0
            best_dist   = abs(np.log(max(ratio, 1e-9)))
            for factor in rescale_candidates:
                new_v   = v * factor
                new_rat = new_v / median_val if median_val != 0 else 1.0
                dist    = abs(np.log(max(new_rat, 1e-9)))
                if dist < best_dist:
                    best_dist   = dist
                    best_factor = factor
            if best_factor != 1.0:
                fixed_result.append((round(v * best_factor, 4), canonical, True))
            else:
                fixed_result.append((v, u, ok))
        else:
            fixed_result.append((v, u, ok))

    return fixed_result

def generate_jsons(df, out_dir):
    print("\nGenerating JSONs...")
    df = df.dropna(subset=["Commodity","Region","Attribute","MarketYear","Value","WasdeNumber"])
    df["WasdeNumber"] = pd.to_numeric(df["WasdeNumber"], errors="coerce")
    df["Value"]       = pd.to_numeric(df["Value"],       errors="coerce")
    df["Unit"]        = df["Unit"].fillna("").astype(str).str.strip()
    df = df.dropna(subset=["WasdeNumber","Value"])


    manifest = []

    for commodity in sorted(df["Commodity"].unique()):
        cdf   = df[df["Commodity"] == commodity].copy()
        grain = is_grain(commodity)

        all_mkt_years = sorted(cdf["MarketYear"].unique().tolist())
        latest_3      = all_mkt_years[-3:] if len(all_mkt_years) >= 3 else all_mkt_years
        if cdf[cdf["MarketYear"].isin(latest_3)]["WasdeNumber"].nunique() < 2:
            print("  SKIP " + commodity + " — insufficient recent data")
            continue

        data       = {}
        unit_display = {}

        for (region, attribute, mkt_year), grp in cdf.groupby(
                ["Region","Attribute","MarketYear"]):

            # ── Filter out early long-range projections ───────────
            try:
                mkt_start_year = int(str(mkt_year).split("/")[0])
                fy = pd.to_numeric(grp["ForecastYear"], errors="coerce")
                grp = grp[fy.fillna(mkt_start_year) >= mkt_start_year]
            except Exception:
                pass

            if grp.empty:
                continue

            # ── Deduplicate by WasdeNumber ────────────────────────
            # The same (region, attribute, mktYear, wasdeNum) can appear
            # under multiple ReportTitles. Keep only one row per WasdeNumber,
            # preferring the row whose ReportTitle best matches the region.
            if "ReportTitle" in grp.columns:
                r_lower = region.lower()
                if "united states" in r_lower or "u.s." in r_lower:
                    pref_kw = "u.s."
                elif "world" in r_lower:
                    pref_kw = "world"
                else:
                    # For other countries use first word of region name
                    pref_kw = r_lower.split(",")[0].split("(")[0].strip()

                grp = grp.copy()
                grp["_pref"] = (
                    grp["ReportTitle"]
                    .fillna("")
                    .str.lower()
                    .str.contains(pref_kw, na=False)
                    .astype(int)
                )
                # Sort: by WasdeNumber asc, then preferred title first
                grp = grp.sort_values(
                    ["WasdeNumber", "_pref"], ascending=[True, False]
                )
                # Keep only ONE row per WasdeNumber (highest preference wins)
                grp = grp.drop_duplicates(subset=["WasdeNumber"], keep="first")
                grp = grp.drop(columns=["_pref"])

            grp = grp.sort_values("WasdeNumber").reset_index(drop=True)

            vals  = grp["Value"].tolist()
            units = grp["Unit"].tolist()

            # Normalize all values in this series to same unit
            normed = normalize_series_values(vals, units, commodity)

            rows = []
            for idx2, (row_idx, row) in enumerate(grp.iterrows()):
                if idx2 < len(normed):
                    norm_val, norm_unit, ok = normed[idx2]
                else:
                    norm_val, norm_unit, ok = float(row["Value"]), str(row["Unit"]), False

                rows.append({
                    "releaseNum":    idx2 + 1,
                    "wasdeNum":      int(row["WasdeNumber"]),
                    "reportDate":    str(row.get("ReportDate", "")),
                    "value":         round(norm_val, 4) if norm_val is not None else None,
                    "forecastYear":  int(row["ForecastYear"]) if pd.notna(row.get("ForecastYear")) else None,
                    "forecastMonth": int(row["ForecastMonth"]) if pd.notna(row.get("ForecastMonth")) else None,
                    "unit":          norm_unit,
                    "unitOk":        ok
                })

                # Track canonical unit for display
                disp_key = region + "||" + attribute
                if disp_key not in unit_display:
                    unit_display[disp_key] = norm_unit

            key = region + "||" + attribute + "||" + mkt_year
            data[key] = rows

        fname = commodity.replace("/","-").replace(" ","_") + ".json"
        out = {
            "commodity":   commodity,
            "isGrain":     grain,
            "regions":     sorted(cdf["Region"].unique().tolist()),
            "attributes":  sorted(cdf["Attribute"].unique().tolist()),
            "marketYears": all_mkt_years,
            "unitMap":     unit_display,
            "data":        data,
            "lastUpdated": datetime.utcnow().strftime("%Y-%m-%d")
        }
        with open(out_dir / fname, "w") as f:
            json.dump(out, f, separators=(",",":"))
        kb = (out_dir / fname).stat().st_size // 1024
        manifest.append({"commodity": commodity, "file": fname,
                         "regions": out["regions"]})

    with open(out_dir / "manifest.json", "w") as f:
        json.dump({"commodities": manifest,
                   "lastUpdated": datetime.utcnow().strftime("%Y-%m-%d")}, f)
    print(str(len(manifest)) + " JSONs written to /data/")



def load_raw():
    files = sorted(RAW.glob("*.csv.gz"))
    if not files:
        return None
    df = pd.concat([pd.read_csv(f, low_memory=False, dtype={"MarketYear": str}) for f in files], ignore_index=True)
    return df.drop_duplicates(subset=["WasdeNumber", "Commodity", "Region", "MarketYear", "Attribute", "ReportTitle"])


def latest_number():
    nums = [int(p.name.split(".")[0]) for p in RAW.glob("*.csv.gz") if p.name.split(".")[0].isdigit()]
    return max(nums) if nums else None


def build(force=False):
    """Rebuild data/wasde/json when the raw store has a report the JSONs do not."""
    n = latest_number()
    if n is None:
        return None
    stamp = JSON / "_built_from.txt"
    if not force and stamp.exists() and stamp.read_text().strip() == str(n):
        return JSON
    df = load_raw()
    df = df[df.Commodity.isin(WANT)]
    JSON.mkdir(parents=True, exist_ok=True)
    generate_jsons(df, JSON)
    stamp.write_text(str(n))
    print(f"wasde_store: built JSONs from {len(df):,} rows, latest WASDE #{n}")
    return JSON


def local_dir():
    """Directory of locally built WASDE JSONs, or None (callers then fall back to wasde-analytics)."""
    if os.getenv("WASDE_DIR"):
        return os.getenv("WASDE_DIR")
    try:
        d = build()
        return str(d) if d else None
    except Exception as e:
        print("wasde_store: local build failed, using wasde-analytics:", str(e)[:200])
        return None


if __name__ == "__main__":
    import sys
    d = build(force="--force" in sys.argv)
    print("built:", d, "latest WASDE #", latest_number())
