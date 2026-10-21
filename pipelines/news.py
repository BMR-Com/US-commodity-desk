"""Ag-market headlines from major outlets via RSS (runs in GitHub Actions; no keys).

Google News RSS search, restricted to named outlets (Reuters, Bloomberg, Dow Jones/WSJ/MarketWatch/Barron's,
DTN/Progressive Farmer, Successful Farming, Farm Progress, AgWeb, Brownfield, Feedstuffs, Dairy Herd, National Hog
Farmer, Drovers, S&P Global, Farm Journal, Hoard's Dairyman) plus the Brownfield and farmdoc daily feeds directly.
Stores headline, outlet, link and time only (no article text). Each item is tagged with the markets it mentions.
Keeps 45 days. Writes data/news/news.json.
"""
import email.utils, json, re, time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote
import pandas as pd
import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "news"
H = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk; +https://bmr-com.github.io/us--Ags-desk/)"}
SITES = ["reuters.com", "bloomberg.com", "wsj.com", "marketwatch.com", "barrons.com", "dtnpf.com", "agriculture.com",
         "farmprogress.com", "agweb.com", "brownfieldagnews.com", "feedstuffs.com", "dairyherd.com", "nationalhogfarmer.com",
         "drovers.com", "spglobal.com", "hoards.com", "farmdocdaily.illinois.edu", "successful-farming.com", "agrimoney.com", "ft.com"]
QUERIES = {  # topic: search terms
    "corn": "corn futures OR corn prices OR corn crop OR corn exports",
    "soybeans": "soybean futures OR soybean prices OR soybeans China OR soybean crop",
    "meal_oil": "soymeal OR soyoil OR soybean oil OR soybean meal OR crush margins OR renewable diesel",
    "wheat": "wheat futures OR wheat prices OR wheat crop OR Black Sea wheat",
    "south_america": "Brazil soybeans OR Brazil corn OR Argentina soybeans OR Argentina corn OR Conab OR safrinha",
    "hogs": "hog futures OR hog prices OR pork exports OR lean hogs",
    "cattle": "cattle futures OR cattle prices OR beef prices OR screwworm OR feeder cattle",
    "cotton": "cotton futures OR cotton prices OR cotton crop OR cotton exports OR ICE cotton OR cotton mills",
    "dairy": "dairy prices OR milk prices OR cheese prices OR butter prices OR Class III milk",
    "usda": "USDA WASDE OR USDA report OR crop progress OR export sales",
    "trade_policy": "China tariffs soybeans OR farm trade deal OR biofuel RVO OR EPA biofuel",
    "weather": "Corn Belt weather OR Brazil drought OR Argentina dry OR La Nina crops OR El Nino crops",
}
TAGS = {
    "corn": r"\bcorn\b|maize|safrinha|ethanol",
    "soybeans": r"soybean|\bsoy\b|\bsoya\b|\bbeans\b",
    "meal": r"soymeal|soybean meal|\bmeal\b|crush",
    "oil": r"soyoil|soybean oil|renewable diesel|biodiesel|biofuel|\bRVO\b|vegetable oil|palm oil",
    "wheat": r"wheat",
    "hogs": r"\bhogs?\b|\bpork\b|\bpigs?\b|swine",
    "cattle": r"cattle|\bbeef\b|screwworm|feedlot|steer",
    "cotton": r"cotton",
    "dairy": r"dairy|\bmilk\b|cheese|butter|whey|nonfat",
    "south_america": r"brazil|argentin|conab|safrinha|rosario|parana|mato grosso",
    "usda": r"\bUSDA\b|WASDE|crop progress|export sales|NASS",
}


def fetch(url):
    for i in range(3):
        try:
            r = requests.get(url, headers=H, timeout=30)
            if r.status_code == 200:
                return r.content
        except Exception:
            pass
        time.sleep(2 + 2 * i)
    return None


def parse(xml, topic):
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        source = src_el.text.strip() if src_el is not None and src_el.text else ""
        if not source and " - " in title:
            source = title.rsplit(" - ", 1)[1]
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        pub = it.findtext("pubDate")
        try:
            ts = email.utils.parsedate_to_datetime(pub).astimezone(tz=None).strftime("%Y-%m-%dT%H:%MZ") if pub else None
        except Exception:
            ts = None
        if title and link:
            out.append({"title": title, "link": link, "source": source or "", "time": ts, "topic": topic})
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "news.json"
    old = json.loads(p.read_text()).get("items", []) if p.exists() else []
    items = []
    sites = " OR ".join(f"site:{s}" for s in SITES)
    for topic, q in QUERIES.items():
        url = f"https://news.google.com/rss/search?q={quote(f'({q}) ({sites}) when:7d')}&hl=en-US&gl=US&ceid=US:en"
        x = fetch(url)
        if x:
            got = parse(x, topic)
            items += got
            print(topic, len(got))
        time.sleep(1.5)
    broad = "cotton OR corn OR soybeans OR soybean OR wheat OR grain OR cattle OR hogs OR pork OR beef OR dairy OR milk OR cheese OR soymeal OR soyoil OR USDA"
    for site in ["reuters.com", "bloomberg.com", "wsj.com", "marketwatch.com", "barrons.com", "ft.com", "agriculture.com", "farmprogress.com",
                 "brownfieldagnews.com", "nationalhogfarmer.com", "dairyherd.com", "drovers.com", "hoards.com", "feedstuffs.com", "agweb.com"]:
        url = f"https://news.google.com/rss/search?q={quote(f'({broad}) site:{site} when:7d')}&hl=en-US&gl=US&ceid=US:en"
        x = fetch(url)
        if x:
            got = parse(x, "outlet:" + site)
            items += got
            print(site, len(got))
        time.sleep(1.2)
    for name, url in [("Brownfield", "https://www.brownfieldagnews.com/feed/"), ("farmdoc daily", "https://farmdocdaily.illinois.edu/feed")]:
        x = fetch(url)
        if x:
            got = parse(x, "feeds")
            for g in got:
                g["source"] = g["source"] or name
            items += got
            print(name, len(got))
    df = pd.DataFrame(old + items)
    if df.empty:
        return
    df["key"] = df.title.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.slice(0, 90)
    df = df.sort_values("time", na_position="first").drop_duplicates("key", keep="last")
    df["time"] = df.time.fillna(pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%MZ"))
    cutoff = (pd.Timestamp.now("UTC") - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    df = df[df.time >= cutoff]
    AG = r"cotton|soy|corn|maize|grain|crop|safra|safrinha|harvest|plant|wheat|cattle|beef|hog|pork|dairy|milk|cheese|butter|farm|ag\b|agri|fertili|ethanol|biofuel|crush|livestock|feed|USDA|WASDE|export sales|tariff"
    def tags(t):
        if not re.search(AG, t, re.I):
            return []
        return [k for k, rx in TAGS.items() if re.search(rx, t, re.I)]
    df["tags"] = df.title.apply(tags)
    df = df[df.tags.str.len() > 0].sort_values("time", ascending=False)
    rows = df.drop(columns=["key"]).to_dict("records")
    p.write_text(json.dumps({"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "items": rows[:600]}, ensure_ascii=False, indent=0))
    print("kept", len(rows), "items;", df.source.value_counts().head(12).to_dict())


if __name__ == "__main__":
    main()
