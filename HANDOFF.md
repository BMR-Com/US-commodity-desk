# US Ags Desk — build notes (handoff)

Status as of 2026-10-19. Read this first when picking the work up in a new session.

## Goal
Research desk for CME-listed US ags, one section per commodity with 4 tabs:
1. **Primer** — what the contract is and how it settles, interactive; how each S&D line moves price; links to other commodities.
2. **S&D** — balance built from USDA data, updated as reports land.
3. **Futures, options & COT flows** — kept separate from price charts.
4. **Outlook** — synthesis of 1–3.

Order: **dairy** (Class III/IV milk, cheese, butter, NDM, dry whey) → **lean hogs** → **live & feeder cattle** → **grains & oilseeds** (cotton-desk style: WASDE, weekly export sales, inspections, daily flash sales).

## Data sources (probed from GitHub Actions, see `probe/` branch)
| Source | Access | Use |
|---|---|---|
| USDA mandatory price reporting datamart `mpr.datamart.ams.usda.gov/services/v1.1/reports` | open, no key | LM_HG201 (2511, hog index), LM_PK602 (2498, pork cutout), LM_XB403 (2453, boxed beef), LM_CT100/150 (2466/2477, fed cattle), NDPSR (2993), class prices (2991), advanced prices (2989), FMMO utilization/components (3345–3462) |
| TradingView (tvdatafeed) | open | futures daily: CME LE, HE, GF, DC, CSC, CB, GNF, DY, CBOT ZC/ZS/ZM/ZL/ZW, KE; per-contract e.g. LEZ2026. Class IV symbol still to find |
| Yahoo Finance | open | live/regular futures prices (same approach as cftc-cot-full) |
| CFTC Socrata | open | COT codes: Class III 052641, Class IV 052644, NDM 052642, dry whey 052645, butter 050642, cheese 063642, lean hogs 054642, live cattle 057642, feeder cattle 061641 |
| USDA MARS API | key `AMS_API_KEY` (secret to add) | feeder cattle auction reports (Feeder Cattle Index inputs), other Market News |
| USDA NASS QuickStats | key `NASS_API_KEY` (secret to add) | milk production, dairy products, cold storage, cattle on feed, hogs & pigs, slaughter |
| USDA FAS export sales API | key `FAS_API_KEY` (secret to add) | weekly export sales; weekly report text, daily flash sales and FGIS inspections are public without a key |
| cmegroup.com | **blocked from GitHub runners** (timeouts) | daily volume / open interest and settlement CSVs must come through the user's browser |

## Decisions from Ma (2026-10-19)
- CME open interest and settlements: download via browser on a schedule (needs a session linked to Ma's computer / Chrome), push into this repo.
- Prices: Yahoo or TradingView; futures/options flow charts separate from price charts.
- Learning sources: CME Institute courses (livestock, dairy, grains), ADMIS livestock/grains dashboards (commentary only, no data files), other broker free data.
- Methodology/model logic should stay out of this public repo where possible (BMR-Com rule); open question whether to compute in a private repo and publish outputs here.

## CME via browser (working 2026-10-19)
CME's own JSON endpoints work from a browser tab on cmegroup.com (same-origin fetch); no CSV downloads needed.
- Trade dates: `/CmeWS/mvc/Volume/TradeDates?exchange=CME|CBOT` (reportType PRELIMINARY/FINAL)
- Futures volume/OI by month: `/CmeWS/mvc/Volume/Details/F/{fut_id}/{YYYYMMDD}/P?tradeDate=...`
- Options volume/OI by strike, calls/puts: `/CmeWS/mvc/Volume/Details/O/{opt_id}/{YYYYMMDD}/P?tradeDate=...`
- Futures settlements: `/CmeWS/mvc/Settlements/Futures/Settlements/{fut_id}/FUT?strategy=DEFAULT&tradeDate=MM/DD/YYYY`
- Product IDs: in `cme/collect.js` (note Class IV is GDK on Globex, futures 778 / options 779).
- `cme/collect.js` runs in the page and returns CSVs; gzip+base64 the result in the page (bridge caps a result at ~260k chars; one day of all 17 products is ~140 KB gzipped), then `python cme/ingest.py <payload>` writes `data/cme/<date>/`.

## Next steps
1. ~~CME courses, CME volume/OI + settlements, evening scheduled download~~ — done 2026-10-19. Dairy course notes in `notes/cme-courses.md`; livestock and grains courses listed there, to read in their phases. Scheduled task "CME ags evening volume/OI download" runs Mon–Fri 21:41 CT on Ma's Mac (built-in browser) and commits `data/cme/<date>/`. Ma chose to keep raw CME data in this public repo.
2. Dairy pipeline: NDPSR weekly, class/component prices monthly, Class III/IV rebuild from NDPSR using the post-June-2025 FMMO formulas (verify against AMS), futures from TradingView/Yahoo, COT.
3. Dairy primer + S&D tab once NASS key is in place.
