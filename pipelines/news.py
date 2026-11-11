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
try:
    from research_sources import admis, rabobank
except Exception:  # keep the news run alive if the research module breaks
    admis = rabobank = lambda *a, **k: []

OUT = Path(__file__).resolve().parent.parent / "data" / "news"
H = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk; +https://bmr-com.github.io/US-commodity-desk/)"}
SITES = ["rigzone.com", "naturalgasintel.com", "oilprice.com", "reuters.com", "bloomberg.com", "wsj.com", "marketwatch.com", "barrons.com", "dtnpf.com", "agriculture.com",
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
    "natgas": "natural gas futures OR natural gas prices OR Henry Hub OR LNG exports OR gas storage OR LNG terminal",
    "crude": "oil prices OR crude oil futures OR OPEC OR WTI crude OR Brent crude OR crude inventories OR shale output",
    "products": "diesel prices OR gasoline prices OR refinery outage OR crack spread OR heating oil futures OR distillate stocks",
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
    "natgas": r"natural gas|\bnat ?gas\b|\bLNG\b|Henry Hub|gas storage|liquefaction",
    "crude": r"\bcrude\b|\boil price|\bOPEC|\bWTI\b|\bBrent\b|shale|oil output|oil futures|barrel",
    "products": r"diesel|gasoline|refiner|crack spread|heating oil|distillate|jet fuel|\bRBOB\b",
}


# ───────── source quality and relevance (2026-11-11) ─────────
# Only sources that matter for prices are kept. Tier 1: Reuters, Bloomberg, Dow Jones (WSJ, MarketWatch, Barron's), FT and
# price-reporting agencies; tier 2: exchanges, commodity boards, official statistics and trade data, and broker/bank research
# the desk reads; tier 3: specialist ag/energy trade press. Everything else (local papers, lifestyle, sports) is dropped.
TIER_RX = [
    (1, r"^reuters|^bloomberg|wall street journal|^wsj|dow jones|marketwatch|barron|financial times|^ft\b|s&p global|platts|argus"),
    (2, r"usda|foreign agricultural service|\bnass\b|\bams\b|\bers\b|cftc|^ice\b|intercontinental exchange|cme group|\beia\b|energy information|"
        r"\biea\b|international energy agency|opec|icco|international cocoa|international coffee org|\bico\b|icac|international cotton advisory|"
        r"international sugar org|unica|conab|cocobod|conseil caf|cecaf|national cotton council|cotton incorporated|cotlook|mpob|malaysian palm|"
        r"comtrade|census bureau|customs|secex|mdic|admis|rabobank|czapp|czarnikow|farmdoc"),
    (3, r"dtn|progressive farmer|brownfield|farm progress|successful farming|agweb|pro farmer|farm journal|feedstuffs|national hog farmer|drovers|"
        r"dairy herd|hoard|natural gas intelligence|rigzone|oilprice|barchart|daily coffee news|cotton grower|farm press|ethanol producer|"
        r"pork business|the pig site|farms\.com|world.grain|sosland|food business news|agrimoney|nasdaq|investing\.com|kitco|fastmarkets|"
        r"agricensus|spglobal|commodity|ag web|agri-pulse|agripulse|american ag network|rfd-tv|kfgo|farm news|country journal|agrolatam|notícias agrícolas|noticias agricolas"),
]
CONTEXT = (r"price|futures|market|crop|harvest|plant|acre|yield|export|import|shipment|sales|production|output|supply|demand|stock|inventor|"
           r"usda|wasde|\bice\b|cbot|nymex|tariff|\btrade|\bmills?\b|\bgin|bale|weather|drought|\brain|frost|\bheat\b|flood|forecast|deficit|surplus|grind|"
           r"arrival|crush|refin|opec|\brigs?\b|storage|\blng\b|barrel|bushel|tonne|\btons?\b|cash|basis|spread|rally|slump|slid|fell|\bfall|rise|\brose\b|gain|"
           r"drop|climb|surge|plunge|record|outlook|report|estimate|fund|speculat|cot\b|hedg|contract|cargo|freight|port|farmer|grower|ethanol|"
           r"biofuel|feedlot|slaughter|herd|cutout|disease|outbreak|subsid|policy|\bbans?\b|quota|duty|\bdeal|china|brazil|india|consum|inflation|dollar")
NEG = {
    "cotton": r"\b(tom|sen\.?|senator|aimee|rep\.?|mr\.?|ms\.?|judge|coach|officer|deputy)\s+cotton\b|cotton candy|cotton swab|cotton bowl|king cotton|"
              r"cotton ball|cotton club|cottonwood|cotton[- ]?tail|cotton mouth|cottonmouth|cotton on\b|egyptian cotton sheets|cotton (t-?shirt|dress|sheets|towel)",
    "sugar": r"blood sugar|sugar daddy|sugar land|sugar bowl|sugar ray|sugar[- ]free|sugary drink|diabet|sugar cookie|sugar rush|sugar glider",
    "coffee": r"coffee shop|coffee table|coffeehouse|barista|latte|starbucks (menu|drink|holiday)|coffee (recipe|maker|machine|mug)|best coffee",
    "cocoa": r"cocoa butter (lotion|skin)|hot cocoa (recipe|bar)|cocoa beach",
    "cattle": r"cattle call|cattle dog",
    "corn": r"corn ?hole|candy corn|corn dog|corn maze|corn nation|popcorn|cornhusker|cornell",
    "wheat": r"shredded wheat|wheat thins|buckwheat",
    "dairy": r"dairy queen|dairy[- ]free",
    "hogs": r"road hog|hog wild|harley|groundhog|hedgehog",
    "crude": r"crude (joke|humor|remark|language)",
}


NEG_ALL = (r"stock price & latest news|company profile|\bprofile\b|share price|\bltd\b|\(\w+\.(bo|ns)\)|digital edition|food banks?|donat|coupon|"
           r"scholarship|recipe|obituar|\baward|festival|county fair|pageant|queen|podcast episode|webinar|hall of fame|4-h|ffa\b")


def tier_of(source):
    s = (source or "").lower()
    for t, rx in TIER_RX:
        if re.search(rx, s):
            return t
    return None


def relevant_tags(text):
    """Commodity tags for a headline (plus teaser): the commodity word, a market context word, and none of the known false hits."""
    if not re.search(CONTEXT, text, re.I) or re.search(NEG_ALL, text, re.I):
        return []
    return [k for k, rx in TAGS.items() if re.search(rx, text, re.I) and not (k in NEG and re.search(NEG[k], text, re.I))]


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
    # commodity boards, exchanges, official statistics and trade data
    boards = ["usda.gov", "fas.usda.gov", "cftc.gov", "eia.gov", "theice.com", "ice.com", "cmegroup.com", "icco.org", "ico.org", "icac.org", "isosugar.org",
              "unica.com.br", "conab.gov.br", "cocobod.gh", "conseilcafecacao.ci", "cotton.org", "cottoninc.com", "opec.org", "iea.org", "mpob.gov.my"]
    bq = " OR ".join(f"site:{b}" for b in boards)
    url = f"https://news.google.com/rss/search?q={quote(f'({bq}) when:14d')}&hl=en-US&gl=US&ceid=US:en"
    x = fetch(url)
    if x:
        got = parse(x, "boards")
        items += got
        print("boards", len(got))
    for name, url in [("Brownfield", "https://www.brownfieldagnews.com/feed/"), ("farmdoc daily", "https://farmdocdaily.illinois.edu/feed")]:
        x = fetch(url)
        if x:
            got = parse(x, "feeds")
            for g in got:
                g["source"] = g["source"] or name
            items += got
            print(name, len(got))
    for src in (admis, rabobank):  # ADMIS commentary + Rabobank free research (headline, link, short teaser)
        try:
            items += src()
        except Exception as e:
            print(src.__name__, "failed:", e)
    df = pd.DataFrame(old + items)
    if df.empty:
        return
    df["key"] = df.title.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.slice(0, 90)
    df = df.sort_values("time", na_position="first").drop_duplicates("key", keep="last")
    df["time"] = df.time.fillna(pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%MZ"))
    cutoff = (pd.Timestamp.now("UTC") - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    df = df[df.time >= cutoff]
    if "teaser" not in df:
        df["teaser"] = None
    df["tier"] = df.source.apply(tier_of)
    df = df[df.tier.notna()]
    df["tags"] = df.apply(lambda r: relevant_tags(f"{r.title} {r.teaser if isinstance(r.teaser, str) else ''}"), axis=1)
    df = df[df.tags.str.len() > 0].sort_values("time", ascending=False)
    df["tier"] = df.tier.astype(int)
    rows = [{k: v for k, v in r.items() if not (k == "teaser" and not isinstance(v, str))} for r in df.drop(columns=["key"]).to_dict("records")]
    p.write_text(json.dumps({"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "items": sorted([x for x in rows if x["source"] not in ("ADMIS", "Rabobank", "Czapp")][:600] + [x for x in rows if x["source"] in ("ADMIS", "Rabobank", "Czapp")], key=lambda x: x["time"], reverse=True)}, ensure_ascii=False, indent=0))
    print("kept", len(rows), "items;", df.source.value_counts().head(12).to_dict())


if __name__ == "__main__":
    main()
