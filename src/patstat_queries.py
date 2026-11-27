"""PATSTAT connection, sector selection, scopes and counting functions.

Sections 1, 2.1, 6.1 and 6.2 of the notebook, unchanged: the same SQLAlchemy
queries, run through the PATSTAT client on TIP. Importing this module opens the
connection to the database named in config/sector.yaml (TEST or PROD).
"""
from dataclasses import dataclass
import pandas as pd

from sqlalchemy import and_, case, distinct, func, or_

from epo.tipdata.patstat import PatstatClient
from epo.tipdata.patstat.database.models import (
    TLS201_APPLN,               # import the needed tables for the extractions
    TLS202_APPLN_TITLE,
    TLS203_APPLN_ABSTR,
    TLS206_PERSON,
    TLS207_PERS_APPLN,
    TLS224_APPLN_CPC,
    TLS230_APPLN_TECHN_FIELD,
    TLS901_TECHN_FIELD_IPC,
)

from settings import (
    APPLN_TIME_COLUMN, ENV, EXCLUDE_CPC_PREFIXES, FAMILY_TIME_COLUMN, IPR_TYPE,
    LAST_COMPLETE_YEAR, SECTOR_CPC_PREFIXES, SECTOR_KEYWORDS, SECTOR_NAME, YEAR_MAX, YEAR_MIN,
)

patstat = PatstatClient(env=ENV)
db = patstat.orm()
print(f"Sector: {SECTOR_NAME} | env: {ENV} | years {YEAR_MIN}-{YEAR_MAX} "
      f"| family year: {FAMILY_TIME_COLUMN} | application year: {APPLN_TIME_COLUMN} "
      f"| complete years up to {LAST_COMPLETE_YEAR}")


# ================================================================ 2.1 Selecting the sector

def symbol_prefix_condition(symbol_column, codes):
    """OR-condition: the blank-stripped classification symbol starts with one of the codes."""
    symbol = func.replace(symbol_column, " ", "")
    return or_(*(symbol.like(code.replace(" ", "") + "%") for code in codes))


def keyword_condition(terms):
    """OR-condition: any term appears in the title or abstract (case-insensitive)."""
    title = func.lower(TLS202_APPLN_TITLE.appln_title)
    abstract = func.lower(TLS203_APPLN_ABSTR.appln_abstract)
    return or_(*(col.like(f"%{t.lower()}%") for t in terms for col in (title, abstract)))


def sector_family_ids(cpc_prefixes=SECTOR_CPC_PREFIXES, keywords=SECTOR_KEYWORDS):
    """Query of the docdb_family_ids that belong to the sector (CPC codes OR keywords)."""
    family_id = TLS201_APPLN.docdb_family_id.label("docdb_family_id")
    by_cpc = (
        db.query(family_id)
        .join(TLS224_APPLN_CPC, TLS201_APPLN.appln_id == TLS224_APPLN_CPC.appln_id)
        .filter(symbol_prefix_condition(TLS224_APPLN_CPC.cpc_class_symbol, cpc_prefixes))
    )
    if not keywords:
        return by_cpc.distinct()
    by_keywords = (
        db.query(family_id)
        .outerjoin(TLS202_APPLN_TITLE, TLS201_APPLN.appln_id == TLS202_APPLN_TITLE.appln_id)
        .outerjoin(TLS203_APPLN_ABSTR, TLS201_APPLN.appln_id == TLS203_APPLN_ABSTR.appln_id)
        .filter(keyword_condition(keywords))
    )
    # Explicit UNION ALL works on BigQuery; outer DISTINCT preserves the original set.
    return by_cpc.union_all(by_keywords).distinct()


#Anna: exclusion rule added after validation round 1 (ships, aircraft/drones, wind turbines)
excluded_ids = (
    db.query(TLS201_APPLN.docdb_family_id)
    .join(TLS224_APPLN_CPC, TLS201_APPLN.appln_id == TLS224_APPLN_CPC.appln_id)
    .filter(symbol_prefix_condition(TLS224_APPLN_CPC.cpc_class_symbol, EXCLUDE_CPC_PREFIXES))
    .distinct()
)
sector_ids = (
    db.query(TLS201_APPLN.docdb_family_id.label("docdb_family_id"))
    .filter(TLS201_APPLN.docdb_family_id.in_(sector_family_ids().subquery().select()))
    .filter(TLS201_APPLN.docdb_family_id.notin_(excluded_ids.subquery().select()))
    .distinct()
)


# ================================================================ 6.1 Scopes

IS_PCT_APPLN = and_(TLS201_APPLN.appln_auth == "WO", TLS201_APPLN.appln_kind.like("W%"))


def _restrict(q, family_ids):
    """Keep only the families in family_ids (None = all patents)."""
    if family_ids is None:
        return q
    return q.filter(TLS201_APPLN.docdb_family_id.in_(family_ids.subquery().select()))


def family_scope(family_ids=None):
    """Family level: one row per DOCDB family."""
    year = func.min(getattr(TLS201_APPLN, FAMILY_TIME_COLUMN))
    q = db.query(
        TLS201_APPLN.docdb_family_id.label("unit_id"),
        year.label("year"),
        func.max(case((IS_PCT_APPLN, 1), else_=0)).label("is_pct"),
        func.max(case((TLS201_APPLN.granted == "Y", 1), else_=0)).label("is_granted"),
        func.max(TLS201_APPLN.docdb_family_size).label("family_size"),
    ).filter(TLS201_APPLN.ipr_type == IPR_TYPE)
    return (
        _restrict(q, family_ids)
        .group_by(TLS201_APPLN.docdb_family_id)
        .having(year.between(YEAR_MIN, YEAR_MAX))
        .subquery()
    )


def application_scope(family_ids=None, time_column=APPLN_TIME_COLUMN):
    """Application level: one row per appln_id, dated by its own time_column."""
    year = getattr(TLS201_APPLN, time_column)
    q = db.query(
        TLS201_APPLN.appln_id.label("unit_id"),
        year.label("year"),
        case((IS_PCT_APPLN, 1), else_=0).label("is_pct"),
        case((TLS201_APPLN.granted == "Y", 1), else_=0).label("is_granted"),
        TLS201_APPLN.docdb_family_size.label("family_size"),
    ).filter(TLS201_APPLN.ipr_type == IPR_TYPE, year.between(YEAR_MIN, YEAR_MAX))
    return _restrict(q, family_ids).subquery()


@dataclass(frozen=True)
class Scope:
    name: str     # "all patents" or the sector name
    level: str    # "family" or "application"
    sq: object    # SQLAlchemy subquery, one row per unit


SCOPES = [
    Scope("all patents", "family", family_scope()),
    Scope(SECTOR_NAME, "family", family_scope(sector_ids)),
    Scope("all patents", "application", application_scope()),
    Scope(SECTOR_NAME, "application", application_scope(sector_ids)),
]
SECTOR_SCOPES = [s for s in SCOPES if s.name == SECTOR_NAME]   # family first, then application


# ================================================================ 6.2 Counting functions

def _join_applications(q, scope):
    """Join the applications of each unit: all applications of a family, or the application itself."""
    key = TLS201_APPLN.docdb_family_id if scope.level == "family" else TLS201_APPLN.appln_id
    return q.join(TLS201_APPLN, key == scope.sq.c.unit_id).filter(TLS201_APPLN.ipr_type == IPR_TYPE)


def _tag(df, scope):
    return df.assign(scope=scope.name, level=scope.level)


def count_per_year(scope, only_pct=False):
    """Number of units (families or applications) per year; only_pct keeps those via PCT."""
    sq = scope.sq
    q = db.query(sq.c.year, func.count().label("n")).group_by(sq.c.year).order_by(sq.c.year)
    if only_pct:
        q = q.filter(sq.c.is_pct == 1)
    return _tag(patstat.df(q), scope)


def _split_equally(scope, unit_category, category):
    """Fractional counting: each unit is split equally across its distinct categories (sums to 1)."""
    pairs = unit_category.distinct().subquery()
    k = db.query(pairs.c.unit_id, func.count().label("k")).group_by(pairs.c.unit_id).subquery()
    q = (
        db.query(getattr(pairs.c, category), pairs.c.year, func.sum(1.0 / k.c.k).label("n_frac"))
        .join(k, k.c.unit_id == pairs.c.unit_id)
        .group_by(getattr(pairs.c, category), pairs.c.year)
    )
    return _tag(patstat.df(q), scope)


def fractional_by_country(scope, role="applicant"):
    """Fractional counts by person country and year (role: 'applicant' or 'inventor').

    Each unit is split among its distinct persons with a known country.
    """
    sq = scope.sq
    seq_nr = TLS207_PERS_APPLN.applt_seq_nr if role == "applicant" else TLS207_PERS_APPLN.invt_seq_nr
    ctry = func.trim(TLS206_PERSON.person_ctry_code)   # unknown countries are NULL, '' or blanks ('  ')
    persons = (
        _join_applications(
            db.query(sq.c.unit_id, sq.c.year, TLS207_PERS_APPLN.person_id, ctry.label("ctry")).distinct(), scope
        )
        .join(TLS207_PERS_APPLN, TLS207_PERS_APPLN.appln_id == TLS201_APPLN.appln_id)
        .join(TLS206_PERSON, TLS206_PERSON.person_id == TLS207_PERS_APPLN.person_id)
        .filter(seq_nr > 0, ctry.isnot(None), ctry != "")
        .subquery()
    )
    # one person = one share of the unit; a country with 2 of 3 persons gets 2/3
    k = db.query(persons.c.unit_id, func.count().label("k")).group_by(persons.c.unit_id).subquery()
    q = (
        db.query(persons.c.ctry, persons.c.year, func.sum(1.0 / k.c.k).label("n_frac"))
        .join(k, k.c.unit_id == persons.c.unit_id)
        .group_by(persons.c.ctry, persons.c.year)
    )
    return _tag(patstat.df(q), scope).assign(role=role)


def fractional_by_cpc_subclass(scope):
    """Fractional counts by CPC subclass (first 4 characters) and year."""
    sq = scope.sq
    subclass = func.substr(func.replace(TLS224_APPLN_CPC.cpc_class_symbol, " ", ""), 1, 4)
    q = (
        _join_applications(db.query(sq.c.unit_id, sq.c.year, subclass.label("subclass")), scope)
        .join(TLS224_APPLN_CPC, TLS224_APPLN_CPC.appln_id == TLS201_APPLN.appln_id)
    )
    return _split_equally(scope, q, "subclass")


def fractional_by_techn_field(scope):
    """Fractional counts by WIPO technology field (1-35) and year.

    tls230 weights sum to 1 per application; at family level they are rescaled
    so that every family also sums to 1.
    """
    sq = scope.sq
    unit_field = (
        _join_applications(
            db.query(sq.c.unit_id, sq.c.year, TLS230_APPLN_TECHN_FIELD.techn_field_nr,
                     func.sum(TLS230_APPLN_TECHN_FIELD.weight).label("w")),
            scope,
        )
        .join(TLS230_APPLN_TECHN_FIELD, TLS230_APPLN_TECHN_FIELD.appln_id == TLS201_APPLN.appln_id)
        .group_by(sq.c.unit_id, sq.c.year, TLS230_APPLN_TECHN_FIELD.techn_field_nr)
        .subquery()
    )
    unit_total = (
        db.query(unit_field.c.unit_id, func.sum(unit_field.c.w).label("w_total"))
        .group_by(unit_field.c.unit_id)
        .subquery()
    )
    q = (
        db.query(unit_field.c.techn_field_nr, unit_field.c.year,
                 func.sum(unit_field.c.w / unit_total.c.w_total).label("n_frac"))
        .join(unit_total, unit_total.c.unit_id == unit_field.c.unit_id)
        .group_by(unit_field.c.techn_field_nr, unit_field.c.year)
    )
    return _tag(patstat.df(q), scope)


def techn_field_names():
    """WIPO field and sector names (tls901), one row per field."""
    return patstat.df(
        db.query(TLS901_TECHN_FIELD_IPC.techn_field_nr, TLS901_TECHN_FIELD_IPC.techn_field,
                 TLS901_TECHN_FIELD_IPC.techn_sector).distinct()
    ).drop_duplicates("techn_field_nr")


def count_by_office(scope):
    """Units per office and year.

    Family level: families with at least one application at the office.
    Application level: applications filed at the office.
    """
    sq = scope.sq
    q = (
        _join_applications(
            db.query(TLS201_APPLN.appln_auth.label("office"), sq.c.year,
                     func.count(distinct(sq.c.unit_id)).label("n")),
            scope,
        )
        .group_by(TLS201_APPLN.appln_auth, sq.c.year)
    )
    return _tag(patstat.df(q), scope)


def scope_profile(scope):
    """Number of units, units via PCT, granted units and mean family size (complete years only)."""
    sq = scope.sq
    q = db.query(
        func.count().label("n"),
        func.sum(sq.c.is_pct).label("n_pct"),
        func.sum(sq.c.is_granted).label("n_granted"),
        func.avg(sq.c.family_size * 1.0).label("mean_family_size"),
    ).filter(sq.c.year <= LAST_COMPLETE_YEAR)
    return _tag(patstat.df(q), scope)


#Anna
def missing_applicant_country():
    """Sector families (complete years) with no applicant that has a known country."""
    fam = SECTOR_SCOPES[0]   # family level
    ctry = func.trim(TLS206_PERSON.person_ctry_code)
    known = (
        db.query(fam.sq.c.unit_id)
        .join(TLS201_APPLN, TLS201_APPLN.docdb_family_id == fam.sq.c.unit_id)
        .join(TLS207_PERS_APPLN, TLS207_PERS_APPLN.appln_id == TLS201_APPLN.appln_id)
        .join(TLS206_PERSON, TLS206_PERSON.person_id == TLS207_PERS_APPLN.person_id)
        .filter(TLS207_PERS_APPLN.applt_seq_nr > 0, ctry != "", fam.sq.c.year <= LAST_COMPLETE_YEAR)
        .distinct()
        .subquery()
    )
    n_total = patstat.df(
        db.query(func.count().label("n")).select_from(fam.sq).filter(fam.sq.c.year <= LAST_COMPLETE_YEAR)
    ).iloc[0, 0]
    n_known = patstat.df(db.query(func.count().label("n")).select_from(known)).iloc[0, 0]
    return int(n_total), int(n_total - n_known)


# ================================================================ Step 0 queries (#Anna)

def count_rows(query):
    """Number of rows returned by a query (used for the sector size before/after the exclusion)."""
    return int(patstat.df(db.query(func.count().label("n")).select_from(query.subquery())).iloc[0, 0])


def validation_sample(n=100):
    """Random sample of n sector families with titles, abstracts and CPC codes, for manual review."""
    sample_query = (
        db.query(TLS201_APPLN.docdb_family_id)
        .filter(TLS201_APPLN.docdb_family_id.in_(sector_ids.statement))
        .distinct()
        .order_by(func.rand())
        .limit(n)
    )
    sample_family_ids = [row[0] for row in sample_query.all()]

    patent_query = (
        db.query(
            TLS201_APPLN.docdb_family_id,
            TLS201_APPLN.appln_id,
            TLS202_APPLN_TITLE.appln_title,
            TLS203_APPLN_ABSTR.appln_abstract,
        )
        .select_from(TLS201_APPLN)
        .outerjoin(TLS202_APPLN_TITLE, TLS201_APPLN.appln_id == TLS202_APPLN_TITLE.appln_id)
        .outerjoin(TLS203_APPLN_ABSTR, TLS201_APPLN.appln_id == TLS203_APPLN_ABSTR.appln_id)
        .filter(TLS201_APPLN.docdb_family_id.in_(sample_family_ids))
    )
    patent_data = (
        patstat.df(patent_query).groupby("docdb_family_id")
        .agg({
            "appln_id": lambda x: "; ".join(map(str, x.dropna().unique())),
            "appln_title": lambda x: " | ".join(str(v) for v in x.dropna().unique()),
            "appln_abstract": lambda x: " | ".join(str(v) for v in x.dropna().unique()),
        })
        .reset_index()
    )
    cpc_query = (
        db.query(TLS201_APPLN.docdb_family_id, TLS224_APPLN_CPC.cpc_class_symbol)
        .join(TLS224_APPLN_CPC, TLS201_APPLN.appln_id == TLS224_APPLN_CPC.appln_id)
        .filter(TLS201_APPLN.docdb_family_id.in_(sample_family_ids))
        .distinct()
    )
    cpc_data = (
        patstat.df(cpc_query).groupby("docdb_family_id")["cpc_class_symbol"]
        .apply(lambda x: "; ".join(sorted(set(x.dropna()))))
        .reset_index(name="CPC_codes")
    )
    review_data = patent_data.merge(cpc_data, on="docdb_family_id", how="left")
    review_data["relevance"] = ""
    review_data["notes"] = ""
    return review_data


def applicants_by_family():
    """Every applicant of every sector family, with PATSTAT's name versions (section 10.1).

    person_name = name as written on the application; psn_name = EPO standardised name;
    han_name = OECD harmonised name.
    """
    fam = SECTOR_SCOPES[0]   # family level
    q = (
        _join_applications(
            db.query(
                fam.sq.c.unit_id.label("family_id"),
                fam.sq.c.year,
                TLS206_PERSON.person_id,
                TLS206_PERSON.person_name,
                TLS206_PERSON.psn_id,
                TLS206_PERSON.psn_name,
                TLS206_PERSON.psn_sector,
                TLS206_PERSON.han_name,
                func.trim(TLS206_PERSON.person_ctry_code).label("ctry"),
            ).distinct(),
            fam,
        )
        .join(TLS207_PERS_APPLN, TLS207_PERS_APPLN.appln_id == TLS201_APPLN.appln_id)
        .join(TLS206_PERSON, TLS206_PERSON.person_id == TLS207_PERS_APPLN.person_id)
        .filter(TLS207_PERS_APPLN.applt_seq_nr > 0)   # applicants only, not inventors
    )
    return patstat.df(q)


def sector_family_cpc():
    """One row per selected family/year/CPC, including families with no applicant."""
    scope = next(s for s in SECTOR_SCOPES if s.level == "family")
    q = (db.query(scope.sq.c.unit_id.label("family_id"), scope.sq.c.year,
                  TLS224_APPLN_CPC.cpc_class_symbol)
         .select_from(scope.sq))
    q = _join_applications(q, scope)
    q = q.join(TLS224_APPLN_CPC, TLS201_APPLN.appln_id == TLS224_APPLN_CPC.appln_id).distinct()
    return patstat.df(q)


def sector_family_members():
    """Every PI application in the existing sector family scope, without person joins."""
    scope = next(s for s in SECTOR_SCOPES if s.level == "family")
    q = db.query(scope.sq.c.unit_id.label("docdb_family_id"), scope.sq.c.year,
                 TLS201_APPLN.appln_id).select_from(scope.sq)
    return patstat.df(_join_applications(q, scope).distinct())


def comparison_family_counts(prefixes):
    """Additional CPC-only field; same PI, dating and year rules as original Step 1."""
    benchmark = family_scope(sector_family_ids(cpc_prefixes=tuple(prefixes), keywords=()))
    q = db.query(benchmark.c.year, func.count().label("n")).group_by(benchmark.c.year)
    main = next(s for s in SECTOR_SCOPES if s.level == "family").sq
    overlap = (db.query(func.count()).select_from(main)
               .join(benchmark, main.c.unit_id == benchmark.c.unit_id)
               .filter(main.c.year <= LAST_COMPLETE_YEAR))
    return patstat.df(q), int(overlap.scalar())


def first_patent_ever(psn_ids, chunk=5000):
    """First observed PI patent-family year, in ANY field, of each PATSTAT standardised name (psn_id).

    This is the first observed PI family year for mapped standardized names,
    not a verified founding date. PSN coverage is reported downstream.
    """
    psn_ids = sorted({int(i) for i in psn_ids if int(i) > 0})
    if not psn_ids:
        return pd.DataFrame(columns=["psn_id", "first_patent_year"])
    parts = []
    for start in range(0, len(psn_ids), chunk):
        q = (
            db.query(TLS206_PERSON.psn_id, func.min(TLS201_APPLN.earliest_filing_year).label("first_patent_year"))
            .join(TLS207_PERS_APPLN, TLS207_PERS_APPLN.person_id == TLS206_PERSON.person_id)
            .join(TLS201_APPLN, TLS201_APPLN.appln_id == TLS207_PERS_APPLN.appln_id)
            .filter(TLS206_PERSON.psn_id.in_(psn_ids[start:start + chunk]),
                    TLS207_PERS_APPLN.applt_seq_nr > 0,
                    TLS201_APPLN.ipr_type == IPR_TYPE,
                    TLS201_APPLN.earliest_filing_year.between(1800, YEAR_MAX))   # drops the 9999 placeholders
            .group_by(TLS206_PERSON.psn_id)
        )
        parts.append(patstat.df(q))
        print(f"  first patents: {min(start + chunk, len(psn_ids)):,} of {len(psn_ids):,} names")
    return pd.concat(parts, ignore_index=True)
