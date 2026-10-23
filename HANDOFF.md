# US Commodity Desk — build notes (handoff)

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

## COT desk (2026-10-20, Ma: "more detailed like cot full repo … under water … next level for CTAs")
- `models/cot_desk.py` → `data/cot_desk/<SYM>.json` + `summary.json`; `assets/cotdesk.js` (CotDesk.mount) at the top of every Flows tab.
- Positioning by all five trader groups (percentiles 1/3/5y/all, COT index, z, streak, traders, top-4/8 concentration, driver), $ exposure and flows.
- Money under water: LIFO cost layers of MM gross longs/shorts on nominal front-month closes over 2 years; % under water, open P&L, half-under-water level, ±15% grid.
- CTA: trend score (sign of 20/60/120/250-day returns, roll-adjusted), MM-net-vs-score fit (R² 0.45–0.74 grains/meats, weak in dairy: flagged), 2-week flow sensitivity (corr 0.5–0.67), flip levels per lookback with flow if flipped, ±10% scenarios, breakout/MA triggers on the tradable contract, next trigger up/down.

## Running without Claude + summary page (2026-10-20)
- Everything except CME and FAS flash runs in GitHub Actions. Probe (2026-10-20): cmegroup.com returns 403 "IP blocked … web scraping" to GitHub runners (requests and headless Chromium); fas.usda.gov returns Akamai Access Denied.
- `pipelines/tv_settle.py`: TradingView settlements written to data/cme/<date>/fut_settlements.csv with a SOURCE marker for dates the CME download is missing (weekdays, settled bars only); cme/ingest.py removes the marker when real data arrives. flows.py OI/options use real CME days only.
- `local/mac_collector.py` + `local/install_mac.sh`: launchd job on Ma's Mac (weekdays 9:35 pm), Playwright with installed Chrome, runs cme/collect.js and cme/collect_flash.js, ingests, pushes. Replaces the Claude scheduled task once installed (the Claude task can then be disabled).
- `models/summary.py` → data/summary/summary.json; `assets/summary.js` is the landing page (nav "Summary"): per market fundamentals / technicals / flows paragraphs, overall view (40/30/30 weights, conviction from agreement), levels to watch, trade ideas by method with how each method has tested.

## Morning brief and export-sales timing (2026-10-21, Ma: "daily morning brief … before 8am ET"; "export report at 9 instead of 8:30")
- `models/morning_brief.py` → `data/brief/latest.{json,md}` + archive `data/brief/<date>.md`: key points (overnight movers, today's reports, fresh flash sales, strongest views, trend-trigger breaks), calendar (today + 4 days, ET), key numbers for all 12 markets (last vs prior settle, 1w/1m, rating, RSI, support/resistance, CTA triggers, funds net and weekly change, CME OI change, desk view), board crush and ratios, technical outlook + flags + headlines per market. Shown as the first card on the Summary page.
- Workflow `brief.yml`: daily 10:35 and 11:35 UTC (both before 8 am ET in either season): ohlc → technicals → news → calendar → trader_sheet → summary → brief. No `tv_settle` here (a morning bar is not a settlement).
- Weekly export sales: `grains_trade.yml` now runs Thursday 12:31 and 13:31 UTC with `grains_trade.py export_sales_release`, which polls the FAS API every 2 min (up to 45) until the new week (previous Thursday) appears, then fetches and rebuilds the ESR brief, trader sheet, summary and morning brief. A run before 8:25 ET exits (DST twin). 14:00 UTC weekday run catches holiday-shifted Friday releases; 17:30 UTC Thursday stays as a backstop. Before this the first Thursday pull was 14:00 UTC (10 ET in daylight time).

## Prices from Yahoo, Markets & macro tab, US/China calendar (2026-10-21, Ma: "use Yahoo since it is free")
- Data source notes: Yahoo Finance (free; Yahoo's exchange page: CBOT/CME 10 min delayed, NYMEX/COMEX/ICE US 30 min, FX real time, S&P/Dow/Nasdaq indices real time) — checked from Actions: ZC=F last trade ~10 min old. TradingView via tvdatafeed (no login) is also free and ~10 min delayed for CME, but it is an unofficial library. FRED is blocked from Actions (timeouts); investing.com 403; US Treasury yield-curve CSV works.
- `pipelines/ohlc.py`: Yahoo first (ZC=F 10y continuous; contracts as ZCZ26.CBT / LEZ26.CME / CTZ26.NYB), TradingView only as fallback per series. `contracts.py` (expired contracts) and `prices.py` stay on TradingView: Yahoo has no expired-contract history.
- `pipelines/markets.py` → `data/markets/markets.json` + `closes.csv`: 74 instruments (energy, metals, grains, softs, livestock & dairy, GSCI, US/world indices, FX incl. BRL/MXN/CNY/ARS, US yields 13w/2y/5y/10y/30y, T-note/bond futures) + Treasury par curve and 2s10s. Futures changes use the front contract's own history (=F rolls show as fake moves, e.g. Class III Oct→Nov +17%).
- `pipelines/econ_calendar.py` → `data/macro/econ_calendar.json`: Forex Factory weekly export, US/China/Global, forecast + previous (no actuals in the export), with "why it matters for commodities". `models/macro.py` → `data/macro/macro.json`: rule-based macro read (rates, dollar, BRL, MXN, risk, energy, China, breadth) → tailwind/headwind for ags; untested context.
- `markets.yml` hourly 11–22 UTC weekdays + Sunday 23 UTC; brief.yml also runs markets/calendar/macro. Site: "Markets & macro" tab (heat map with 1d…1y toggle and table view, Treasury curve, 2s10s, calendar). Morning brief has macro + US/China releases sections; the 7:46 ET task adds actual results and news.
- Fixed all workflows' commit loops: `git rebase --abort` with no rebase in progress exited the step under `bash -e`, so a push race failed the run.

## Geography, trade & weather primer (2026-10-21, Ma: maps, trade flows, top exporters/destinations, weather vs history)
- `pipelines/geo.py` (steps psd comtrade nass usdm): USDA PSD bulk zip (free) → production/exports/imports by country; UN Comtrade public preview API (free, ~1 call/3 s) → bilateral exports of the top exporters by HS code (EU = reporter 97, extra-EU); NASS QuickStats state data (cotton, hogs Dec 1, cattle Jan 1, milk, cheese, corn/soy/wheat/sorghum); U.S. Drought Monitor state stats (aoi = state FIPS). Raw → `data/geo/raw/`.
- `pipelines/geo_weather.py`: 46 crop regions (US for comparison; Brazil, Argentina, China, India, Pakistan, Australia, EU, Russia, Ukraine, Canada, NZ) from Open-Meteo: rain 30/60/90 d and season to date vs 2011–25 with percentiles, water balance (rain − ET0), Tmax anomaly and hot days, ERA5-Land soil moisture percentiles, 16-day forecast vs normal, weekly charts. 15-year histories cached once in `data/geo/weather_hist/*.csv.gz`; GEO_WX_NEW=8 new regions per run (Open-Meteo free limit ~10k weighted calls/day), so all regions have history after ~6 daily runs.
- `models/geo.py` → `data/geo/<key>.json` (corn, soybeans, meal, oil, wheat, cotton, pork, beef, milk, cheese, butter, nfdm): countries ≥7% of world output shaded on the map, table ≥1%; top 5 exporters, top importers; flows; US top-10 destinations from ESR (ESR now also pulls cotton 1404/1301, beef 1701, pork 1702) or Comtrade for dairy; US states; weather regions for ≥7% producers and top-5 exporters; weather/crop websites by country. USDA IPAD Crop Explorer is retired (503) — not linked.
- `assets/geo.js` (d3 + topojson from jsdelivr, world-atlas / us-atlas): tab "Where it's grown, trade & weather" in grains (per commodity; KC uses wheat), cotton, hogs (pork), cattle (beef), dairy (milk/cheese/butter/NFDM picker). `geo.yml`: daily 10:20 UTC (weather + USDM), Mondays full refresh.

## Options pricer (2026-10-21, Ma: "option pricer as separate tab … IV/RV stats … strategies … payoff … Greeks")
- `models/vol.py` → `data/vol/vol.json` (in brief.yml and data.yml after technicals): per live contract HV10/20/30/60/90 and Parkinson-20 from Yahoo daily bars, estimated option expiry (exchange rules, holidays ignored) and days left; per market 20-day vol percentile (1y/5y), vol cone 10–120 d, monthly vol seasonality (continuous series with roll gaps > 4σ removed); contract multipliers and strike steps; rate = ^IRX.
- `assets/options.js` (top tab "Options pricer"): Black-76 (European approximation of American options on futures), 24 strategy presets + custom legs (calls/puts/futures, per-leg vol), payoff at expiry and after N days with vol shift, Greek-vs-price chart, position and per-leg Greeks in $ per lot.
- No free implied vol for CME ag options. Next step: add CME option settlements to the nightly browser collector (`/CmeWS/mvc/Settlements/Options/...`) and back out IV per strike with Black-76 for a real skew/term structure.
- Yahoo `range=max` returned weekly bars for some contracts; ohlc now uses 2y for contracts and falls back to TradingView if bars are not daily.

## CME option settlements and implied-vol desk (2026-10-21, Ma: "download CME option settles daily … implied vol stats")
- Endpoints (browser, same-origin): `/CmeWS/mvc/Settlements/Options/TradeDateAndExpirations/{fut_id}` (option types; use optionType AME = standard American monthlies; expirations with contractId and the last 5 trade dates), `/CmeWS/mvc/Settlements/Options/Settlements/{opt_pid}/OOF?strategy=DEFAULT&optionProductId={opt_pid}&monthYear={contractId}&optionExpiration={opt_pid}-{code}&tradeDate=MM/DD/YYYY&pageSize=500`, `/CmeWS/mvc/ProductCalendar/Options/{opt_pid}` (exact last trade dates). Grain prices in cents and eighths ("242'1" = 242.125), grain strikes in $/bu; "CAB" = cabinet.
- `collect_options.js(DAYS, MAXEXP, GAP, HAVE)`: the nightly task passes DAYS=3 and HAVE from `python3 cme/options_have.py`, so a day CME cut off is filled on the next run; pacing uses a MessageChannel loop because background tabs throttle setTimeout to about once a minute. CME lists a trade date for option settlements only the next morning, so the task runs at 06:11 CT Tue–Sat.
- CME.s edge blocked the browser after ~300 quick requests on 2026-10-21 (all fetches "Failed to fetch", page would not load for a while). `cme/collect_options.js` spaces requests (0.7 s), fetches the nearest 10 expiries, and stops after repeated failures; run it last in the nightly task, without awaiting, and poll.
- `cme/ingest_options.py <payload>` → `data/cme/options/<YYYYMMDD>/<SYM>.csv.gz` with Black-76 IV, delta, gamma (serial grain options map to the next futures month). Backfilled 2026-10-14..20 for DC, GDK, CSC (and CB 10-19/20) before the block.
- `models/options_desk.py` (data.yml) → `data/options/<SYM>.json`: per expiry ATM IV, 1d/1w change, 25Δ RR/fly, expected move, RV20 and IV−RV, OI/P-C, walls, max pain, gamma peak; term structure and smiles now vs a week ago; strike map; IV history (`data/cme/options/iv_history.csv`, accumulates daily). Options tab shows it and the pricer can price off a CME series with leg vols from the smile.

## Crop calendars by country (2026-10-21, Ma: "harvest calendar … each country which stage … weather impact … compare historical")
- `models/crop_calendar.py`: stage windows per commodity and country (after USDA FAS/IPAD and GEOGLAM crop calendars; IPAD itself is retired) with stage sensitivity and what matters; maps each country to its Open-Meteo regions; `read()` turns stage + weather percentiles into an impact line.
- `models/geo.py` adds `calendar` to each page: stage now / next, weather impact, region readings, PSD production, yield and area vs last year and the 5-year average with a 10-year yield series. Front end: "Crop calendar and conditions by country" card (12-month stage grid with this month marked, one panel per country).
- Pork has no crop calendar (supply follows herds and feed); beef and dairy use pasture/milk-season calendars.

## US economic snapshot (2026-10-21, Ma: "US economic snapshot … do we need any API … focus only on USA")
- `pipelines/us_macro.py` → `data/macro/us_econ.json`, no keys: BLS public API v2 (CPI, core, food at home, energy, PPI final demand/core/farm, payrolls, unemployment, AHE, participation; no-key limit 25 requests/day, so markets.yml runs it at 13 and 19 UTC only), BEA via DBnomics (real GDP and consumer spending q/q ann., PCE and core PCE price index → y/y, saving rate), UMich sentiment via DBnomics, NY Fed (EFFR, target range, recent moves, SOFR), Treasury real yields (TIPS) → 10-yr real yield and breakevens. ISM is licensed and the DBnomics mirror is stale → calendar only. FRED would need a free API key and fred.stlouisfed.org times out from Actions; BLS/BEA/Census release-schedule pages are 403 from Actions; CME FedWatch blocked.
- Economic calendar is now US only. Markets & macro tab: "US economy snapshot" card (rates tiles, inflation/jobs/growth/sentiment tiles with sparklines and next release); morning brief has a "US economy" paragraph.

## Energy desk (2026-10-21, Ma: "bring the natgas repo features into this desk … I will provide the API key as a secret")
- `energy.html` = the BMR-Com/natgas terminal (gas storage, S&D, STEO, gas-weighted degree days, weather-driven storage model, storage-implied fair value, oil stocks, refining and cracks, prices, technicals, COT desk, ETF options, signal scorecard), served from this repo. Change: `loadSeries` reads `data/energy/eia/<k>.json` first (no key needed in the browser); a pinned ID or a missing file falls back to the browser key. CFTC and Open-Meteo are still called from the page (CORS-enabled). Shown inside index.html as the **Energy** tab (iframe, lazy-loaded; `#energy/<tab>` deep-links a sub-tab, e.g. `#energy/gstor`); when framed, energy.html hides its brand and its Options & IV / Markets & macro links switch the parent tab via postMessage. Still opens standalone too.
- `pipelines/energy_eia.py` (EIA_API_KEY secret) fetches the terminal's 52 SPECS (`pipelines/energy_eia_specs.json`, extracted from the page) with the same ID-then-name-match fallback → `data/energy/eia/`. `pipelines/energy_prices.py` = natgas fetch_data.py → `data/energy/prices.json`, `options.json`. `models/energy_summary.py` → `data/energy/summary.json` (storage vs 5-yr, crude/products, cracks, IV vs RV) for the morning brief "Energy" section. Workflow `energy.yml`: weekdays 22:40 UTC, Wed/Thu after the EIA weekly reports.
- Ags-desk analytics extended to NG, CL, HO, RB: contracts (TV, from 2015) and ohlc (Yahoo .NYM), technicals, realized vol (vol.py with NYMEX option expiry rules), CFTC COT (cot.py codes; cot_desk group "energy"), CME futures volume/OI/settlements (collect.js, NYMEX ids 444/425/426/429) and CME option settlements → implied-vol desk + pricer (collect_options.js, options_desk.py). Options tab deep link: index.html#options/NG.

## Storage retention (2026-10-21, Ma: "auto delete after 6 months or convert so size stays small")
- `pipelines/retention.py` runs in every data.yml run (idempotent). Deletes `data/cme/<YYYYMMDD>/`, `data/cme/options/<YYYYMMDD>/` and `data/brief/<date>.md` older than 183 days (`KEEP_DAYS`); before deleting CME futures days it appends per-symbol total OI/volume to `data/cme/oi_history.csv` (flows.py merges it into the OI history). Option IV stats persist in `iv_history.csv`.
- Archives read only by Python are gzipped: `data/esmis/*/*.txt.gz` (esmis.py writes .gz; `esmis_parse.read()`), `data/grains/raw/crop_progress|annual/*/<year>.csv.gz` (crop_progress.py writes .gz). First run cut data/ from 529 MB to 324 MB; model outputs verified identical.
- Cotton crop progress, ginning and classing are not stored here: the Cotton tab frames the BMR-Com/cotton-crop-progress site.

## Research signals (2026-10-21, Ma: "apply the relevant learnings from these files [research summaries library] for each commodity")
- Library: iCloud `drive-summaries 2/Summaries` (620 summaries, mostly equity quant). The 36 that transfer to futures (commodity futures, TSMOM/trend, vol/options, sizing, execution, backtesting) were read and applied.
- `models/research.py` -> `data/research/research.json`; runs in data.yml (after options_desk) and contracts.yml. UI: **Signals** tab (`assets/signals.js`, `#signals/<SYM>`): cross-market table plus per-market detail (trend/TSMOM with 40% EWMA vol scaling, variance-ratio signature, information discreteness, GR roll-adjusted excess returns, carry with calendar-month percentile and seasonal adjustment, GHR cross-section ranks and tercile backtests, inventories from WASDE/EIA, IV-RV and IV² − RV², term slope, Breeden-Litzenberger density with tail ratios vs lognormal, COT crowding, crash/whipsaw flags, vol-target sizing, inverse-vol weights, half-Kelly upper bound, sqrt impact). Each item cites its paper; the morning brief adds a "Research signals" line per market.
- Density: quadratic smile in log-moneyness fitted to OTM settles above 1.5x the minimum tick (min-tick settles inflate wing IVs), flat wings, uniform strike grid; rejected if the density does not price the future within 1%.

## COT (full) tab and desk chatbot (2026-10-21, Ma: "port cftc cot full as a separate tab … all tabs … AI chatbot … I have a Groq API key, free version")
- `cot/` = BMR-Com/cftc-cot-full copied as-is (index.html, js/, tabs/, scripts/; copied from the live Pages site since the repo is outside this session's GitHub scope). Tabs: Summary & Ideas, COT Analyzer, Scatter, Index (CIT), Triggers & Flows, Seasonality, Custom Formula (AI Analysis tab removed 2026-10-21 at Ma's request). Shown in index.html as **COT (full)** (iframe, `#cot/<tab|ticker>`); framed mode hides its brand.
- `.github/workflows/cot_full.yml`: Fri after the CFTC release + retries (Fri eve, Sat, Mon) and weekday prices; runs cot/scripts prices.py → fetch_cit_data.py → fetch_cot_data.py (builds cot/data/latest_summary.json and cot/data/web/). The big CSVs (bcom_cot_master ~34 MB, CIT, prices) are kept in the Actions cache (restore/save, key cot-work-<run>), not in git (.gitignore); a cache miss just rebuilds from the CFTC API since 2006.
- Chatbot: `assets/chat.js` ("💬 Ask the desk", every tab). `models/ai_context.py` → `data/ai/context.json` (cards: overview, all-markets table, one per market from brief/summary/research/options/geo, export sales, WASDE, COT full, research method). Per question the page sends the overview + table + best alias-matched cards (≤16k chars) + text of the open tab (≤3.5k chars) to Groq (`llama-3.3-70b-versatile`, falls back to Llama 4 Scout / GPT-OSS 120B / Llama 3.1 8B on 429/413/5xx). Key pasted once in the chat settings; stored in the browser only; never in the repo. Runs in data.yml, contracts.yml, brief.yml, cot_full.yml.
- Chat proxy (Ma: "save the Groq key in secrets … rate limit anyone doing more than 500"): `worker/chat-proxy` (Cloudflare Worker, free plan) holds GROQ_API_KEY, checks per-user access codes (secret DESK_USERS = "name:code;name2:code2") and counts questions per user per UTC day in a SQLite Durable Object (DAILY_LIMIT 500 in wrangler.toml); falls back across Groq models server-side (one count per question). `.github/workflows/chat_proxy.yml` deploys it with cloudflare/wrangler-action@v3 when the four secrets exist (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, GROQ_API_KEY, DESK_USERS) and writes the Worker URL to data/ai/proxy.json; chat.js then asks for user name + access code instead of a Groq key and shows "n/500 today". Without proxy.json it stays in bring-your-own-key mode.

## Energy tab rebuilt as a full section (2026-10-21, Ma: "primers, trade flows, production, LNG terminal maps … news and calendar … price charts … everything")
- `assets/energy_desk.js`: sub-tabs Energy terminal (energy.html frame) · Primer (NG/CL/HO/RB contract specs, price drivers, seasonality, ag linkages, key reports) · Production, trade & LNG (`assets/energy_geo.js`) · Price charts, technicals & COT (Tech.mount + CotDesk.mount NG/CL/HO/RB) · News & calendar (Intel). Hashes `#e-primer`, `#e-geo`, `#e-charts`, `#e-news`, `#energy[/<terminal tab>]`.
- `pipelines/energy_geo.py` (weekly, `energy_geo.yml`, EIA_API_KEY): EIA international crude production and petroleum consumption, US crude production by state, gas marketed production by state, US exports by destination (crude, distillate, gasoline), LNG and pipeline exports by point of exit and destination, refining capacity by state; OWID/Energy Institute gas production; UN Comtrade flows (HS 2709, 271111, 271121, 271019, 271012). `models/energy_geo.py` → `data/energy/geo/{crude,natgas,products}.json`; LNG terminal coordinates in TERMINALS.
- Calendar: EIA WPSR (Wed), storage (Thu), API (Tue), Baker Hughes (Fri), STEO/OPEC MOMR/IEA OMR (estimated), NYMEX last trade days. News: topics natgas/crude/products.
- Chatbot = live answers only (Ma: no predefined answers; ai_daily and its pre-written reads were removed). Two steps per question with the user's browser Groq key: a fast model reads the card catalogue (id | title | first line of data/ai/context.json) and picks up to 6 cards; the main model (best of the key's live /models list) answers from those cards + open-tab text + chart numbers, reasoning across them. Soft cap 1,000 questions/day per browser. Cloudflare proxy code stays dormant (Ma declined Cloudflare).
- Energy S&D and fair value (Ma: "do S&D for each energy commodity like the ags; fair value from storage / stock-to-use"): `models/energy_sd.py` → `data/energy/sd.json`, Energy > "Supply, demand & fair value". Per market: inventories vs same week of last 5 years (+ days of supply), seasonal chart, balance table (crude/distillate/gasoline weekly incl. EIA adjustment; gas monthly by sector in Bcf/d), NG end-Oct / end-Mar storage projection at the 5-yr pace. Fair value = 5-year rolling OLS: NG log front futures ~ storage % vs 5-yr + season (R² ~0.7, walk-forward gap closes); WTI M1−M2 ~ Cushing & crude vs 5-yr (outright WTI not modelled: R² ~0); Gulf Coast ULSD/gasoline cracks ~ days of supply vs 5-yr + season. Each shows a quality label (usable / partial / weak) and a walk-forward test. New EIA weekly specs: distProd, gasoProd, distExp, gasoExp, distImp, gasoImp; demGaso fixed to WGFUPUS2 (was total products supplied, also in energy.html).

- 2026-10-21: chatbot DISABLED at Ma's request (answers not good enough): `assets/chat.js` is no longer loaded by index.html and `models/ai_context.py` no longer runs in the workflows. Code and data/ai/context.json are kept; to re-enable, add `<script src="assets/chat.js"></script>` back to index.html and the ai_context step back to data.yml. The COT (full) tab's AI Analysis tab was removed too (cot/js/ai-tab.js, cot/tabs/ai-tab.html deleted).

## Backtest lab (2026-10-21, Ma: "run backtests … trend, COT, carry, 55-week breakout, fundamentals, low PMU long … hit ratio, drawdown, Sharpe per strategy … top 10 best/worst … new tab")
- `models/backtest_lab.py` → `data/backtest/lab.json` (+ `equity.json` monthly equity curves); weekly `backtest.yml` (Sat 15:30 UTC). UI: **Backtest** tab (`assets/backtest.js`, `#backtest/<SYM>`).
- 27 markets: desk 20 (daily roll-adjusted contracts, COT data/cot/*_fo.csv since 2006) + KC, SB, CC, GC, SI, HG, CO from cot/data/web/series (weekly px, roll gaps removed). ~30 rules per market (trend MAs, 20/55/100-day turtle, 55-week breakout/MA, TSMOM 3/6/12/12-1, COT extremes/flows/covering/liquidation/room-to-buy/crowded/commercials/producer longs, carry, carry x trend/COT, US stocks/use from PSD (final values: look-ahead caveat), seasonal, 3-family vote).
- No look-ahead: Friday information, executed at next trading day's close; 10% vol target per market, 5 bp per unit turnover (and 4x cost check); IS to 2018 vs OOS 2019+; noise bar sqrt(2 ln N)/sqrt(years) ≈ 0.82 for ~780 tests; event studies report fwd 4/13-week returns and managed-money response (Δ net % OI).
- Main findings (2026-10-21): trend/breakout rules are the only family with consistent positive median Sharpe (~0.2-0.3, positive in 75-90% of markets); COT rules alone ≈ 0 (fading extremes and following flows lose on median); specs DO cover after a 200-day cross from short (+2.9% OI in 4 weeks) but price does not follow on average; dairy (Class IV, butter, NFDM) trend rules Sharpe >1 out of sample (USDA-average settlement makes prices persistent; thin markets).
- Baskets (Ma: "basket of trades across commodities … low drawdown … 1-2 week signals … literature … dairy details"): `models/basket_lab.py` → `data/backtest/baskets.json`; Backtest tab sub-tabs Baskets / Single-market rules / Dairy deep dive (`#bt-baskets`, `#bt-rules`, `#bt-dairy`). 31 portfolio sleeves: cross-sectional carry, XS momentum 1/2/4/13/26/52 wk, 1-wk reversal, TS trend at 1/2/4/13/26/52 wk + blend, MA trend, carry x momentum, basis-momentum (Boons-Prado), hedging pressure (Basu-Miffre), spec liquidity provision (Kang-Rouwenhorst-Tang), skewness (Fernandez-Perez et al.), desk carry x spec-turn idea, carry x trend, dairy trend, fast ag trend, equal-risk long-only, and a blend of sleeves selected on 2008-18 only. Risk-weighted legs, basket vol-targeted to 10% on trailing 52 wk, 5 bp/unit turnover; gross Sharpe reported. Findings: dairy trend basket Sharpe 1.6 (2019+ 1.3); blend 0.93 (2019+ 1.0, DD -21%); 4-week TS trend 0.88 (2019+ 1.39, DD -18%); carry x trend 0.71; carry alone 0.30; positioning/flow, reversal, skew, fast ag trend negative after costs; desk carry x spec-turn idea fails 2019+.

## Technical pattern lab (Backtest → Technical patterns)
- `models/tech_lab.py` → `data/backtest/tech.json` (weekly in backtest.yml, ~1 min). Daily roll-adjusted closes for the 20 desk markets; ~55 patterns (RSI14/RSI2, % below 9-day MA, Bollinger, down-day runs, stochastic, trend pullbacks to 9/20/50-day, MACD/EMA/SMA crosses, 20/55-day breakouts, RSI/MACD divergences) × long/short × hold 5/10/20 days; next-close entry, non-overlapping, 5 bp/side; IS/OOS split 2019.
- Also: recovery-to-9-day-MA study (touch vs regain signal-day level) and uptrend dip-to-MA study.
- A "Top findings" card (built client-side from baskets.json + tech.json + lab.json) sits above the Backtest sub-tabs; long lists are collapsed in <details>.

## Recent-regime check (Backtest → 2020-23 vs 2024-25)
- `backtest_lab.WINDOWS` = fit 2020-2023, test 2024-2025, live 2026+. backtest_lab rows gain r_is/r_oos/live Sharpe, `hold_wk` (avg run of the same position) and `horizon` (short-term ≤2.5 weeks, else long-term); basket_lab sleeves gain r_is/r_oos/live stats, hold_wk (2×gross/weekly turnover) and three "recent blends" picked on 2020-23 only (all / short-term / long-term); tech_lab adds 40-day holds, per-window stats and `regime` (pooled + single-market, short vs long, flipped patterns, families).
- UI sub-tab `#bt-regime` is built client-side from lab.json, baskets.json and tech.json; ranking = the weaker of the two windows.

## Dairy weekly-to-monthly convergence lab (Backtest → Dairy deep dive, top)
- `models/dairy_arb.py` → `data/dairy/derived/dairy_arb.json`, run nightly in contracts.yml after the per-contract refresh.
- Daily nowcast of each open contract month (DC, GDK, CSC, CB, GNF, DY): published NDPSR weeks + unpublished weeks predicted from CME spot (data/ams/cme_daily_dairy, 2021+; OLS on same/1/2-week-earlier spot, refit monthly on past data); naive = last print carried. Evaluation uses traded days only (TradingView history repeats the last trade on no-volume days; the last row per contract is the final settlement and is excluded).
- Tests: accuracy by stage, gap trade on NDPSR release days to settlement (costs = 1 bid-ask: DC 0.05, GDK 0.10, CSC 0.005, CB/GNF/DY 0.5c; t-stats clustered by contract month), release-day reaction/drift, Class III/IV vs component-futures formula arbitrage (2012+, hedge ratios per 10 lots), live nowcast vs futures table.

## Contract specs on every primer
- `models/contract_specs.py` → `data/specs/specs.json` (nightly in contracts.yml; also after the Mac collector): standard / mini / micro contracts per market with size, tick, front price (data/technicals), contract value in $, 20-day typical daily move in $, CME maintenance margin for the front month (initial ≈ 110%), margin % of value, leverage. Cotton (ICE) has no flat published margin: shown as an estimate (99% two-day move), marked *.
- Margins: `data/specs/margins.json` from `cme/collect_margins.js` (CME Group CmeWS / services margins endpoints, run in a cmegroup.com page by `local/mac_collector.py`; first seeded 2026-10-21 through the Mac browser).
- UI: `assets/specs.js` (`Specs.slot(group, [syms])`) placed in the dairy, grains, cotton, hogs, cattle and energy primers.

## Price dates fix (important)
- TradingView daily bars for evening-open sessions (CME dairy, NYMEX energy, ICE cotton Sundays) were stamped one day early. `pipelines/tvdates.py` converts timestamps to exchange trade dates (contracts.py, prices.py, ohlc.py); `contracts.py` repairs stored rows on its next run (idempotent); `models/futures_io.load_contracts` repairs at read time. Checked against CME settlement files in data/cme: 93-100% exact matches after the fix (0-50% before).

## Dairy forecasting and trading lab (Dairy → Primer, bottom)
- `models/dairy_lab.py` → `data/dairy/derived/dairy_lab.json` (Wednesdays in contracts.yml; ~20 min). Weekly decisions on NDPSR release days since 2013, every open contract month up to 6 out; walk-forward models refit monthly on settled contracts; forecasts y = log(settlement/futures).
- Inputs: NDPSR weekly, CME daily spot (MARS 2021+ plus `data/ams/cme_daily_dairy_hist/history.csv` from DMN weekly recaps Nov 2018+, `pipelines/cme_dairy_hist.py`, workflow cme_hist.yml), ERS product supply/use (stocks, production, exports, disappearance; 55-day availability lag), announced class/product prices.
- Desk book = two pre-specified sleeves on all six contracts, one lot per signal: convergence (spot nowcast gap, ≤2 months out) + trend (4-week futures momentum, ≤5 months). 2020-26 Sharpe ≈1.8 (2020-23 1.65, 2024-26 2.16). Fundamentals regressions do not beat no-change out of sample.
- UI: `assets/dairylab.js` (`DairyLab.mount`) into `#dairyLab` on the dairy primer.
- `models/dairy_ideas.py` → `data/dairy/derived/dairy_ideas.json` (after dairy_lab on Wednesdays): convergence variants (all six, butter+whey, 2x cost, trend-confirmed, spot month after first print, calendar spread), daily breakout with trailing stop per contract, 4-week trend; Sharpe by period, hit, payoff, max drawdown, Calmar; worked examples; today's signals. Reads the panel `dairy_panel.csv.gz` written by dairy_lab. Shown on the Dairy primer (data check, the convergence trade explained, ideas table).

## Dairy trade playbook (Outlook tab)
- `models/dairy_playbook.py` (nightly in contracts.yml, after dairy_arb) writes `data/dairy/derived/playbook.json`: every tested
  dairy strategy as a trade card (thesis, entry, exit, risk, what to track), today's positions from the latest settlements and
  spot nowcast, and the track record from `dairy_ideas.json` (weekly, Wednesdays).
- `assets/playbook.js` renders any `<div data-playbook="...json">`; shared with the meats playbook.

## Meats strategy lab and playbooks (hogs / cattle Outlook tabs)
- `models/meats_lab.py` (nightly in contracts.yml, ~2-3 min) tests on HE, LE, GF since 2012 with walk-forward models and
  2012-19 / 2020-23 / 2024-26 splits: cash convergence (rebuilt Lean Hog Index; 5-area weekly live steer price), expiry
  premium, 4-week trend, seasonal, breakout with stops, feeders vs the feeding margin. Live cattle positions end on the
  last business day before the contract month (delivery); `premx_LE_*` holds through the delivery month for comparison.
- Writes `data/livestock/derived/meats_lab.json`, `playbook_hogs.json`, `playbook_cattle.json`; rendered by
  `assets/playbook.js` at the top of the hogs and cattle Outlook tabs. Positions are listed only for ideas whose weakest
  period Sharpe is at least 0.3.
- Findings (Oct 2026): futures beat every cash-based forecast of the final settlement at every horizon. Hogs: nothing
  robust. Live cattle: cash + seasonal convergence within 6 weeks (gap > $2) is the only idea positive in all periods
  (Sharpe ~0.6). The long live-cattle premium (Sharpe ~1.1) is earned almost entirely in the delivery month.
- No Feeder Cattle Index history yet (the Mac collector stores the last 5 values in data/cme/indexes.csv); a GF cash
  convergence test can be added once enough history accumulates.

## Contract calendar (roll / notice / last trading days)
- `models/contract_calendar.py` (nightly in contracts.yml) codes the CME / ICE expiry rules for every desk market (CBOT grains,
  ICE cotton, CME livestock and dairy, NYMEX energy) with the US exchange holiday calendar and writes `data/specs/calendar.json`:
  next contracts with first position day, first notice day, last trading day, USDA announcement (dairy) and a desk
  "roll / exit by" date. On Mondays (or with `--check`) it checks the rules against every expired contract's last bar.
- Rendered under every primer's "Contracts, size and margin" card (`assets/specs.js`), and as a "Roll / exit by" column on
  every playbook position (`assets/playbook.js`).

## Lab export (mirroring into another repo)
- `models/lab_export.py` (nightly) writes `data/lab_export/manifest.json`: back-test results, strategy labs, playbooks,
  calendar and the model code, each with sha256 and Pages URL. A private repo can mirror them with the sync workflow
  (`sync_desk_lab.yml`, given to the owner to add there; it needs no secrets).

## Desk clock (2026-10-22): reliable timing without GitHub cron
- GitHub's cron on this repo delivered runs 1-5 hours late or not at all (on Thu 2026-10-22 none of the eight export-sales
  crons fired; the morning brief cron ran ~5 h late). `.github/workflows/clock.yml` + `pipelines/clock.py` now start each
  data workflow with workflow_dispatch (runs immediately) on an America/New_York timetable (DST handled), skipping any
  workflow that already ran after the entry time and catching up missed entries (up to 4 h) once per workflow. One clock
  runs at a time (≤ ~5h50m), hands over to the next during the day, stops overnight and at weekends; seven weekday crons
  restart it. Uses GITHUB_TOKEN (actions: write); no secrets. `python3 pipelines/clock.py --plan` prints the week.
- Workflows keep their own crons as a backstop; duplicates are harmless (each workflow has a concurrency group).

## What needs Claude (scheduled tasks on Ma's account) vs what does not
- GitHub Actions (no Claude): every data pipeline, model, lab, playbook and the site.
- Claude task "CME ags evening download + FAS flash sales" (weekdays 21:41 CT, uses the Claude desktop browser on Ma's
  computer): CME futures volume/OI/settlement files, option settlements, FAS flash sales. The no-Claude alternative is
  `local/mac_collector.py` (launchd via `bash local/install_mac.sh`; now also collects options and margins); once it is
  installed and pushing ("CME data and FAS flash (Mac collector)" commits), the Claude task can be disabled.
- Claude task "US Ags morning brief" (07:46 ET daily): sends the brief to Ma's phone with a news search; the brief data
  itself is built by brief.yml.
- Claude task "Weekly research report (cotton, sugar, coffee)" (Fri 16:48 CT): the research blog artifact.
- Site chat: Groq via the chat proxy (GROQ_API_KEY), not Claude.

## China cotton (2026-10-23, Ma: "China trade data … cotton crop progress … Chinese cotton prices vs support price … intelligent brief"; "keep this separate")
Kept isolated from the rest of the desk: own data folder `data/china/`, own workflow `china.yml`, own Mac task, own front-end file `assets/china.js` (Cotton tab 6 · China; guarded so a failure only blanks this tab). Nothing else reads `data/china/`.
- Collection runs in GitHub Actions (`china.yml` → `pipelines/china_collect.py`: customs by plain HTTP, CCA by rendering its pages in headless Chromium and running `china/collect_cca.js`); verified 2026-10-23 that both sites answer GitHub runners. The Mac task "China cotton daily collector" is only a fallback. The Claude workspace itself cannot reach these sites.
- Sources:
  - China Cotton Association, china-cotton.org (cncotton.com redirects there): `china/collect_cca.js` reads the site's own pages in a hidden same-origin frame (CCIndex daily table back to 2013, Cotlook A with 1%/sliding-duty landed prices, latest quotes, balance sheet, NBS and CCA production tables, yearly cotton imports, and new production-monitoring surveys from /newsList?id=6, /warning and the home page). Its data API signs requests; do not call it directly, read the pages. Hidden tabs throttle timers, so the collectors wait on fetch ticks / MutationObserver.
  - China customs English monthly bulletin, table (14)/(13): `china/collect_gacc.js` on english.customs.gov.cn (monthly{YYYY}.html). Quantities in 10,000 t. The Chinese customs site and stats.customs.gov.cn are blank (blocked).
  - UN Comtrade monthly China imports by HS/origin (history; China had posted only to Dec 2024 as of Oct 2026) → `data/china/raw/comtrade_china_monthly.csv`.
  - Zhengzhou CF1!/CY1!, FX_IDC:USDCNY, ICEUS:CT1! via tvdatafeed in `china.yml` → `data/china/tv_prices.csv`.
- Incremental: `python china/ingest.py known` gives the last stored dates and article URLs; the collectors read only newer rows / unseen articles / missing customs months; `china/ingest.py cca|gacc <payload>` merges into `data/china/raw/`.
- Months the English customs bulletin has not posted yet are filled from the CCA's monthly import report (customs figures for cotton and cotton yarn), flagged in `imports.filled_from_cca`. USDA China balance (Aug–Jul) from `data/geo/raw/psd.json` (geo.py now keeps Domestic Use) with a snapshot fallback `data/china/raw/usda_psd_china.json`; `imports.usda_check` compares marketing-year import pace and mill use with USDA.
- `models/china_cotton.py` → `data/china/cotton.json`: survey parser (output estimates by survey month, picking/selling % by region at "截至M月D日", seed-cotton price), progress vs last year and earlier seasons at the same date, projected final (past moves from the same survey month to the CCA final), imports (customs YTD, lint-equivalent yarn ×1.1, origins), prices in ¢/lb (incl./ex-VAT), target price 18,600 yuan/t (2026–28), import margins, CY–CF spinning margin, rule-based brief.
- Safety (Ma: "save China history as of each update … so it doesn't corrupt other files"): `models/china_cotton.py` publishes `data/china/cotton.json` only if the build passes checks (brief, crop, progress, imports, prices), via a temp file, and keeps a dated copy in `data/china/history/` (90 builds, `index.json`); the tab falls back to the latest copy. `china/ingest.py` refuses any update that would shrink stored history. The workflow commits raw data even when the model refuses to publish.
- Yarn-origin demand (`imports.origin_demand`): extra yarn China imports this year by supplying country (shares: latest month in `data/china/raw/yarn_origin_shares.csv`, else Comtrade) → extra lint spun there (×1.1), vs that country's USDA imports and the US 5-yr share from the cotton ESR brief. Also written as text to `data/china/esr_note.json`, shown at the bottom of Cotton → Export sales; nothing in the ESR tables reads it.

## Cotton loan (2026-10-23, Ma: "start adding cotton in the loan ... statewide and storage age ... form wise ... weekly")
- `pipelines/cotton_loan.py` (workflow `cotton_loan.yml`, Fridays 15:37 UTC; FSA SORS public reports open from GitHub runners, blocked from the Claude workspace): PSL-43R monthly CSV+PDF (`data/cotton_loan/raw/psl43r/`), PSL-61R monthly and weekly cotton rows (`psl61r_monthly/`, `psl61r_weekly/`), and once per ISO week the current state views (loans incl. Form G by state, outstanding by state x maturity month, upland 6100 and ELS 6000) in `raw/state/<YYYY-Www>/`. Only new snapshots fetched; files never overwritten. FSA keeps 14 monthly PSL-43R / 12 PSL-61R snapshots (Oct 2025 missing) and 5 weekly ones, so y/y is monthly only; weekly history starts 2026-09-21.
- `models/cotton_loan.py` -> `data/cotton_loan/loan.json`; UI `assets/cotton_loan.js` (Cotton > Loan tab, isolated try/catch).
- US fibre share: `pipelines/us_fiber.py` + `models/us_fiber.py` (workflow `fiber.yml`, weekly): Comtrade preview, one month per call, two calls/month, stops on the hourly quota; apparel share by weight tracks ERS within ~1 pt.
- China: `data/china/raw/policy_history.json` (sliding-scale quota by year, reserve sales/purchases) feeds the USDA-check paragraph; update by hand when NDRC/reserve announce.
