#!/usr/bin/env python3
"""Manifest of the desk's back-tests, strategy labs, trade playbooks and contract calendar, for mirroring into another
repository (e.g. a private signal lab). The files themselves are served by GitHub Pages; the manifest lists each one with
its size, checksum and last update so a sync job can copy only what changed. Writes data/lab_export/manifest.json.
"""
import hashlib, json, subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://bmr-com.github.io/US-commodity-desk/"
FILES = {
    "results": {
        "data/dairy/derived/dairy_arb.json": "Dairy weekly-survey -> monthly settlement convergence: nowcasts, live gaps, formula arbitrage",
        "data/dairy/derived/dairy_lab.json": "Dairy forecasting and trading lab: walk-forward models, strategy grid, desk book",
        "data/dairy/derived/dairy_ideas.json": "Dairy strategy ideas with track records, worked examples and today's signals",
        "data/dairy/derived/playbook.json": "Dairy trade playbook: entry, exit, risk, what to track, live positions (nightly)",
        "data/livestock/derived/meats_lab.json": "Hogs and cattle strategy lab: convergence, premium, trend, seasonal, breakout, feeding margin",
        "data/livestock/derived/playbook_hogs.json": "Lean hogs trade playbook (nightly)",
        "data/livestock/derived/playbook_cattle.json": "Live and feeder cattle trade playbook (nightly)",
        "data/livestock/derived/hogs_convergence.json": "Lean hog index forecasting tests vs futures",
        "data/backtest/lab.json": "Rule back-tests across markets: trend, COT, carry, fundamentals, seasonal; regime splits",
        "data/backtest/tech.json": "Technical pattern combinations (RSI, moving averages, pullbacks, MACD, divergences)",
        "data/backtest/baskets.json": "Strategy baskets and blends",
        "data/backtest/equity.json": "Equity curves for the back-tests",
        "data/specs/calendar.json": "Contract calendar: first position / notice day, last trading day, roll-by date",
        "data/specs/specs.json": "Contract specs, value per contract and margins",
    },
    "code": {
        "models/dairy_arb.py": "", "models/dairy_lab.py": "", "models/dairy_ideas.py": "", "models/dairy_playbook.py": "", "models/dairy_class.py": "",
        "models/meats_lab.py": "", "models/hogs.py": "", "models/hogs_convergence.py": "", "models/tech_lab.py": "", "models/backtest_lab.py": "",
        "models/basket_lab.py": "", "models/contract_calendar.py": "", "models/contract_specs.py": "", "models/futures_io.py": "",
        "pipelines/tvdates.py": "", "HANDOFF.md": "Desk documentation: every model, data source and workflow",
    },
}


def updated(p):
    try:
        return subprocess.run(["git", "log", "-1", "--format=%cI", "--", p], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None
    except Exception:
        return None


def main():
    items = []
    for kind, files in FILES.items():
        for p, desc in files.items():
            f = ROOT / p
            if not f.exists():
                continue
            b = f.read_bytes()
            items.append({"path": p, "kind": kind, "desc": desc, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "url": BASE + p, "updated": updated(p)})
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "source": "https://github.com/BMR-Com/US-commodity-desk", "base": BASE, "files": items}
    (ROOT / "data" / "lab_export").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "lab_export" / "manifest.json").write_text(json.dumps(out, indent=1))
    print(len(items), "files")


if __name__ == "__main__":
    main()
