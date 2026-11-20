"""Metals desk catch-up (run by .github/workflows/metals_catchup.yml; lean port of the softs desk's watchdog).

1. Data status (pipelines/metals_status.py) and the conclusion of the last metals workflow run.
2. If an automatic source is late/missing or the last run failed: dispatch metals.yml, wait for it (up to 60 min),
   pull, recheck the status.
3. Exit 1 (red) if something automatic is still late or the rerun failed. Manual sources (COMEX stocks via the Mac
   collector) are listed but never turn it red.
Writes data/metals/catchup.json (last 60 checks).
"""
import json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
LOGP = ROOT / "data" / "metals" / "catchup.json"
REPO = os.environ.get("REPO", "BMR-Com/US-commodity-desk")
API = f"https://api.github.com/repos/{REPO}/actions/workflows/metals.yml"
H = {"Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}", "Accept": "application/vnd.github+json"}


def status():
    subprocess.run([sys.executable, "pipelines/metals_status.py"], cwd=ROOT, check=False)
    s = json.loads((ROOT / "data" / "metals" / "status.json").read_text())
    return [r for r in s["sources"] if r["state"] in ("late", "missing") and not r["manual"]], [r for r in s["sources"] if r["manual"] and r["state"] != "ok"]


def last_run():
    r = requests.get(API + "/runs?per_page=5&branch=main", headers=H, timeout=30).json().get("workflow_runs", [])
    done = [x for x in r if x["status"] == "completed"]
    return done[0] if done else None


def main():
    late, manual = status()
    lr = last_run()
    failed = lr is not None and lr["conclusion"] not in ("success", "skipped")
    rec = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "late": [r["source"] for r in late], "needs_mac": [r["source"] for r in manual],
           "last_run": lr and {"id": lr["id"], "conclusion": lr["conclusion"], "at": lr["updated_at"]}, "action": "none"}
    ok = True
    if late or failed:
        t0 = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = requests.post(API + "/dispatches", headers=H, json={"ref": "main"}, timeout=30)
        rec["action"] = f"reran metals.yml (dispatch {r.status_code})"
        run = None
        for _ in range(120):                       # wait up to 60 min
            time.sleep(30)
            runs = requests.get(API + f"/runs?per_page=5&branch=main&created=>={t0}", headers=H, timeout=30).json().get("workflow_runs", [])
            run = runs[0] if runs else None
            if run and run["status"] == "completed":
                break
        rec["rerun"] = run and {"id": run["id"], "conclusion": run["conclusion"]}
        subprocess.run(["git", "pull", "-q", "--rebase", "origin", "main"], cwd=ROOT, check=False)
        late, manual = status()
        rec["late_after"] = [x["source"] for x in late]
        ok = not late and bool(run) and run["conclusion"] == "success"
    log = json.loads(LOGP.read_text()) if LOGP.exists() else []
    LOGP.parent.mkdir(parents=True, exist_ok=True)
    LOGP.write_text(json.dumps((log + [rec])[-60:], indent=1))
    print(json.dumps(rec, indent=1))
    if not ok:
        print("::error::metals catch-up: " + ("; ".join(rec.get("late_after") or []) or "rerun failed"))
        sys.exit(1)


if __name__ == "__main__":
    main()
