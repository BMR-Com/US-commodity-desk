#!/usr/bin/env python3
"""Nightly CME + USDA flash-sales collector for Ma's Mac. Runs WITHOUT Claude.

CME (cmegroup.com) and USDA FAS (fas.usda.gov) block GitHub's servers, so these two feeds are fetched from
a home connection. This script opens each site in a real browser (Google Chrome via Playwright), runs the
same collectors the desk uses (cme/collect.js, cme/collect_flash.js), writes the files with the desk's own
ingest scripts, and pushes to GitHub. GitHub Actions then rebuilds every model and the site.

Install once:  bash local/install_mac.sh      (creates a venv, installs Playwright, schedules this script)
Run by hand:   ~/.ags-desk/venv/bin/python local/mac_collector.py
Log:           ~/.ags-desk/collector.log
"""
import asyncio, base64, datetime as dt, json, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG = Path.home() / ".ags-desk" / "collector.log"
PROFILE = Path.home() / ".ags-desk" / "chrome-profile"


def log(*a):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} " + " ".join(str(x) for x in a)
    print(line)
    with LOG.open("a") as f:
        f.write(line + "\n")


def sh(*cmd):
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if r.returncode:
        log("FAILED", " ".join(cmd), r.stderr.strip()[-400:])
    return r


async def collect():
    from playwright.async_api import async_playwright
    out = {}
    async with async_playwright() as p:
        kw = dict(headless=True, args=["--disable-blink-features=AutomationControlled"])
        try:
            ctx = await p.chromium.launch_persistent_context(str(PROFILE), channel="chrome", **kw)  # installed Google Chrome
        except Exception:
            ctx = await p.chromium.launch_persistent_context(str(PROFILE), **kw)  # Playwright's Chromium
        page = await ctx.new_page()
        # CME
        try:
            await page.goto("https://www.cmegroup.com/markets/agriculture/dairy/class-iii-milk.volume.html", wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(4000)
            res = await page.evaluate((REPO / "cme" / "collect.js").read_text())
            out["cme"] = res
            log("CME", res.get("dates"), "settlement rows", res.get("fut_settlements", "").count("\n"), "errors", len(res.get("errors") or []))
        except Exception as e:
            log("CME failed:", str(e)[:300])
        try:   # exchange margins for the primers' contract tables
            out["margins"] = await page.evaluate((REPO / "cme" / "collect_margins.js").read_text())
            log("CME margins rows", len(out["margins"].get("rows") or []))
        except Exception as e:
            log("CME margins failed:", str(e)[:300])
        # USDA FAS flash sales
        try:
            await page.goto("https://www.fas.usda.gov/newsroom/search?news%5B0%5D=news_type%3A10106", wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(3000)
            out["flash"] = await page.evaluate((REPO / "cme" / "collect_flash.js").read_text())
            log("FAS flash payload", len(out["flash"]))
        except Exception as e:
            log("FAS failed:", str(e)[:300])
        await ctx.close()
    return out


def main():
    sh("git", "pull", "-q", "--rebase", "origin", "main")
    res = asyncio.run(collect())
    tmp = Path(tempfile.mkdtemp())
    if res.get("cme") and res["cme"].get("fut_settlements", "").count("\n") > 10:
        (tmp / "cme.json").write_text(json.dumps(res["cme"]))
        r = sh(sys.executable, "cme/ingest.py", str(tmp / "cme.json"))
        log(r.stdout.strip()[-500:])
    if res.get("margins") and len(res["margins"].get("rows") or []) > 30:
        m = res["margins"]; m["source"] = "CME Group margins (outright maintenance), collected from cmegroup.com"
        (REPO / "data" / "specs" / "margins.json").write_text(json.dumps(m, indent=0))
        sh(sys.executable, "models/contract_specs.py")
    if res.get("flash"):
        (tmp / "flash.b64").write_text(res["flash"])
        r = sh(sys.executable, "pipelines/flash.py", str(tmp / "flash.b64"))
        log(r.stdout.strip()[:300])
    sh("git", "add", "data/cme", "data/grains/raw/flash", "data/specs")
    if sh("git", "diff", "--cached", "--quiet").returncode == 0:
        log("nothing new")
        return
    sh("git", "commit", "-q", "-m", f"CME data and FAS flash (Mac collector) {dt.date.today()}")
    for _ in range(3):
        if sh("git", "pull", "-q", "--rebase", "origin", "main").returncode == 0 and sh("git", "push", "-q", "origin", "main").returncode == 0:
            log("pushed")
            return
    log("push failed")


if __name__ == "__main__":
    main()
