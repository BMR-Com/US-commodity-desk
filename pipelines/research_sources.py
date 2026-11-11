"""Research sources added to the news feed (2026-11-11): ADMIS daily commentary and Rabobank (RaboResearch) free articles.

Both are read through the publishers' own public JSON endpoints (ADMIS: WordPress REST API; Rabobank: the search API
behind rabobank.com/knowledge). Only headline, link, time and a short publisher teaser (<= 60 words) are kept, for the
daily digest; the desk pages show headline and link. Rabobank items marked Exclusive (login) are skipped.
"""
import html, re
import requests

H = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk; +https://bmr-com.github.io/US-commodity-desk/)"}
ADMIS_CATS = {748: "softs", 23: "grains", 12: "livestock", 14: "energies"}
RABO_ENTITIES = ["globalsites.article", "globalsites.article-in-depth", "globalsites.article-quick-read-in-depth",
                 "globalsites.knowledge-bundle", "globalsites.podcast-article", "globalsites.video-article"]
RABO_SECTORS = ("agricommodit", "sugar", "grains", "oilseed", "dairy", "animalprotein", "farminputs", "beverages|coffee", "cocoa", "cotton")
RABO_WORDS = r"coffee|cocoa|sugar|cotton|ethanol|grain|wheat|corn|maize|soy|oilseed|palm|dairy|milk|beef|cattle|pork|\bhogs?\b|fertili|commodit|COT\b|freight"


def _clean(s, words=60):
    t = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    t = re.sub(r"\s+", " ", t).strip()
    w = t.split(" ")
    return " ".join(w[:words]) + ("…" if len(w) > words else "")


def admis(per_cat=20):
    out = []
    for cid, cat in ADMIS_CATS.items():
        try:
            r = requests.get("https://www.admis.com/wp-json/wp/v2/posts", headers=H, timeout=30,
                             params={"categories": cid, "per_page": per_cat, "_fields": "date_gmt,link,title,excerpt"})
            r.raise_for_status()
            for p in r.json():
                out.append({"title": _clean(p["title"]["rendered"], 40), "link": p["link"], "source": "ADMIS",
                            "time": p["date_gmt"][:16] + "Z", "topic": "admis:" + cat,
                            "teaser": _clean(p.get("excerpt", {}).get("rendered"))})
        except Exception as e:
            print("ADMIS", cat, "failed:", e)
    print("ADMIS", len(out))
    return out


def rabobank(pages=2, size=50):
    out = []
    for pg in range(pages):
        body = {"advancedQuery": [{"category": "sectors", "keywords": ["foodagribusiness"]}], "countryCode": "global",
                "entityTypes": RABO_ENTITIES, "languageCodes": ["en"], "paging": {"pageSize": size, "pageNumber": pg},
                "site": "www.rabobank.com", "sort": {"direction": "descending", "field": "DATE"}}
        try:
            r = requests.post("https://www.rabobank.com/wapi/global-sites/components/filters", json=body, headers=H, timeout=30)
            r.raise_for_status()
            res = r.json().get("results", [])
        except Exception as e:
            print("Rabobank failed:", e)
            break
        for it in res:
            raw = it.get("raw", {})
            if (raw.get("hassecurecontent") or ["false"])[0] == "true":
                continue  # Exclusive: login only
            sect = " ".join(raw.get("sector") or [])
            text = f"{it.get('title', '')} {raw.get('intro', '')}"
            if not (any(s in sect for s in RABO_SECTORS) or re.search(RABO_WORDS, text, re.I)):
                continue
            out.append({"title": _clean(it.get("title"), 40), "link": "https://www.rabobank.com" + it.get("clickUri", ""),
                        "source": "Rabobank", "time": (raw.get("created") or "")[:16] + "Z", "topic": "rabobank",
                        "teaser": _clean(raw.get("intro") or raw.get("description"))})
        if len(res) < size:
            break
    print("Rabobank (free, ag)", len(out))
    return out
