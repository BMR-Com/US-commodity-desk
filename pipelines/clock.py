#!/usr/bin/env python3
"""Desk clock: starts the data workflows at the right US Eastern times, because GitHub's own cron is unreliable on this
repo (scheduled runs arrive 1-5 hours late or not at all, e.g. none of the eight Thursday export-sales crons fired on
2026-10-22).

One clock job runs at a time (up to ~5h50m). It walks today's timetable in America/New_York time and, for each entry
that is due, starts the workflow with workflow_dispatch (which GitHub runs immediately) unless that workflow already has
a run created after the entry's time. Missed entries up to GRACE old are caught up when a clock starts late. Before its
time budget runs out (in its last HANDOVER_AT minutes; until then it sleeps in short naps) the clock starts the next
clock, as long as the next entry is less than CHAIN_GAP away; it never hands over within MIN_AGE of starting unless it
dispatched something (2026-11-10 fix: it used to hand over at once overnight and relaunch itself every ~10 s); overnight
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
    ("brief.yml", {SUN}, "17:20"),            # Sunday pre-open brief before the 8 pm ET CBOT reopen (runs markets itself)
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


HANDOVER_AT = timedelta(minutes=10)    # hand over only in the last 10 minutes of this clock's budget
MIN_AGE = timedelta(minutes=30)        # never start a new clock this soon after starting, unless something was dispatched
NAP = timedelta(minutes=10)            # longest single sleep, so the loop re-checks regularly


def main(now_fn=lambda: datetime.now(ET), sleep_fn=time.sleep, dispatch_fn=None, ran_since_fn=None):
    """Run the timetable. Returns "handover", "stop" or "done". The clock functions are injectable for --selftest."""
    dispatch_fn = dispatch_fn or dispatch
    ran_since_fn = ran_since_fn or ran_since
    start = now_fn()
    deadline = start + BUDGET
    print(f"clock up {start:%a %Y-%m-%d %H:%M %Z}, budget to {deadline:%H:%M}")
    done = set()
    dispatched_any = False
    while True:
        now = now_fn()
        todo = [(t, wf) for t, wf in entries(now.date()) + entries(now.date() + timedelta(days=1)) if (t, wf) not in done]
        due = [(t, wf) for t, wf in todo if now - GRACE <= t <= now]
        latest = {}
        for t, wf in due:                       # a late clock catches up once per workflow, not once per missed entry
            done.add((t, wf))
            latest[wf] = max(latest.get(wf, t), t)
        for wf, t in sorted(latest.items(), key=lambda x: x[1]):
            print(f"{now:%H:%M} due {wf} @ {t:%a %H:%M}")
            if ran_since_fn(wf, t):
                print(f"  {wf} already ran after {t:%H:%M}")
            else:
                dispatch_fn(wf)
                dispatched_any = True
            done.add((t, wf))
        nxt = min((t for t, wf in todo if t > now), default=None)
        if nxt is None:
            print("nothing left today; stopping")
            return "done"
        if nxt > deadline:
            if nxt - deadline >= CHAIN_GAP:
                print(f"next entry {nxt:%a %H:%M} is more than {CHAIN_GAP} away: stopping; the clock's cron restarts it")
                return "stop"
            if now >= deadline - HANDOVER_AT:
                if now - start < MIN_AGE and not dispatched_any:   # e.g. a tiny CLOCK_BUDGET_MIN: never chain-loop
                    print("budget used up within minutes of starting and nothing dispatched: stopping, no hand-over")
                    return "stop"
                print(f"next entry {nxt:%a %H:%M} is past this clock's budget: starting the next clock")
                dispatch_fn("clock.yml")
                return "handover"
            until = deadline - HANDOVER_AT     # keep this clock alive until its budget is nearly used
        else:
            until = nxt
        wait = min((until - now_fn()).total_seconds(), NAP.total_seconds())
        print(f"sleeping {wait / 60:.0f} min (next entry {nxt:%a %H:%M})")
        sleep_fn(max(1, wait))


def selftest():
    """Simulate whole nights with a fake clock: each hand-over starts the next clock ~1 min later (as the queued run would).
    Asserts hand-overs stay small and that no clock hands over within MIN_AGE of starting without dispatching."""
    import contextlib, io
    days = [datetime(2026, 11, 10, tzinfo=ET).date(),    # Tue (EST)
            datetime(2026, 7, 14, tzinfo=ET).date(),     # Tue (EDT)
            datetime(2026, 11, 13, tzinfo=ET).date(),    # Fri -> Sat idle
            datetime(2026, 11, 14, tzinfo=ET).date(),    # Sat -> Sun brief
            datetime(2026, 11, 15, tzinfo=ET).date()]    # Sun
    for day in days:
        for hh in (21, 2, 6):
            d0 = day + timedelta(days=1) if hh < 12 else day
            t0 = datetime.combine(d0, dtime(hh, 0), ET)
            horizon = t0 + timedelta(hours=14)
            clock = {"now": t0}
            log = []

            def now_fn():
                return clock["now"]

            def sleep_fn(sec):
                assert sec <= NAP.total_seconds() + 1, f"slept {sec}s in one go"
                clock["now"] = clock["now"] + timedelta(seconds=sec)

            def dispatch_fn(wf):
                log.append((clock["now"], wf))
                return True

            handovers, runs, t = 0, 0, t0
            while t < horizon and runs < 50:
                runs += 1
                clock["now"] = t
                n_before = len([x for x in log if x[1] != "clock.yml"])
                with contextlib.redirect_stdout(io.StringIO()):
                    res = main(now_fn, sleep_fn, dispatch_fn, lambda wf, tt: False)
                age = clock["now"] - t
                if res == "handover":
                    handovers += 1
                    work = len([x for x in log if x[1] != "clock.yml"]) > n_before
                    assert age >= MIN_AGE or work, f"hand-over {age} after start with nothing dispatched"
                    t = clock["now"] + timedelta(minutes=1)
                else:
                    break
            sat = [x for x in log if x[0].weekday() == SAT and x[1] != "clock.yml"]
            assert not sat, f"Saturday dispatches: {sat}"
            print(f"start {t0:%a %m-%d %H:%M %Z}: {runs} clock run(s), {handovers} hand-over(s), "
                  f"{len(log) - handovers} dispatch(es) in the next 14 h")
            assert handovers <= 4, f"{handovers} hand-overs from {t0}"
    for t0 in (datetime(2026, 11, 15, 19, 7, tzinfo=UTC), datetime(2026, 7, 12, 19, 7, tzinfo=UTC),   # Sunday crons
               datetime(2026, 11, 15, 22, 3, tzinfo=UTC)):
        clock = {"now": t0.astimezone(ET)}
        got = []

        def adv(sec):
            clock["now"] += timedelta(seconds=sec)
        with contextlib.redirect_stdout(io.StringIO()):
            res = main(lambda: clock["now"], adv, lambda wf: got.append(wf) or True, lambda wf, tt: False)
        assert "brief.yml" in got and res == "stop", (t0, got, res)
        print(f"Sunday cron {t0:%H:%M UTC} ({clock['now']:%Z}): dispatched {got}, then {res}")
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--plan" in sys.argv:
        d = datetime.now(ET).date()
        for k in range(7):
            for t, wf in entries(d + timedelta(days=k)):
                print(f"{t:%a %m-%d %H:%M ET}  {wf}")
    else:
        main()
