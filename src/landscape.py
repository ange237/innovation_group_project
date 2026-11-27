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
# Paste this entire block after Anna's Step 1 definitions.
# Replace the old Step 2 and old main block, including the final __main__ call.
# All Step 2 logic and support functions are included below.
# PEST remains a separate written PDF report; no PEST processing runs here.
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from settings import ROOT, OUTPUT_DIR, STEP0_DIR

STEP2_DIR = OUTPUT_DIR / "step2"

CODE_LABELS = {
    "B60L53/00":"EV charging, general",
    "B60L53/10":"Energy transfer between station and vehicle",
    "B60L53/12":"Inductive charging",
    "B60L53/14":"Conductive charging",
    "B60L53/16":"EV charging connectors",
    "B60L53/18":"EV charging cables",
    "B60L53/20":"On-board charging converters",
    "B60L53/22":"Charging converter design",
    "B60L53/24":"Charging through the propulsion converter",
    "B60L53/30":"Charging station design",
    "B60L53/302":"Cooling of charging equipment",
    "B60L53/305":"Charging communication interfaces",
    "B60L53/31":"Charging columns",
    "B60L53/35":"Automatic or assisted relative positioning",
    "B60L53/36":"Positioning the vehicle",
    "B60L53/37":"Optical position detection",
    "B60L53/38":"Positioning adapted to inductive charging",
    "B60L53/39":"Position-responsive primary-coil activation",
    "B60L53/50":"Stations with energy storage or generation",
    "B60L53/51":"Photovoltaic charging stations",
    "B60L53/52":"Wind-powered charging stations",
    "B60L53/53":"Stations with batteries",
    "B60L53/54":"Stations with fuel cells",
    "B60L53/55":"Stations with capacitors",
    "B60L53/56":"Stations with mechanical storage",
    "B60L53/57":"Off-grid charging stations",
    "B60L53/60":"Monitoring or controlling charging stations",
    "B60L53/62":"Control in response to charging parameters",
    "B60L53/63":"Control in response to network capacity",
    "B60L53/64":"Optimising energy costs",
    "B60L53/65":"Vehicle or battery identification",
    "B60L53/66":"Station-vehicle data transfer",
    "B60L53/665":"Measuring, billing or payment",
    "B60L53/67":"Control of several charging stations",
    "B60L53/68":"Remote monitoring or control",
    "B60L53/80":"Battery exchange",
    "B60L55/00":"Vehicle-to-grid",
}

def history_profile(ids,first):
    """First observed PI family year plus completeness of the PSN-ID lookup."""
    mapping=ids[["applicant","psn_id"]].drop_duplicates()
    if first.psn_id.duplicated().any():
        raise ValueError("Duplicate PSN IDs returned by the history query.")
    joined=mapping.merge(first,on="psn_id",how="left",validate="many_to_one")
    out=joined.groupby("applicant").agg(
        first_observed_patent_year=("first_patent_year","min"),
        psn_ids_total=("psn_id","nunique"),psn_ids_with_history=("first_patent_year","count"))
    out["patent_history_coverage_pct"]=100*out.psn_ids_with_history/out.psn_ids_total
    out["patent_history_status"]=np.select(
        [out.patent_history_coverage_pct.eq(100),out.patent_history_coverage_pct.gt(0)],
        ["complete_mapped_ids","partial"],default="not_observed")
    return out.reset_index()

def concentration_ratio(patents_per_firm,k):
    """Share (%) of all family-applicant attributions held by the k largest names."""
    x=np.sort(np.asarray(patents_per_firm,dtype=float))[::-1]
    return 100*x[:k].sum()/x.sum() if x.sum()>0 else np.nan


def herfindahl(patents_per_firm):
    """Professor's HH: sum of squared shares, on the 0-1 scale."""
    x=np.asarray(patents_per_firm,dtype=float)
    return float(np.sum((x/x.sum())**2)) if x.sum()>0 else np.nan


def coefficient_of_variation(patents_per_firm):
    """Sample standard deviation divided by the mean, as in the tutorial."""
    x=np.asarray(patents_per_firm,dtype=float)
    return x.std(ddof=1)/x.mean() if len(x)>1 and x.mean()>0 else np.nan


def lorenz_curve(patents_per_firm):
    """Cumulative applicant share and family-credit share, including the origin."""
    x=np.sort(np.asarray(patents_per_firm,dtype=float))
    if not len(x) or x.sum()<=0: return np.array([0.,1.]),np.array([0.,np.nan])
    return np.arange(len(x)+1)/len(x),np.r_[0,np.cumsum(x)/x.sum()]


def gini(patents_per_firm):
    """Integrate the Lorenz curve with the professor's trapezoid formula."""
    a,b=lorenz_curve(patents_per_firm)
    return 1-2*np.sum(np.diff(a)*(b[1:]+b[:-1])/2)


def lotka(patents_per_firm):
    """Descriptive log-frequency slope and p-value; not a validated power law."""
    f=pd.Series(patents_per_firm,dtype=float).value_counts().sort_index()
    if len(f)<3 or any(f.index<=0): return np.nan,np.nan
    fit=stats.linregress(np.log(f.index),np.log(f.values))
    return fit.slope,fit.pvalue


def six_measures(patents_per_firm):
    """The tutorial's six families of concentration measures, for observed names."""
    x=np.asarray(patents_per_firm,dtype=float)
    if np.any(~np.isfinite(x)) or np.any(x<=0):
        raise ValueError('Concentration requires positive finite portfolio counts.')
    slope,pvalue=lotka(x);hh=herfindahl(x)
    return {'applicants':len(x),'families (sum over applicants)':int(x.sum()),
        'CV':coefficient_of_variation(x),'CR4 (%)':concentration_ratio(x,4),
        'CR8 (%)':concentration_ratio(x,8),'HH':hh,'1/HH':1/hh if hh>0 else np.nan,
        'Lotka L':slope,'Lotka p-value':pvalue,'Gini':gini(x)}


def concentration_by_window(links,start,end,window=3):
    """Complete non-overlapping windows ending at the last complete year."""
    if window<1 or end<start: raise ValueError('Invalid concentration window.')
    first=start+((end-start+1)%window)
    rows=[]
    for left in range(first,end-window+2,window):
        right=left+window-1
        data=links[links.year.between(left,right)]
        counts=data.groupby('applicant').unit_id.nunique()
        row=six_measures(counts.to_numpy())
        row.update(window=f'{left}-{right}',start=left,end=right,
                   unique_named_families=data.unit_id.nunique())
        rows.append(row)
    return pd.DataFrame(rows)


def applicant_table(links,info,history,start,end,split=2015):
    """Professor's applicant profile, ranked on complete years only."""
    data=links[links.year.between(start,end)].drop_duplicates(['unit_id','applicant'])
    group=data.groupby('applicant')
    result=pd.DataFrame({'families':group.unit_id.nunique(),
        f'families since {split}':data[data.year.ge(split)].groupby('applicant').unit_id.nunique(),
        'first year in the sector':group.year.min(),'last year in the sector':group.year.max()})
    result[f'families since {split}']=result[f'families since {split}'].fillna(0).astype(int)
    result=result.join(info.set_index('applicant')[['type','country']],validate='one_to_one')
    result=result.join(history.set_index('applicant'),validate='one_to_one')
    result['type']=result.type.fillna('unknown')
    result['status']=np.where(result['first year in the sector']<split,'incumbent','entrant')
    result['left_censored']=result['first year in the sector'].eq(start)
    result['ranking_end_year']=end
    return result.sort_values(['families','applicant'],ascending=[False,True])


def entry_exit_table(links,history,start,last_complete,last_shown):
    """Tutorial entry and last-observation disappearance, with coverage flags."""
    data=links[links.year.between(start,last_shown)].drop_duplicates(['unit_id','applicant'])
    group=data.groupby('applicant')
    first,last=group.year.min(),group.year.max()
    h=history.set_index('applicant')
    active=data[['applicant','year']].drop_duplicates()
    active['new to the sector']=active.year.eq(active.applicant.map(first))
    known=active.applicant.map(h.patent_history_coverage_pct).eq(100)
    active['known history']=known
    active['new to patenting']=active.year.eq(active.applicant.map(h.first_observed_patent_year)) & known
    active['last family']=active.year.eq(active.applicant.map(last))
    result=active.groupby('year').agg(active_applicants=('applicant','count'),
        new_to_the_sector=('new to the sector','sum'),new_to_patenting=('new to patenting','sum'),
        leaving=('last family','sum'),applicants_with_complete_history=('known history','sum'))
    result=result.reindex(range(start,last_shown+1),fill_value=0)
    result.index.name='year'
    # Unknown history cannot establish that nobody starts patenting in a year.
    result.loc[result.applicants_with_complete_history.eq(0),'new_to_patenting']=np.nan
    result['patent_history_coverage_pct']=100*result.applicants_with_complete_history/result.active_applicants.replace(0,np.nan)
    result['rate of disappearance (%)']=100*result.leaving/result.active_applicants.replace(0,np.nan)
    result.loc[result.index>last_complete-3,'rate of disappearance (%)']=np.nan
    new=data.assign(new=data.year.eq(data.applicant.map(first)))
    shares=100*new.groupby(['year','unit_id']).new.any().groupby('year').mean()
    result["entrants' share of families (%)"]=shares.reindex(result.index)
        # Identify families with at least one confirmed first-observed patentee.
    patent_entry = data.assign(
        history_known=data.applicant.map(
            h.patent_history_coverage_pct
        ).eq(100),
        new_patentee=(
            data.year.eq(data.applicant.map(h.first_observed_patent_year))
            & data.applicant.map(h.patent_history_coverage_pct).eq(100)
        ),
    )

    family_entry = patent_entry.groupby(['year', 'unit_id']).agg(
        new_patentee=('new_patentee', 'any'),
        complete_history=('history_known', 'all'),
    )
    family_entry['classified'] = (
        family_entry.new_patentee | family_entry.complete_history
    )

    # Denominator: all families with identified applicants in that year.
    # With incomplete history, the confirmed share is a lower bound.
    yearly_entry = family_entry.groupby(level='year')
    confirmed_share = 100 * yearly_entry.new_patentee.mean()
    classified_families = yearly_entry.classified.sum()

    result["confirmed new patentees' share of families (%)"] = (
        confirmed_share.where(classified_families.gt(0))
    )
    result['family_history_classification_coverage_pct'] = (
        100 * yearly_entry.classified.mean()
    )
    result['left_censored']=result.index==start
    result['incomplete']=result.index>last_complete
    return result


def subfield(cpc):
    """Tutorial CPC group: retain the first two digits after the slash."""
    if not isinstance(cpc,str) or '/' not in cpc: return None
    main,subgroup=cpc.replace(' ','').split('/',1)
    return f'{main}/{subgroup[:2]}' if len(subgroup)>=2 else None


def subfield_growth(family_cpc,prefixes,past,recent):
    """Compare two five-year periods with one family/group occurrence."""
    if past[1]-past[0]!=recent[1]-recent[0] or past[1]>=recent[0]:
        raise ValueError('Choose equally long, disjoint periods as in the tutorial.')
    prefixes=tuple(p.replace(' ','') for p in prefixes)
    data=family_cpc.copy();data['cpc']=data.cpc.fillna('').str.replace(' ','',regex=False)
    data=data[data.cpc.str.startswith(prefixes)]
    data['subfield']=data.cpc.map(subfield)
    data=data.dropna(subset=['subfield']).drop_duplicates(['unit_id','subfield'])
    a=data[data.year.between(*past)].groupby('subfield').unit_id.nunique()
    b=data[data.year.between(*recent)].groupby('subfield').unit_id.nunique()
    left,right=f'families {past[0]}-{past[1]}',f'families {recent[0]}-{recent[1]}'
    result=pd.DataFrame({left:a,right:b}).fillna(0).astype(int)
    result['growth (%)']=100*(result[right]/result[left].replace(0,np.nan)-1)
    result['growth_status']=np.where(result[left].eq(0),'newly_observed_zero_base','defined')
    result.index.name='subfield'
    return result.sort_values([right,'subfield'],ascending=[False,True])


def load_data(root=ROOT):
    """Reuse exact Step 0 labels and existing Step 1 scope; no new harmonisation."""
    import yaml
    from patstat_queries import db,patstat,SECTOR_SCOPES,sector_family_cpc,first_patent_ever
    root=Path(root)
    cfg=yaml.safe_load((root/'config/sector.yaml').read_text(encoding='utf-8'))
    handoff=root/cfg['output_dir']/'step0';step1=root/cfg['output_dir']/'step1'
    manifest=json.loads((handoff/'handoff_manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['source_sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Step 0 code/settings changed: rerun extraction and cleaning.')
    raw=handoff/'sector_family_applicants.csv'
    if hashlib.sha256(raw.read_bytes()).hexdigest()!=manifest['applicants_sha256']:
        raise ValueError('Step 0 handoff changed after export.')
    for name,digest in manifest['context_sha256'].items():
        if hashlib.sha256((handoff/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Step 0 context changed: '+name)
    if not (step1/'handoff_manifest.json').is_file() or (step1/'handoff_manifest.json').read_bytes()!=(handoff/'handoff_manifest.json').read_bytes():
        raise ValueError('Run Step 1 from this Step 0 export before Step 2.')
    links=pd.read_csv(raw).rename(columns={'family_id':'unit_id','applicant':'applicant','year':'year'})
    if links.duplicated(['unit_id','applicant']).any() or links.applicant.isna().any():
        raise ValueError('Invalid family-applicant pairs in Step 0.')
    if not np.allclose(links.groupby('unit_id').share.sum(),1,atol=1e-10,rtol=0):
        raise ValueError('Step 0 fractional credits fail the input consistency check.')
    if links.groupby('unit_id').year.nunique().gt(1).any(): raise ValueError('Inconsistent family years.')
    info=pd.read_csv(handoff/'applicant_info.csv',keep_default_na=False,na_values=[''])
    ids=pd.read_csv(handoff/'applicant_psn_ids.csv')
    first=first_patent_ever(ids.psn_id.unique(),chunk=cfg['step2'].get('history_batch_size',5000))
    history=history_profile(ids,first)
    scope=next(s for s in SECTOR_SCOPES if s.level=='family')
    universe=patstat.df(db.query(scope.sq.c.unit_id,scope.sq.c.year))
    if universe.unit_id.duplicated().any(): raise ValueError('Duplicate sector families.')
    if not links.unit_id.isin(universe.unit_id).all(): raise ValueError('Named families outside the Step 1 scope.')
    volume=pd.read_csv(step1/'volume_per_year.csv')
    totals=volume[volume.scope.eq(cfg['sector']['name']) & volume.level.eq('family') & volume.series.eq('all')].set_index('year').n
    actual=universe.groupby('year').unit_id.nunique()
    years=totals.index.union(actual.index)
    if totals.index.duplicated().any() or not actual.reindex(years,fill_value=0).eq(totals.reindex(years,fill_value=0)).all():
        raise ValueError('Live scope differs from Step 1 annual totals. Rerun on one database snapshot.')
    checked=links[['unit_id','year']].merge(universe,on='unit_id',validate='many_to_one',suffixes=('_handoff','_scope'))
    if not checked.year_handoff.eq(checked.year_scope).all():
        raise ValueError('Family years differ between Step 0 and the current scope.')
    cpc=sector_family_cpc().rename(columns={'family_id':'unit_id','cpc_class_symbol':'cpc'})
    cpc['cpc']=cpc.cpc.fillna('').str.replace(' ','',regex=False)
    cpc=cpc.drop_duplicates(['unit_id','cpc'])
    return dict(config=cfg,links=links,info=info,history=history,first_patents=first,
                family_cpc=cpc,universe=universe,step0_manifest=manifest)


def concentration_analysis(data,output):
    """Section 5.1: overall measures and HH, numbers-equivalent, CR4 over time."""
    import matplotlib.pyplot as plt
    cfg=data['config'];start,end=cfg['years']['min'],cfg['years']['max']
    last=end-max(cfg['truncated_years']['earliest_filing_year'],cfg['truncated_years']['appln_filing_year'])
    links=data['links'];complete=links[links.year.between(start,last)]
    counts=complete.groupby('applicant').unit_id.nunique()
    overall=pd.Series(six_measures(counts.to_numpy()),name=cfg['sector']['name']).to_frame()
    windows=concentration_by_window(links,start,last,cfg['step2']['window'])
    overall.to_csv(output/'concentration_overall.csv')
    windows.to_csv(output/'concentration_windows.csv',index=False)
    fig,axes=plt.subplots(1,3,figsize=(15,4.5))
    for ax,metric in zip(axes,['HH','1/HH','CR4 (%)']):
        ax.plot(windows.end,windows[metric],marker='o',ms=4)
        ax.axvspan(last+.5,end+.5,color='grey',alpha=.15)
        ax.set(title=metric,xlabel='last year of complete window',xlim=(start,end));ax.grid(alpha=.2)
    fig.suptitle(cfg['sector']['name']+': inventive concentration (full counting)')
    fig.tight_layout();fig.savefig(output/'01_concentration.png',dpi=180,bbox_inches='tight');plt.close(fig)
    return overall,windows


def applicant_analysis(data,output):
    """Section 5.2: full applicant profile and professor-style entry/disappearance."""
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    cfg=data['config'];start,end=cfg['years']['min'],cfg['years']['max']
    # Use the configured completeness rule rather than a hard-coded year.
    last=end-max(cfg['truncated_years']['earliest_filing_year'],cfg['truncated_years']['appln_filing_year'])
    top=applicant_table(data['links'],data['info'],data['history'],start,last,cfg['step2']['split_year'])
    entry=entry_exit_table(data['links'],data['history'],start,last,end)
    top.to_csv(output/'applicants.csv');entry.to_csv(output/'entry_exit.csv')
    fig,axes=plt.subplots(1,2,figsize=(14,4.5))
    entry[['active_applicants','new_to_the_sector','new_to_patenting']].plot(ax=axes[0],marker='o',ms=2.5)
    entry[[
        "entrants' share of families (%)",
        "confirmed new patentees' share of families (%)",
        'rate of disappearance (%)',
    ]].plot(ax=axes[1], marker='o', ms=2.5)

    axes[1].legend(
        [
            'Families with a new sector entrant',
            'Families with a confirmed new patentee',
            'Observed disappearance rate',
        ],
        fontsize=8,
    )
    axes[0].set(title='Applicants per year',xlabel='year')
    axes[1].set(title='Entry and observed disappearance',xlabel='year',ylim=(0,100))
    axes[1].yaxis.set_major_formatter(PercentFormatter(100))
    for ax in axes: ax.axvspan(last+.5,end+.5,color='grey',alpha=.15);ax.grid(alpha=.2)
    fig.suptitle(cfg['sector']['name']+': incumbents and entrants');fig.tight_layout()
    fig.savefig(output/'02_entry_exit.png',dpi=180,bbox_inches='tight');plt.close(fig)
    return top,entry


def subfield_analysis(data,output):
    """Section 5.3: two-digit CPC groups, period growth and median-size filter."""
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    cfg=data['config'];end=cfg['years']['max']
    last=end-max(cfg['truncated_years']['earliest_filing_year'],cfg['truncated_years']['appln_filing_year'])
    recent=(last-4,last);past=(recent[0]-5,recent[0]-1)
    table=subfield_growth(data['family_cpc'],cfg['sector']['cpc_prefixes'],past,recent)
    table['label']=table.index.map(lambda value:CODE_LABELS.get(value,value))
    a,b=f'families {past[0]}-{past[1]}',f'families {recent[0]}-{recent[1]}'
    plot=table[table[a].gt(0)]
    fastest=plot[plot[b].ge(plot[b].median())].sort_values('growth (%)',ascending=False).head(3)
    table['among_fastest_supported']=table.index.isin(fastest.index)
    table.to_csv(output/'subfield_growth.csv')
    fig,ax=plt.subplots(figsize=(11,6));ax.scatter(plot[b],plot['growth (%)'],s=65,alpha=.65)
    for name,row in plot.iterrows(): ax.annotate(name,(row[b],row['growth (%)']),xytext=(4,4),textcoords='offset points',fontsize=8)
    ax.axhline(0,color='grey',lw=.8)
    ax.set(title=cfg['sector']['name']+': subfield growth map',xlabel=f'families {recent[0]}-{recent[1]} (size today)',ylabel=f'growth vs {past[0]}-{past[1]}')
    ax.yaxis.set_major_formatter(PercentFormatter(100));fig.tight_layout()
    fig.savefig(output/'03_subfield_growth.png',dpi=180,bbox_inches='tight');plt.close(fig)
    return table,fastest


def save_inputs(data,output):
    """Persist the exact data used, including families with no applicant."""
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    folder=output/'data';folder.mkdir(exist_ok=True)
    for name,key in [('family_applicants.csv','links'),('family_cpc.csv','family_cpc'),
                     ('family_universe.csv','universe'),('first_patents_by_psn.csv','first_patents'),
                     ('applicant_history.csv','history')]:
        data[key].to_csv(folder/name,index=False)
    return output


def finish_run(data,output,root=ROOT):
    """Record exact output hashes and the small, explicit departures from the tutorial."""
    root,output=Path(root),Path(output)
    report=root/'reports/Step_2_PEST_EV_Charging_Toyota.pdf'
    owned=['concentration_overall.csv','concentration_windows.csv','applicants.csv',
           'entry_exit.csv','subfield_growth.csv','01_concentration.png','02_entry_exit.png',
           '03_subfield_growth.png','data/family_applicants.csv','data/family_cpc.csv',
           'data/family_universe.csv','data/first_patents_by_psn.csv','data/applicant_history.csv']
    files=[output/name for name in owned if (output/name).is_file()]
    source=[str(Path(__file__).resolve().relative_to(root)).replace('\\','/'),
            'src/patstat_queries.py','src/harmonise.py','src/settings.py','config/sector.yaml']
    manifest=dict(method='professor_section5_ev_charging_v1',counting='full family-applicant attributions',
        tutorial='11_competitive_landscape.ipynb, Section 5',step0_manifest=data['step0_manifest'],
        source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in source},
        outputs=[dict(file=str(p.relative_to(output)).replace('\\','/'),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files],
        adaptations=['Reuse existing EV scope, exclusions and Step 0 group/JV labels.',
            'Rank applicants on complete years; the tutorial top table uses all displayed years.',
            'Reuse PI mapped-PSN history since 1800; the tutorial starts at 1900 without a PI filter.',
            'Complete non-overlapping windows end at the last complete year; early remainder omitted only there.',
            'Unknown history, zero-base growth and undefined concentration remain missing.'],
        other_files_note='Unlisted files may belong to an earlier version; they are not this run outputs.',
        pest=dict(mode='separate_written_report',file='reports/Step_2_PEST_EV_Charging_Toyota.pdf',
                  sha256=hashlib.sha256(report.read_bytes()).hexdigest() if report.exists() else None))
    (output/'step2_run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (output/'READING_GUIDE.md').write_text('''# Professor-aligned Step 2

Read concentration_overall.csv, concentration_windows.csv, applicants.csv,
entry_exit.csv and subfield_growth.csv. Three figures follow tutorial Sections
5.1-5.3. The data/ folder contains the exact analysis inputs, not new sector definitions.

Full counting follows the professor: one family counts once per distinct
applicant. Portfolio sums are family-applicant attributions, not unique families.
The population includes all named applicant types, not only legal firms.
Concentration concerns inventive activity, not sales or market shares.

Applicant ranking uses complete years. Entry is first observed in the sector,
not founding. First-observed patenting is restricted to mapped PSN IDs with
complete lookup coverage. Disappearance is the last observed sector year in
the available data, not a three-year-gap statistic or a verified company closure.
It is masked after the last complete year minus three. Early entry is left-censored.

CPC groups retain two digits after the slash, as in the tutorial: /302 and /305
become /30. Deduplicate family-group pairs. Groups overlap and must not be
summed as a partition. Zero-base growth is undefined. The three fastest groups
are selected among existing groups at least as large as their current median size.

PEST is the written report in reports/, not a Python extraction or score.
RTA, automated screening, SDG and extra PV/wind comparisons are not part of this run.
Check step2_run_manifest.json for exact source hashes and declared adaptations.
The manifest records local inputs and code; preserve the PATSTAT edition and
runtime versions separately to reproduce a later remote extraction.
''',encoding='utf-8')


def run_step2(root=ROOT,output=None):
    """Execute only the professor-aligned patent landscape; never run PEST code."""
    data=load_data(root)
    output=save_inputs(data,output or Path(root)/data['config']['output_dir']/'step2')
    overall,windows=concentration_analysis(data,output)
    applicants,entry=applicant_analysis(data,output)
    subfields,fastest=subfield_analysis(data,output)
    finish_run(data,output,root)
    print(overall.round(3).to_string())
    print(applicants.head(15).to_string())
    print('Step 2 saved in',output,'| PEST: reports/Step_2_PEST_EV_Charging_Toyota.pdf')
    return dict(overall=overall,windows=windows,applicants=applicants,entry_exit=entry,subfields=subfields,fastest=fastest)


def section10_step2(applicants=None):
    """Run the professor-aligned Step 2 with the existing project handoffs."""
    return run_step2(ROOT, STEP2_DIR)


def main():
    parser = argparse.ArgumentParser(description="Anna Step 1 and professor-aligned Step 2")
    parser.add_argument("--step", choices=("1", "2", "all"), default="all")
    parser.add_argument("--skip-pest", action="store_true", help="Compatibility flag: PEST is always a separate report.")
    args = parser.parse_args()
    manifest_path = STEP0_DIR / "handoff_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Run src/01_extract.py and src/02_clean.py first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, digest in manifest["source_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Step 0 settings changed: rerun extraction and cleaning.")
    if args.step in ("1", "all"):
        STEP1_DIR.mkdir(parents=True, exist_ok=True)
        section7_volume()
        section8_technology()
        section9_geography()
        (STEP1_DIR / "handoff_manifest.json").write_bytes(manifest_path.read_bytes())
        print("Step 1 done. Outputs in", STEP1_DIR)
    if args.step in ("2", "all"):
        section10_step2()
    print("PEST report: reports/Step_2_PEST_EV_Charging_Toyota.pdf")


if __name__ == "__main__":
    main()
