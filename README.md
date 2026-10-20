# US Ags Desk

BMR-Com research desk for CME-listed US agricultural markets: dairy, lean hogs, live and feeder cattle, grains and oilseeds. Each market has four tabs: a contract primer, supply and demand, futures/options/COT flows, and an outlook.

Site: https://bmr-com.github.io/us--Ags-desk/

Data: USDA AMS mandatory price reporting, USDA NASS, USDA ERS, USDA WASDE, USDA FGIS export inspections, CFTC Commitments of Traders, CME Group. Updated automatically on weekdays.

Research use only; not investment advice.

## How it updates (no Claude needed)

| Feed | Where it runs | Needs |
|---|---|---|
| USDA (AMS datamart & Market News, NASS, ERS, ESMIS, FGIS, FAS export sales), CFTC COT, WASDE, TradingView prices | GitHub Actions on a schedule (free for public repos) | repo secrets `NASS_API_KEY`, `AMS_API_KEY`, `FAS_API_KEY` |
| Every model, the summary page, the technicals and COT desks | GitHub Actions after each data run | — |
| CME settlements, open interest by contract, option strikes, CME livestock indexes; USDA daily flash sales | Ma's Mac (CME and fas.usda.gov block GitHub's servers) | `local/mac_collector.py`, installed once with `bash local/install_mac.sh` |

If the Mac collector does not run, settlements fall back to TradingView closes (`pipelines/tv_settle.py`) so curves and cash-vs-futures panels stay current; only open interest by contract, option strikes, the CME feeder index and flash sales pause.
