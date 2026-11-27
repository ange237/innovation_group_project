"""Applicant name harmonisation (Step 0 cleaning, section 10 of the notebook).

1. PATSTAT's PSN name (EPO standardised) as the base, raw name as fallback.
2. Method A of tutorial 11: remove legal forms (CO, LTD, KK, AG...) and punctuation.
3. Our own rules on top: merge renamed firms, IP-holding arms and
   majority-owned subsidiaries. Groups are defined as they exist today
   (Daimler -> Mercedes-Benz Group, PSA -> Stellantis), because the client would
   acquire or partner with today's company.
3. Joint ventures (typically 50/50 in China) are never merged into either parent.

No database connection here, so the rules can be tested offline.
"""
import re
from math import comb

import pandas as pd

from helpers import complete_years

# ---------------------------------------------------------------- method A (tutorial 11, section 2.2)
# Legal-form words to remove (extend the set for the countries of your sector)
LEGAL_FORMS = {
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "LLC", "LP", "PLC",
    "GMBH", "AG", "KG", "MBH", "SE", "SA", "SAS", "SPA", "SRL", "BV", "NV", "AB", "AS", "ASA", "OY", "OYJ",
    "KK", "KABUSHIKI", "KAISHA", "LTDA", "PTY", "THE", "AKTIENGESELLSCHAFT", "GESELLSCHAFT",
}


def clean_with_dictionary(name):
    "Preserve Unicode letters/digits; strip punctuation and edge legal-form words."
    words = re.sub(r"[^\w\s]", " ", str(name).upper(), flags=re.UNICODE).replace("_", " ").split()
    while words and words[-1] in LEGAL_FORMS:      # e.g. "TOYOTA JIDOSHA KABUSHIKI KAISHA" -> "TOYOTA JIDOSHA"
        words.pop()
    while words and words[0] in LEGAL_FORMS:       # e.g. "KABUSHIKI KAISHA TOSHIBA" -> "TOSHIBA"
        words.pop(0)
    return " ".join(words)


def applicant_type(psn_sector):
    "Translate the PATSTAT psn_sector into the types used in the deck (tutorial 11, section 2.3)."
    s = str(psn_sector).upper()
    if "UNIVERSITY" in s:
        return "university"
    if "COMPANY" in s:
        return "firm"
    if "GOV" in s:
        return "government / non-profit"
    if "HOSPITAL" in s:
        return "hospital"
    if "INDIVIDUAL" in s:
        return "individual"
    return "unknown"

GROUP_RULES = {
    "STATE GRID (CN)":     [r"\bSTATE GRID\b", r"\bCHINA ELECTRIC POWER RESEARCH INST"],  # wholly owned provincial companies and institutes
    "TOYOTA MOTOR":        [r"\bTOYOTA MOTOR\b", r"\bTOYOTA JIDOSHA\b"],          # English / Japanese name, regional subsidiaries
    "TOYOTA INDUSTRIES":   [r"\bTOYOTA INDUSTRIES\b", r"\bTOYOTA JIDOSHOKKI\b"],
    "DENSO":               [r"\bDENSO\b"],
    "AISIN":               [r"\bAISIN\b"],
    "HYUNDAI MOTOR":       [r"\bHYUNDAI MOTOR\b"],
    "KIA":                 [r"^KIA\b"],                                            # name must START with KIA
    "HYUNDAI MOBIS":       [r"\bHYUNDAI MOBIS\b"],
    "MERCEDES-BENZ GROUP": [r"\bDAIMLER\b(?! TRUCK)", r"\bMERCEDES[- ]BENZ\b(?! TURK)"],  # Daimler Truck and Mercedes-Benz Turk are separate since 2021
    "VOLKSWAGEN GROUP":    [r"\bVOLKSWAGEN\b", r"\bAUDI\b", r"\bPORSCHE\b"],      # VW owns ~100% of Audi, ~75% of Porsche AG
    "STELLANTIS":          [r"\bSTELLANTIS\b", r"\bPSA AUTOMOBILES\b", r"\bPEUGEOT\b", r"\bCITROEN\b",
                            r"\bFIAT CHRYSLER\b", r"\bFCA US\b", r"\bOPEL\b"],    # PSA + FCA merged in 2021
    "FORD MOTOR":          [r"\bFORD GLOBAL TECH", r"\bFORD MOTOR\b"],             # Ford's IP-holding arm
    "GENERAL MOTORS":      [r"\bGM GLOBAL TECH", r"\bGENERAL MOTORS\b"],           # GM's IP-holding arm
    "PANASONIC":           [r"\bPANASONIC\b"],                                     # incl. Panasonic Intellectual Property
    "LS ELECTRIC":         [r"\bLSIS\b", r"\bLS ELECTRIC\b", r"\bLS INDUSTRIAL SYSTEMS\b"],  # LSIS renamed LS Electric in 2020
    "BAIC GROUP":          [r"\bBAIC\b", r"\bBEIJING ELECTRIC VEHICLE\b"],         # BJEV is BAIC's EV subsidiary
    "GEELY":               [r"\bGEELY\b", r"\bVOLVO CAR"],                         # Volvo Cars (not AB Volvo trucks) is Geely-owned
}

# Business groups WITHOUT majority ownership; merged only if use_business_groups is true
BUSINESS_GROUPS = {
    "HYUNDAI MOTOR GROUP": ["HYUNDAI MOTOR", "KIA", "HYUNDAI MOBIS"],
    "TOYOTA GROUP":        ["TOYOTA MOTOR", "TOYOTA INDUSTRIES", "DENSO", "AISIN"],
}

JOINT_VENTURES = [   # kept as separate applicants, never merged into a parent
    r"\bSAIC[- ]GENERAL MOTORS\b", r"\bSAIC[- ]VOLKSWAGEN\b", r"\bFAW[- ]VOLKSWAGEN\b",
    r"\bFAW[- ]TOYOTA\b", r"\bGAC[- ]TOYOTA\b", r"\bBEIJING HYUNDAI\b", r"\bYUEDA KIA\b",
    r"\bFOTON DAIMLER\b", r"\bBEIJING BENZ\b", r"\bDONGFENG\b",
]

ALL_GROUPS = set(GROUP_RULES) | set(BUSINESS_GROUPS)


def to_group(name, use_business_groups=False):
    """Harmonised applicant for one (PSN) name: its group, or the name itself."""
    if any(re.search(p, name) for p in JOINT_VENTURES):
        return name
    for group, patterns in GROUP_RULES.items():
        if any(re.search(p, name) for p in patterns):
            if use_business_groups:
                for big_group, members in BUSINESS_GROUPS.items():
                    if group in members:
                        return big_group
            return group
    return name


def clean_names(applicants_raw):
    """Upper-case and strip the name columns; missing names become ''."""
    out = applicants_raw.copy()
    for col in ("person_name", "psn_name", "psn_sector", "han_name", "ctry"):
        if col in out:
            out[col] = out[col].fillna("").astype(str).str.strip().str.upper()
    return out


def harmonised_name(name, use_business_groups=False, legal_forms=True):
    """One PATSTAT name -> harmonised applicant: (method A) then our group rules."""
    base = clean_with_dictionary(name) if legal_forms else name
    return to_group(base, use_business_groups)


def harmonise(applicants_raw, use_business_groups=False, legal_forms=True):
    """Add the column 'applicant': PSN name (raw name if PSN is missing), legal forms removed, group rules."""
    out = clean_names(applicants_raw)
    base_name = out["psn_name"].where(out["psn_name"] != "", out["person_name"])
    name_map = {n: harmonised_name(n, use_business_groups, legal_forms) for n in base_name.unique()}
    out["applicant"] = base_name.map(name_map)
    return out


def applicant_info(harmonised):
    """One row per applicant: its type and its country (the most frequent known one, tutorial 11)."""
    df = harmonised[harmonised["applicant"] != ""]
    types = df.assign(type=df["psn_sector"].map(applicant_type)).groupby("applicant")["type"].agg(
        lambda t: t.value_counts().index[0])
    known = df[df["ctry"] != ""].drop_duplicates(["family_id", "applicant", "ctry"])
    country = known.groupby("applicant")["ctry"].agg(lambda c: c.value_counts().index[0])
    result = pd.DataFrame({"type": types, "country": country}).rename_axis("applicant")
    total = df.groupby("applicant").family_id.nunique()
    known_n = known.groupby("applicant").family_id.nunique()
    result["country_known_families"] = known_n.reindex(result.index,fill_value=0).astype(int)
    result["country_family_coverage_pct"] = 100*result.country_known_families/total
    result["country_definition"] = "Most frequent known family-country record; not verified legal domicile"
    return result


def applicant_psn_ids(harmonised):
    """The PATSTAT psn_ids behind each harmonised applicant (to find its first patent ever)."""
    ids = harmonised.loc[harmonised["applicant"] != "", ["applicant", "psn_id"]].dropna()
    ids = ids[pd.to_numeric(ids["psn_id"], errors="coerce") > 0]
    return ids.astype({"psn_id": "int64"}).drop_duplicates()


# ---------------------------------------------------------------- gold standard (tutorial 11, section 2.4)

def pairs_inside(group_sizes):
    "Number of pairs of names inside groups of the given sizes: n(n-1)/2 for each group."
    return sum(comb(int(n), 2) for n in group_sizes)


def precision_recall_f1(gold_groups, predicted_groups):
    "Pairwise precision, recall and F1 of a predicted grouping against the gold groups."
    df = pd.DataFrame({"gold": list(gold_groups), "pred": list(predicted_groups)})
    tp = pairs_inside(df.groupby(["gold", "pred"]).size())         # merged by you and in the gold standard
    tp_fp = pairs_inside(df.groupby("pred").size())                # all the pairs you merged
    tp_fn = pairs_inside(df.groupby("gold").size())                # all the pairs that belong together
    precision = tp / tp_fp if tp_fp else 1.0
    recall = tp / tp_fn if tp_fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"groups found": df["pred"].nunique(), "precision": precision, "recall": recall, "F1": f1}


def evaluate_on_gold(gold):
    """Compare three harmonisation methods on the hand-labelled names (columns comp, Group)."""
    names = gold["comp"].astype(str).str.strip().str.upper()
    methods = {
        "PATSTAT name as it is": names,
        "method A (legal forms removed)": names.map(clean_with_dictionary),
        "method A + our group rules": names.map(harmonised_name),
    }
    table = pd.DataFrame({m: precision_recall_f1(gold["Group"], pred) for m, pred in methods.items()}).T
    table.insert(0, "true organisations", gold["Group"].nunique())
    return table


def applicant_counts(df, name_col):
    """Fractional family counts per applicant (complete years only).

    Each family is split equally among its DISTINCT names, so one firm filing
    under two person records in the same family still counts once.
    """
    d = complete_years(df)[["family_id", name_col]]
    d = d[d[name_col] != ""].drop_duplicates()
    d = d.assign(share=1 / d.groupby("family_id")[name_col].transform("count"))
    return d.groupby(name_col)["share"].sum().sort_values(ascending=False)


def name_version_comparison(applicants_raw):
    """How much each name version merges (section 10.2): distinct names and top-10 share."""
    rows = []
    for col in ("person_name", "psn_name", "han_name"):
        c = applicant_counts(applicants_raw, col)
        rows.append({"name_version": col,
                     "rows_with_name (%)": (applicants_raw[col] != "").mean() * 100,
                     "distinct_names": len(c),
                     "top10_share (%)": c.head(10).sum() / c.sum() * 100 if c.sum() else float("nan")})
    return pd.DataFrame(rows)


def family_applicants(harmonised):
    """One row per family and harmonised applicant, with its fractional share of the family.

    This is the cleaned table used by Step 2 (concentration, entrants).
    """
    fam_app = harmonised.loc[harmonised["applicant"] != "", ["family_id", "year", "applicant"]].drop_duplicates()
    return fam_app.assign(share=1 / fam_app.groupby("family_id")["applicant"].transform("count"))


def top_applicants(harmonised, n=30):
    """Top-n harmonised applicants over the complete years (section 10.4)."""
    fam_app = family_applicants(harmonised)
    complete = complete_years(fam_app)
    merged_names = (harmonised[harmonised["psn_name"] != ""]
                    .groupby("applicant")["psn_name"].nunique().rename("PSN names merged"))
    applicant_type = (harmonised.groupby("applicant")["psn_sector"]
                      .agg(lambda s: s[s != ""].mode().iat[0] if (s != "").any() else "").rename("type"))
    top = (complete.groupby("applicant")["share"].sum().rename("families (fractional)")
           .sort_values(ascending=False).head(n).to_frame()
           .join(merged_names).join(applicant_type))
    top["share of named families (%)"] = top["families (fractional)"] / complete["share"].sum() * 100
    return top


def merge_report(harmonised):
    """Every PSN name merged into a group, so the rules can be checked by eye."""
    merged = harmonised.loc[harmonised["applicant"].isin(ALL_GROUPS), ["applicant", "psn_name"]]
    return merged.drop_duplicates().sort_values(["applicant", "psn_name"])


def joint_ventures_found(harmonised):
    """PSN names recognised as joint ventures and therefore kept separate."""
    names = harmonised["psn_name"].where(harmonised["psn_name"] != "", harmonised["person_name"]).unique()
    return sorted(n for n in names if any(re.search(p, clean_with_dictionary(n)) for p in JOINT_VENTURES))
