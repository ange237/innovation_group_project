# Global EV charging PEST: reading guide

This run replaces the geographically narrow PEST as the active analysis. Original inputs and older outputs are preserved for audit, but only files listed in this run manifest are current evidence. There is no runtime network access or PATSTAT dependency.

## What to read

1. pest_matrix.csv: eight factors, evidence pointers and explicitly analyst-written implications.
2. market_snapshot.csv: 2025 comparisons and 2020-2025 sales CAGR. market_history.csv contains only those six years and six core metrics.
3. consumer_evidence.csv: Deloitte Q48 concerns in eight focus markets, Q46 cost importance with its different sample, and Ipsos country-average/urban/rural context. Percentages are extracted from original PDFs. Country order and chart order have been visually checked. Negative/undefined Ipsos page-27 chart values are not used.
4. context_evidence.csv: eight selected policy cases across major macroareas and four qualitative economics/technology findings. Interpretation is curated; evidence is retrieved from the actual archived page. IEA policy classifications describe the May 2026 inventory, not a live legal assessment. Targets are not achievements; expired measures are not current subsidies.
5. coverage.csv and pest_sources.csv: geographical gaps, original file names, source URLs and hashes. An absent policy case is not evidence of no policy. Surveys do not cover all countries; no whole-world inference is made.

## Counting and comparability

EV is the IEA workbook BEV+PHEV total; do not add its components again. Regions, World and component countries are never summed. The workbook charging categories are disjoint; if any category is missing the total/share is unknown. kW per EV is an estimated public-capacity indicator for plug-in LDVs, not car-only installed-base arithmetic or actual charging speed. Missing values are never zeros or forward-filled years. Historical external data through 2025 are independent of the PATSTAT complete-year cutoff. Rounded source data imply rounding uncertainty.

Sales CAGR uses the explicitly selected 2020-2025 interval, including a pandemic-affected base. Base sales are exported; high percentages from small starting markets are not evidence of larger absolute opportunities. This contextual CAGR does not replace Anna's Step 1 baseline or calculations.

Deloitte Q48 has multiple responses and larger bases than Q46. Southeast Asia is a regional sample. Ipsos samples in several countries overrepresent connected/urban/affluent respondents; the country average is not population weighted. See Ipsos page 39 and Deloitte question notes. No significance test, interpolation, combined survey average or causal regression is added.

## Economic interpretation and limits

Demand growth, cost sensitivity and private/public charging economics are covered. Comparable global CPO tariffs, station utilization, margins, connection costs and financing costs have not been acquired. Consequently this run does not estimate profitability or declare a most attractive investment country. Protocol capability is not deployment, certification or guaranteed vehicle compatibility. Draft implications are not source findings or investment recommendations.

The older Eurostat-only prices, 2024 spending commitments and USA/England social time series are excluded from the active synthesis. No SDG proxy replaces social attitudes. The source archive retains unused reports; downloading them does not make every report an analytical input.
