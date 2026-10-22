# US Commodity Desk

BMR-Com research desk for US commodity futures: grains and oilseeds, cotton, lean hogs, live and feeder cattle, dairy, and energy (natural gas, WTI crude, ULSD heating oil, RBOB gasoline). Softs, metals and other BCOM markets are covered in the COT desk and the backtests.

Site: https://bmr-com.github.io/US-commodity-desk/

Research use only; not investment advice.

## What is on the site

| Tab | What it shows |
|---|---|
| Summary | One-page read of every market: price, curve, positioning, fundamentals and the week's events |
| Markets & macro | Futures, FX, rates and equity snapshot (updated hourly on weekdays), calendar and news |
| Options pricer | Black-76 pricer and implied-volatility tools for the desk's futures options |
| Backtest | Top findings first, then: baskets across commodities, single-market rules (trend, carry, COT, fundamentals, seasonals), technical patterns (RSI, moving averages, MACD, divergences, breakouts), a 2020-23 vs 2024-25 regime check split into short-term and long-term strategies, and a dairy deep dive |
| Signals | Trend, carry, inventories, options-implied odds, positioning and position sizing per market |
| Dairy, Grains & oilseeds, Cotton, Lean hogs, Live & feeder cattle | Per market: contract primer, supply and demand, futures / options / COT flows, outlook |
| COT (full) | CFTC Commitments of Traders desk (summary and trade ideas, analyzer, scatter, index traders, triggers and flows, seasonality, custom formula) |
| Energy | Primers, supply and demand with storage and stocks-to-use fair-value models, production / trade-flow / LNG-terminal maps, price charts, COT, news and calendar |

## Data

USDA (AMS mandatory price reporting and Market News, NASS, ERS, ESMIS, FGIS export inspections, FAS export sales, PSD, WASDE), EIA (API v2), CFTC Commitments of Traders, CME Group, Energy Institute via Our World in Data, UN Comtrade, Open-Meteo weather, US Drought Monitor, TradingView / Yahoo prices. Everything updates automatically on a schedule.

## How it updates (no Claude needed)

| Feed | Where it runs | Needs |
|---|---|---|
| USDA (AMS datamart & Market News, NASS, ERS, ESMIS, FGIS, FAS export sales), CFTC COT, WASDE, TradingView prices | GitHub Actions on a schedule (free for public repos) | repo secrets `NASS_API_KEY`, `AMS_API_KEY`, `FAS_API_KEY` |
| Energy: EIA weekly storage and petroleum stocks, daily prices, ETF options (`energy`); EIA monthly/annual, OWID, Comtrade maps (`energy_geo`, Mondays) | GitHub Actions | repo secret `EIA_API_KEY` |
| COT (full) desk: all BCOM markets, index traders (`cot_full`, Friday after the release, retries Sat/Mon) | GitHub Actions | — |
| Markets & macro snapshot (`markets`, hourly on weekdays), news (`intel`, every 3 h), weather and drought (`geo`, daily) | GitHub Actions | — |
| Every model, the summary page, the technicals and COT desks | GitHub Actions after each data run | — |
| Backtests: rules, baskets, technical patterns, regime check (`backtest`) | GitHub Actions, Saturdays | — |
| CME settlements, open interest by contract, option strikes, CME livestock indexes; USDA daily flash sales | Ma's Mac (CME and fas.usda.gov block GitHub's servers) | `local/mac_collector.py`, installed once with `bash local/install_mac.sh` |

### Release timing (all times US Central)

| USDA / CFTC release | Desk refresh |
|---|---|
| Weekly export sales, Thu 7:30 am | `grains-trade` 9:00 am (retry 12:30 pm): raw data, export sales brief, sales/flash models, WASDE cross-check |
| Crop Progress, Mon 3 pm | `grains` 4:30 pm: crop progress, condition→yield model, WASDE cross-check |
| WASDE, 11 am (8th–14th) | `wasde` 3:25, 4:50 and 6:30 pm (after BMR-Com/wasde-analytics parses the release): balance sheets, WASDE briefs, summary |
| COT, Fri 2:30 pm | `data` 4:40 pm |
| Everything else | `data` weekdays 3:20 pm; news every 3 h; calendar, weather and South America twice a day |
| Cotton | export sales, crop progress, on-call and the cotton WASDE read come from the BMR-Com cotton repos' own schedules; cotton COT, prices and technicals run in `data` |

If the Mac collector does not run, settlements fall back to TradingView closes (`pipelines/tv_settle.py`) so curves and cash-vs-futures panels stay current; only open interest by contract, option strikes, the CME feeder index and flash sales pause.

### Storage

`pipelines/retention.py` (run by `data`) keeps the repo small: dated files older than six months are deleted or folded into compact gzipped archives, and the large COT and price CSVs live in the GitHub Actions cache instead of git.
