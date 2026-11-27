# Project G 09 - Integrated project through Step 2

This release combines project_g_09 with the supplied team09_step2 project.
Step 0 is based primarily on the supplied team's implementation. Anna's Step 1
source block, calculations and sector queries are unchanged. Step 2 combines the
complementary analyses from both versions. Step 3 is not included.

## Run on TIP

Extract project_g_09_global_pest.zip into a fresh location. It contains one
project_g_09 folder. Upload all bundled external files, then run:

```bash
cd ~/project_g_09
python src/01_extract.py
python src/02_clean.py
python src/landscape.py
```

These are the three entry points for the full patent pipeline. The configuration uses PROD.
01_extract and 02_clean together implement Step 0; landscape runs the unchanged
Step 1, then the integrated Step 2 and PEST. Shared modules load automatically.

Run the full sequence once: name normalization and Step 0 metadata have changed,
so previous applicant handoffs and company results must not be reused. Do not
merge this release's outputs with earlier exports. Step 1's code remains the same;
rerunning it creates a consistent new handoff, not a new Step 1 methodology.

Later, after a valid full run, you can use:

```bash
python src/landscape.py --step 2
python src/landscape.py --step pest --pest-offline
```

PEST reads verified local Excel, PDF and HTML sources without web access. Install
the additional PDF reader with `python -m pip install 'pypdf>=5,<7'` if needed.
To run just the new PEST without PATSTAT, extraction or cleaning:

```bash
python src/global_pest.py
```

Outputs go to `outputs/step2/pest_global`. To target an existing Step 2 folder:

```bash
python src/global_pest.py --results outputs/step2-Copy1
```

requirements.txt lists dependencies;
Step 0 captures actual TIP runtime versions in requirements-tip.txt.

## Step 0 - primarily the supplied team project

The original sector scope is retained: B60L53/ and B60L55/00 or the existing ten
keywords; whole-family exclusions B63, B64 and F03D; PI patents; original dates and
time window. The explicit UNION ALL plus outer DISTINCT fix for BigQuery remains.

Cleaning starts from PSN names, with raw names as fallback. The supplied method A
removes punctuation and legal-form words at the edges before the existing group
rules. Subsidiary and joint-venture rules are retained; business groups without
majority ownership remain separate by default. Unicode letters are preserved,
including accented and non-Latin names. This avoids deleting names through an
ASCII-only expression. Group identity and false merges still require review.

The supplied country/type profile and PSN-ID mapping are exported as:

- outputs/step0/sector_family_applicants.csv: full-precision family credits.
- outputs/step0/applicant_info.csv: modal type/country and country coverage.
- outputs/step0/applicant_psn_ids.csv: mapped standardized-name identifiers.
- outputs/step0/name_normalisation_audit.csv: original names versus cleaned label.
- outputs/step0/applicant_name_merges.csv: names mapped into the stated groups.

Country/type summaries use complete years. The country is the most frequent known
family-country record, not independently verified legal domicile or ownership.
Mixed-type review flags are preserved in Step 2 rather than hidden by a modal type.

The supplied optional gold-standard comparison computes pairwise precision,
recall and F1 for raw standardized names, method A, and method A plus group rules.
If the real course CSV is available, place it at config/PATSTAT_500_label_datav4.csv
and rerun cleaning. It is not bundled; no real benchmark result is claimed when it
is missing. The optional random validation sample remains available through
python src/01_extract.py --validation-sample 100. No existing manual review is
invented or overwritten.

## Step 1 - unchanged

The Anna source block at the beginning of src/landscape.py is byte-for-byte equal
to the previous project. Its volume, CAGR, technological mix, WIPO, office and
country calculations and the seven figures are unchanged. The sector query,
family/application counting functions and helpers used by it are preserved.
The original reference notebooks are also preserved. Run the scripts above for
the integrated pipeline; those notebooks document earlier exploratory work.

## Integrated Step 2

The main analysis retains annual fractional CR4/HHI, observed participation,
three-year inactivity, detailed CPC-symbol growth relative to the whole sector,
recent RTA with coverage and support, and the transparent review-group rules.
The additional PV/wind sector comparison remains enabled. The review pool is
neither a ranking of investments nor a final acquisition list.

The supplied project's complementary analyses now run in the same stage:

| Output | Purpose and interpretation |
|---|---|
| concentration_overall.csv / 09_lorenz_curve.png | Whole-period distribution of credits: CR4, CR8, HHI, equivalent applicants, CV, Gini and descriptive Lotka OLS. |
| concentration_windows.csv / 14_concentration_windows.png | Complete non-overlapping triennial windows with both full and fractional counting. The annual fractional view remains primary. |
| applicant_history.csv / applicant_first_patents_by_psn.csv | First observed PI family-origin year in any field for mapped PSN IDs, with lookup coverage. |
| patenting_entry_annual.csv / 15_patenting_entry.png | First sector appearance versus observed first patenting, with history coverage and first-year censoring. |
| all_applicants_complete_years.csv / top_applicants_complete_years.csv | Descriptive family totals, type, country and patent history, restricted to complete years. |
| subfield_growth_grouped.csv | Optional two-digit grouping with a relative-sector growth check; detailed growth and RTA remain separate. |

The history query searches all fields for PI family origins from 1800 to the
configured maximum year, in batches. First observed does not mean verified
first-ever patenting, company creation or start-up status. Incomplete mapped-ID
history is explicit and does not become a claim that an applicant never patented.
The first-year sector-entry count is censored. The last-observation rate is a
supplementary metric distinct from the existing three-year inactivity measure;
neither establishes firm closure.

Patent credit concentration is not revenue-market concentration. Whole-period,
annual and triennial statistics have different scopes and are not independent
confirmations. Lotka is a descriptive log-frequency fit, not a formal validation
of a power-law distribution. Do not apply market HHI thresholds.

All top lists and growth comparisons exclude 2023-2025 as incomplete. Time-series
charts retain a grey incomplete-year area. Coarse CPC aggregation intentionally
merges /302 and /305 into /30; it never replaces the detailed primary analysis.
The network-capacity label for B60L53/63 is corrected against the official scheme.
CPC tags overlap, so subgroup shares do not sum to 100%.

## PEST and external evidence

The active PEST is now `src/global_pest.py`, automatically called by landscape.
It uses six descriptive IEA market/infrastructure indicators, eight selected policy
cases, Deloitte Q46/Q48 international consumer evidence, Ipsos settlement-type
context, and four qualitative economic/technology findings. There are four figures
and four core evidence tables, plus a small PEST synthesis and source/coverage files.

The market comparison covers 12 countries across major macroareas and six separate
world/regional aggregates in 2020-2025. The common snapshot year is 2025. Sales CAGR
uses an explicitly disclosed 2020 base, with its original count retained; it does not
replace Anna's Step 1 CAGR. Social evidence has eight Deloitte focus markets, one
being a regional sample, not worldwide representative coverage. Read the question
bases and limitations before interpreting percentages.

Original PDF/HTML files are verified against
`data/external/global_pest_sources/source_manifest.json` before extraction. Qualitative
policy and technology interpretations are curated and clearly separated from source
evidence. A changed PDF layout fails rather than silently assigning wrong values.
No runtime API, web search, language model or PATSTAT connection is required for the
standalone module. The full source archive is retained, but unused reports are listed
as unused in the new run manifest.

The previous USA/England survey series, Europe-only electricity comparison and 2024
public-spending commitments are no longer active PEST inputs. Their original files,
legacy import helpers and regression tests remain for audit. Older `outputs/step2/pest`
files are historical only; the new run does not regenerate or combine them.

Read `outputs/step2/pest_global/READING_GUIDE.md` and `pest_run_manifest.json` for the
authoritative outputs. The new run does not invent global averages, composite scores,
profitability estimates or country investment rankings. External data periods remain
independent of the PATSTAT cutoff and cannot establish causal explanations of patents.

## Verification and ownership

```bash
python -m unittest discover -s tests -v
```

Tests cover the supplied name rules, new metadata/history handling, concentration
windows, detailed and coarse growth, original indicators, PEST imports and an
end-to-end SQLite extraction/cleaning/landscape fixture. Source integrity checks
verify the unchanged Anna block, Step 1 query functions and all external inputs.
These checks do not replace real TIP PROD execution or identity review.

Read outputs/step2/step2_run_manifest.json and READING_GUIDE.md after running.
Source provenance, preservation checks and the actual local test result are
recorded in release_verification.json. This package ends at Step 2.
