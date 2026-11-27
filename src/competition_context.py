"""Integrated tutorial context for Step 2; no changes to Anna's Step 1."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from scipy import stats

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


def lorenz(values):
    """Cumulative positive credit distribution, with a defined empty result."""
    x = np.sort(np.asarray(values,dtype=float))
    x = x[np.isfinite(x)&(x>0)]
    if not len(x):
        return np.array([0.,1.]),np.array([0.,np.nan])
    return np.arange(len(x)+1)/len(x),np.r_[0,np.cumsum(x)/x.sum()]


def distribution_measures(values, counting):
    """Tutorial inequality measures with explicit units and denominators.

    Lotka is descriptive OLS on log frequency, not a verified power-law fit.
    It is deliberately undefined for fractional family counts.
    """
    x = np.asarray(values,dtype=float);x=x[np.isfinite(x)&(x>0)]
    row = {"counting":counting,"applicants":len(x),"attributions":x.sum(),
           "CR4_pct":np.nan,"CR8_pct":np.nan,"HH":np.nan,"equivalent_applicants":np.nan,
           "CV":np.nan,"Gini":np.nan,"Lotka_slope":np.nan,"Lotka_pvalue":np.nan}
    if not len(x):
        return row
    shares = np.sort(x/x.sum())[::-1]
    row.update(CR4_pct=100*shares[:4].sum(),CR8_pct=100*shares[:8].sum(),
               HH=float((shares**2).sum()),CV=x.std(ddof=1)/x.mean() if len(x)>1 else 0.)
    row["equivalent_applicants"] = 1/row["HH"]
    a,b=lorenz(x)
    row["Gini"] = 1-float(np.sum(np.diff(a)*(b[1:]+b[:-1])))
    if counting=="full" and np.allclose(x,np.round(x)):
        frequencies=pd.Series(x).value_counts().sort_index()
        if len(frequencies)>=3:
            fit=stats.linregress(np.log(frequencies.index),np.log(frequencies.values))
            row.update(Lotka_slope=fit.slope,Lotka_pvalue=fit.pvalue)
    return row


def window_concentration(links,start,end,window):
    """Complete non-overlapping windows, aligned on the last complete year."""
    if window<1 or end<start:
        raise ValueError("Invalid concentration window.")
    rows=[];first=end-window+1
    while first-window>=start:
        first-=window
    for left in range(first,end-window+2,window):
        if left<start:
            continue
        right=left+window-1;d=links[links.earliest_filing_year.between(left,right)]
        if d.empty:
            continue
        for method in ["full","fractional"]:
            values=(d.groupby("clean_name").docdb_family_id.nunique() if method=="full"
                    else d.groupby("clean_name").fractional_credit.sum())
            row=distribution_measures(values,method)
            row.update(window=f"{left}-{right}",start=left,end=right,
                       unique_named_families=d.docdb_family_id.nunique())
            rows.append(row)
    return pd.DataFrame(rows,columns=["counting","applicants","attributions","CR4_pct","CR8_pct",
        "HH","equivalent_applicants","CV","Gini","Lotka_slope","Lotka_pvalue","window","start","end",
        "unique_named_families"])


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


def patenting_entry_annual(links,history,start,end):
    """Sector entry and first-observed all-field patenting remain distinct."""
    complete=links[links.earliest_filing_year.between(start,end)]
    active=complete[["clean_name","earliest_filing_year"]].drop_duplicates()
    first_sector=active.groupby("clean_name").earliest_filing_year.min()
    last_sector=active.groupby("clean_name").earliest_filing_year.max()
    h=history.set_index("applicant")
    rows=[]
    for year in range(start,end+1):
        names=active.loc[active.earliest_filing_year.eq(year),"clean_name"]
        has_history=names.map(h.patent_history_coverage_pct).eq(100)
        observed=names[has_history].map(h.first_observed_patent_year)
        n=len(names)
        rows.append({"year":year,"active_applicants":n,
            "new_to_sector_observed":np.nan if year==start or not n else int(names.map(first_sector).eq(year).sum()),
            "active_applicants_with_complete_history":int(has_history.sum()) if n else np.nan,
            "patent_history_coverage_pct":100*has_history.sum()/n if n else np.nan,
            "new_to_patenting_observed":int(observed.eq(year).sum()) if n and has_history.any() else np.nan,
            "last_observed_in_scope_pct":100*names.map(last_sector).eq(year).sum()/n if n and year+3<=end else np.nan,
            "left_censored_sector_entry":year==start,
            "definition":"First observed PI patent-family origin for mapped PSN names; not firm founding"})
    return pd.DataFrame(rows)


def complete_top_applicants(links,info,history,start,end,split):
    """The incoming descriptive top table, restricted to complete years."""
    d=links[links.earliest_filing_year.between(start,end)]
    result=d.groupby("clean_name").agg(families=("docdb_family_id","nunique"),
        fractional_credits=("fractional_credit","sum"),
        first_sector_year=("earliest_filing_year","min"),
        last_sector_year=("earliest_filing_year","max")).reset_index().rename(columns={"clean_name":"applicant"})
    since=d[d.earliest_filing_year.ge(split)].groupby("clean_name").docdb_family_id.nunique()
    result["families_since_split"]=result.applicant.map(since).fillna(0).astype(int)
    result["status"]=np.where(result.first_sector_year.lt(split),"observed_before_split","first_observed_from_split")
    result["left_censored"]=result.first_sector_year.eq(start)
    result=result.merge(info,on="applicant",how="left",validate="one_to_one")
    result=result.merge(history,on="applicant",how="left",validate="one_to_one")
    return result.sort_values(["families","applicant"],ascending=[False,True])


def grouped_subfields(cpc,past,recent,totals=None,min_base=10):
    """Optional coarse two-digit groups, separate from exact-symbol RTA."""
    d=cpc.copy()
    d["cpc_group"]=d.cpc_subgroup.str.extract(r"^([A-Z][0-9]{2}[A-Z][0-9]+/[0-9]{2})",expand=False)
    d=d.dropna(subset=["cpc_group"]).drop_duplicates(["docdb_family_id","cpc_group"])
    a=d[d.earliest_filing_year.between(*past)].groupby("cpc_group").docdb_family_id.nunique()
    b=d[d.earliest_filing_year.between(*recent)].groupby("cpc_group").docdb_family_id.nunique()
    out=pd.DataFrame({"families_past":a,"families_recent":b}).fillna(0).reset_index()
    npast=past[1]-past[0]+1;nrecent=recent[1]-recent[0]+1
    out["growth_pct"]=100*((out.families_recent/nrecent)/(out.families_past/npast).replace(0,np.nan)-1)
    out["comparable_base"]=out.families_past.ge(min_base)
    out["label"]=out.cpc_group.map(CODE_LABELS).fillna(out.cpc_group)
    out["relative_growth_index"]=np.nan
    if totals is not None:
        base=totals.loc[totals.year.between(*past),"families"].sum()/npast
        now=totals.loc[totals.year.between(*recent),"families"].sum()/nrecent
        if base>0 and now>0:
            out["relative_growth_index"]=(1+out.growth_pct/100)/(now/base)
    return out.sort_values("families_recent",ascending=False)


def run_integrated_context(applicants,cpc,totals,screening,root,step0,out,first_query,
                           year_min,last_complete,year_max,window,past,recent,split,batch):
    """Join both projects' complementary Step 2 questions in the same run."""
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    root,step0,out=Path(root),Path(step0),Path(out)
    files=[]
    def save(df,name,index=False):
        df.to_csv(out/name,index=index);files.append(name)
    def savefig(fig,name):
        fig.tight_layout();fig.savefig(out/name,dpi=180,bbox_inches="tight");plt.close(fig);files.append(name)
    info_path=step0/"applicant_info.csv";ids_path=step0/"applicant_psn_ids.csv"
    # Country code NA is Namibia, not a missing-value token.
    info=pd.read_csv(info_path,keep_default_na=False)
    info["country"]=info.country.replace("",np.nan)
    ids=pd.read_csv(ids_path)
    first=first_query(ids.psn_id.unique(),chunk=batch)
    save(first,"applicant_first_patents_by_psn.csv")
    history=history_profile(ids,first)
    save(history,"applicant_history.csv")
    entry=patenting_entry_annual(applicants,history,year_min,last_complete)
    save(entry,"patenting_entry_annual.csv")
    complete=applicants[applicants.earliest_filing_year.between(year_min,last_complete)]
    top=complete_top_applicants(complete,info,history,year_min,last_complete,split)
    save(top,"all_applicants_complete_years.csv")
    save(top.head(15),"top_applicants_complete_years.csv")
    country=info.set_index("applicant")
    enriched=screening.copy()
    enriched["country"]=enriched.clean_name.map(country.country)
    for name in ["type","country_known_families","country_family_coverage_pct","country_definition"]:
        enriched["modal_type" if name=="type" else name]=enriched.clean_name.map(country[name])
    enriched=enriched.merge(history.rename(columns={"applicant":"clean_name"}),on="clean_name",how="left",validate="one_to_one")
    # Global cumulative inequality and triennial concentration answer different
    # time-scope questions from the existing annual concentration CSV.
    rows=[]
    fig,ax=plt.subplots(figsize=(7,6))
    for method in ["full","fractional"]:
        x=(complete.groupby("clean_name").docdb_family_id.nunique() if method=="full"
           else complete.groupby("clean_name").fractional_credit.sum())
        row=distribution_measures(x,method);rows.append(row)
        a,b=lorenz(x);ax.plot(a,b,label=f"{method}; Gini={row['Gini']:.3f}")
    ax.plot([0,1],[0,1],color="grey",ls="--")
    ax.set(title=f"Applicant credit inequality, {year_min}-{last_complete}",
           xlabel="cumulative share of applicant labels",ylabel="cumulative share of patent credits")
    ax.xaxis.set_major_formatter(PercentFormatter(1));ax.yaxis.set_major_formatter(PercentFormatter(1));ax.legend()
    savefig(fig,"09_lorenz_curve.png");save(pd.DataFrame(rows),"concentration_overall.csv")
    windows=window_concentration(complete,year_min,last_complete,window)
    save(windows,"concentration_windows.csv")
    fig,axes=plt.subplots(1,2,figsize=(13,4))
    for method,style in [("fractional","-"),("full","--")]:
        w=windows[windows.counting.eq(method)];mid=(w.start+w.end)/2
        axes[0].plot(mid,w.CR4_pct,style,marker="o",label=method)
        axes[1].plot(mid,w.HH,style,marker="o",label=method)
    axes[0].set(title=f"CR4, complete {window}-year windows",ylabel="credit share (%)")
    axes[1].set(title=f"HHI, complete {window}-year windows",ylabel="HHI (0-1)")
    for ax in axes:
        ax.axvspan(last_complete+.5,year_max+.5,color="grey",alpha=.15,label="incomplete years")
        ax.set_xlim(year_min,year_max);ax.set_xlabel("family origin year");ax.legend(fontsize=8)
    savefig(fig,"14_concentration_windows.png")
    fig,axes=plt.subplots(1,2,figsize=(13,4))
    axes[0].plot(entry.year,entry.new_to_sector_observed,marker="o",ms=2.5,label="first observed in this sector")
    axes[0].plot(entry.year,entry.new_to_patenting_observed,marker="o",ms=2.5,label="first observed patenting, mapped IDs")
    axes[1].plot(entry.year,entry.patent_history_coverage_pct,marker="o",ms=2.5,label="active names with complete mapped history")
    axes[0].set(title="Sector entry versus observed patenting entry",ylabel="applicant labels")
    axes[1].set(title="Coverage of the all-field lookup",ylabel="active applicant labels (%)",ylim=(0,100))
    for ax in axes:
        ax.axvspan(last_complete+.5,year_max+.5,color="grey",alpha=.15)
        ax.set_xlim(year_min,year_max);ax.set_xlabel("family origin year");ax.legend(fontsize=7)
    savefig(fig,"15_patenting_entry.png")
    save(grouped_subfields(cpc,past,recent,totals),"subfield_growth_grouped.csv")
    provenance={"created_utc":datetime.now(timezone.utc).isoformat(),
        "source_hashes":{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [info_path,ids_path]},
        "patent_history_definition":"First observed PI family origin since 1800, all fields, mapped PSN IDs only; not founding",
        "country_definition":"Modal known family-country record in complete years; not verified legal domicile",
        "context_file_counts":{"psn_ids":len(first),"applicants_with_mapped_history":len(history)},
        "classification_source":"https://www.uspto.gov/web/patents/classification/cpc/html/cpc-B60L.html"}
    save(pd.DataFrame([{"key":k,"description":v} for k,v in {
        "primary_counting":"Fractional annual concentration remains the primary view.",
        "windows":"Complete non-overlapping windows; early residual years omitted only here.",
        "lotka":"Descriptive log-frequency OLS for whole counts, not a validated power-law model.",
        "top_table":"Descriptive full-family totals, complete years only; not the screening shortlist.",
        "history":"Partial/unknown history is not classified as never previously patenting.",
        "last_observation":"Last observed year is distinct from three-year inactivity and not firm exit.",
        "coarse_groups":"Optional coarse groups collapse detailed codes; exact-symbol RTA remains unchanged."}.items()]),
        "integrated_method_notes.csv")
    (out/"applicant_history_provenance.json").write_text(json.dumps(provenance,indent=2),encoding="utf-8")
    files.append("applicant_history_provenance.json")
    return enriched,{"files":files,**provenance}


def pest_strategy_review(matrix):
    """Connect the empirical PEST to the supplied five-stage client framework.

    Draft mechanisms/responses are analyst proposals, not source observations.
    Opportunity/threat classification and priority require explicit team review.
    """
    result=matrix.copy()
    effects={
        "Political":"Regulation and reported commitments may alter deployment obligations and support available in a target country.",
        "Economic":"Observed demand and input costs may affect regional charging economics; revenues and utilization remain unobserved.",
        "Social":"Reported attitudes, visibility and concerns may affect adoption in the surveyed population; global extrapolation is unsupported.",
        "Technological":"Deployment mix and estimated capacity may change equipment, interoperability and grid-integration requirements."}
    responses={
        "Political":"Check current programme status, eligibility and local obligations before assessing an acquisition or partnership scenario.",
        "Economic":"Test local demand, utilization and cost scenarios before translating market growth into a business case.",
        "Social":"Validate the survey question and population; assess user friction and adoption barriers in the proposed target market.",
        "Technological":"Compare the target's verified engineering capabilities with Toyota's needs; validate real-world performance and grid constraints."}
    result["effect_on_toyota_draft"]=result.pillar.map(effects)
    result["opportunity_or_threat"]="requires_team_review"
    result["priority"]="requires_team_review"
    result["strategic_response_draft"]=result.pillar.map(responses)
    price=result.source_id.eq("EUROSTAT_NRG_PC_205")
    result.loc[price,"strategic_response_draft"]=(
        "Test tariff and consumption-band sensitivity; verify operator contracts, grid charges and utilization before estimating margins.")
    result["strategy_review_status"]="draft_analyst_proposal_not_source_fact"
    return result


READING_GUIDE = """
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
"""
