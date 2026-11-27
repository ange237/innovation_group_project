# Focused global PEST implementation

The user authorized replacing geographically narrow PEST analyses with a small, descriptive international evidence base. Steps 0 and 1, and Step 2 patent calculations, must remain unchanged. All new comments and outputs are in English.

Selected approach: a deterministic offline Python module, called by landscape.py and also runnable independently without PATSTAT. It reads the original IEA workbook and archived PDFs/HTML, checks source hashes, extracts explicitly selected questions and paragraphs, and exports four core evidence tables, a small PEST synthesis, coverage notes and four figures. No LLM or runtime web access is needed. Broad keyword scraping was rejected because it confuses question bases, policy status and observation years. A composite country score was rejected because the sources do not justify weights or a common population.

Market comparisons use 2020-2025 history, selected countries across six macroareas, and separate IEA regional/world aggregates. Missing charger categories remain missing. Growth compares the same geography, indicator and exact endpoint years. Social evidence uses Deloitte Q46 and Q48 (eight focus markets, including one regional sample), plus explicitly reported Ipsos urban/rural and country-average context. Ipsos page 27 is excluded because its signed chart values lack a clear definition. Policy cases retain the IEA classification and snapshot date; legislative classification does not turn a target into an achieved installation count. Qualitative economics and interoperability evidence is kept separate from measured observations.

The new run writes to outputs/step2/pest_global. Legacy local PEST sources stay archived but are not active inputs. Existing pest outputs are not deleted or mixed with this release. An output manifest lists the authoritative files. Outputs have source identifiers, periods, definitions and limitations; no unsupported global average, country league table, profitability estimate or causal patent explanation is produced.

Implementation plan:
- [x] Add tests for missing components, duplicate conflicts, exact-year growth, PDF extraction and integrity failures.
- [x] Implement source verification, selected PDF/HTML extraction and compact market comparison.
- [x] Replace only the PEST entry point in landscape.py; retain legacy helper functions for backward compatibility.
- [x] Run offline extraction and inspect generated figures; check Step 0/1 hashes and Step 2 patent code.
- [x] Update run instructions and package the verified project.
