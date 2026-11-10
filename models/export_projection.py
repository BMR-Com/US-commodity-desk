"""The desk's one US export projection: `proj.central` in data/grains/derived/esr_brief.json (grains_esr_brief.py, the
middle of its sales-flow views, in USDA units). Every place that presents "the export projection" (text, votes,
trade-idea reasons, the WASDE preview) reads it here. The older "commitments / usual share of final" number is the
commitment pace: grains_sales.py keeps it because its backtest (direction of USDA's next export revision) is defined on
it, and it is shown only as pace. Callers fall back to their own pace number when the brief is missing.
"""
import json
from pathlib import Path

BRIEF = Path(__file__).resolve().parent.parent / "data" / "grains" / "derived" / "esr_brief.json"


def desk_projection(key):
    """{value, usda, unit, week, my, src} for an esr_brief key (corn, soybeans, meal, oil, wheat, kc, cotton) or None."""
    try:
        b = next((c for c in json.loads(BRIEF.read_text()).get("commodities", []) if c.get("key") == key), None)
    except Exception:
        return None
    if not b:
        return None
    v = (b.get("proj") or {}).get("central") or b.get("implied")
    if not v:
        return None
    return {"value": float(v), "usda": b.get("target"), "unit": b.get("w_unit"), "week": b.get("week"), "my": b.get("my"),
            "src": "desk"}
