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
- Model logic: Ma chose (2026-10-19) to build everything in this public repo for now and split proprietary parts out later. Keep all model code under `models/` so it can move as one folder.

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
2. ~~Dairy v1~~ — done 2026-10-19.
   - Pipeline `.github/workflows/data.yml` (weekdays 20:20 UTC, Fri 21:40 UTC, and on pushes to pipelines/models/data/cme): `pipelines/usda_dairy.py` (AMS datamart all sections full history: NDPSR 2993, class 2991, advanced 2989, FMMO 3345–3462; ERS dairy supply/use CSVs), `pipelines/cot.py` (CFTC disaggregated F+O and futures-only, dairy + livestock), `pipelines/prices.py` (TradingView continuous 1!/2!; Class IV root is GDK).
   - Models: `models/dairy_class.py` (FMMO formulas by regime; rebuild matches every announced Class III/IV since 2013 to the cent; NDPSR month-to-date nowcast; futures-implied III/IV from CSC/CB/GNF/DY settlements), `models/dairy_sd.py` (ERS monthly balances, stocks/use metrics, WASDE balance and revisions read from BMR-Com/wasde-analytics data JSONs), `models/flows.py` (COT summaries/percentiles, curves, OI by month, option OI by strike; dairy and livestock).
   - Site: `index.html` + `assets/` — dairy tabs Primer (interactive class price calculator), S&D, Flows, Outlook (rule-based readout; Ma's written view from `data/dairy/outlook.md` if present). Needs GitHub Pages enabled (Settings → Pages → main, root).
   - Access notes: USDA hosts are blocked from the Claude workspace but open from GitHub Actions; WASDE CSV on usda.gov is 403 from Actions (use wasde-analytics outputs); NASS reports are open as text via esmis.nal.usda.gov (no key) — QuickStats would need NASS_API_KEY.
3. Dairy v2: NASS milk production / cold storage / dairy products (ESMIS text) to run the balance ahead of ERS; CME spot dairy (daily, via the browser collector); per-day production seasonal; GDT/EU prices for export parity.
4. Lean hogs, then cattle: datamart LM_HG201/2511 (CME Lean Hog Index rebuild), LM_PK602/2498 (pork cutout), LM_CT100/150, LSWFEDCC 2700, boxed beef 2453; NASS hogs & pigs, cattle on feed, slaughter (ESMIS); ERS meat supply & disappearance; CME Feeder Cattle Index (needs MARS key for auction data). Livestock flows JSON already builds.

## Testing framework (Ma, 2026-10-20)
These markets settle to USDA cash numbers, so models are judged on **convergence**: does a fundamental estimate of the final settlement beat the futures price at the time, and does (model - futures) predict (settlement - futures)? COT is secondary.
- Per-contract history incl. expired: `pipelines/contracts.py` → `data/contracts/<SYM>.csv` (TradingView; workflow `contracts.yml`, weekday evenings). Final close = final settlement.
- First-print NASS reports with true release dates: `pipelines/esmis.py` → `data/esmis/<slug>/*.txt`; parser `models/esmis_parse.py` (Hogs and Pigs done: 87 releases 2005–2026). NASS QuickStats/`load_time` are revised values and reload dates — never use them for backtests.
- Results so far:
  - Lean Hog Index rebuild (`models/hogs.py`) matches CME published values to the cent.
  - H&P weight-group slaughter forecast: MAPE 1.4–2.7% vs naive 3.1–3.7% (2015–26) — `models/hogs_sd.py` (still uses revised QuickStats inventories; switch to esmis_parse first prints).
  - Hogs convergence (`models/hogs_convergence.py` quarterly; `models/hogs_expiry.py` daily last 30 bdays): futures beat every cash/seasonal/supply/margin/weight model; blend weight 0. H&P vs trend barely predicts report-day moves (true surprise needs trade estimates).
  - Dairy convergence (`models/dairy_convergence.py`): futures beat NDPSR-based forecasts at all horizons (current month III: futures 7c vs 51c).
  - Systematic bias (`models/convergence_bias.py`): live cattle futures settle ~2–3% above their 20–60-bdays-out price in both 2010–17 and 2018–26 (quarter-clustered t 2.3–3.2); dry whey ~+3% from 60 days (weaker). NDM/Class IV discounts were 2010–17 only.
- Next: CME spot dairy daily (nightly collector) for front-month dairy; cattle model (COF placements/days on feed, 5-area cash, FCI) with the LE bias as a lead; MARS key in repo returns "User is not found".

## Grains desk (built overnight 2026-10-20)
- Workflows: `grains.yml` (NASS crop progress/condition + annual acreage/yield/production, batched per commodity/year/level, completed years stored once: `data/grains/raw/crop_progress/<crop>/<year>.csv`, `data/grains/raw/annual/...`), `grains_trade.yml` (FGIS inspections → weekly aggregates `data/grains/raw/inspections/weekly_CY*.csv`; FAS export sales need a `FAS_API_KEY` secret in this repo — not set yet; FAS daily flash page blocks GitHub runners → collect via Ma's browser later), `contracts.yml` (now incl. ZC ZS ZM ZL ZW KE), `data.yml` (COT/prices incl. grains; ESMIS incl. crop-production, grain-stocks, acreage, prospective-plantings, crop-progress).
- Models: `grains_wasde.py` (US/world balances with revisions from wasde-analytics; US rows filtered to domestic units and rounded to published precision — the source mixes metric/bushel and conversion noise), `grains_exports.py` (inspection pace vs USDA; calibrated inspections→Census ratio), `grains_condition.py` (condition index → yield deviation from trend; LOYO backtest vs trend and USDA same-date forecast), `grains_tests.py` (WASDE revision momentum, tests HTML), `flows.py` grains group (COT, curves, OI, options, relative value, seasonality), `convergence_bias.py` incl. grains.
- 2026-10-20 fix: wasde-analytics stores some years' US exports/production/stocks only in MMT (world-table key collision). These are now converted to bushels (`MT_CONVERT` in grains_wasde.py) instead of dropped: corn/soy/wheat history went from ~10 to 16+ years. All findings below are re-run on the full history.
- Findings: corn S/U-price fit elasticity −0.83 (R² 0.73), wheat R² 0.43, soy 0.27, meal/oil ~0. WASDE revision momentum: soy crush 74%, meal exports 71%, corn ethanol 68%, corn/soy exports 66–67% (was 79% on the partial history); yield/production ~coin-flip.
- Export sales (FAS ESR, `models/grains_sales.py`, live 2026-10-20): commitment-implied exports call the direction of USDA's next export revision 82% corn, 82% soy, 73% meal, 80% oil, 72% wheat (weekly readings, 14 MYs; 79–90% when gap >3%). Strongest tested signal on the grains desk. Level forecast worse than USDA. Price: corn gap vs next-4-week return corr 0.24 non-overlapping but all post-2018 (−0.04 before), 7/14 years positive, sign-trade t 0.75 — not robust; soy 0.19, more consistent but weak (t 0.9). Release-day reaction to net sales vs 4-wk avg: nothing. Inspections pace: revision hit 62% corn, 73% soy, 67% wheat. Price tests now start at the release day (an earlier version had a one-week look-ahead).
- Site: `assets/grains.js` — Corn, Soybeans, Meal, Oil, Chicago wheat, KC wheat × 4 tabs; primer has balance what-if (S/U fit) and board crush calculator. Wheat tabs use the all-wheat WASDE balance (class balances not in wasde-analytics after 2013/14).
- Condition → yield (corn, live 2026-10-20): best week 34; LOYO over 29 years MAE 4.37 bu/ac vs 6.54 for trend, direction right 72%; but USDA's same-date forecast is better (3.62 vs 4.41 on 17 common years). 2026: model 183.0 vs USDA 181.2, trend 185.8. Soybeans (week 37): MAE 1.36 vs 2.08 trend, direction 76%; on common years model 1.22 vs USDA same-date 1.29 — the one place the condition model edges USDA. Winter wheat (week 22): 2.12 vs 2.78, 79%; spring wheat (week 29): 2.39 vs 4.02, 86% (no USDA same-date comparison for wheat yet). Winter wheat uses crop-year weeks (fall ratings = negative weeks). Spring wheat shown on wheat tabs.
- Open: FAS_API_KEY secret (export sales), FAS flash sales via Ma's browser (fas.usda.gov newsroom "Private Exporters Report Sales Activity"), trade-estimate data for report-surprise tests, wheat class balances.

## Flash sales, price index fix (2026-10-20)
- FAS daily export sales announcements: collected in Ma's Mac browser (fas.usda.gov allowed for the built-in browser; GitHub runners get 403). `cme/collect_flash.js` (newest 3 listing pages + full text of truncated teasers) → `pipelines/flash.py` → `data/grains/raw/flash/{announcements.json,flash.csv}`. Nightly task step 5. Backfill 2012→now: 1,296 announcements, 1,571 sales parsed; 559 pre-2024 multi-sale posts only partly parsed (FAS rate-limits detail pages with 403 after ~150 quick requests — refetch slowly some day).
- `models/grains_flash.py`: tally vs prior years, China share, sales since the last ESR week (feeds the next weekly report), event test. Result: announcement days show no excess front-month move for corn/soy (t < 1); wheat's rare big sales +1.25% (n=12, t 2.3, small sample).
- `cot_backtest.roll_adjusted_index` rebuilt from per-contract closes (data/contracts): physical contracts roll on the 20th of the month before delivery, cash-settled 5 trading days before expiry; starts 2006. The old TradingView c1/c2 roll detection decayed corn/wheat toward zero (−0.2 to −0.36%/day). All price tests re-run: dairy COT extremes still persist (Class III/IV after extreme longs t≈2, cheese after extreme shorts t≈−2.5); grains sales-gap → 4-week price corr 0.16 corn / 0.14 soy non-overlapping, not robust (7/14 years, sign-trade t < 1).

## AMS MARS (key works since 2026-10-20), basis, dairy spot
- `pipelines/ams_mars.py` (AMS_API_KEY; history from mid-2020): CME daily spot dairy 1603, Iowa 2850 / Illinois 3192 / Gulf 3147 / IA-MN barge 3043 / KC wheat 3223 / Minneapolis 3046 / Portland 3148 bids, ethanol 3617, Mexico feeder imports 3486, beef drop value 2829 → `data/ams/<name>/<year>.csv`. Daily in data.yml; `ams.yml` = backfill with a commit per report.
- `models/grains_basis.py`: spot basis series (Gulf, N. Illinois River barge, Iowa interior, Chicago SRW, Gulf SRW, KC HRW 11%), seasonal by year, convergence test (basis vs its same-week norm → nearby-next spread change and nearby futures over 20 trading days). Spreads: nothing. Corn river/interior basis → nearby futures corr ~0.22–0.27 non-overlapping, strongest fifth +4.0% vs weakest −1.9%, 6/7 years — only ~40 independent windows, indicative only.
- Dairy: weekly NDPSR cheese now blends blocks with moisture-adjusted barrels +3¢ before June 2025 (matches announced monthly cheese to 0.4¢; was blocks-only, 4–5¢ off). Current-month fundamental Class III error falls from 0.51 to 0.26 $/cwt; futures still 0.07. `models/dairy_spot.py`: CME spot-informed nowcast is no better than carrying the latest NDPSR week; futures beat both.

## Price & technicals (2026-10-20, Ma: "price chart just the way you did for cotton")
- `pipelines/ohlc.py` (TradingView, in data.yml): continuous front + next 5–6 live contracts OHLCV → `data/ohlc/<SYM>.csv`.
- `models/technicals.py`: indicator/rating/levels code ported from cotton-crop-progress/scripts/build_technicals.py (units per contract), calendar spreads between live contracts, seasonality/percentiles from data/contracts aligned on weeks to last trade → `data/technicals/<SYM>.json`.
- `assets/tech.js` (Tech.mount): the cotton technicals page as a panel at the top of every Outlook tab (dairy has a market picker for all six contracts; cattle LE/GF). Uses lightweight-charts 4.1.3 + Chart.js.
