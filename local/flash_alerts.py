#!/usr/bin/env python3
"""Release-time phone alerts (Bloomberg-style flash) from Ma's Mac. Runs WITHOUT Claude, needs no GitHub access.

At each release time launchd starts this script; it polls the USDA page every few seconds until the new numbers
appear, parses the headline numbers and pushes them to Ma's phone through ntfy.sh (free, no account: the phone app
subscribes to a private random topic name stored in ~/.ags-desk/ntfy_topic). Outbound requests only.

  esr    Thursday 7:30 CT (Friday after a holiday): weekly export sales, FAS highlights page
         -> wheat, corn, soybeans: net sales current MY (vs previous week / 4-wk avg), next MY, exports;
            upland cotton: current-MY net sales and shipments only
  macro  7:30 CT on US release days (from the desk's economic calendar): jobless claims (Labor Department weekly
         release, no key), CPI, payrolls / unemployment rate / hourly earnings, PPI (BLS API: works without a key at
         ~25 calls a day; put a free BLS key in ~/.ags-desk/bls_key to poll faster), each vs the calendar's forecast
  wasde  ~11:00 CT on WASDE day: USDA's report CSV -> US production, yield, exports, ending stocks (new crop) for
         corn, soybeans, wheat, cotton, world ending stocks, each with the change vs last month's report

Use:
  python flash_alerts.py esr | wasde | macro      wait for the release and alert (what launchd runs)
  python flash_alerts.py esr --now        parse what is posted now and alert (no waiting, ignores "already sent")
  python flash_alerts.py wasde --dry      print instead of sending
  python flash_alerts.py test             send a test notification
State (what was already sent): ~/.ags-desk/alerts_state.json. Log: ~/.ags-desk/alerts.log
"""
import json, re, subprocess, sys, time, io, os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

HOME = Path.home() / ".ags-desk"
LOG, STATE, TOPIC_F = HOME / "alerts.log", HOME / "alerts_state.json", HOME / "ntfy_topic"
CT = ZoneInfo("America/Chicago")
ESR_URL = "https://apps.fas.usda.gov/export-sales/highlite.htm"
WASDE_URL = "https://www.usda.gov/sites/default/files/documents/oce-wasde-report-data-{}.csv"
UA = {"User-Agent": "Mozilla/5.0 (BMR-Com research)"}
DRY = "--dry" in sys.argv
NOW = "--now" in sys.argv


def log(*a):
    HOME.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(CT):%Y-%m-%d %H:%M:%S} " + " ".join(str(x) for x in a)
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save_state(**kw):
    s = state(); s.update(kw)
    STATE.write_text(json.dumps(s, indent=1))


def send(title, body, tags="chart_with_upwards_trend"):
    if DRY:
        print(f"--- {title}\n{body}"); return
    topic = TOPIC_F.read_text().strip()
    for i in range(3):
        try:
            r = requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                              headers={"Title": title.encode("utf-8"), "Priority": "high", "Tags": tags}, timeout=15)
            if r.ok:
                log("sent:", title); return
            log("ntfy", r.status_code, r.text[:200])
        except Exception as e:
            log("ntfy error", e)
        time.sleep(2)


def poll(fetch, until_ct, fast_s=4, slow_s=30, fast_for_min=12):
    """Call fetch() until it returns something; fast at first, then slower, stop at until_ct."""
    t0 = time.time()
    while datetime.now(CT) < until_ct:
        try:
            r = fetch()
            if r:
                return r
        except Exception as e:
            log("poll error", str(e)[:200])
        time.sleep(fast_s if time.time() - t0 < fast_for_min * 60 else slow_s)
    return None


def keep_awake():
    try:      # macOS: keep the Mac awake while this process runs
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
    except Exception:
        pass


# ───────── export sales ─────────
ESR_COMS = [("Wheat", r"Wheat:"), ("Corn", r"Corn:"), ("Soybeans", r"Soybeans:"), ("Cotton", r"Cotton:")]


def k(s):
    return float(s.replace(",", "")) / 1000.0


def parse_esr(text):
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).replace("&nbsp;", " ")
    m = re.search(r"for the period ([A-Za-z]+ \d{1,2}\s*-\s*(?:[A-Za-z]+ )?\d{1,2}, \d{4})", t)
    if not m:
        return None
    period = m.group(1)
    out = []
    for name, tag in ESR_COMS:
        i = t.find(tag)
        if i < 0:
            continue
        nxt = min([j for j in (t.find(x[1], i + 5) for x in ESR_COMS) if j > i] + [t.find(" Export Adjustments", i + 5) if t.find(" Export Adjustments", i + 5) > i else len(t), i + 2500])
        p = t[i:nxt]
        unit = "RB" if name == "Cotton" else "MT"
        s = re.search(r"Net sales(?P<red> reductions)? of (?:Upland )?(?:totaling )?(?P<v>[\d,]+) (?:metric tons \(MT\)|MT|RB) for (?P<my>\d{4}/\d{4})", p)
        line = f"{name}: "
        if s:
            v = k(s["v"]) * (-1 if s["red"] else 1)
            line += f"net {v:,.1f}k {unit} {s['my'][2:4]}/{s['my'][7:9]}"
            vs = None if name == "Cotton" else re.search(r"were ((?:up|down|unchanged)[^.]*?(?:average|week)(?:[^.]*?average)?)", p[s.end():s.end() + 220])
            if vs:
                c = (vs.group(1).replace(" percent", "%").replace("from the previous week", "w/w")
                     .replace("from the prior 4-week average", "vs 4wk").replace("noticeably ", ""))
                line += f" ({c})"
        elif re.search(r"No net sales", p):
            line += "no net sales"
        nm = re.search(r"Net sales(?: reductions)? of ([\d,]+) (?:MT|RB) for (\d{4}/\d{4}) were", p[s.end():] if s else "")
        if nm and name != "Cotton":                  # cotton: current-MY sales and shipments only (Ma)
            line += f"; next MY {k(nm.group(1)):,.1f}k"
        e = re.search(r"(?:Upland )?[Ee]xports (?:of Upland )?(?:totaling |of )?([\d,]+) (?:MT|RB)", p)
        if e:
            line += f"; {'shipments' if name == 'Cotton' else 'exports'} {k(e.group(1)):,.1f}k"
        out.append(line)
    return {"period": period, "lines": out} if out else None


def esr():
    keep_awake()
    now = datetime.now(CT)
    last = state().get("esr_period")

    def fetch():
        r = requests.get(ESR_URL, headers=UA, timeout=30)
        if r.status_code != 200:
            return None
        x = parse_esr(r.text)
        if x and (NOW or x["period"] != last):
            return x
        return None
    if not NOW and not last and now < now.replace(hour=7, minute=30, second=0):   # first run: what is posted now is old
        try:
            b = parse_esr(requests.get(ESR_URL, headers=UA, timeout=30).text)
            last = b and b["period"]
        except Exception:
            pass
    if not NOW and last and now.weekday() == 4 and state().get("esr_sent_on") == (now - timedelta(days=1)).date().isoformat():
        log("esr: already sent this week"); return
    x = fetch() if NOW else poll(fetch, now.replace(hour=8, minute=45, second=0))
    if not x:
        log("esr: no new report by the cut-off"); return
    at = datetime.now(CT)
    send(f"USDA export sales {at:%H:%M:%S} CT", f"Week {x['period']}\n" + "\n".join(x["lines"]), "ship")
    save_state(esr_period=x["period"], esr_sent_on=at.date().isoformat())


# ───────── US macro ─────────
CAL_URL = "https://bmr-com.github.io/US-commodity-desk/data/macro/econ_calendar.json"
CLAIMS_URL = "https://www.dol.gov/ui/data.pdf"
BLS_URL = "https://api.bls.gov/publicAPI/{}/timeseries/data/"
# calendar title -> what to fetch
MACRO = {"Unemployment Claims": "claims", "CPI m/m": "cpi", "Core CPI m/m": "cpi", "CPI y/y": "cpi",
         "Non-Farm Employment Change": "jobs", "Unemployment Rate": "jobs", "Average Hourly Earnings m/m": "jobs",
         "PPI m/m": "ppi", "Core PPI m/m": "ppi"}
BLS = {"cpi": ["CUSR0000SA0", "CUSR0000SA0L1E", "CUUR0000SA0", "CUUR0000SA0L1E"],
       "jobs": ["CES0000000001", "LNS14000000", "CES0500000003"],
       "ppi": ["WPSFD4", "WPSFD49104"]}


def today_events():
    try:
        ev = requests.get(CAL_URL, headers=UA, timeout=30).json().get("events", [])
    except Exception as e:
        log("calendar unavailable", e); return {}
    d = datetime.now(CT).date().isoformat()
    return {e["title"]: e for e in ev if e.get("country") == "US" and e.get("date") == d and e.get("title") in MACRO
            and str(e.get("time", "")).startswith("8:30")}


def fc(evs, title):
    e = evs.get(title)
    if not e:
        return ""
    bits = [f"f'cast {e['forecast']}" if e.get("forecast") else "", f"prev {e['previous']}" if e.get("previous") else ""]
    return " (" + ", ".join(b for b in bits if b) + ")" if any(bits) else ""


def claims():
    from pypdf import PdfReader
    r = requests.get(CLAIMS_URL, headers=UA, timeout=30)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return None
    t = re.sub(r"\s+", " ", PdfReader(io.BytesIO(r.content)).pages[0].extract_text() or "")
    w = re.search(r"In the week ending ([A-Za-z]+ \d{1,2})", t)
    a = re.search(r"advance figure for seasonally adjusted initial claims was ([\d,]+), an? (increase|decrease) of ([\d,]+)", t)
    c = re.search(r"seasonally adjusted insured unemployment during the week ending [A-Za-z]+ \d{1,2} was ([\d,]+)", t)
    if not (w and a):
        return None
    sign = "+" if a.group(2) == "increase" else "-"
    return {"key": w.group(1), "initial": a.group(1), "chg": sign + a.group(3), "cont": c.group(1) if c else None}


def bls(series):
    key = (HOME / "bls_key").read_text().strip() if (HOME / "bls_key").exists() else ""
    body = {"seriesid": series, "startyear": str(datetime.now(CT).year - 1), "endyear": str(datetime.now(CT).year)}
    if key:
        body["registrationkey"] = key
    r = requests.post(BLS_URL.format("v2" if key else "v1"), json=body, headers=UA, timeout=30).json()
    out = {}
    for sr in r.get("Results", {}).get("series", []):
        pts = [x for x in sr["data"] if x["period"].startswith("M") and x["period"] != "M13"]
        pts.sort(key=lambda x: (x["year"], x["period"]))
        out[sr["seriesID"]] = [(f"{x['year']}-{x['period'][1:]}", float(x["value"])) for x in pts]
    return out


def pct(a, b):
    return 100 * (a / b - 1)


def macro():
    keep_awake()
    evs = today_events()
    kinds = sorted({MACRO[t] for t in evs})
    if not kinds:
        log("macro: no tracked US release at 8:30 ET today"); return
    key_on = (HOME / "bls_key").exists()
    st = state()
    for kind in kinds:
        until = datetime.now(CT).replace(hour=8, minute=0, second=0)
        early = datetime.now(CT) < datetime.now(CT).replace(hour=7, minute=30, second=0)
        if kind == "claims":
            base = st.get("claims_week")
            if not base and early:
                try:
                    base = (claims() or {}).get("key")
                except Exception:
                    pass
            x = poll(lambda: (lambda c: c if c and c["key"] != base else None)(claims()), until, fast_s=3, slow_s=20, fast_for_min=4)
            if x:
                send(f"US jobless claims {datetime.now(CT):%H:%M:%S} CT",
                     f"Initial {x['initial']} ({x['chg']}){fc(evs, 'Unemployment Claims')}\nContinuing {x['cont'] or '–'}\nWeek ending {x['key']}", "briefcase")
                save_state(claims_week=x["key"])
            continue
        ser = BLS[kind]
        last = st.get(f"{kind}_period")
        if not last and early:
            try:
                last = (bls(ser).get(ser[0]) or [("", 0)])[-1][0]
            except Exception:
                pass

        def get():
            d = bls(ser)
            p = (d.get(ser[0]) or [("", 0)])[-1][0]
            return d if p and p != last else None
        d = poll(get, until, fast_s=3 if key_on else 12, slow_s=60, fast_for_min=4 if key_on else 4)
        if not d:
            log(f"macro {kind}: nothing new by 8:00 CT"); continue
        per = d[ser[0]][-1][0]
        v = {k: dict(x) for k, x in d.items()}
        prev = lambda sid, n=1: d[sid][-1 - n][1] if len(d[sid]) > n else None
        last_ = lambda sid: d[sid][-1][1]
        yago = lambda sid: v[sid].get(f"{int(per[:4]) - 1}{per[4:]}")
        if kind == "cpi":
            lines = [f"CPI m/m {pct(last_('CUSR0000SA0'), prev('CUSR0000SA0')):+.1f}%{fc(evs, 'CPI m/m')}",
                     f"Core m/m {pct(last_('CUSR0000SA0L1E'), prev('CUSR0000SA0L1E')):+.1f}%{fc(evs, 'Core CPI m/m')}",
                     f"CPI y/y {pct(last_('CUUR0000SA0'), yago('CUUR0000SA0')):.1f}%{fc(evs, 'CPI y/y')}",
                     f"Core y/y {pct(last_('CUUR0000SA0L1E'), yago('CUUR0000SA0L1E')):.1f}%"]
            title = "US CPI"
        elif kind == "jobs":
            lines = [f"Payrolls {last_('CES0000000001') - prev('CES0000000001'):+,.0f}k{fc(evs, 'Non-Farm Employment Change')}",
                     f"Unemployment {last_('LNS14000000'):.1f}%{fc(evs, 'Unemployment Rate')}",
                     f"Hourly earnings m/m {pct(last_('CES0500000003'), prev('CES0500000003')):+.1f}%{fc(evs, 'Average Hourly Earnings m/m')}"]
            title = "US jobs"
        else:
            lines = [f"PPI m/m {pct(last_('WPSFD4'), prev('WPSFD4')):+.1f}%{fc(evs, 'PPI m/m')}",
                     f"Core PPI m/m {pct(last_('WPSFD49104'), prev('WPSFD49104')):+.1f}%{fc(evs, 'Core PPI m/m')}"]
            title = "US PPI"
        send(f"{title} {datetime.now(CT):%H:%M:%S} CT", f"{per}\n" + "\n".join(lines) + "\n(m/m from BLS index levels; can differ by 0.1 from the headline)", "bar_chart")
        save_state(**{f"{kind}_period": per})


# ───────── WASDE ─────────
US = {"Corn": ("U.S. Feed Grain and Corn", "m bu"), "Oilseed, Soybean": ("U.S. Soybeans", "m bu"),
      "Wheat": ("U.S. Wheat Supply", "m bu"), "Cotton": ("U.S. Cotton", "m bales")}
SHOW = {"Corn": "Corn", "Oilseed, Soybean": "Soy", "Wheat": "Wheat", "Cotton": "Cotton"}
ATTR = [("Yield per Harvested Acre", "yld"), ("Production", "prod"), (("Exports", "Exports, Total"), "exp"), ("Ending Stocks", "end")]


def get_csv(ym):
    import pandas as pd
    from curl_cffi import requests as cf          # usda.gov needs a browser-like request
    r = cf.get(WASDE_URL.format(ym), impersonate="chrome120", timeout=60)
    if r.status_code == 200 and len(r.content) > 5000 and b"WasdeNumber" in r.content[:2000]:
        return pd.read_csv(io.StringIO(r.content.decode("utf-8-sig")), low_memory=False, dtype={"MarketYear": str})
    return None


def wasde_vals(d):
    v = {}
    proj = d[d.ProjEstFlag.astype(str).str.contains("Proj")]
    if not len(proj):
        return v
    my = sorted(m for m in proj[proj.Commodity == "Corn"].MarketYear.astype(str).unique() if "/" in m)[-1]
    for com, (title, _) in US.items():
        u = proj[(proj.Commodity == com) & (proj.Region == "United States") & (proj.MarketYear == my) & proj.ReportTitle.str.startswith(title)]
        for a, key in ATTR:
            x = u[u.Attribute.isin(a if isinstance(a, tuple) else (a,))]
            if len(x):
                v[(com, key)] = float(x.Value.iloc[0])
        w = proj[(proj.Commodity == com) & (proj.Region == "World") & (proj.MarketYear == my) & (proj.Attribute == "Ending Stocks") & proj.ReportTitle.str.startswith("World")]
        if len(w):
            v[(com, "world_end")] = float(w.Value.iloc[0]); v[(com, "world_unit")] = w.Unit.iloc[0]
    v["my"] = my
    return v


def wasde():
    keep_awake()
    now = datetime.now(CT)
    if now.weekday() > 4 and not NOW:
        return
    ym = now.strftime("%Y-%m")
    prev_ym = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    last = state().get("wasde_number", 0)
    if not NOW and state().get("wasde_month") == ym:
        log("wasde: this month's report already sent"); return

    if not NOW and not last and now < now.replace(hour=11, minute=0, second=0):   # first run: baseline from what is posted
        for m_ in (ym, prev_ym):
            try:
                b = get_csv(m_)
                if b is not None:
                    last = max(last, int(b.WasdeNumber.max()))
            except Exception:
                pass

    def fetch():
        d = get_csv(ym)
        if d is None:
            return None
        n = int(d.WasdeNumber.max())
        return d if (NOW or n > last) else None
    d = get_csv(ym) if NOW else poll(fetch, now.replace(hour=11, minute=40, second=0), fast_s=3, slow_s=30, fast_for_min=10)
    if d is None:
        log("wasde: no new report (not a report day, or not posted by the cut-off)"); return
    at = datetime.now(CT)
    cur = wasde_vals(d)
    try:
        prv = wasde_vals(get_csv(prev_ym))
    except Exception:
        prv = {}
    lines = []
    for com in US:
        parts = []
        for a, key in ATTR:
            if (com, key) in cur:
                c, p = cur[(com, key)], prv.get((com, key))
                dec = 0 if (com, key) == ("Cotton", "yld") else 2 if com == "Cotton" else 1 if key == "yld" else 0
                ch = f" ({c - p:+,.{dec}f})" if p is not None and abs(c - p) > 1e-9 else (" (unch)" if p is not None else "")
                parts.append(f"{key} {c:,.{dec}f}{ch}")
        if (com, "world_end") in cur:
            c, p = cur[(com, "world_end")], prv.get((com, "world_end"))
            parts.append(f"world end {c:,.2f}" + (f" ({c - p:+,.2f})" if p is not None else ""))
        if parts:
            lines.append(f"{SHOW[com]} {cur['my'][2:]}: " + ", ".join(parts))
    lines.append("US: m bu (cotton m bales), yield bu/ac (cotton lb/ac); world in MMT (cotton m bales); change vs last month")
    send(f"WASDE #{int(d.WasdeNumber.max())} {at:%H:%M:%S} CT", "\n".join(lines), "bar_chart")
    save_state(wasde_number=int(d.WasdeNumber.max()), wasde_month=ym)


if __name__ == "__main__":
    what = (sys.argv[1:] or ["test"])[0]
    try:
        if what == "esr":
            esr()
        elif what == "wasde":
            wasde()
        elif what == "macro":
            macro()
        else:
            send("BMR-Com flash test", f"Phone alerts are set up. {datetime.now(CT):%Y-%m-%d %H:%M:%S} CT", "white_check_mark")
    except Exception as e:
        log(what, "failed:", repr(e)[:300])
