# StockMind AI 8.0 research preview

This branch is an experimental, daily-data research implementation, not a live trading
system. No orders are placed, and all decisions stay WAIT until further strategy
validation. The public site on main is not changed by this branch.

## Run the research pipeline locally

Use an environment with Python 3.11 and the scanner's existing dependencies. Obtain
appropriate permission to use the data. Do not upload restricted source data, generated
market reports, or credentials to the public repository or public Actions artifacts.

The existing upgrade scripts run the shared scanner and chart collector:
```sh
python upgrade_scanner.py
python market_chart_upgrade.py
python scanner.py
python research_engine_v8.py --as-of YYYY-MM-DD --historical research_history.json
```

Use the actual last completed exchange session, not merely the current calendar date.
The scanner's weekday-based freshness rule does not yet account for every exchange holiday.
Missing or inconsistent data should remain unverified.

For financials and disclosure research, supply source records obtained under suitable
terms, using the optional flags:
```sh
python research_engine_v8.py --as-of YYYY-MM-DD --historical research_history.json --financials financials.json --news announcements.json
```

The financial input is a JSON object keyed by stock symbol. Each record includes:
- available_date (YYYY-MM-DD, when the information was available)
- source_url (HTTPS disclosure or licensed feed provenance)
- sector and financial_company (boolean)
- optional normalized metrics: roe_pct, roce_pct, revenue_growth_pct, profit_growth_pct,
  free_cash_flow_yield_pct, pe, pb, debt_to_equity

Use comparable accounting periods and consistently calculated metrics. The engine checks
dates and compares at least ten available sector peers per metric; it requires at least
four eligible metrics to produce a research score. It does not independently verify source
authenticity or that the accounting metrics were normalized correctly.

The news input is a JSON object keyed by symbol, each value an array of records with
available_date, source_url, headline, and optional category. Risk categories currently
recognized: fraud, default, regulatory_action, auditor_resignation. Categories must be
sourced or reviewed; the engine does not perform automatic sentiment classification.
Absence of records is unknown, not a positive signal.

Open research.html locally and select research_v8.json. The browser reads the local file;
no upload is required. This is separate from public data publication.

## Validation and remaining gates

The dashboard CI uses synthetic fixtures, including missing-data and stale-data tests.
The sample scanner workflow runs in an ephemeral runner, and logs aggregate counts only.
It does not publish the new reports.

The 8.0 engine includes peer-relative scores, source-dated disclosure review, approved
direction-probability display, empirical return scenarios, a fixed-rule chronological
holdout backtest, and an integrated research ranking. These are not evidence of future
profitability. Full-market real-data integration, source adapters and rights, portfolio-level
costs and slippage, point-in-time delisted stock coverage, forward paper tests, and real
mobile browser validation remain release gates. The research page displays historical
scenario percentiles, not calibrated future price forecasts.

Chart publication in the proposed scanner workflow is gated by the repository variable
STOCKMIND_CHART_PUBLICATION_APPROVED. Leave it unset unless authorized redistribution
rights have been confirmed. NSE recovery diagnostics are excluded from this export.
Existing public market data should also be reviewed for compliance.

Provider information:
- https://www.nseindia.in/static/market-data/nse-data-policy
- https://ranaroussi.github.io/yfinance/


## Public website: on-demand company research

The new company_research.html page includes an optional personal Fincrux connection
and a GDELT company-name news search. Fincrux's free Hobby plan is limited; consult
https://fincrux.org/docs/company-financials and https://fincrux.org/pricing before
using it. An account and personally authorized API key are needed for live financial
requests. The browser sends the key only to the documented Fincrux endpoint over
HTTPS, clears the input after dispatch, and does not store it or publish responses.
If the provider's CORS policy or rate limits prevent direct requests, import an
authorized company-financials response locally. Do not put secrets in GitHub.

The news panel searches GDELT on demand and provides original article links and
index dates. It applies a company-name headline relevance filter, not a verified
entity-resolution or sentiment classifier. Risk words are cues to read the source,
not allegations or automatic trade recommendations. GDELT attribution:
https://www.gdeltproject.org/ (terms: https://gdeltproject.org/about.html).
The official exchange filing links are available when the news service is down.

Neither feature republishes a collected raw dataset to the repository. No full-market
fundamental peer scores are enabled without enough comparable, dated data. Public
historical chart publication remains opt-in and subject to provider/exchange rights.
