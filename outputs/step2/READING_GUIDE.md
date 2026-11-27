# Step 2: competition and screening

Read the core outputs listed in step2_run_manifest.json; unlisted old files must
not be mixed with the revised results. Step 1 code and queries are unchanged.
Step 0 now uses the supplied team project's legal-form cleaning; regenerate all applicant results.

1. q1_concentration_annual: the primary view is fractional CR4 and HHI (0-1).
Each named family contributes one total credit; full counting is a sensitivity
check with a different denominator. CR4 leaders change yearly (q1_cr4_leaders).
This is patent-activity concentration among observed labels, not market power.
Residual aliases and ownership changes require review before consolidation claims.
Coverage is recorded in sector_participation_annual. Do not apply market HHI cutoffs.

2. sector_participation_annual: new means first observed in the sector dataset,
not newly founded or first-ever patenting worldwide. The first year is censored.
Entrant-family share counts unique named families and can include incumbents on
the same family; it is not an exclusive entrant credit share. q2_inactivity_3y
requires three complete follow-up years and measures inactivity, not firm exit.
Applicants on later PI family members retain the original family origin date;
first observation is therefore retrospective, not a real-time entry signal.

3. q3_subfield_growth: compare annual mean frequencies in the two disjoint periods.
relative_growth_index = subfield growth factor / whole-sector growth factor;
above 1 means faster than the sector. share_change_pp uses all sector families,
including uncoded/unnamed ones. Overlapping CPC incidences do not sum to 100%.
Zero-base growth is undefined; small bases are flagged, not promoted as leaders.
Code labels can be supplied via step2.subfield_labels after checking definitions.
CPC reclassification and coverage can change measured trajectories.

4. q2_applicant_summary adds equal-period actor growth, fractional share changes,
repeat activity and recent growing-subfield exposure. Recent/lifetime share is
not used as growth. q3_specialization_rta uses the same recent window as screening;
RTA >1 means relative technical focus, not quality. Coverage and support flags are
included; the heatmap leaves unsupported applicant portfolios blank.

5. q4_player_screening selects recorded COMPANY names with >=10 recent families,
>=2 active recent years and activity in the last three complete years (defaults).
It includes the 15 largest recent fractional portfolios as benchmarks and other
up to 15 other eligible firms with the largest sector-share gains and supported
RTA >=1 in a growing subfield. The union contains at most 30 names by default.
These are transparent screening rules, not a present/future score or a purchase
recommendation. Every identity requires review; related companies remain distinct
under the supplied Step 0 group rules. Mixed metadata remains explicitly flagged.
Countries are modal known family-country records from the integrated Step 0.
They are not verified legal domicile. Never interpret first observation as founding.

PEST: pest_global/pest_matrix.csv uses selected international IEA and consumer evidence,
with deterministic extraction from hash-checked local PDFs and HTML.
No online download or unverified source search is performed.
The social block separates international survey questions and populations.
Political context includes eight selected cases across major macroareas;
coverage is not a comprehensive account of policies in every jurisdiction.
Current macro context does not causally explain historical patent counts.

Complete-year inference ends at the shared last complete year; time figures retain
and shade later years. Step 1 remains the source of sector growth and geography.
Additional PV/wind comparison is opt-in with run_additional_field_comparison: true.
The exploratory appendix is opt-in with run_exploratory_appendix: true; SDG also
requires run_sdg_analysis: true. Family name co-occurrence is not a partner network
and is deliberately not exported as evidence of collaboration by the main run.

## Integrated context from the supplied team project

Step 0 uses its legal-form cleaning, country/type profiles, PSN-ID mapping and
optional pairwise gold-standard evaluation. Existing group/JV rules are retained.
Unicode names are preserved. Review name_normalisation_audit.csv before reporting.
Cleaning can change applicant counts and credits; original Step 1 sector
queries, figures and counting code are unchanged.

concentration_overall.csv adds cumulative CR8, CV, Gini, Lotka and equivalent
applicants. concentration_windows.csv adds both counting methods in complete
non-overlapping triennial windows. Their time scopes differ from the primary
annual fractional series. Lotka OLS is descriptive and no market HHI cutoffs apply.

applicant_history.csv reports the first observed PI family year across all fields
for mapped PSN IDs. The query begins in 1800 and excludes placeholder years;
this is not verified first-ever patenting or founding. Coverage is explicit.
patenting_entry_annual.csv counts first-observed patenting only for active names
with complete mapped-ID history. Sector entry is left-censored in the first year.
The last-observation rate is supplementary, distinct from three-year inactivity;
neither establishes company closure. Incomplete years are excluded from top lists.

all_applicants_complete_years.csv and top_applicants_complete_years.csv describe
size, type, country and history. They do not replace the reviewed screening rules.
Country is the modal known family-country record, not verified legal domicile.
The mixed-type identity flags remain visible in the main screening outputs.

subfield_growth_grouped.csv provides the supplied two-digit aggregation and
retains a relative-sector growth check. Detailed subgroup growth and RTA remain
primary, so cooling /302 is not silently replaced by general station design /30.
The /63 label refers to network capacity, not vehicle parameters.

The empirical PEST inputs, processing and four-pillar outputs remain integrated.
Step 3 is not included in this package. All patent outputs must be regenerated
after the changed Step 0 normalization; no old company results are bundled.
