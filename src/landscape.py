"""Landscape · Original Step 1 (sections 7-9) followed by Step 2.

Same queries, same counting rules and the same seven figures as
notebooks/02_step1_general_description.ipynb; the tables the notebook displays
are also saved as CSV files.

Run from the repository root:
    python src/landscape.py
    python src/landscape.py --step pest
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

from settings import (
    APPLN_TIME_COLUMN, FAMILY_TIME_COLUMN, GROWTH_BASE_YEARS, IP5_OFFICES, LAST_COMPLETE_YEAR, LEVELS,
    YEAR_MAX, SECTOR_NAME, SHOWN_OFFICES, STEP1_DIR, TOP_N, UNIT_LABEL, YEAR_MIN,
)
from patstat_queries import (
    SCOPES, SECTOR_SCOPES, Scope, application_scope, count_by_office, count_per_year,
    fractional_by_country, fractional_by_cpc_subclass, fractional_by_techn_field,
    missing_applicant_country, scope_profile, sector_ids, techn_field_names,
)
from helpers import (
    complete_years, pool_other, save_figure, save_table, shade_truncated, share_over_time,
    share_table, side_by_side, stack_100,
)

#Anna: definitions of the CPC subclasses shown in the table
CPC_DEFINITIONS = {
    "B60L": "PROPULSION OF ELECTRICALLY-PROPELLED VEHICLES",
    "Y02T": "CLIMATE CHANGE MITIGATION TECHNOLOGIES RELATED TO TRANSPORTATION",
    "H02J": "ELECTRIC POWER NETWORKS; CIRCUIT ARRANGEMENTS OR SYSTEMS FOR SUPPLYING OR DISTRIBUTING ELECTRIC POWER; SYSTEMS FOR STORING ELECTRIC ENERGY",
    "Y02E": "REDUCTION OF GREENHOUSE GAS [GHG] EMISSIONS, RELATED TO ENERGY GENERATION, TRANSMISSION OR DISTRIBUTION",
    "Y04S": "SYSTEMS INTEGRATING TECHNOLOGIES RELATED TO POWER NETWORK OPERATION, COMMUNICATION OR INFORMATION TECHNOLOGIES FOR IMPROVING THE ELECTRICAL POWER GENERATION, TRANSMISSION, DISTRIBUTION, MANAGEMENT OR USAGE, i.e. SMART GRIDS",
    "G06Q": "INFORMATION AND COMMUNICATION TECHNOLOGY [ICT] SPECIALLY ADAPTED FOR ADMINISTRATIVE, COMMERCIAL, FINANCIAL, MANAGERIAL OR SUPERVISORY PURPOSES; SYSTEMS OR METHODS SPECIALLY ADAPTED FOR ADMINISTRATIVE, COMMERCIAL, FINANCIAL, MANAGERIAL OR SUPERVISORY PURPOSES, NOT OTHERWISE PROVIDED FOR",
    "F03D": "WIND MOTORS",
    "Y02B": "CLIMATE CHANGE MITIGATION TECHNOLOGIES RELATED TO BUILDINGS, e.g. HOUSING, HOUSE APPLIANCES OR RELATED END-USER APPLICATIONS",
    "H01M": "PROCESSES OR MEANS, e.g. BATTERIES, FOR THE DIRECT CONVERSION OF CHEMICAL ENERGY INTO ELECTRICAL ENERGY",
    "H01R": "ELECTRICALLY-CONDUCTIVE CONNECTIONS; STRUCTURAL ASSOCIATIONS OF A PLURALITY OF MUTUALLY INSULATED ELECTRICAL CONNECTING ELEMENTS; COUPLING DEVICES; CURRENT COLLECTORS",
    "B60Y": "INDEXING SCHEME RELATING TO ASPECTS CROSS-CUTTING VEHICLE TECHNOLOGY",
    "Other": "Aggregated group of remaining CPC subclasses.",
}


# STEP 1 ANNA: count each original scope once per year and reuse the results.
# The family and application scopes, PCT flag and date rules come from
# the unchanged imported notebook queries. Complete-year filters apply to
# CAGR and profile statistics; 2023-2025 stay visible and shaded in figures.
def section7_volume():
    """7. Volume per year (figure 01), the three datings (figure 02), growth (figure 03), profile."""
    volume = pd.concat(
        [count_per_year(s).assign(series="all") for s in SCOPES]
        + [count_per_year(s, only_pct=True).assign(series="via PCT") for s in SCOPES],
        ignore_index=True,
    )
    save_table(volume, STEP1_DIR / "volume_per_year.csv", index=False)

    fig, axes = side_by_side(f"{SECTOR_NAME}: volume per year", sharex=True)
    for ax, scope in zip(axes, SECTOR_SCOPES):
        data = volume.query("scope == @scope.name and level == @scope.level")
        for series, grp in data.groupby("series"):
            ax.plot(grp["year"], grp["n"], marker="o", ms=3, label=f"{UNIT_LABEL[scope.level]}, {series}")
        shade_truncated(ax)
        year_col = FAMILY_TIME_COLUMN if scope.level == "family" else APPLN_TIME_COLUMN
        ax.set(title=f"{UNIT_LABEL[scope.level]} per {year_col}", xlabel="year", ylabel=UNIT_LABEL[scope.level])
        ax.legend()
    plt.tight_layout()
    save_figure(STEP1_DIR / "01_volume_per_year.png")

    # 7.1 The same sector, three ways to date it
    dating = pd.concat(
        [
            count_per_year(Scope(SECTOR_NAME, "application", application_scope(sector_ids, col)))
            .assign(series=f"applications by {col}")
            for col in ("appln_filing_year", "earliest_publn_year", "earliest_filing_year")
        ]
        + [volume.query("scope == @SECTOR_NAME and level == 'family' and series == 'all'")
           .assign(series=f"families by {FAMILY_TIME_COLUMN}")],
        ignore_index=True,
    )
    save_table(dating, STEP1_DIR / "volume_three_datings.csv", index=False)

    fig, ax = plt.subplots(figsize=(10, 5))
    for series, grp in dating.groupby("series"):
        ax.plot(grp["year"], grp["n"], marker="o", ms=3, label=series)
    shade_truncated(ax)
    ax.set(title=f"{SECTOR_NAME}: the same patents dated in different ways", xlabel="year", ylabel="count")
    ax.legend()
    save_figure(STEP1_DIR / "02_volume_three_datings.png")

    # 7.2 Growth: sector vs all patents, from each base year (complete years only)
    totals = volume.query("series == 'all'").pivot_table(index="year", columns=["level", "scope"], values="n")
    end = LAST_COMPLETE_YEAR
    growth_tables = []
    for base in GROWTH_BASE_YEARS:
        yrs = end - base
        g = pd.DataFrame({
            "base year": base,
            "count base year": totals.loc[base],
            f"count {end}": totals.loc[end],
            "total growth (%)": (totals.loc[end] / totals.loc[base] - 1) * 100,
            "CAGR (%)": ((totals.loc[end] / totals.loc[base]) ** (1 / yrs) - 1) * 100,
        })
        print(f"\n--- base year {base} ---")
        print(g.drop(columns="base year").round(1).to_string())
        growth_tables.append(g)
    save_table(pd.concat(growth_tables), STEP1_DIR / "growth_by_base_year.csv")

    start = YEAR_MIN
    growth_path = (totals.loc[start:end] / totals.loc[start] - 1) * 100
    fig, axes = side_by_side(f"{SECTOR_NAME} vs all patents: growth (%) since {start}", sharey=True)
    for ax, level in zip(axes, LEVELS):
        for scope_name in ("all patents", SECTOR_NAME):
            ax.plot(growth_path.index, growth_path[(level, scope_name)], marker="o", ms=3, label=scope_name)
        shade_truncated(ax)
        ax.set_xlim(YEAR_MIN, YEAR_MAX)
        ax.axhline(0, color="grey", lw=0.8)
        ax.set(title=UNIT_LABEL[level], xlabel="year", ylabel=f"growth since {start}")
        ax.yaxis.set_major_formatter(PercentFormatter(100))
        ax.legend()
    plt.tight_layout()
    save_figure(STEP1_DIR / "03_growth_vs_all_patents.png")

    # Patent intensity: PCT share, grant rate, family size (appropriability question)
    profile = pd.concat([scope_profile(s) for s in SCOPES], ignore_index=True)
    profile["pct_share (%)"] = profile["n_pct"] / profile["n"] * 100
    profile["grant_rate (%)"] = profile["n_granted"] / profile["n"] * 100
    profile = profile[["scope", "level", "n", "pct_share (%)", "grant_rate (%)", "mean_family_size"]]
    print("\n", profile.round(2).to_string(index=False))
    profile.round(2).to_csv(STEP1_DIR / "scope_profile.csv", index=False)


# STEP 1 ANNA: preserve the original fractional CPC-subclass and WIPO mix.
# Choose the common top subclasses from complete-year family counts, pool
# the remainder as Other, then divide by each column/year total for shares.
# These subclass shares are distinct from Step 2 full-symbol subgroup growth.
def section8_technology():
    """8. CPC subclass mix (figure 04) and WIPO technology sectors and fields (figure 05)."""
    cpc_mix = pd.concat([fractional_by_cpc_subclass(s) for s in SECTOR_SCOPES], ignore_index=True)

    #Anna: inspect all CPC subclasses before pooling them into "Other"
    cpc_raw_counts = cpc_mix.groupby(["subclass", "level"])["n_frac"].sum().unstack(fill_value=0)
    cpc_raw_counts["total"] = cpc_raw_counts.sum(axis=1)
    save_table(cpc_raw_counts.sort_values("total", ascending=False), STEP1_DIR / "cpc_all_subclasses.csv")

    # one top-8 list, chosen at family level, used for both levels
    top = (complete_years(cpc_mix[cpc_mix["level"] == "family"])
           .groupby("subclass")["n_frac"].sum().nlargest(TOP_N).index)
    cpc_pooled = cpc_mix.copy()
    cpc_pooled["subclass"] = cpc_pooled["subclass"].where(cpc_pooled["subclass"].isin(top), "Other")
    cpc_pooled = cpc_pooled.groupby(["subclass", "year", "level"], as_index=False)["n_frac"].sum()

    cpc_counts = complete_years(cpc_pooled).pivot_table(index="subclass", columns="level", values="n_frac",
                                                        aggfunc="sum", fill_value=0)[list(LEVELS)]
    cpc_shares = share_table(cpc_counts)
    print("\n", cpc_shares.round(1).to_string())
    cpc_shares["definition"] = cpc_shares.index.map(CPC_DEFINITIONS)
    save_table(cpc_shares, STEP1_DIR / "cpc_subclass_shares.csv")

    fig, axes = side_by_side(f"{SECTOR_NAME}: CPC subclass mix over time", sharey=True)
    for ax, level in zip(axes, LEVELS):
        stack_100(ax, share_over_time(cpc_pooled[cpc_pooled["level"] == level], "subclass"),
                  f"share of {UNIT_LABEL[level]}")
    axes[-1].legend(loc="center left", bbox_to_anchor=(1, 0.5), fontsize=8)
    plt.tight_layout()
    save_figure(STEP1_DIR / "04_cpc_mix_over_time.png")

    # 8.2 WIPO technology sectors (5) and fields (35)
    fields = (
        pd.concat([fractional_by_techn_field(s) for s in SECTOR_SCOPES], ignore_index=True)
        .merge(techn_field_names(), on="techn_field_nr", how="left")
    )
    techn_sector_counts = complete_years(fields).pivot_table(index="techn_sector", columns="level", values="n_frac",
                                                             aggfunc="sum", fill_value=0)[list(LEVELS)]
    techn_sector_shares = share_table(techn_sector_counts)
    print("\n", techn_sector_shares.round(1).to_string())
    save_table(techn_sector_shares, STEP1_DIR / "wipo_sector_shares.csv")

    bars = techn_sector_shares.drop("Total").T   # one bar per level, each bar = 100%
    fig, ax = plt.subplots(figsize=(11, 3))
    left = np.zeros(len(bars))
    for techn_sector in bars.columns:
        values = bars[techn_sector].values
        ax.barh([UNIT_LABEL[l] for l in bars.index], values, left=left, label=techn_sector)
        for y, (x0, v) in enumerate(zip(left, values)):
            if v >= 5:
                ax.text(x0 + v / 2, y, f"{v:.0f}%", ha="center", va="center", color="white", fontsize=9)
        left += values
    ax.set(title=f"{SECTOR_NAME}: split across the 5 WIPO technology sectors", xlim=(0, 100))
    ax.xaxis.set_major_formatter(PercentFormatter(100))
    ax.invert_yaxis()
    ax.legend(loc="center left", bbox_to_anchor=(1, 0.5))
    save_figure(STEP1_DIR / "05_wipo_sectors.png")

    field_counts = complete_years(fields).pivot_table(index="techn_field", columns="level", values="n_frac",
                                                      aggfunc="sum", fill_value=0)[list(LEVELS)]
    top_fields = field_counts["family"].nlargest(TOP_N).index
    field_counts = field_counts.groupby(field_counts.index.where(field_counts.index.isin(top_fields), "Other")).sum()
    field_shares = share_table(field_counts)
    print("\n", field_shares.round(1).to_string())
    save_table(field_shares, STEP1_DIR / "wipo_field_shares.csv")


# STEP 1 ANNA: preserve office counts and applicant/inventor country shares.
# Application offices are mutually exclusive; family office counts may overlap.
# Country weights follow the original known-person rule, not a new weighting
# by country. Unknown-country coverage is different from Step 2 name coverage.
def section9_geography():
    """9. Filing offices (figure 06) and applicant/inventor countries (figure 07)."""
    off_raw = pd.concat([count_by_office(s) for s in SECTOR_SCOPES], ignore_index=True)

    #Anna: all offices, not only the IP5 (Germany is larger than Korea in this sector)
    app = complete_years(off_raw.query("level == 'application'")).groupby("office")["n"].sum()
    all_offices = (app / app.sum() * 100).sort_values(ascending=False).head(15).to_frame("applications (%)")
    print("\n", all_offices.round(1).to_string())
    save_table(all_offices, STEP1_DIR / "office_shares_top15.csv")

    offices = off_raw.copy()
    offices["office"] = offices["office"].where(offices["office"].isin(SHOWN_OFFICES + ("WO",)), "Other")
    offices = offices.groupby(["level", "office", "year"], as_index=False)["n"].sum()

    office_counts = complete_years(offices.query("level == 'application'")).groupby("office")["n"].sum().to_frame("applications")
    office_shares = share_table(office_counts)
    ip5_share = office_shares.loc[list(IP5_OFFICES), "applications"].sum()
    print(f"\nShare of the sector's applications filed at the IP5: {ip5_share:.1f}%")
    save_table(office_shares, STEP1_DIR / "office_shares.csv")

    fig, axes = side_by_side(f"{SECTOR_NAME}: filings at the IP5 offices and Germany (DE)", sharex=True)
    for ax, level in zip(axes, LEVELS):
        data = offices.query("level == @level and office in @SHOWN_OFFICES")
        for office, g in data.groupby("office"):
            ax.plot(g["year"], g["n"], marker="o", ms=3, label=office)
        shade_truncated(ax)
        title = ("families with an application at the office" if level == "family"
                 else "applications filed at the office")
        ax.set(title=title, xlabel="year", ylabel=UNIT_LABEL[level])
    axes[-1].legend(loc="center left", bbox_to_anchor=(1, 0.5))
    plt.tight_layout()
    save_figure(STEP1_DIR / "06_filing_offices_over_time.png")

    # 9.2 Applicant and inventor countries (fractional counts)
    countries = pd.concat(
        [fractional_by_country(s, role) for s in SECTOR_SCOPES for role in ("applicant", "inventor")],
        ignore_index=True,
    )
    country_counts = complete_years(countries).pivot_table(index="ctry", columns=["level", "role"], values="n_frac",
                                                           aggfunc="sum", fill_value=0)
    country_counts = country_counts[[(lvl, role) for lvl in LEVELS for role in ("applicant", "inventor")]]
    top_countries = country_counts[("family", "applicant")].nlargest(TOP_N).index
    country_counts = country_counts.groupby(country_counts.index.where(country_counts.index.isin(top_countries), "Other")).sum()
    country_shares = share_table(country_counts)
    print("\n", country_shares.round(1).to_string())
    save_table(country_shares, STEP1_DIR / "country_shares.csv")

    #Anna: the shares above only cover families WITH a known applicant country
    n_total, n_missing = missing_applicant_country()
    print(f"\n{n_missing:,} of {n_total:,} sector families ({n_missing / n_total * 100:.1f}%) have no applicant country")
    pd.DataFrame({"families": [n_total], "no_applicant_country": [n_missing],
                  "missing (%)": [round(n_missing / n_total * 100, 1)]}).to_csv(
        STEP1_DIR / "missing_applicant_country.csv", index=False)

    fig, axes = side_by_side(f"{SECTOR_NAME}: applicant countries over time", sharey=True)
    for ax, level in zip(axes, LEVELS):
        data = countries.query("role == 'applicant' and level == @level")
        stack_100(ax, share_over_time(pool_other(data, "ctry"), "ctry"), f"share of {UNIT_LABEL[level]}")
    axes[-1].legend(loc="center left", bbox_to_anchor=(1, 0.5))
    plt.tight_layout()
    save_figure(STEP1_DIR / "07_applicant_countries_over_time.png")



# STEP OWNERSHIP
# Anna's notebook sections 7-9 are preserved above. Her Section 10 name
# harmonisation and top-applicant ranking run in 02_clean.py; the random
# validation sample is handled by 01_extract.py. Step 2 reads those handoffs.
# Step 2 uses the SAME Step 0 family-applicant pairs and company rules.
import argparse
import hashlib
import json
from pathlib import Path
from scipy import stats
from settings import ROOT, OUTPUT_DIR, STEP0_DIR, _cfg
from patstat_queries import sector_family_cpc, sector_family_members, comparison_family_counts, patstat, first_patent_ever
from competition_context import CODE_LABELS, run_integrated_context, pest_strategy_review, READING_GUIDE as INTEGRATED_READING_GUIDE

STEP2_DIR = OUTPUT_DIR / "step2"
STEP2_CONFIG = _cfg["step2"]
STEP2_CONFIG.setdefault("subfield_labels", CODE_LABELS)
SPLIT_YEAR = STEP2_CONFIG["split_year"]
WINDOW = STEP2_CONFIG["window"]
PAST_PERIOD = tuple(STEP2_CONFIG["past_period"])
RECENT_PERIOD = tuple(STEP2_CONFIG["recent_period"])
MIN_GROWTH_BASE = STEP2_CONFIG["min_growth_base"]
SUBFIELD_CPC_PREFIXES = tuple(p.replace(" ", "") for p in STEP2_CONFIG["subfield_cpc_prefixes"])


# HANDOFF VALIDATION: one row per family/name and one origin year per family.
# Positive fractional credits must sum to one for every named family.
# This detects duplicate links and rounded/lost credit before any analysis.
def validate_family_applicants(data):
    """Reject duplicate names, inconsistent years and rounded/lost family credits."""
    required = {"docdb_family_id", "clean_name", "earliest_filing_year", "fractional_credit"}
    if not required.issubset(data.columns):
        raise ValueError("Missing Step 0 family-applicant columns.")
    if data.duplicated(["docdb_family_id", "clean_name"]).any():
        raise ValueError("Duplicate family-applicant pairs: rerun Step 0.")
    if data.clean_name.fillna("").str.strip().eq("").any():
        raise ValueError("Empty harmonised applicant name.")
    if data.groupby("docdb_family_id").earliest_filing_year.nunique().gt(1).any():
        raise ValueError("Multiple first years for the same family.")
    if not data.fractional_credit.gt(0).all() or not np.isfinite(data.fractional_credit).all():
        raise ValueError("Invalid fractional credit.")
    credits = data.groupby("docdb_family_id").fractional_credit.sum()
    if not np.allclose(credits, 1, atol=1e-10, rtol=0):
        raise ValueError("Each observed family's credits must sum to one: rerun Step 0.")


# HANDOFF LOADING: verify the recorded source/data hashes, load the existing
# cleaned pairs and rename columns only. Do not query or harmonise names again.
# Anna's Section 10 mappings are applied upstream in 02_clean.py.
def load_step0_applicants():
    """Reuse exported names; never run a different name-cleaning algorithm in Step 2."""
    path = STEP0_DIR / "sector_family_applicants.csv"
    manifest_path = STEP0_DIR / "handoff_manifest.json"
    if not path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Run python src/01_extract.py and python src/02_clean.py before landscape.py.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative, expected in manifest["source_sha256"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Selection or grouping changed: rerun Step 0 before landscape.py.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["applicants_sha256"]:
        raise ValueError("Step 0 data changed after export: rerun Step 0.")
    metadata = STEP0_DIR / "sector_family_applicant_sectors.csv"
    if not metadata.is_file() or hashlib.sha256(metadata.read_bytes()).hexdigest() != manifest["metadata_sha256"]:
        raise ValueError("Step 0 applicant-sector metadata changed: rerun Step 0.")
    # The integrated Step 0 supplies country/type, mapped IDs and a name crosswalk.
    required_context = {"applicant_info.csv", "applicant_psn_ids.csv", "name_normalisation_audit.csv"}
    if not required_context.issubset(manifest.get("context_sha256", {})):
        raise ValueError("Run the integrated Step 0 extraction and cleaning before landscape.py.")
    for filename, expected in manifest["context_sha256"].items():
        context_path = STEP0_DIR / filename
        if not context_path.is_file() or hashlib.sha256(context_path.read_bytes()).hexdigest() != expected:
            raise ValueError("Step 0 context changed after export: " + filename)
    data = pd.read_csv(path).rename(columns={"family_id": "docdb_family_id", "year": "earliest_filing_year",
                                           "applicant": "clean_name", "share": "fractional_credit"})
    validate_family_applicants(data)
    return data


# EXPORT: retain calculation precision; round only when presenting results.
def write_step2(data, name, index=False):
    """Keep full numeric precision; formatting belongs in the presentation."""
    data.to_csv(STEP2_DIR / f"{name}.csv", index=index)


# PLOTTING: apply the shared year limits, grid and incomplete-year shading.
# Shading describes data completeness and is not a confidence interval.
def finish_time_axis(ax):
    """Format a calendar-year axis using the shared completeness rule."""
    shade_truncated(ax)
    ax.set_xlim(YEAR_MIN, YEAR_MAX)
    ax.set_xlabel("family earliest filing year")
    ax.grid(alpha=0.2)

# INEQUALITY: sort positive portfolio credits, then cumulate applicant shares
# and credit shares. The equality diagonal is a graphical reference only.
def lorenz_curve(counts) -> tuple[np.ndarray, np.ndarray]:
    """Return (cum_firm_share, cum_patent_share) starting at (0, 0) and ending at (1, 1)."""
    c = np.sort(np.asarray(counts, dtype=float))
    c = c[c > 0]
    n = len(c)
    if n == 0:
        return np.array([0.0, 1.0]), np.array([0.0, 1.0])
    cum_firms = np.concatenate(([0.0], np.arange(1, n + 1) / n))
    cum_patents = np.concatenate(([0.0], np.cumsum(c) / c.sum()))
    return cum_firms, cum_patents


# GINI: integrate the Lorenz curve with trapezoids and return 1 minus twice
# the area. An empty/zero portfolio has an undefined Gini, not zero inequality.
def gini_from_counts(counts) -> float:
    """Measure portfolio inequality from the area under its Lorenz curve."""
    if len(counts) == 0 or np.sum(counts) <= 0:
        return np.nan
    x, y = lorenz_curve(counts)
    return float(1.0 - 2.0 * (np.trapezoid(y, x) if hasattr(np, "trapezoid") else np.trapz(y, x)))


# CONCENTRATION: normalise positive finite applicant credits by their sum.
# CR4/CR8 sum the largest four/eight shares; HHI sums squared shares;
# 1/HHI is an effective count of equally sized applicants, not literal firms.
# Full counting uses family-name attributions; fractional counting uses one
# total credit per named family. These are patent shares, not market shares.
# The optional Lotka exponent is an exploratory log-log frequency fit for
# integer portfolio sizes; it is not a validated power-law or causal model.
def concentration_measures(counts, label: str = "", exploratory=False) -> dict:
    """Concentration of full attributions or fractional credits, as supplied."""
    c = np.sort(np.asarray(counts, dtype=float))[::-1]
    c = c[np.isfinite(c) & (c > 0)]
    total = float(c.sum())
    shares = c / total if total > 0 else np.array([])
    hh = float(np.sum(shares ** 2)) if total > 0 else np.nan
    out = {
        "group": label,
        "applicants": len(c),
        "attributions": total,
        "CR4": float(shares[:4].sum()) if total > 0 else np.nan,
        "CR8": float(shares[:8].sum()) if total > 0 else np.nan,
        "HH": hh,
        "1/HH": 1.0 / hh if hh > 0 else np.nan,
        "Gini": gini_from_counts(c) if exploratory else np.nan,
        "Lotka L": np.nan,
    }
    # Lotka concerns integer portfolio sizes, not rounded fractional credits.
    if exploratory and len(c) > 0 and np.allclose(c, np.round(c)):
        sizes, freqs = np.unique(c.astype(int), return_counts=True)
        mask = sizes >= 2
        if mask.sum() >= 3:
            slope, _, _, _, _ = stats.linregress(np.log10(sizes[mask]), np.log10(freqs[mask]))
            out["Lotka L"] = float(-slope)
    return out


# COHORTS: obtain each name's first/last family origin years and split its
# portfolio before/after SPLIT_YEAR. First observation is not incorporation
# or actual market entry. Total families support the cohort analysis rather
# than creating another top-applicant league table.
def classify_incumbents_entrants(
    df: pd.DataFrame,
    split_year: int = SPLIT_YEAR,
    applicant_col: str = "clean_name",
    year_col: str = "earliest_filing_year",
    unit_col: str = "docdb_family_id",
) -> pd.DataFrame:
    """Classify applicants as 'incumbent' (active < split_year) or 'entrant' (first active >= split_year)."""
    first_year = df.groupby(applicant_col)[year_col].min().rename("first_year")
    last_year = df.groupby(applicant_col)[year_col].max().rename("last_year")
    total_fams = df.groupby(applicant_col)[unit_col].nunique().rename("total_families")
    pre_fams = (
        df[df[year_col] < split_year]
        .groupby(applicant_col)[unit_col]
        .nunique()
        .rename("pre_split_families")
    )
    post_fams = (
        df[df[year_col] >= split_year]
        .groupby(applicant_col)[unit_col]
        .nunique()
        .rename("post_split_families")
    )

    summary = pd.concat([first_year, last_year, total_fams, pre_fams, post_fams], axis=1).fillna(0)
    summary["pre_split_families"] = summary["pre_split_families"].astype(int)
    summary["post_split_families"] = summary["post_split_families"].astype(int)
    summary["status"] = np.where(summary["first_year"] < split_year, "incumbent", "entrant")
    return summary.sort_values("total_families", ascending=False)


# WINDOW TURNOVER: compare sets of active names in complete WINDOW-year
# intervals. New names exclude all previously observed names; absence uses
# the previous-window active set. The first window is left-censored and
# the final partial window is excluded. Absence is not a business exit.
def compute_entry_exit(
    df: pd.DataFrame,
    window: int = WINDOW,
    year_min: int = YEAR_MIN,
    year_max: int = LAST_COMPLETE_YEAR,
    applicant_col: str = "clean_name",
    unit_col: str = "docdb_family_id",
) -> pd.DataFrame:
    """First observations and absence in the next complete window, not business exits."""
    rows = []
    seen_so_far = set()
    prev_active = set()
    for w_start in range(year_min, year_max - window + 2, window):
        w_end = w_start + window - 1
        sub = df[df.earliest_filing_year.between(w_start, w_end)]
        active = set(sub[applicant_col].dropna().unique())
        new_to_sector = active - seen_so_far
        disappeared = prev_active - active
        total_fams = sub[unit_col].nunique()
        entrant_fams = sub[sub[applicant_col].isin(new_to_sector)][unit_col].nunique()
        first_window = w_start == year_min
        rows.append({
            "window": f"{w_start}-{w_end}",
            "active_applicants": len(active),
            "new_to_sector": np.nan if first_window else len(new_to_sector),
            "entrants_share_families_%": (100 * entrant_fams / total_fams
                if total_fams > 0 and not first_window else np.nan),
            "disappeared_from_prev": np.nan if first_window else len(disappeared),
            "rate_of_disappearance_%": (100 * len(disappeared) / len(prev_active)
                if prev_active else np.nan),
            "left_censored": first_window,
        })
        seen_so_far.update(active)
        prev_active = active
    return pd.DataFrame(rows)


# SUBGROUP GROWTH: deduplicate family/full-CPC pairs, count two disjoint
# periods and divide by each period length before comparing annual means.
# Zero-base growth stays undefined; small bases are flagged. A family can
# belong to several subgroups, so these counts must not be added together.
# Anna's CPC mix uses four-character subclasses and percentages instead.
def subfield_growth_table(df, past=(2013, 2017), recent=(2018, 2022), min_base=10):
    """Compare annual family frequencies; no artificial +1 for a zero base."""
    if past[1] < past[0] or recent[1] < recent[0] or past[1] >= recent[0]:
        raise ValueError("Choose two ordered, non-overlapping periods.")
    data = df.drop_duplicates(["docdb_family_id", "cpc_subgroup"])
    pre = data[data.earliest_filing_year.between(*past)].groupby("cpc_subgroup").docdb_family_id.nunique()
    post = data[data.earliest_filing_year.between(*recent)].groupby("cpc_subgroup").docdb_family_id.nunique()
    result = pd.concat([pre.rename("families_past"), post.rename("families_recent")], axis=1).fillna(0)
    result[["families_past", "families_recent"]] = result[["families_past", "families_recent"]].astype(int)
    result["annual_past"] = result.families_past / (past[1] - past[0] + 1)
    result["annual_recent"] = result.families_recent / (recent[1] - recent[0] + 1)
    result["growth_%"] = np.nan
    positive_base = result.annual_past > 0
    result.loc[positive_base, "growth_%"] = 100 * (
        result.loc[positive_base, "annual_recent"] / result.loc[positive_base, "annual_past"] - 1)
    result["growth_status"] = "comparable_base"
    result.loc[result.families_past < min_base, "growth_status"] = "small_base"
    result.loc[result.families_past == 0, "growth_status"] = "new_in_recent_period"
    return result.reset_index().sort_values("families_recent", ascending=False).reset_index(drop=True)


# FOLLOW-UP: among names active at year t, count those absent in t+1 to t+3.
# Calculate the rate only when all three follow-up years are complete.
# This is observed patenting inactivity, not a verified company closure.
def compute_inactivity(df, year_min=YEAR_MIN, year_max=LAST_COMPLETE_YEAR):
    """Measure three-year patenting inactivity only with complete follow-up."""
    rows = []
    data = df[["clean_name", "docdb_family_id", "earliest_filing_year"]].drop_duplicates()
    for year in range(year_min, year_max + 1):
        active = set(data.loc[data.earliest_filing_year == year, "clean_name"])
        inactive_n = np.nan
        rate = np.nan
        complete = year + 3 <= year_max
        if complete:
            following = data[data.earliest_filing_year.between(year + 1, year + 3)]
            inactive_n = len(active - set(following.clean_name))
            if active:
                rate = 100 * inactive_n / len(active)
        rows.append({"year": year, "active_applicants": len(active),
                     "inactive_3y": inactive_n, "inactivity_rate_%": rate,
                     "complete_followup": complete})
    return pd.DataFrame(rows)


# RTA: divide applicant subgroup incidence by sector subgroup incidence.
# The applicant denominator is its coded-family portfolio; the sector
# denominator includes all coded selected families, even without names.
# RTA above one means relative specialization, not quality or market share.
def compute_specialization(applicants, cpc):
    """Compare coded-family subgroup incidence within applicant and sector portfolios."""
    names = applicants[["docdb_family_id", "clean_name"]].drop_duplicates()
    codes = cpc[["docdb_family_id", "cpc_subgroup"]].drop_duplicates()
    pairs = names.merge(codes, on="docdb_family_id", how="inner")
    columns = ["clean_name", "cpc_subgroup", "families_in_subfield", "coded_portfolio",
               "sector_subfield_families", "sector_coded_families", "RTA"]
    if pairs.empty:
        return pd.DataFrame(columns=columns)
    portfolio = pairs.groupby("clean_name").docdb_family_id.nunique().rename("coded_portfolio")
    counts = pairs.groupby(["clean_name", "cpc_subgroup"]).docdb_family_id.nunique().rename("families_in_subfield")
    sector_counts = codes.groupby("cpc_subgroup").docdb_family_id.nunique().rename("sector_subfield_families")
    result = counts.reset_index().merge(portfolio, on="clean_name", validate="many_to_one")
    result = result.merge(sector_counts, on="cpc_subgroup", validate="many_to_one")
    result["sector_coded_families"] = codes.docdb_family_id.nunique()
    applicant_share = result.families_in_subfield / result.coded_portfolio
    sector_share = result.sector_subfield_families / result.sector_coded_families
    result["RTA"] = applicant_share / sector_share
    return result[columns].sort_values(["clean_name", "cpc_subgroup"]).reset_index(drop=True)


# PARTICIPATION: reuse Anna's whole-sector annual totals as denominators
# and derive active/new-name counts from the existing cleaned family pairs.
# Applicant-name coverage is not Anna's country-information coverage.
# Entrant family shares count each observed family once even with many names.
def sector_participation(links, totals):
    """Measure observed-name participation using existing sector family totals."""
    data = links[["docdb_family_id", "clean_name", "earliest_filing_year"]].drop_duplicates()
    data = data[data.clean_name.fillna("").str.strip().ne("")]
    first = data.groupby("clean_name").earliest_filing_year.min()
    rows = []
    for year, total in totals[["year", "families"]].itertuples(index=False, name=None):
        active = data[data.earliest_filing_year.eq(year)]
        n_active = active.clean_name.nunique()
        observed = active.docdb_family_id.nunique()
        new = first[first.eq(year)].index
        new_families = active[active.clean_name.isin(new)].docdb_family_id.nunique()
        left_censored = year == totals.year.min()
        rows.append({"year": year, "families": total, "families_with_applicant": observed,
                     "applicant_coverage_pct": 100*observed/total if total else np.nan,
                     "active_applicants": n_active,
                     "new_applicants": np.nan if left_censored else len(new),
                     "new_applicant_share_pct": 100*len(new)/n_active if n_active and not left_censored else np.nan,
                     "entrant_family_share_observed_pct": 100*new_families/observed if observed and not left_censored else np.nan,
                     "mean_full_families": len(active)/n_active if n_active else np.nan,
                     "mean_fractional_families": observed/n_active if n_active else np.nan})
    return pd.DataFrame(rows)


# NEW FIELD COMPARISON: query only the additional PV/wind scopes, with the
# existing PI/date rules. EV and all-patent denominators are read from Step 1.
# CAGR is newly calculated only for the added fields, never again for EV.
# The plot compares EV with PV/wind; Anna's EV/all-patent plot is not repeated.
# The added CPC-only fields can overlap; record overlaps instead of summing.
def section_comparison(volume, sector_panel):
    """Explicit additional fields; reuse Step 1 for EV and the all-patent benchmark."""
    base = int(STEP2_CONFIG["comparison_base_year"])
    if not YEAR_MIN <= base < LAST_COMPLETE_YEAR:
        raise ValueError("Comparison base must precede the last complete year.")
    all_counts = volume[volume.scope.eq("all patents") & volume.level.eq("family") & volume.series.eq("all")]
    world = all_counts.set_index("year").n.reindex(range(YEAR_MIN, YEAR_MAX + 1), fill_value=0)
    rows, summaries, overlaps = [sector_panel.assign(sector=SECTOR_NAME)], [], []
    for name, prefixes in STEP2_CONFIG["comparison_sectors"].items():
        counts, overlap = comparison_family_counts(prefixes)
        values = counts.set_index("year").n.reindex(world.index, fill_value=0).astype(float)
        frame = values.rename("families").rename_axis("year").reset_index()
        frame["sector"] = name
        frame["all_patent_families"] = frame.year.map(world)
        frame["share_all_patents_pct"] = 100 * frame.families / frame.all_patent_families.replace(0, np.nan)
        complete_values = values.where(values.index <= LAST_COMPLETE_YEAR)
        frame["yoy_pct"] = (100 * (complete_values / complete_values.shift(1).replace(0, np.nan) - 1)).to_numpy()
        frame["rolling3_families"] = complete_values.rolling(3, min_periods=3).mean().to_numpy()
        frame["incomplete"] = frame.year.gt(LAST_COMPLETE_YEAR)
        rows.append(frame)
        start, end = float(values.loc[base]), float(values.loc[LAST_COMPLETE_YEAR])
        summaries.append({"sector": name, "base_year": base, "end_year": LAST_COMPLETE_YEAR,
                          "families_base": start, "families_end": end,
                          "cagr_pct": 100 * ((end / start) ** (1 / (LAST_COMPLETE_YEAR - base)) - 1) if start > 0 else np.nan,
                          "cagr_status": "defined" if start > 0 else "zero_base"})
        overlaps.append({"comparison_sector": name, "shared_complete_families_with_ev": overlap,
                         "definition": "CPC-only benchmark; same PI and dating; EV-specific exclusions do not apply"})
    panel = pd.concat(rows, ignore_index=True)
    panel["index_base100"] = np.nan
    for name, group in panel.groupby("sector"):
        value = group.loc[group.year.eq(base), "families"].iloc[0]
        if value > 0:
            panel.loc[group.index, "index_base100"] = 100 * group.families / value
    # This single file replaces the EV-only diagnostics; no duplicate extraction or panel export.
    write_step2(panel, "sector_growth_diagnostics")
    write_step2(pd.DataFrame(summaries), "comparison_additional_field_cagr")
    write_step2(pd.DataFrame(overlaps), "comparison_scope_overlap")
    fig, ax = plt.subplots(figsize=(11, 5))
    for name, group in panel.groupby("sector"):
        shown = group[group.year.ge(base) & group.year.le(LAST_COMPLETE_YEAR)]
        ax.plot(shown.year, shown.index_base100, label=name)
    # Anna's figure 03 already compares EV with all patents. This figure adds
    # only the photovoltaic/wind comparison, retaining EV as the reference.
    finish_time_axis(ax)
    ax.set_xlim(base, YEAR_MAX)
    ax.set(title=f"Additional Step 2 field comparison: {base} = 100", ylabel="family-count index")
    ax.legend()
    save_figure(STEP2_DIR / "16_additional_field_comparison.png")


# STEP 2 ORCHESTRATION: add distribution, cohort and subgroup questions only.
# Reuse Step 1 totals and the Step 0 cleaned names; do not rerun Anna's
# volume, CAGR, CPC-subclass, WIPO, office or country analysis here.
# RELATIVE SUBFIELD GROWTH: use all selected sector families from Step 1,
# including families with no charging CPC or applicant. CPC incidences overlap.
# The ratio of annual growth factors identifies gains relative to the sector;
# it is not a CAGR and is undefined when either historical base is zero.
def contextual_subfield_growth(cpc, totals, past=PAST_PERIOD, recent=RECENT_PERIOD, min_base=10):
    result = subfield_growth_table(cpc, past, recent, min_base)
    before = totals.loc[totals.year.between(*past), "families"].sum()
    after = totals.loc[totals.year.between(*recent), "families"].sum()
    n_before, n_after = past[1] - past[0] + 1, recent[1] - recent[0] + 1
    sector_factor = (after / n_after) / (before / n_before) if before > 0 else np.nan
    result["sector_families_past"] = before
    result["sector_families_recent"] = after
    result["sector_growth_pct"] = 100 * (sector_factor - 1)
    result["share_past_pct"] = 100 * result.families_past / before if before > 0 else np.nan
    result["share_recent_pct"] = 100 * result.families_recent / after if after > 0 else np.nan
    result["share_change_pp"] = result.share_recent_pct - result.share_past_pct
    result["relative_growth_index"] = ((result.annual_recent / result.annual_past.replace(0, np.nan)) /
                                        sector_factor if sector_factor > 0 else np.nan)
    result["trajectory"] = "insufficient_base"
    reliable = result.growth_status.eq("comparable_base") & result.relative_growth_index.notna()
    result.loc[reliable & result.relative_growth_index.gt(1), "trajectory"] = "faster_than_sector"
    result.loc[reliable & result.relative_growth_index.le(1), "trajectory"] = "slower_than_sector"
    result.loc[reliable & np.isclose(result.relative_growth_index, 1), "trajectory"] = "in_line_with_sector"
    result.loc[result.families_past.eq(0), "trajectory"] = "new_observed_code"
    result["label"] = result.cpc_subgroup.map(STEP2_CONFIG.get("subfield_labels", {})).fillna(result.cpc_subgroup)
    return result


# ACTOR DYNAMICS: compare full counts per year across the SAME two periods as
# the subfield analysis. Fractional shares use all named sector-family credits.
# A large recent/lifetime proportion is deliberately not called growth.
def actor_period_dynamics(applicants, past=PAST_PERIOD, recent=RECENT_PERIOD, min_base=10):
    data = applicants[applicants.earliest_filing_year.le(LAST_COMPLETE_YEAR)].copy()
    before = data[data.earliest_filing_year.between(*past)]
    after = data[data.earliest_filing_year.between(*recent)]
    result = data.groupby("clean_name").agg(first_year=("earliest_filing_year", "min"),
                                           last_year=("earliest_filing_year", "max"))
    for label, frame in [("past", before), ("recent", after)]:
        result[f"families_{label}"] = frame.groupby("clean_name").docdb_family_id.nunique().reindex(result.index, fill_value=0)
        credits = frame.groupby("clean_name").fractional_credit.sum().reindex(result.index, fill_value=0)
        result[f"fractional_credits_{label}"] = credits
        result[f"share_named_families_{label}_pct"] = 100 * credits / credits.sum() if credits.sum() > 0 else np.nan
    result["annual_past"] = result.families_past / (past[1] - past[0] + 1)
    result["annual_recent"] = result.families_recent / (recent[1] - recent[0] + 1)
    result["growth_pct"] = 100 * (result.annual_recent / result.annual_past.replace(0, np.nan) - 1)
    result["growth_base_sufficient"] = result.families_past.ge(min_base)
    result["share_change_pp"] = result.share_named_families_recent_pct - result.share_named_families_past_pct
    result["recent_active_years"] = after.groupby("clean_name").earliest_filing_year.nunique().reindex(result.index, fill_value=0)
    latest = data[data.earliest_filing_year.between(max(recent[0], recent[1]-2), recent[1])]
    result["latest_three_year_families"] = latest.groupby("clean_name").docdb_family_id.nunique().reindex(result.index, fill_value=0)
    result["entry_status"] = np.where(result.first_year.ge(recent[0]),
        "first_observed_in_recent_period", "observed_before_recent_period")
    result.loc[result.first_year.eq(YEAR_MIN), "entry_status"] = "present_at_start_left_censored"
    result["entry_definition"] = "first sector-family origin observed in this dataset; not founding or first-ever patent"
    return result.reset_index()


# RECENT SPECIALIZATION: keep the RTA numerator, denominator and growth period
# aligned. Coverage makes uncoded parts of each actor's portfolio visible.
def recent_specialization(applicants, cpc, recent=RECENT_PERIOD):
    names = applicants[applicants.earliest_filing_year.between(*recent)]
    codes = cpc[cpc.earliest_filing_year.between(*recent)]
    result = compute_specialization(names, codes)
    all_families = names.groupby("clean_name").docdb_family_id.nunique()
    result["all_recent_families"] = result.clean_name.map(all_families)
    result["coded_coverage_pct"] = 100 * result.coded_portfolio / result.all_recent_families
    result["sufficient_base"] = (result.families_in_subfield.ge(STEP2_CONFIG.get("min_rta_families", 5)) &
        result.coded_portfolio.ge(STEP2_CONFIG.get("min_rta_portfolio", 10)) &
        result.coded_coverage_pct.ge(STEP2_CONFIG.get("min_coded_coverage_pct", 50)))
    result["period_start"], result["period_end"] = recent
    return result


# SCREENING: combine recent volume, repeat activity and technical exposure.
# No composite score, acquisition recommendation or automatic identity merge
# is made. PSN COMPANY identifies a recorded type, not a verified start-up.
def company_type_flags(labels):
    """Keep clear company evidence despite UNKNOWN; flag conflicting entity types."""
    tokens = labels.fillna("").map(lambda x: {v.strip().upper() for v in str(x).split(";")} - {""})
    company = tokens.map(lambda x: "COMPANY" in x)
    conflict = tokens.map(lambda x: bool(x & {"UNIVERSITY", "HOSPITAL", "INDIVIDUAL", "PERSON"}))
    return pd.DataFrame({"is_recorded_company": company & ~conflict,
                         "type_review_required": tokens.map(lambda x: x != {"COMPANY"}),
                         "type_conflict": company & conflict}, index=labels.index)


def screen_players(dynamics, rta, growth, applicants, cpc, metadata):
    result = dynamics.copy()
    labels = metadata.copy().fillna("")
    labels["psn_sector"] = labels.psn_sector.str.upper().str.strip()
    kinds = labels.groupby("applicant").psn_sector.agg(lambda x: "; ".join(sorted(set(x)-{""})))
    result["recorded_type"] = result.clean_name.map(kinds).fillna("unknown")
    flags = company_type_flags(result.recorded_type)
    for column in flags:
        result[column] = flags[column]
    result["country"] = "not available in shared handoff; review required"
    result["identity_review_required"] = True
    hot = set(growth.loc[growth.trajectory.eq("faster_than_sector"), "cpc_subgroup"])
    eligible_rta = rta[rta.cpc_subgroup.isin(hot) & rta.sufficient_base & rta.RTA.ge(1)]
    if eligible_rta.empty:
        result["specialized_growing_subfields"] = ""
    else:
        descriptions = eligible_rta.groupby("clean_name").cpc_subgroup.agg(lambda x: "; ".join(sorted(set(x))))
        result["specialized_growing_subfields"] = result.clean_name.map(descriptions).fillna("")
    names = applicants[applicants.earliest_filing_year.between(*RECENT_PERIOD)]
    codes = cpc[cpc.earliest_filing_year.between(*RECENT_PERIOD) & cpc.cpc_subgroup.isin(hot)]
    exposed = names[["docdb_family_id", "clean_name"]].merge(
        codes[["docdb_family_id"]].drop_duplicates(), on="docdb_family_id", how="inner")
    exposure = exposed.groupby("clean_name").docdb_family_id.nunique()
    result["families_in_growing_subfields"] = result.clean_name.map(exposure).fillna(0).astype(int)
    result["growing_subfield_exposure_pct"] = (100 * result.families_in_growing_subfields /
                                               result.families_recent.replace(0, np.nan))
    result["persistent_recent_activity"] = (result.recent_active_years.ge(STEP2_CONFIG.get("min_recent_active_years", 2)) &
                                              result.latest_three_year_families.gt(0))
    result["eligible_for_screening"] = (result.is_recorded_company & result.persistent_recent_activity &
        result.families_recent.ge(STEP2_CONFIG.get("min_screen_recent_families", 10)))
    result["screening_reason"] = ""
    eligible = result[result.eligible_for_screening]
    n = int(STEP2_CONFIG.get("screen_top_n", 15))
    scale = eligible.nlargest(n, "fractional_credits_recent").index
    result.loc[scale, "screening_reason"] = "recent sector scale; benchmark incumbent or active firm"
    specialist = result.eligible_for_screening & result.specialized_growing_subfields.ne("") & result.share_change_pp.gt(0)
    emerging = result[specialist].nlargest(n, "share_change_pp").index
    result.loc[emerging, "screening_reason"] = "gaining sector share and specialized in a growing subfield"
    result["selected_for_step3_review"] = result.screening_reason.ne("")
    return result.sort_values(["selected_for_step3_review", "fractional_credits_recent"], ascending=False)


def section10_step2(applicants):
    """Map competitive structure and build a reviewable Step 3 screening table."""
    STEP2_DIR.mkdir(parents=True, exist_ok=True)
    if not YEAR_MIN <= PAST_PERIOD[0] <= PAST_PERIOD[1] < RECENT_PERIOD[0] <= RECENT_PERIOD[1] <= LAST_COMPLETE_YEAR:
        raise ValueError("Step 2 periods must be ordered, disjoint and complete.")
    validate_family_applicants(applicants)
    # Reuse Anna's saved whole-sector counts; never query or recompute Step 1.
    volume = pd.read_csv(STEP1_DIR / "volume_per_year.csv")
    selected = volume[volume.scope.eq(SECTOR_NAME) & volume.level.eq("family") & volume.series.eq("all")]
    if selected.year.duplicated().any():
        raise ValueError("Duplicate Step 1 annual sector counts.")
    totals = selected.set_index("year").n.reindex(range(YEAR_MIN, YEAR_MAX+1), fill_value=0).rename("families").rename_axis("year").reset_index()
    complete = applicants[applicants.earliest_filing_year.between(YEAR_MIN, LAST_COMPLETE_YEAR)].copy()
    participation = sector_participation(applicants, totals)
    participation["incomplete"] = participation.year.gt(LAST_COMPLETE_YEAR)
    if participation.families_with_applicant.gt(participation.families).any():
        raise ValueError("Applicants and Step 1 totals differ: rerun from the same Step 0 export.")
    participation["entry_definition"] = "first observed in sector, not first-ever patent"
    participation["left_censored"] = participation.year.eq(YEAR_MIN)
    write_step2(participation, "sector_participation_annual")

    # Fractional counting is the main view: one credit per named family.
    # Full counting stays in the CSV as a sensitivity check, not a second story.
    rows, leaders = [], []
    for year in range(YEAR_MIN, YEAR_MAX+1):
        active = applicants[applicants.earliest_filing_year.eq(year)]
        for method, values in [("full", active.groupby("clean_name").docdb_family_id.nunique()),
                               ("fractional", active.groupby("clean_name").fractional_credit.sum())]:
            row = concentration_measures(values, method)
            row.update(year=year, incomplete=year > LAST_COMPLETE_YEAR,
                       unique_observed_families=active.docdb_family_id.nunique())
            row["HHI"] = row["HH"]
            rows.append(row)
            for name, value in values.nlargest(4).items():
                leaders.append(dict(year=year, counting=method, applicant=name, credits=value,
                                    counting_total=values.sum(), share_pct=100*value/values.sum()))
    annual = pd.DataFrame(rows).drop(columns=["Gini", "Lotka L", "CR8"])
    write_step2(annual, "q1_concentration_annual")
    write_step2(pd.DataFrame(leaders), "q1_cr4_leaders")
    main = annual[annual.group.eq("fractional")]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    axes[0].plot(main.year, 100*main.CR4, label="fractional patent credits")
    axes[1].plot(main.year, main.HHI, label="HHI, scale 0-1")
    axes[0].set(title="CR4: four largest observed applicants", ylabel="named-family credits (%)")
    axes[1].set(title="Concentration of patent activity", ylabel="HHI (higher = more concentrated)")
    for ax in axes:
        finish_time_axis(ax)
        ax.legend()
    save_figure(STEP2_DIR / "08_concentration_annual.png")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    axes[0].plot(participation.year, participation.active_applicants, label="active names")
    axes[0].plot(participation.year, participation.new_applicants, label="first observed in sector")
    axes[1].plot(participation.year, participation.entrant_family_share_observed_pct,
                 label="families with a newly observed name")
    axes[0].set(title="Observed sector participation", ylabel="applicants")
    axes[1].set(title="Weight of newly observed applicants", ylabel="named families (%)")
    for ax in axes:
        finish_time_axis(ax)
        ax.legend()
    save_figure(STEP2_DIR / "10_participation.png")
    inactivity = compute_inactivity(complete)
    write_step2(inactivity, "q2_inactivity_3y")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(inactivity.year, inactivity["inactivity_rate_%"], label="no observed family in t+1 to t+3")
    ax.set(title="Observed patenting inactivity, not business exit", ylabel="active applicants at t (%)")
    finish_time_axis(ax)
    ax.legend()
    save_figure(STEP2_DIR / "11_inactivity_3y.png")

    # One CPC retrieval supports growth, recent RTA and screening. No new
    # applicant cleaning or first-member-year filter is introduced.
    cpc = sector_family_cpc().rename(columns={"family_id": "docdb_family_id", "year": "earliest_filing_year"})
    cpc["cpc_subgroup"] = cpc.cpc_class_symbol.fillna("").str.replace(" ", "", regex=False)
    cpc = cpc[cpc.cpc_subgroup.str.startswith(SUBFIELD_CPC_PREFIXES) &
              cpc.earliest_filing_year.between(YEAR_MIN, LAST_COMPLETE_YEAR)]
    cpc = cpc.drop_duplicates(["docdb_family_id", "cpc_subgroup"])
    growth = contextual_subfield_growth(cpc, totals, PAST_PERIOD, RECENT_PERIOD, MIN_GROWTH_BASE)
    write_step2(growth, "q3_subfield_growth")
    dynamics = actor_period_dynamics(complete, PAST_PERIOD, RECENT_PERIOD, MIN_GROWTH_BASE)
    rta = recent_specialization(complete, cpc, RECENT_PERIOD)
    write_step2(rta, "q3_specialization_rta")
    metadata = pd.read_csv(STEP0_DIR / "sector_family_applicant_sectors.csv").fillna("")
    metadata = metadata[metadata.year.between(YEAR_MIN, LAST_COMPLETE_YEAR)]
    screening = screen_players(dynamics, rta, growth, complete, cpc, metadata)
    integrated = {"files": []}
    if STEP2_CONFIG.get("run_integrated_context", True):
        screening, integrated = run_integrated_context(
            applicants, cpc, totals, screening, ROOT, STEP0_DIR, STEP2_DIR, first_patent_ever,
            YEAR_MIN, LAST_COMPLETE_YEAR, YEAR_MAX, WINDOW, PAST_PERIOD, RECENT_PERIOD,
            SPLIT_YEAR, STEP2_CONFIG.get("history_batch_size", 5000))
    write_step2(screening, "q2_applicant_summary")
    shortlist = screening[screening.selected_for_step3_review]
    write_step2(shortlist, "q4_player_screening")

    # Size vs relative growth separates large fields from small fast growers.
    reliable = growth[growth.growth_status.eq("comparable_base") & growth.relative_growth_index.notna()]
    if not reliable.empty:
        fig, ax = plt.subplots(figsize=(11, 6))
        ax.scatter(reliable.families_recent, reliable.relative_growth_index,
                   s=40+300*reliable.share_recent_pct/100, alpha=0.7)
        ax.axhline(1, color="grey", linestyle="--", label="same growth as sector")
        for _, row in reliable.nlargest(10, "families_recent").iterrows():
            ax.annotate(row.label, (row.families_recent, row.relative_growth_index), fontsize=8,
                        xytext=(3, 4), textcoords="offset points")
        ax.set(xscale="log", xlabel=f"families in {RECENT_PERIOD[0]}-{RECENT_PERIOD[1]} (log scale)",
               ylabel="subfield / sector growth factor (1 = sector)", title="Subfield size and growth relative to the sector")
        ax.legend()
        save_figure(STEP2_DIR / "12_subfield_growth.png")
    # Use the same recent period for both the shortlist and the RTA matrix.
    names = shortlist.head(12).clean_name
    codes = growth.head(10).cpc_subgroup
    if len(names) and len(codes) and not rta.empty:
        matrix = rta.pivot(index="clean_name", columns="cpc_subgroup", values="RTA").reindex(index=names, columns=codes)
        coverage = rta.groupby("clean_name").coded_coverage_pct.first()
        base = rta.groupby("clean_name").coded_portfolio.first()
        supported = (coverage.reindex(names).ge(STEP2_CONFIG.get("min_coded_coverage_pct", 50)) &
                     base.reindex(names).ge(STEP2_CONFIG.get("min_rta_portfolio", 10)))
        matrix.loc[supported.to_numpy()] = matrix.loc[supported.to_numpy()].fillna(0)
        matrix.loc[~supported.to_numpy()] = np.nan
        fig, ax = plt.subplots(figsize=(12, 7))
        image = ax.imshow(np.ma.masked_invalid(matrix.to_numpy(dtype=float)), aspect="auto", cmap="YlGnBu", vmin=0)
        ax.set_xticks(range(len(codes)), codes, rotation=60, ha="right")
        ax.set_yticks(range(len(names)), names)
        ax.set_title("Recent specialization of screened firms (blank = insufficient coverage)")
        fig.colorbar(image, ax=ax, label="RTA (1 = sector incidence; not quality)")
        save_figure(STEP2_DIR / "13_specialization_rta.png")

    # Additional sector comparison remains available for the broader context,
    # but is separate from the core competition/screening outputs.
    if STEP2_CONFIG.get("run_additional_field_comparison", False):
        world = volume[volume.scope.eq("all patents") & volume.level.eq("family") & volume.series.eq("all")]
        panel = totals.copy()
        panel["all_patent_families"] = panel.year.map(world.set_index("year").n)
        panel["share_all_patents_pct"] = 100*panel.families/panel.all_patent_families.replace(0, np.nan)
        values = panel.families.where(panel.year.le(LAST_COMPLETE_YEAR))
        panel["yoy_pct"] = 100*(values/values.shift(1).replace(0, np.nan)-1)
        panel["rolling3_families"] = values.rolling(3, min_periods=3).mean()
        panel["incomplete"] = panel.year.gt(LAST_COMPLETE_YEAR)
        section_comparison(volume, panel)
    # SDG proposals are exploratory and never replace the mandatory PEST.
    if STEP2_CONFIG.get("run_exploratory_appendix", False):
        write_step2(compute_entry_exit(complete), "q2_entry_exit")
        overall = pd.DataFrame([
            concentration_measures(complete.groupby("clean_name").docdb_family_id.nunique(), "full", exploratory=True),
            concentration_measures(complete.groupby("clean_name").fractional_credit.sum(), "fractional", exploratory=True)])
        write_step2(overall, "q1_overall_concentration")
        if STEP2_CONFIG.get("run_sdg_analysis", False):
            section_sdg(applicants)
    # Write an explicit current-run file list; older files in this directory
    # are not silently presented as results of the new methodology.
    current = ["q1_concentration_annual.csv", "q1_cr4_leaders.csv", "sector_participation_annual.csv",
               "q2_inactivity_3y.csv", "q2_applicant_summary.csv", "q3_subfield_growth.csv",
               "q3_specialization_rta.csv", "q4_player_screening.csv", "08_concentration_annual.png",
               "10_participation.png", "11_inactivity_3y.png"]
    if not reliable.empty:
        current.append("12_subfield_growth.png")
    if len(names) and len(codes) and not rta.empty:
        current.append("13_specialization_rta.png")
    manifest = {"method": "integrated-competition-and-screening-v3", "core_outputs": current,
                "integrated_context": integrated,
                "step0_legal_form_cleaning": bool(_cfg["applicants"].get("legal_form_cleaning", True)),
                "past_period": list(PAST_PERIOD), "recent_period": list(RECENT_PERIOD),
                "last_complete_year": LAST_COMPLETE_YEAR,
                "thresholds": {"growth_base": MIN_GROWTH_BASE,
                    "screen_recent_families": STEP2_CONFIG.get("min_screen_recent_families", 10),
                    "screen_active_years": STEP2_CONFIG.get("min_recent_active_years", 2),
                    "min_coded_coverage_pct": STEP2_CONFIG.get("min_coded_coverage_pct", 50)},
                "step1_source_sha256": hashlib.sha256((STEP1_DIR / "volume_per_year.csv").read_bytes()).hexdigest(),
                "other_files_note": "Unlisted outputs can belong to an older run or an optional appendix; do not mix methods."}
    (STEP2_DIR / "step2_run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (STEP2_DIR / "READING_GUIDE.md").write_text(
        STEP2_READING_GUIDE + (INTEGRATED_READING_GUIDE if integrated["files"] else ""), encoding="utf-8")
    print("Step 2: competition mapped;", len(shortlist), "firms selected for identity and Step 3 review.")
    print("Current outputs are listed in step2_run_manifest.json; PEST runs next unless explicitly skipped.")


STEP2_READING_GUIDE = """# Step 2: competition and screening

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
"""


# Exploratory proposals from the previous Step 2; never an official SDG classification.
SDG_RULES_VERSION = 'ev-sql-cpc-text-v1'
SDG_RULES_SQL = "SELECT 'E7_eff_cpc' AS rule_id, 7 AS sdg, '7.3' AS target_hint, 'Y02T10/92' AS cpc_prefix, '' AS text_pattern, 'Energy-efficient vehicle charging/discharging CPC tag' AS reason\nUNION ALL\nSELECT 'E7_eff_text', 7, '7.3', 'B60L53/', '%energy efficien%', 'EV charging and energy-efficiency text evidence'\nUNION ALL\nSELECT 'E7_solar', 7, '7.2', 'B60L53/', '%solar%', 'EV charging and solar-energy text evidence'\nUNION ALL\nSELECT 'E7_pv', 7, '7.2', 'B60L53/', '%photovoltaic%', 'EV charging and photovoltaic text evidence'\nUNION ALL\nSELECT 'E7_renewable', 7, '7.2', 'B60L53/', '%renewable energy%', 'EV charging and renewable-energy text evidence'\nUNION ALL\nSELECT 'I9_station_cpc', 9, '9.1', 'Y02T90/12', '', 'Charging-station tag: proposed infrastructure association for review'\nUNION ALL\nSELECT 'I9_station_text', 9, '9.1', 'B60L53/', '%charging station%', 'EV charging and charging-station text evidence'\nUNION ALL\nSELECT 'I9_infra_text', 9, '9.1', 'B60L53/', '%charging infrastructure%', 'EV charging and infrastructure text evidence'\nUNION ALL\nSELECT 'U11_bus', 11, '11.2', 'B60L53/', '%electric bus%', 'EV charging and electric-bus text evidence'\nUNION ALL\nSELECT 'U11_public', 11, '11.2', 'B60L53/', '%public transport%', 'EV charging and public-transport text evidence'\nUNION ALL\nSELECT 'C13_station', 13, 'to verify', 'Y02T90/12', '', 'Y02T climate tag for charging stations'\nUNION ALL\nSELECT 'C13_charge', 13, 'to verify', 'Y02T10/7072', '', 'Y02T climate tag for EV charging systems'\nUNION ALL\nSELECT 'C13_eff', 13, 'to verify', 'Y02T10/92', '', 'Y02T climate tag for efficient vehicle charging/discharging'"

# SDG RETRIEVAL: join the explicit CPC/text rules to the supplied PI members.
# Only English title/abstract text is inspected. IDs are integer-formatted
# by the batch caller. Each result records the rule and supporting evidence.
# These are proposed associations, not official SDG classifications.
def sdg_query(ids_sql):
    """Build the evidence query for the caller's validated integer application IDs."""
    return f"""
WITH sdg_rules AS ({SDG_RULES_SQL})
SELECT a.appln_id, a.docdb_family_id, r.sdg, r.target_hint,
       r.rule_id, r.reason,
       MIN(REPLACE(c.cpc_class_symbol, ' ', '')) AS cpc_evidence,
       MIN(t.appln_title) AS patent_title,
       MIN(CASE WHEN r.text_pattern <> '' THEN
           SUBSTR(CONCAT(COALESCE(t.appln_title, ''), ' ',
                         COALESCE(b.appln_abstract, '')), 1, 600)
           ELSE NULL END) AS text_excerpt
FROM tls201_appln a
JOIN tls224_appln_cpc c ON c.appln_id = a.appln_id
LEFT JOIN tls202_appln_title t
 ON t.appln_id = a.appln_id AND t.appln_title_lg = 'en'
LEFT JOIN tls203_appln_abstr b
 ON b.appln_id = a.appln_id AND b.appln_abstract_lg = 'en'
JOIN sdg_rules r ON REPLACE(c.cpc_class_symbol, ' ', '')
                   LIKE CONCAT(r.cpc_prefix, '%')
WHERE a.appln_id IN ({ids_sql})
 AND (r.text_pattern = '' OR
      LOWER(CONCAT(COALESCE(t.appln_title, ''), ' ',
                   COALESCE(b.appln_abstract, ''))) LIKE r.text_pattern)
GROUP BY a.appln_id, a.docdb_family_id, r.sdg, r.target_hint,
         r.rule_id, r.reason
ORDER BY a.docdb_family_id, r.sdg, a.appln_id, r.rule_id
"""


# SDG ANALYSIS: retrieve all selected PI members in bounded batches, then
# deduplicate application/family/SDG/rule evidence and family/SDG proposals.
# Complete-year summaries divide by all selected sector families, not just
# named families. Keep proposals separate from manually accepted matches;
# overlapping SDG shares may sum to more than 100 percent.
def section_sdg(applicants):
    """Save proposed associations separately from reviewed, accepted associations."""
    members = sector_family_members()
    years = members[["docdb_family_id", "year"]].drop_duplicates()
    ids = sorted(members.appln_id.astype(int).unique())
    batch = int(STEP2_CONFIG.get("sdg_batch_size", 500))
    if batch <= 0:
        raise ValueError("SDG batch size must be positive.")
    parts = []
    for start in range(0, len(ids), batch):
        result = pd.DataFrame(patstat.sql_query(sdg_query(", ".join(str(x) for x in ids[start:start+batch])), use_legacy_sql=False))
        if not result.empty:
            parts.append(result)
    columns = ["appln_id", "docdb_family_id", "sdg", "target_hint", "rule_id", "reason",
               "cpc_evidence", "patent_title", "text_excerpt"]
    candidates = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)
    # Keep rule-level evidence before collapsing to unique family/SDG pairs.
    candidates = candidates.drop_duplicates(["appln_id", "docdb_family_id", "sdg", "rule_id"])
    candidates["status"] = "proposed_unvalidated"
    candidates["method_version"] = SDG_RULES_VERSION
    candidates["source"] = candidates.appln_id.map(lambda x: "PATSTAT appln_id=" + str(int(x)))
    write_step2(candidates, "sdg_proposed_evidence")
    proposed = candidates[["docdb_family_id", "sdg"]].drop_duplicates().merge(years, on="docdb_family_id", validate="many_to_one")
    complete_years = years[years.year.le(LAST_COMPLETE_YEAR)]
    counts = proposed[proposed.year.le(LAST_COMPLETE_YEAR)].groupby("sdg").docdb_family_id.nunique()
    summary = counts.reindex([7, 9, 11, 13], fill_value=0).rename("families").reset_index()
    summary["pct_all_sector_families"] = 100 * summary.families / len(complete_years) if len(complete_years) else np.nan
    summary["status"] = "proposed_unvalidated"
    write_step2(summary, "sdg_proposed_summary")
    if not proposed.empty:
        annual = proposed.groupby(["year", "sdg"]).docdb_family_id.nunique().rename("proposed_families")
        write_step2(annual, "sdg_proposed_annual", index=True)
    # The exported template is a starting point for review, not accepted data.
    template_columns = ["docdb_family_id", "sdg", "decision", "target", "evidence", "source"]
    if candidates.empty:
        template = pd.DataFrame(columns=template_columns)
    else:
        def distinct_text(values):
            """Combine distinct non-null evidence strings without multiplying associations."""
            return " | ".join(sorted(set(values.fillna("").astype(str))))
        evidence = candidates.copy()
        evidence["evidence"] = (evidence.rule_id + ": " + evidence.reason + " | CPC=" +
                                 evidence.cpc_evidence.fillna("") + " | text=" + evidence.text_excerpt.fillna("CPC signal only"))
        template = evidence.groupby(["docdb_family_id", "sdg"], as_index=False).agg(
            target=("target_hint", distinct_text), evidence=("evidence", distinct_text), source=("source", distinct_text))
        template["decision"] = "uncertain"
        template = template[template_columns]
    write_step2(template, "sdg_review_template")
    # The human review file is an INPUT, never overwritten by the program.
    review_path = ROOT / "config" / "sdg_review.csv"
    if not review_path.is_file():
        print("SDG proposals saved. No reviewed associations: config/sdg_review.csv is absent.")
        return
    # Validate decisions, integer IDs, scope membership and supporting fields
    # before aggregating any accepted SDG association.
    review = pd.read_csv(review_path)
    if not set(template_columns).issubset(review.columns):
        raise ValueError("SDG review is missing required columns.")
    for field in ["docdb_family_id", "sdg"]:
        numbers = pd.to_numeric(review[field], errors="raise")
        if numbers.isna().any() or numbers.mod(1).ne(0).any():
            raise ValueError("SDG review identifiers must be integers.")
        review[field] = numbers.astype("int64")
    if not review.sdg.between(1, 17).all() or not review.docdb_family_id.isin(years.docdb_family_id).all():
        raise ValueError("SDG review contains an out-of-scope family or SDG.")
    if review.duplicated(["docdb_family_id", "sdg"]).any() or not review.decision.isin(["accepted", "rejected", "uncertain"]).all():
        raise ValueError("SDG review contains duplicate or invalid decisions.")
    if review[["target", "evidence", "source"]].fillna("").astype(str).apply(lambda col: col.str.strip().eq("")).any().any():
        raise ValueError("Each SDG decision needs a target, evidence and source.")
    accepted = review[review.decision.eq("accepted")][["docdb_family_id", "sdg"]].merge(years, on="docdb_family_id", validate="many_to_one")
    write_step2(accepted, "sdg_accepted_associations")
    final = accepted[accepted.year.le(LAST_COMPLETE_YEAR)].groupby("sdg").docdb_family_id.nunique().rename("families").reset_index()
    final["pct_all_sector_families"] = 100 * final.families / len(complete_years) if len(complete_years) else np.nan
    write_step2(final, "sdg_accepted_summary")
    # Reuse the existing fractional applicant credits. SDG memberships may
    # overlap, so credits summed across SDGs need not equal named families.
    links = applicants[applicants.earliest_filing_year.le(LAST_COMPLETE_YEAR)].merge(
        accepted[["docdb_family_id", "sdg"]], on="docdb_family_id", validate="many_to_many")
    credits = links.groupby(["clean_name", "sdg"]).fractional_credit.sum().rename("fractional_families")
    write_step2(credits, "sdg_accepted_applicants", index=True)
    print("SDG categories overlap; their shares may sum to more than 100%.")


# EXECUTION ORDER: validate the cleaned handoff, run Anna's Step 1 once,
# then run only the additional Step 2 analyses. Step 2-only execution checks
# that the saved Step 1 tables belong to the same recorded extraction.
def main():
    """Run the selected stages while checking that all handoffs refer to the same scope."""
    parser = argparse.ArgumentParser(description="Team 09 landscape: original Step 1 plus Step 2")
    parser.add_argument("--step", choices=("1", "2", "pest", "all"), default="all")
    parser.add_argument("--skip-pest", action="store_true", help="Run patent analyses without the PEST appendix.")
    parser.add_argument("--pest-offline", action="store_true", help="Compatibility option: global PEST always reads verified local sources offline.")
    parser.add_argument("--pest-refresh", action="store_true", help="Compatibility option: local sources are reread on every PEST run.")
    parser.add_argument("--pest-no-pdfs", action="store_true", help="Compatibility option: no downloads; the archived local PDFs are still read.")
    parser.add_argument("--pest-results", type=Path, default=None,
                        help="Existing Step 2 folder for --step pest, e.g. outputs/step2-Copy1.")
    args = parser.parse_args()
    if args.pest_offline and args.pest_refresh:
        parser.error("--pest-offline and --pest-refresh cannot be combined.")
    if args.pest_results is not None and args.step != "pest":
        parser.error("Use --pest-results only with --step pest; full runs use their own Step 2 results.")
    # Validate the handoff before running expensive Step 1 queries.
    applicants = load_step0_applicants() if args.step in ("2", "all") else None
    if args.step in ("1", "all"):
        STEP1_DIR.mkdir(parents=True, exist_ok=True)
        section7_volume()
        section8_technology()
        section9_geography()
        if (STEP0_DIR / "handoff_manifest.json").is_file():
            (STEP1_DIR / "handoff_manifest.json").write_bytes((STEP0_DIR / "handoff_manifest.json").read_bytes())
        print("Step 1 done. Outputs in", STEP1_DIR)
    if args.step in ("2", "all"):
        if not (STEP1_DIR / "volume_per_year.csv").is_file():
            raise FileNotFoundError("Run landscape.py --step 1 first, or omit --step to run both.")
        recorded = STEP1_DIR / "handoff_manifest.json"
        current = STEP0_DIR / "handoff_manifest.json"
        if not recorded.is_file() or recorded.read_bytes() != current.read_bytes():
            raise ValueError("Step 1 tables belong to another Step 0 export: rerun landscape.py without --step.")
        section10_step2(applicants)

    # Run PEST last, after the same-run Step 2 files exist. The pest-only mode
    # reuses saved outputs and does not rerun Step 1 or Step 2 patent analyses.
    if args.step in ("2", "all", "pest") and not args.skip_pest:
        section_pest(results=args.pest_results or STEP2_DIR, refresh=args.pest_refresh,
                     offline=args.pest_offline, download_pdfs=not (args.pest_no_pdfs or args.pest_offline))


# ================================================================
# LEGACY PEST HELPERS: retained for input regression checks and older imports.
# The active PEST entry point below delegates to global_pest.py; it does not
# call section_pest_base or the geographically narrow legacy evidence builders.
# ================================================================
from datetime import datetime, timezone
from html.parser import HTMLParser


# WORKBOOK VALIDATION: use the canonical long data sheet, not its example
# pivot sheets. Identical duplicates are removed once; conflicting keys fail.
def iea_read_workbook(path):
    data = pd.read_excel(path, sheet_name="GEVO_EV_2026", engine="openpyxl")
    keys = ["region_country", "category", "parameter", "mode", "powertrain", "year", "unit"]
    required = set(keys + ["value", "Aggregate group"])
    if not required.issubset(data.columns):
        raise ValueError("The IEA workbook does not have the expected long-data schema.")
    for col in keys[:-2] + ["unit", "Aggregate group"]:
        data[col] = data[col].astype("string").str.strip()
    data["year"] = pd.to_numeric(data.year, errors="raise")
    if data.year.isna().any() or data.year.mod(1).ne(0).any():
        raise ValueError("IEA years must be non-missing integers.")
    data["year"] = data.year.astype(int)
    data["value"] = pd.to_numeric(data.value, errors="raise")
    if (~np.isfinite(data.value.dropna())).any():
        raise ValueError("Non-finite IEA data value.")
    before = len(data)
    data = data.drop_duplicates()
    if data.duplicated(keys, keep=False).any():
        raise ValueError("Conflicting IEA series keys: inspect the workbook before aggregation.")
    return data, {"source_rows": before, "rows_after_deduplication": len(data),
                  "duplicate_rows_removed": before-len(data), "sheet": "GEVO_EV_2026"}


# SERIES SELECTION: read explicit region/year/parameter/mode/powertrain/unit
# combinations. EV is the workbook aggregate of BEV and PHEV (excludes FCEV).
# Never add EV to BEV/PHEV or sum World, regions and their component countries.
# Public slow, fast and ultra-fast points are disjoint in this workbook.
def iea_country_panel(data):
    history = data[data.category.eq("Historical")].copy()
    dimensions = history[["region_country", "year", "Aggregate group"]].drop_duplicates()
    if dimensions.duplicated(["region_country", "year"]).any():
        raise ValueError("Conflicting geographical groups in IEA historical data.")
    panel = dimensions.set_index(["region_country", "year"])
    specs = {
        "car_sales": ("EV sales", "Cars", "EV", "Vehicles"),
        "car_stock": ("EV stock", "Cars", "EV", "Vehicles"),
        "car_sales_share_pct": ("EV sales share", "Cars", "EV", "percent"),
        "car_stock_share_pct": ("EV stock share", "Cars", "EV", "percent"),
        "public_slow": ("EV charging points", "EVSE", "Publicly available slow", "charging points"),
        "public_fast": ("EV charging points", "EVSE", "Publicly available fast", "charging points"),
        "public_ultrafast": ("EV charging points", "EVSE", "Publicly available ultra-fast", "charging points"),
        "ldvs_per_public_point": ("Electric LDVs per charging point", "EV", "EV", "vehicles"),
        "capacity_per_ev_kw": ("Average capacity per EV", "EV", "EV", "kW/EV"),
        "capacity_per_point_kw": ("Average capacity per EVSE", "EV", "EV", "kW/EVSE"),
    }
    for name, (parameter, mode, powertrain, unit) in specs.items():
        selected = history[history.parameter.eq(parameter) & history["mode"].eq(mode) &
                           history.powertrain.eq(powertrain) & history.unit.eq(unit)]
        if selected.duplicated(["region_country", "year"]).any():
            raise ValueError(f"Multiple observations for IEA metric {name}.")
        panel[name] = selected.set_index(["region_country", "year"]).value.reindex(panel.index)
    panel["charging_types_observed"] = panel[["public_slow", "public_fast", "public_ultrafast"]].notna().sum(axis=1)
    # Missing charger types stay unknown rather than becoming invented zeros.
    panel["public_charging_points"] = panel[["public_slow", "public_fast", "public_ultrafast"]].sum(axis=1, min_count=3)
    panel["fast_ultrafast_share_pct"] = (100 * (panel.public_fast + panel.public_ultrafast) /
                                         panel.public_charging_points.replace(0, np.nan))
    panel = panel.reset_index().sort_values(["region_country", "year"])
    for col in ["car_sales", "car_stock", "public_charging_points"]:
        previous = panel.groupby("region_country")[col].shift(1)
        consecutive = panel.year.sub(panel.groupby("region_country").year.shift(1)).eq(1)
        panel[col+"_yoy_pct"] = (100*(panel[col]/previous.replace(0, np.nan)-1)).where(consecutive)
    panel["category"] = "Historical"
    return panel.reset_index(drop=True)


# OPTIONAL POLICY EVIDENCE: only the bundled official EC snapshot is read.
# Verify its URL and raw-content hash; never download an unverified replacement.
def iea_policy_evidence():
    folder = ROOT / "data/external/online_sources/EC_AFIR"
    if not (folder / "metadata.json").is_file() or not (folder / "source.html").is_file():
        return None
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    expected_url = "https://transport.ec.europa.eu/transport-themes/clean-transport/alternative-fuels-sustainable-mobility-europe/alternative-fuels-infrastructure_en"
    raw = (folder / "source.html").read_bytes()
    if metadata.get("url") != expected_url or hashlib.sha256(raw).hexdigest() != metadata.get("sha256"):
        raise ValueError("The official EC source snapshot failed its integrity check.")
    class Paragraphs(HTMLParser):
        def __init__(self):
            super().__init__(); self.active = False; self.parts = []; self.paragraphs = []
        def handle_starttag(self, tag, attrs):
            if tag == "p": self.active = True; self.parts = []
        def handle_data(self, text):
            if self.active: self.parts.append(text)
        def handle_endtag(self, tag):
            if tag == "p" and self.active:
                self.paragraphs.append(" ".join(" ".join(self.parts).split())); self.active = False
    parser = Paragraphs()
    parser.feed(raw.decode(metadata.get("charset", "utf-8"), errors="replace"))
    match = next((text for text in parser.paragraphs if "mandatory national targets" in text.lower()), None)
    if match is None:
        return None
    return {"source_id": "EC_AFIR", "publisher": "European Commission", "source_url": expected_url,
            "file": str((folder / "source.html").relative_to(ROOT)), "sha256": metadata["sha256"],
            "retrieved_utc": metadata.get("retrieved_utc", ""), "status": "verified_official_snapshot",
            "evidence_excerpt": " ".join(match.split()[:25]), "network_access": False, "pdf_extraction": False}


# MARKET EVIDENCE: the IEA workbook supplies vehicle and infrastructure series.
# The integrated wrapper adds fiscal, electricity-price and survey evidence.
# IEA historical years are independent of the PATSTAT publication-lag rule.
def section_pest_base(results=None, refresh=False, offline=False, download_pdfs=True):
    """Use the local IEA Excel plus an optional integrity-checked official EU policy snapshot."""
    results = Path(results) if results is not None else STEP2_DIR
    output = results / "pest"
    output.mkdir(parents=True, exist_ok=True)
    workbook = ROOT / STEP2_CONFIG.get("iea_workbook", "data/external/EV data by country 2026.xlsx")
    if not workbook.is_file():
        raise FileNotFoundError(f"Upload the IEA workbook at {workbook}; no online fallback is used.")
    data, validation = iea_read_workbook(workbook)
    panel = iea_country_panel(data)
    panel.to_csv(output / "iea_historical_indicators.csv", index=False)
    # Export projections with their scenario labels intact, never as history.
    projections = data[data.category.str.startswith("Projection", na=False)]
    projections.to_csv(output / "iea_scenarios.csv", index=False)
    definitions = pd.read_excel(workbook, sheet_name="Definitions", header=None, usecols=[0, 1], engine="openpyxl")
    definitions.columns = ["term", "definition"]
    definitions.dropna(how="all").to_csv(output / "iea_definitions.csv", index=False)
    digest = hashlib.sha256(workbook.read_bytes()).hexdigest()
    source = {"source_id": "IEA_LOCAL_2026", "file": str(workbook.relative_to(ROOT)),
              "sha256": digest, "sheet": "GEVO_EV_2026", "status": "local_workbook_read",
              "publisher": "International Energy Agency", "edition": "Global EV Outlook 2026",
              "source_url": "https://www.iea.org/reports/global-ev-outlook-2026",
              "network_access": False, "pdf_extraction": False}
    policy = iea_policy_evidence()
    registry = [source] + ([{k: v for k, v in policy.items() if k != "evidence_excerpt"}] if policy else [])
    pd.DataFrame(registry).to_csv(output / "pest_sources.csv", index=False)
    if policy:
        pd.DataFrame([policy]).to_csv(output / "pest_policy_evidence.csv", index=False)
    regions = STEP2_CONFIG.get("iea_regions", ["World", "China", "Europe", "USA", "Japan"])
    chosen = panel[panel.region_country.isin(regions)]
    figures = []

    def save_local(fig, name):
        fig.text(0.01, 0.01, "IEA 2026 workbook: historical data only; regions shown separately, not summed.", fontsize=8)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        fig.savefig(output/name, dpi=180, bbox_inches="tight")
        plt.close(fig)
        figures.append(name)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for region, group in chosen.groupby("region_country"):
        axes[0].plot(group.year, group.car_sales/1e6, label=region)
        axes[1].plot(group.year, group.car_stock/1e6, label=region)
    axes[0].set(title="Plug-in electric car sales", ylabel="million cars per year", xlabel="year")
    axes[1].set(title="Plug-in electric car stock", ylabel="million cars in operation", xlabel="year")
    for ax in axes:
        ax.grid(alpha=.2); ax.legend(fontsize=8)
    save_local(fig, "iea_01_ev_demand.png")

    world = panel[panel.region_country.eq("World")].sort_values("year")
    charging = world.dropna(subset=["public_slow", "public_fast", "public_ultrafast"])
    if not charging.empty:
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
        axes[0].stackplot(charging.year, charging.public_slow/1e6, charging.public_fast/1e6,
                          charging.public_ultrafast/1e6, labels=["slow (<=22 kW)", "fast (>22 to 150 kW)", "ultra-fast (>150 kW)"])
        axes[0].set(title="World public charging points", ylabel="million simultaneous charging sockets", xlabel="year")
        axes[0].legend(loc="upper left", fontsize=8)
        axes[1].plot(charging.year, charging.fast_ultrafast_share_pct)
        axes[1].set(title="World fast and ultra-fast share", ylabel="public charging points (%)", xlabel="year", ylim=(0,100))
        save_local(fig, "iea_02_public_charging_mix.png")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for region, group in chosen.groupby("region_country"):
        axes[0].plot(group.year, group.ldvs_per_public_point, label=region)
        axes[1].plot(group.year, group.capacity_per_ev_kw, label=region)
    axes[0].set(title="Plug-in cars and vans per public point", ylabel="LDVs per public charging point", xlabel="year")
    axes[1].set(title="Estimated public charging capacity per EV", ylabel="kW per plug-in car or van", xlabel="year")
    for ax in axes:
        ax.grid(alpha=.2); ax.legend(fontsize=8)
    save_local(fig, "iea_03_infrastructure_indicators.png")

    fig, ax = plt.subplots(figsize=(10, 4.8))
    for region, group in chosen.groupby("region_country"):
        ax.plot(group.year, group.car_sales_share_pct, label=region)
    ax.set(title="Plug-in share of new car sales", ylabel="new car sales (%)", xlabel="year")
    ax.grid(alpha=.2); ax.legend()
    save_local(fig, "iea_04_adoption.png")

    # Keep one latest available value per series, with its own date. A missing
    # metric is explicit; dates are never silently synchronized or forward-filled.
    factors = [
        ("P1", "Political", "Regulation and charging incentives", None, None,
         "Not present in this workbook; no claim about legal requirements or incentives is generated."),
        ("E1", "Economic", "Plug-in car demand", "car_sales", "vehicles per year",
         "Sales indicate potential demand for charging; they do not measure charger revenues or profitability."),
        ("E2", "Economic", "Installed plug-in car base", "car_stock", "vehicles",
         "The vehicle base indicates potential charging demand; private charging and utilization remain unobserved."),
        ("S1", "Social", "Observed EV adoption proxy", "car_sales_share_pct", "percent of new car sales",
         "Sales penetration describes adoption, not consumer attitudes, willingness to pay or equitable access."),
        ("S2", "Social", "Public infrastructure availability proxy", "ldvs_per_public_point", "plug-in cars and vans per public point",
         "This ratio does not measure geographical coverage, queues, household access or service quality."),
        ("T1", "Technological", "Higher-power public charging mix", "fast_ultrafast_share_pct", "percent of public points",
         "Higher-power deployment changes charging infrastructure requirements; it does not establish patent quality."),
        ("T2", "Technological", "Estimated public capacity per EV", "capacity_per_ev_kw", "kW per plug-in car or van",
         "The IEA estimate uses assumed charger power ratings; it is not measured utilization or charging speed."),
    ]
    matrix = []
    for identifier, pillar, factor, metric, unit, interpretation in factors:
        observations = world.dropna(subset=[metric]) if metric is not None else pd.DataFrame()
        latest = observations.iloc[-1] if not observations.empty else None
        matrix.append({"factor_id": identifier, "pillar": pillar, "factor": factor,
            "geographic_scope": "World" if metric else "not supplied", "indicator": metric or "not in workbook",
            "year": latest.year if latest is not None else np.nan,
            "value": latest[metric] if latest is not None else np.nan, "unit": unit or "not applicable",
            "evidence_status": "numeric_observation_requires_interpretation" if latest is not None else "not_available_in_workbook",
            "source_id": source["source_id"], "source_sheet": source["sheet"],
            "evidence_table": "iea_historical_indicators.csv" if metric else "",
            "analyst_interpretation": interpretation, "review_status": "requires_review"})
    matrix = pd.DataFrame(matrix)
    if policy:
        mask = matrix.factor_id.eq("P1")
        matrix.loc[mask, "factor"] = "EU alternative-fuels infrastructure regulation"
        matrix.loc[mask, "geographic_scope"] = "European Union"
        matrix.loc[mask, "indicator"] = "documented infrastructure deployment obligations"
        matrix.loc[mask, "evidence_status"] = "official_policy_evidence_requires_interpretation"
        matrix.loc[mask, "source_id"] = "EC_AFIR"
        matrix.loc[mask, "source_sheet"] = "not applicable: official policy webpage"
        matrix.loc[mask, "evidence_table"] = "pest_policy_evidence.csv"
        matrix.loc[mask, "analyst_interpretation"] = (
            "EU infrastructure obligations are a policy driver. This source does not establish incentive levels "
            "in other markets or causally explain patent activity through 2022.")
    matrix["policy_coverage_note"] = "EU regulation case only; incentives and other jurisdictions are not comprehensively covered."
    matrix.to_csv(output / "pest_matrix.csv", index=False)
    # The numerical evidence table contains the actual selected time series;
    # interpretations are separate and never fed back as observed numbers.
    chosen.to_csv(output / "pest_evidence.csv", index=False)
    manifest = {"run_utc": datetime.now(timezone.utc).isoformat(), "sources": registry, "validation": validation,
        "historical_year_min": int(panel.year.min()), "historical_year_max": int(panel.year.max()),
        "scenario_categories": sorted(projections.category.dropna().unique().tolist()),
        "regions_plotted": regions, "figures": figures,
        "missing_policy_evidence": policy is None, "political_pillar_complete": False,
        "rules": ["The uploaded Excel and, if available, a verified official EC snapshot are read locally; no network or PDF access.",
                  "World and regional aggregates are retained as supplied and never added to countries.",
                  "EV totals are not added to BEV/PHEV components; EV excludes FCEV per workbook definitions.",
                  "All three public charger types must be observed before computing a total.",
                  "Historical IEA data is independent of incomplete PATSTAT years.",
                  "Policy coverage is limited to the bundled EU case; consumer attitudes are absent and social measures are proxies.",
                  "Workbook values are rounded estimates; derived ratios inherit rounding uncertainty."]}
    (output / "pest_run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "READING_GUIDE.md").write_text(
        "# PEST evidence\n\nNumerical data comes only from the supplied IEA workbook. A verified official EU policy snapshot is used if present. No PDF extraction or online access is performed. "
        "Historical observations and scenario projections are exported separately. Political evidence covers an EU regulation case; "
        "other jurisdictions and incentives are not comprehensively covered. Social indicators are adoption/infrastructure proxies. "
        "Consult pest_matrix.csv for explicit limitations and pest_run_manifest.json for aggregation rules. "
        "IEA historical observations through 2025 are independent of PATSTAT publication truncation.\n", encoding="utf-8")
    print("Local IEA evidence saved in", output)
    print("Political evidence: verified EU snapshot" if policy else "Political evidence: unavailable")
    print("IEA market block: adoption/infrastructure proxies; survey evidence is integrated next.")
    return {"matrix": matrix, "evidence": chosen, "sources": registry, "all_factors_matched": False}


# EUROSTAT IMPORT: the supplied export declares A1 dimensions incorrectly.
# Normal-mode reading uses actual cell addresses. All 63 sheets, original
# flags, currencies, tax treatments and consumption bands are retained.
def read_eurostat_prices(path):
    from openpyxl import load_workbook
    import re
    book = load_workbook(path, read_only=False, data_only=True)
    records = []
    for sheet in book:
        if sheet.title == "Summary":
            continue
        cells = list(sheet.values)
        metadata = {}
        for row in cells[:12]:
            if row and isinstance(row[0], str):
                metadata[row[0].strip().rstrip(":")] = next((v for v in row[1:] if v is not None), None)
        if "nrg_pc_205" not in str(metadata.get("Dataset", "")).lower():
            raise ValueError("Unexpected Eurostat dataset.")
        time_index = next((i for i,row in enumerate(cells) if row and row[0] == "TIME"), None)
        if time_index is None:
            raise ValueError(f"Eurostat time axis missing: {sheet.title}")
        periods = [(j,v) for j,v in enumerate(cells[time_index]) if isinstance(v,str) and re.fullmatch(r"\d{4}-S[12]",v)]
        band_match = re.search(r"band (I[A-G])", str(metadata.get("Energy consumption", "")))
        if not band_match or metadata.get("Unit of measure") != "Kilowatt-hour":
            raise ValueError("Unexpected Eurostat consumption band or unit.")
        for row in cells[time_index+2:]:
            if not row or row[0] is None:
                break
            for column,period in periods:
                value = row[column] if column < len(row) else None
                flag = row[column+1] if column+1 < len(row) else None
                number = np.nan if value in (None, "", ":") else float(value)
                records.append({"geography": row[0], "period": period,
                    "year": int(period[:4]), "semester": int(period[-1]), "band": band_match[1],
                    "consumption_band": metadata["Energy consumption"], "tax": metadata.get("Taxes"),
                    "currency": metadata.get("Currency"), "unit": "per kWh", "price": number,
                    "raw_value": str(value) if value is not None else "", "flag": flag or "",
                    "source_sheet": sheet.title, "source_update": metadata.get("Last updated")})
    book.close()
    result = pd.DataFrame(records)
    if result.empty or result.duplicated(["geography", "period", "band", "tax", "currency"]).any():
        raise ValueError("Missing or duplicate Eurostat series observations.")
    return result


# PUBLIC FINANCE: replicate the tracker eligibility, not an annual fiscal
# accounts series. Missing charging allocations stay unknown, never a claim
# that the country spent nothing. Parent IDs and policy IDs remain traceable.
def read_spending_tracker(path, categories_path):
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    data = pd.DataFrame([x for x in records if isinstance(x.get("id"), (int,float))])
    categories = json.loads(Path(categories_path).read_text(encoding="utf-8"))
    data["category"] = data.tech.map(categories)
    data["chart_eligible"] = (data.startYear.notna() & data.startYear.ne(0) & data.tech.notna() &
                               data.tech.ne("") & data.budgetUSD.notna() & data.budgetUSD.ne(0))
    if "private" in data:
        data["chart_eligible"] &= ~data.private.fillna(False).astype(bool)
    data["policy_url"] = data.id.map(lambda x: "https://www.iea.org/policies/"+str(int(x)))
    for column in ["parentIDs", "parentTitles"]:
        data[column] = data[column].map(lambda x: "; ".join(map(str,x)) if isinstance(x,list) else "")
    eligible = data[data.chart_eligible & data.fundingType.eq("Government")]
    summary = eligible.groupby("country").budgetUSD.sum().rename("government_usd_bn").to_frame()
    charging = eligible[eligible.tech.eq("Charging infrastructure")]
    summary["charging_usd_bn"] = charging.groupby("country").budgetUSD.sum()
    summary["charging_allocation_rows"] = charging.groupby("country").size().reindex(summary.index, fill_value=0)
    summary["charging_share_energy_pct"] = 100*summary.charging_usd_bn/summary.government_usd_bn
    summary["charging_record_available"] = summary.charging_allocation_rows.gt(0)
    summary["interpretation"] = "Tracker commitments; not annual payments or a comprehensive fiscal total"
    return data, summary.reset_index().sort_values("government_usd_bn", ascending=False)


# SOCIAL IMPORT: preserve geography, sample base, dates, elicitation and source
# references. Percentages are 0-100; no interpolation or cross-country pooling.
def read_social_evidence(path):
    data = pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False)
    required = {"series_id", "period", "year", "value_pct", "geography", "population", "source_url", "pdf_page_1based", "comparability_group"}
    if not required.issubset(data.columns):
        raise ValueError("Missing social-series provenance or dimensions.")
    data["value_pct"] = pd.to_numeric(data.value_pct, errors="raise")
    if not data.value_pct.between(0,100).all() or data.duplicated(["series_id","period","geography"]).any():
        raise ValueError("Invalid or duplicate social percentages.")
    if data[data.geography.eq("England")].year.gt(2023).any():
        raise ValueError("Do not append post-break England observations to the 2021-2023 series.")
    return data


def verify_external_sources():
    """Fail visibly if any bundled source differs from its recorded bytes."""
    manifest = json.loads((ROOT / "data/external_sources_manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = ROOT / item["file"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"External source missing or changed: {item['file']}. Review and update provenance before use.")
    return manifest


def section_pest(results=None, refresh=False, offline=False, download_pdfs=True):
    """Build the focused international PEST from verified local sources."""
    from global_pest import run_global_pest
    workbook = ROOT / STEP2_CONFIG.get("iea_workbook", "data/external/EV data by country 2026.xlsx")
    return run_global_pest(ROOT, results=results or STEP2_DIR, workbook=workbook)


if __name__ == "__main__":
    main()
