"""Keep a history of weather-model runs for the gas desk: each run's gas-weighted HDD by ensemble (GEFS, ECMWF ENS,
ECMWF AIFS ENS), so the Weather tab can show what the latest run changed against the previous one.
Input: data/energy/wx/hdd_members.json (copied from BMR-Com/natgas data/research). Output: data/energy/wx/runs.json."""
import json
from pathlib import Path
D = Path(__file__).resolve().parent.parent / "data" / "energy" / "wx"
cur = json.loads((D / "hdd_members.json").read_text())
p = D / "runs.json"
runs = json.loads(p.read_text()) if p.exists() else []
models = {}
for name, v in cur.get("ensembles", {}).items():
    models[name] = {k: v[k] for k in ("from", "to", "days", "members", "normal_hdd", "mean", "p10", "p50", "p90", "share_warm30", "share_cold30")}
    models[name]["daily"] = v["daily_mean"]; models[name]["normal"] = v["daily_normal"]
if models and not any(r["generated"] == cur["generated"] for r in runs):
    # an ensemble whose daily values did not change is the same model run served again
    last = runs[-1] if runs else None
    for name, m in models.items():
        m["new_run"] = not (last and name in last["models"] and last["models"][name]["daily"] == m["daily"])
    runs.append({"generated": cur["generated"], "models": models})
runs = runs[-60:]
p.write_text(json.dumps(runs, separators=(",", ":")))
print("runs kept", len(runs), "latest", runs[-1]["generated"] if runs else None)
