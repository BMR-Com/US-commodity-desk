#!/usr/bin/env python3
"""Desk clock: starts the data workflows at the right US Eastern times, because GitHub's own cron is unreliable on this
repo (scheduled runs arrive 1-5 hours late or not at all, e.g. none of the eight Thursday export-sales crons fired on
2026-10-22).

One clock job runs at a time (up to ~5h50m). It walks today's timetable in America/New_York time and, for each entry
that is due, starts the workflow with workflow_dispatch (which GitHub runs immediately) unless that workflow already has
a run created after the entry's time. Missed entries up to GRACE old are caught up when a clock starts late. Before its
time budget runs out the clock starts the next clock, as long as the next entry is less than CHAIN_GAP away; overnight
and at weekends it stops and the clock's own cron entries (several, so one late or dropped run does not matter) start
it again. The workflows keep their own cron entries as a further backstop; duplicate runs are harmless.
Uses the job's GITHUB_TOKEN (actions: write); no secrets.
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

ET, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")
REPO = os.environ.get("GITHUB_REPOSITORY", "BMR-Com/US-commodity-desk")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
BUDGET = timedelta(minutes=int(os.environ.get("CLOCK_BUDGET_MIN", "345")))
GRACE = timedelta(hours=4)
CHAIN_GAP = timedelta(hours=4)
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
WEEKDAYS = {MON, TUE, WED, THU, FRI}

# (workflow file, days of week, "HH:MM" ET, optional day-of-month range)
TABLE = [
    ("brief.yml", WEEKDAYS, "06:35"),                                   # morning brief before 8 am ET
    *[("markets.yml", WEEKDAYS, f"{h:02d}:07") for h in range(7, 19)],  # hourly cross-market snapshot
    ("intel.yml", WEEKDAYS, "06:20"), ("intel.yml", WEEKDAYS, "09:20"), ("intel.yml", WEEKDAYS, "12:20"),
    ("intel.yml", WEEKDAYS, "15:20"), ("intel.yml", WEEKDAYS, "18:20"), ("intel.yml", WEEKDAYS, "21:00"),
    ("grains_trade.yml", {THU}, "08:33"), ("grains_trade.yml", {THU}, "08:45"),   # weekly export sales, 8:30 ET
    ("grains_trade.yml", {THU}, "09:05"), ("grains_trade.yml", {THU}, "09:45"),
    ("grains_trade.yml", {TUE, WED, FRI}, "10:05"),                   # flash sales; a holiday-shifted Friday report
    ("grains_trade.yml", {MON}, "11:15"), ("grains_trade.yml", {MON}, "16:15"),   # inspections, then Crop Progress
    ("grains.yml", {MON}, "16:15"), ("grains.yml", {THU}, "10:05"),
    ("energy.yml", {WED}, "10:40"), ("energy.yml", {THU}, "10:40"),   # EIA petroleum (Wed), gas storage (Thu)
    ("energy.yml", WEEKDAYS, "18:40"),                                 # after the settle: prices, ETF options
    ("wasde.yml", WEEKDAYS, "12:05", (8, 14)), ("wasde.yml", WEEKDAYS, "12:20", (8, 14)),   # WASDE at noon ET
    ("wasde.yml", WEEKDAYS, "16:30", (8, 14)),
    ("cot_full.yml", {FRI}, "15:40"), ("cot_full.yml", {FRI}, "16:15"),   # COT, 3:30 pm ET Friday
    ("cot_full.yml", {MON, TUE, WED, THU}, "18:20"),
    ("data.yml", WEEKDAYS, "16:20"), ("data.yml", {FRI}, "17:40"),     # USDA dairy/livestock, CME, NDPSR (Wed)
    ("contracts.yml", WEEKDAYS, "19:10"),                              # settlements, labs, playbooks, calendar
]


def api(method, path, body=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        txt = r.read()
        return json.loads(txt) if txt else {}


def entries(day):
    out = []
    for row in TABLE:
        wf, days, hm = row[:3]
        dom = row[3] if len(row) > 3 else None
        if day.weekday() not in days or (dom and not dom[0] <= day.day <= dom[1]):
            continue
        h, m = map(int, hm.split(":"))
        out.append((datetime.combine(day, dtime(h, m), ET), wf))
    return sorted(out)


def ran_since(wf, t):
    since = t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        r = api("GET", f"/actions/workflows/{wf}/runs?created=%3E%3D{since}&per_page=1")
        return r.get("total_count", 0) > 0
    except Exception as e:
        print("  check failed:", wf, e)
        return False


def dispatch(wf, inputs=None):
    try:
        api("POST", f"/actions/workflows/{wf}/dispatches", {"ref": "main", **({"inputs": inputs} if inputs else {})})
        print(f"  started {wf}")
        return True
    except Exception as e:
        print(f"  could not start {wf}: {e}")
        return False


def main():
    start = datetime.now(ET)
    deadline = start + BUDGET
    print(f"clock up {start:%a %Y-%m-%d %H:%M %Z}, budget to {deadline:%H:%M}")
    done = set()
    while True:
        now = datetime.now(ET)
        todo = [(t, wf) for t, wf in entries(now.date()) + entries(now.date() + timedelta(days=1)) if (t, wf) not in done]
        due = [(t, wf) for t, wf in todo if now - GRACE <= t <= now]
        latest = {}
        for t, wf in due:                       # a late clock catches up once per workflow, not once per missed entry
            done.add((t, wf))
            latest[wf] = max(latest.get(wf, t), t)
        for wf, t in sorted(latest.items(), key=lambda x: x[1]):
            print(f"{now:%H:%M} due {wf} @ {t:%a %H:%M}")
            if ran_since(wf, t):
                print(f"  {wf} already ran after {t:%H:%M}")
            else:
                dispatch(wf)
            done.add((t, wf))
        nxt = min((t for t, wf in todo if t > now), default=None)
        if nxt is None:
            print("nothing left today; stopping")
            return
        if nxt > deadline:
            if nxt - deadline < CHAIN_GAP:
                print(f"next entry {nxt:%a %H:%M} is past this clock's budget: starting the next clock")
                dispatch("clock.yml")
            else:
                print(f"next entry {nxt:%a %H:%M} is more than {CHAIN_GAP} away: stopping; the clock's cron restarts it")
            return
        wait = (nxt - datetime.now(ET)).total_seconds()
        print(f"sleeping {wait / 60:.0f} min until {nxt:%H:%M}")
        time.sleep(max(1, wait))


if __name__ == "__main__":
    if "--plan" in sys.argv:
        d = datetime.now(ET).date()
        for k in range(7):
            for t, wf in entries(d + timedelta(days=k)):
                print(f"{t:%a %m-%d %H:%M ET}  {wf}")
    else:
        main()
