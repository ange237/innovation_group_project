"""Step 3: present patent-portfolio value, adapted from tutorial 40.

Place this file in project_g_09/src and run: python src/step3.py
Requires the professor-aligned Step 2 data/ snapshots, not a new sector query.
Use --help for period, candidate selection, cutoff and offline replay options.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
from pathlib import Path

import numpy as np
import pandas as pd


INDICATORS = ['volume', 'influence', 'success', 'globalization']
PROFESSOR_WEIGHTS = dict(volume=.15, influence=.40, success=.20, globalization=.25)
EQUAL_WEIGHTS = dict.fromkeys(INDICATORS, .25)
RAW_FILES = ['members.csv', 'publications.csv', 'citations.csv']


def sha256(path):
    """Identify exact inputs; never infer reproducibility from filenames alone."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dates(values):
    """Accept PATSTAT dates or CSV dates; unknown/9999 dates remain missing."""
    text = values.astype('string').str.strip().str.replace(r'\.0$', '', regex=True)
    return pd.to_datetime(text, format='mixed', errors='coerce')


def find_root(explicit=None):
    """Find the project when invoked from either its root or its src directory."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    for origin in [Path(__file__).resolve().parent, Path.cwd()]:
        for path in [origin, *origin.parents]:
            if (path / 'config/sector.yaml').is_file():
                return path
    raise FileNotFoundError('Project not found. Place this file in src/ or pass --root PROJECT.')


def load_inputs(root, cfg, start, end):
    """Reuse exact Step 2 family IDs, dates, names and CPCs, including unnamed families."""
    base = root / cfg.get('output_dir', 'outputs')
    step2 = base / 'step2'
    paths = [step2 / 'data' / n for n in
             ['family_universe.csv', 'family_applicants.csv', 'family_cpc.csv']]
    paths.append(base / 'step0/applicant_info.csv')
    for p in paths:
        if not p.is_file():
            raise FileNotFoundError(f'Missing {p}. Run the professor-aligned landscape.py first.')
    # Check saved datasets, not unrelated source-code text changed after that run.
    manifest_path = step2 / 'step2_run_manifest.json'
    if not manifest_path.is_file():
        raise FileNotFoundError(f'Missing {manifest_path}; rerun Step 2 to export its manifest.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    config_hash = manifest.get('source_sha256', {}).get('config/sector.yaml')
    if not config_hash or sha256(root/'config/sector.yaml') != config_hash:
        raise ValueError('Project configuration differs from the Step 2 run. Restore it or rerun Step 2.')
    expected = {x['file']: x['sha256'] for x in manifest['outputs']}
    for p in paths[:3]:
        key = p.relative_to(step2).as_posix()
        if key not in expected or sha256(p) != expected[key]:
            raise ValueError(f'Step 2 snapshot missing from manifest or changed: {key}')
    old_env = manifest.get('step0_manifest', {}).get('environment')
    if old_env and old_env != cfg['environment']:
        raise ValueError('Step 2 environment differs from config; do not mix TEST and PROD.')
    info_hash = manifest.get('step0_manifest', {}).get('context_sha256', {}).get('applicant_info.csv')
    if info_hash and sha256(paths[3]) != info_hash:
        raise ValueError('Applicant metadata changed since Step 2. Rerun Step 2.')
    u, links, cpc = [pd.read_csv(p, keep_default_na=False, na_values=['']) for p in paths[:3]]
    info = pd.read_csv(paths[3], keep_default_na=False, na_values=[''])
    if 'applicant' not in info or not {'type', 'country'}.issubset(info):
        raise ValueError('applicant_info.csv needs applicant, type and country columns.')
    for frame, columns in [(u,['unit_id','year']), (links,['unit_id','year','applicant']),
                            (cpc,['unit_id','cpc'])]:
        if not set(columns).issubset(frame):
            raise ValueError(f'Invalid Step 2 columns: expected {columns}.')
        for key in ['unit_id', 'year']:
            if key in frame:
                frame[key] = pd.to_numeric(frame[key], errors='raise').astype('int64')
    if u.unit_id.duplicated().any() or u.unit_id.le(0).any():
        raise ValueError('Sector universe needs distinct positive family IDs.')
    if not links.unit_id.isin(u.unit_id).all() or not cpc.unit_id.isin(u.unit_id).all():
        raise ValueError('Step 2 links/CPCs contain families outside its universe.')
    check = links.merge(u, on='unit_id', suffixes=('_link', '_scope'), validate='many_to_one')
    if not check.year_link.eq(check.year_scope).all():
        raise ValueError('Family years disagree across Step 2 snapshots.')
    if links.applicant.isna().any() or links.applicant.astype(str).str.strip().eq('').any():
        raise ValueError('Family-applicant links contain empty names.')
    if info.applicant.duplicated().any():
        raise ValueError('Applicant metadata must have one row per cleaned applicant.')
    last = int(cfg['years']['max']) - max(
        cfg['truncated_years']['earliest_filing_year'], cfg['truncated_years']['appln_filing_year'])
    if not int(cfg['years']['min']) <= start <= end <= last:
        raise ValueError(f'Use a family-year window inside {cfg["years"]["min"]}-{last}.')
    # Verify the global denominator against Step 1 if its annual table is available.
    volume_path = base / 'step1/volume_per_year.csv'
    if volume_path.is_file():
        annual = pd.read_csv(volume_path)
        annual = annual[annual.scope.eq(cfg['sector']['name']) & annual.level.eq('family') & annual.series.eq('all')]
        actual = u.groupby('year').unit_id.nunique()
        expected_counts = annual.set_index('year').n
        years = actual.index.union(expected_counts.index)
        if expected_counts.index.duplicated().any() or not actual.reindex(years,fill_value=0).eq(
                expected_counts.reindex(years,fill_value=0)).all():
            raise ValueError('Step 1 totals differ from Step 2 family universe.')
        paths.append(volume_path)
    u = u[u.year.between(start, end)].copy()
    if u.empty:
        raise ValueError('No sector families in the requested window.')
    links = links[links.unit_id.isin(u.unit_id)].drop_duplicates(['unit_id','applicant'])
    cpc = cpc[cpc.unit_id.isin(u.unit_id)].drop_duplicates(['unit_id','cpc'])
    paths.extend([manifest_path, root / 'config/sector.yaml'])
    return u, links, cpc, info, paths


def fetch_raw(client, db, family_ids, as_of, ipr_type, folder, batch_size):
    """Query missing indicators in batches; archive each compiled SQL statement.

    Citations use the date of the citing publication carrying the reference,
    not the first publication of a potentially much older citing family.
    """
    from sqlalchemy import case, func
    from sqlalchemy.orm import aliased
    from epo.tipdata.patstat.database.models import TLS201_APPLN, TLS211_PAT_PUBLN, TLS212_CITATION
    A, P, C = TLS201_APPLN, TLS211_PAT_PUBLN, TLS212_CITATION
    cited_p, citing_p = aliased(P), aliased(P)
    cited_a, citing_a = aliased(A), aliased(A)
    sql_dir = folder / 'sql'
    sql_dir.mkdir(parents=True, exist_ok=True)
    collected = {name: [] for name in ['members', 'publications', 'citations']}

    def read(query, name, batch):
        statement = query.statement
        sql = str(statement.compile(dialect=db.bind.dialect,
                                    compile_kwargs={'literal_binds': True}))
        (sql_dir / f'{batch:04d}_{name}.sql').write_text(sql, encoding='utf-8')
        return client.df(query)

    ids = sorted(set(int(x) for x in family_ids))
    for offset in range(0, len(ids), batch_size):
        chunk = ids[offset:offset + batch_size]
        number = offset // batch_size + 1
        print(f'PATSTAT batch {number}/{(len(ids)+batch_size-1)//batch_size}: {len(chunk)} families')
        q = (db.query(A.docdb_family_id.label('unit_id'), A.appln_id,
                      A.appln_auth.label('office'), A.appln_kind.label('kind'),
                      A.appln_filing_date.label('filing_date'))
             .filter(A.docdb_family_id.in_(chunk), A.ipr_type == ipr_type))
        members = read(q, 'members', number)
        q = (db.query(A.docdb_family_id.label('unit_id'), A.appln_id,
                      func.min(P.publn_date).label('first_publication'),
                      func.min(case((P.publn_first_grant == 'Y', P.publn_date),
                                    else_=None)).label('first_grant'))
             .select_from(A).join(P, A.appln_id == P.appln_id)
             .filter(A.docdb_family_id.in_(chunk), A.ipr_type == ipr_type,
                     P.publn_date.between(datetime(1800,1,1).date(), as_of.date()))
             .group_by(A.docdb_family_id, A.appln_id))
        pubs = read(q, 'publications', number)
        members = members.merge(pubs[['appln_id','first_grant']], on='appln_id', how='left', validate='one_to_one')
        first = pubs.groupby('unit_id', as_index=False).first_publication.min()
        q = (db.query(cited_a.docdb_family_id.label('cited_family'),
                      citing_a.docdb_family_id.label('citing_family'),
                      citing_p.publn_date.label('citation_date'))
             .select_from(C)
             .join(cited_p, C.cited_pat_publn_id == cited_p.pat_publn_id)
             .join(cited_a, cited_p.appln_id == cited_a.appln_id)
             .join(citing_p, C.pat_publn_id == citing_p.pat_publn_id)
             .join(citing_a, citing_p.appln_id == citing_a.appln_id)
             .filter(cited_a.docdb_family_id.in_(chunk), cited_a.ipr_type == ipr_type,
                     citing_a.docdb_family_id > 0,
                     citing_a.docdb_family_id != cited_a.docdb_family_id,
                     citing_p.publn_date.between(datetime(1800,1,1).date(), as_of.date()))
             .distinct())
        citations = read(q, 'citations', number)
        for name, frame in [('members',members), ('publications',first), ('citations',citations)]:
            collected[name].append(frame)
    result = {name: pd.concat(parts, ignore_index=True) for name,parts in collected.items()}
    for name, frame in result.items():
        frame.drop_duplicates().to_csv(folder / f'{name}.csv', index=False)
    return result


def family_indicators(universe, cpc, members, publications, citations, as_of,
                      citation_years=5, grant_age=5, min_cohort=5):
    """Compute the professor's indicators at family level before firm aggregation."""
    f = universe[['unit_id','year']].rename(columns={'year':'priority_year'}).set_index('unit_id').copy()
    pubs = publications.copy()
    pubs['first_publication'] = dates(pubs.first_publication)
    pubs = pubs[pubs.first_publication.le(as_of)]
    first = pubs.groupby('unit_id').first_publication.min()
    f['first_publication'] = first.reindex(f.index)
    f['citation_window_end'] = f.first_publication + pd.DateOffset(years=citation_years)
    f['citation_window_complete'] = f.citation_window_end.le(as_of)
    x = citations.copy()
    x['citation_date'] = dates(x.citation_date)
    x['start'] = x.cited_family.map(f.first_publication)
    x['end'] = x.cited_family.map(f.citation_window_end)
    x = x[x.citing_family.ne(x.cited_family) & x.citing_family.gt(0)
          & x.citation_date.ge(x.start) & x.citation_date.le(x.end) & x.citation_date.le(as_of)]
    counts = x.groupby('cited_family').citing_family.nunique()
    f['fwd5'] = counts.reindex(f.index, fill_value=0).where(f.citation_window_complete)
    # A family with several subclasses participates once in each field-year cohort.
    # Average its normalised values across those fields; never multiply its firm credit.
    classifications = cpc[['unit_id','cpc']].copy()
    classifications['cpc4'] = classifications.cpc.fillna('').str.replace(' ','',regex=False).str[:4]
    classifications = classifications[classifications.cpc4.str.fullmatch(r'[A-HY]\d{2}[A-Z]')]
    cohorts = classifications[['unit_id','cpc4']].drop_duplicates().merge(
        f[['priority_year','fwd5']], left_on='unit_id', right_index=True, validate='many_to_one')
    grouping = cohorts.groupby(['cpc4','priority_year']).fwd5
    cohorts['cohort_n'] = grouping.transform('count')
    cohorts['cohort_mean'] = grouping.transform('mean')
    valid = cohorts.cohort_n.ge(min_cohort) & cohorts.fwd5.notna()
    # Follow the professor's explicit convention: an observed all-zero cohort
    # has normalised zero, while missing windows/sparse cohorts remain missing.
    cohorts['normalised_citations'] = (cohorts.fwd5 / cohorts.cohort_mean).where(
        cohorts.cohort_mean.gt(0), 0.0).where(valid)
    threshold = grouping.transform(lambda s: s.quantile(.90))
    cohorts['highly_cited'] = (cohorts.fwd5.ge(threshold) & cohorts.fwd5.gt(0)).astype(float).where(valid)
    # Apply the same predeclared support rule to every field; keep a usable main
    # subclass when an additional rare subclass fails, and expose field coverage.
    summary = cohorts.groupby('unit_id').agg(
        fields=('cpc4','size'), fields_valid=('normalised_citations','count'),
        influence=('normalised_citations','mean'), highly_cited=('highly_cited','mean'))
    summary['field_coverage'] = summary.fields_valid / summary.fields
    f = f.join(summary)
    m = members.drop_duplicates('appln_id').copy()
    m['filing_date'] = dates(m.filing_date)
    m['first_grant'] = dates(m.first_grant)
    m['office'] = m.office.fillna('').astype(str).str.strip()
    m['kind'] = m.kind.fillna('').astype(str).str.strip()
    known = m[m.filing_date.le(as_of)]
    national = known[known.office.ne('WO') & known.office.ne('') & known.kind.ne('T')]
    f['offices'] = national.groupby('unit_id').office.nunique().reindex(f.index, fill_value=0).astype(float)
    # Missing member information is not evidence of zero international protection.
    f.loc[~f.index.isin(known.unit_id), 'offices'] = np.nan
    m['unknown_member'] = m.filing_date.isna() | m.office.eq('')
    incomplete_members = m.groupby('unit_id').unknown_member.any().reindex(f.index,fill_value=True)
    f.loc[incomplete_members, 'offices'] = np.nan
    mature = national[national.office.eq('EP') &
                      (national.filing_date + pd.DateOffset(years=grant_age)).le(as_of)].copy()
    mature['has_grant'] = mature.first_grant.le(as_of)
    f['ep_applications'] = mature.groupby('unit_id').appln_id.nunique().reindex(f.index,fill_value=0)
    f['ep_granted'] = mature.groupby('unit_id').has_grant.sum().reindex(f.index,fill_value=0)
    f['member_data_complete'] = ~incomplete_members
    # Optional sensitivity: application success across offices, averaged per family.
    mature_all = national[(national.filing_date + pd.DateOffset(years=grant_age)).le(as_of)].copy()
    mature_all['has_grant'] = mature_all.first_grant.le(as_of)
    f['family_success'] = mature_all.groupby('unit_id').has_grant.mean()
    return f, cohorts


def firm_indicators(links, universe, families, min_coverage=.8):
    """Full family counting as in the tutorial and Step 2; EP success uses applications."""
    links = links[links.unit_id.isin(universe.unit_id)].drop_duplicates(['unit_id','applicant'])
    joined = links[['unit_id','applicant']].merge(families, left_on='unit_id', right_index=True,
                                                validate='many_to_one')
    g = joined.groupby('applicant', sort=True)
    result = pd.DataFrame({'families':g.unit_id.nunique()})
    result['volume'] = result.families / len(universe)
    for source, target in [('influence','influence'), ('offices','globalization'),
                           ('highly_cited','highly_cited_share'), ('family_success','family_success')]:
        result[target] = g[source].mean()
        result[target + '_coverage'] = g[source].count() / result.families
        result.loc[result[target + '_coverage'].lt(min_coverage), target] = np.nan
    result['complete_citation_windows'] = g.citation_window_complete.sum()
    result['mature_ep_applications'] = g.ep_applications.sum()
    result['granted_ep_applications'] = g.ep_granted.sum()
    result['success'] = result.granted_ep_applications / result.mature_ep_applications.replace(0,np.nan)
    result['ep_family_coverage'] = joined.assign(has_ep=joined.ep_applications.gt(0)).groupby('applicant').has_ep.mean()
    result['member_data_coverage'] = g.member_data_complete.mean()
    result['mean_cpc_field_coverage'] = g.field_coverage.mean()
    # Do not invent grant outcomes when family membership is incomplete.
    result.loc[result.member_data_coverage.lt(1), 'success'] = np.nan
    result['median_fwd5'] = g.fwd5.median()
    result['sector_families'] = len(universe)
    return result


def combine(table, weights, method='rrf'):
    """Professor's weighted relative mean or reciprocal-rank fusion, with complete cases.

    All scenarios receive the same preselected complete-case pool. Missing
    indicators never become zero and weights are never silently redistributed.
    """
    w = pd.Series(weights, dtype=float)
    if w.empty or not np.isfinite(w).all() or (w < 0).any() or w.sum() <= 0:
        raise ValueError('Weights must be finite, non-negative, with positive total.')
    w = w[w.gt(0)] / w.sum()
    t = table[list(w.index)]
    valid = t.notna().all(axis=1) & np.isfinite(t).all(axis=1) & t.ge(0).all(axis=1)
    t = t.loc[valid]
    result = pd.Series(np.nan, index=table.index, dtype=float)
    if t.empty:
        return result
    if method == 'rrf':
        ranks = t.rank(ascending=False, method='min')
        result.loc[t.index] = 100 * ((len(t)+1)/(len(t)+ranks)*w).sum(axis=1)
    elif method == 'mean':
        if t.mean().le(0).any():
            return result  # An all-zero dimension has no relative-mean benchmark.
        result.loc[t.index] = 100 * (t/t.mean()*w).sum(axis=1)
    else:
        raise ValueError('method must be rrf or mean')
    return result


def score_firms(firms, candidates, min_families, min_ep):
    """Use a fixed candidate pool for weight and aggregation sensitivity."""
    selected = firms.reindex(candidates).copy()
    selected['score_status'] = ''
    for name, row in selected.iterrows():
        reasons = []
        if row.families < min_families:
            reasons.append('portfolio below minimum size')
        if row.mature_ep_applications < min_ep:
            reasons.append('too few mature EP applications')
        missing = [k for k in INDICATORS if pd.isna(row[k])]
        if missing:
            reasons.append('missing/insufficient coverage: ' + ', '.join(missing))
        selected.loc[name, 'score_status'] = '; '.join(reasons) or 'scored'
    pool = selected[selected.score_status.eq('scored')]
    scores = pd.DataFrame(index=selected.index)
    schemes = {'equal':EQUAL_WEIGHTS, 'professor':PROFESSOR_WEIGHTS}
    for method in ['rrf', 'mean']:
        for scheme, w in schemes.items():
            scores[f'{method}_{scheme}'] = combine(pool, w, method).reindex(selected.index)
    # Removing one dimension preserves the relative weights of the others.
    for key in INDICATORS:
        w = {k:v for k,v in PROFESSOR_WEIGHTS.items() if k != key}
        scores['rrf_without_' + key] = combine(pool,w,'rrf').reindex(selected.index)
    ranks = scores.rank(ascending=False, method='min')
    selected['present_score'] = scores.rrf_equal
    selected['present_rank'] = ranks.rrf_equal
    selected['best_sensitivity_rank'] = ranks.min(axis=1)
    selected['worst_sensitivity_rank'] = ranks.max(axis=1)
    selected = selected.sort_values(['present_rank','applicant'], na_position='last')
    return selected, scores, ranks, scores.corr(method='spearman')


def figures(selected, ranks, output):
    """Save the four underlying profiles alongside the composite and sensitivity."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    shown = selected.copy()
    names = shown.index.to_list()
    fig, axes = plt.subplots(2,2,figsize=(14,max(8,len(shown)*.50)))
    for ax, key in zip(axes.ravel(), INDICATORS):
        factor = 100 if key in ['volume','success'] else 1
        ax.barh(names, shown[key].values*factor, color='#176b9b')
        ax.invert_yaxis()
        ax.set_title(key.capitalize() + (' (%)' if factor==100 else ''))
        ax.grid(axis='x',alpha=.2)
    fig.tight_layout()
    fig.savefig(output/'01_four_indicators.png',dpi=180,bbox_inches='tight'); plt.close(fig)
    valid = shown[shown.present_score.notna()]
    if valid.empty:
        # Always replace our own previous figures on offline replay, including
        # when revised thresholds leave no scored firms.
        for filename,title in [('02_present_score.png','Step 3: present value'),
                               ('03_rank_sensitivity.png','Ranking sensitivity')]:
            fig,ax=plt.subplots(figsize=(10,4));ax.axis('off')
            ax.set_title(title)
            ax.text(.5,.5,'No firms meet the declared scoring requirements.\nSee selected_firms.csv and coverage columns.',
                    ha='center',va='center',transform=ax.transAxes)
            fig.tight_layout();fig.savefig(output/filename,dpi=180,bbox_inches='tight');plt.close(fig)
    if not valid.empty:
        fig,ax=plt.subplots(figsize=(10,max(4,len(valid)*.45)))
        ax.barh(valid.index,valid.present_score,color='#eb8900'); ax.invert_yaxis()
        ax.set(xlabel='Relative patent-portfolio score (equal-weight RRF)',title='Step 3: present value')
        fig.tight_layout();fig.savefig(output/'02_present_score.png',dpi=180,bbox_inches='tight');plt.close(fig)
        grid = ranks.reindex(valid.index)
        fig,ax=plt.subplots(figsize=(13,max(4,len(valid)*.5)))
        im=ax.imshow(grid.to_numpy(dtype=float),aspect='auto',cmap='YlGnBu_r',vmin=1,vmax=max(2,len(valid)))
        ax.set_yticks(range(len(valid)),valid.index)
        ax.set_xticks(range(len(grid.columns)),grid.columns,rotation=35,ha='right')
        for i in range(len(grid)):
            for j in range(len(grid.columns)):
                if pd.notna(grid.iloc[i,j]):
                    color = 'white' if grid.iloc[i,j] < 1+.5*(max(2,len(valid))-1) else 'black'
                    ax.text(j,i,f'{grid.iloc[i,j]:.0f}',ha='center',va='center',fontsize=8,color=color)
        fig.colorbar(im,ax=ax,label='rank; lower is better')
        ax.set_title('Ranking sensitivity on the same firms')
        fig.tight_layout();fig.savefig(output/'03_rank_sensitivity.png',dpi=180,bbox_inches='tight');plt.close(fig)


def raw_identity(universe, cfg, as_of, paths):
    """Freeze query-relevant inputs; reject offline replay after changing them."""
    ids = sorted(int(i) for i in universe.unit_id)
    return dict(environment=cfg['environment'], ipr_type=cfg.get('ipr_type','PI'),
                as_of=as_of.date().isoformat(), family_ids_sha256=hashlib.sha256(
                    json.dumps(ids).encode()).hexdigest(),
                step2_inputs={p.name:sha256(p) for p in paths[:3]})


def method_notes(args, cfg, selected):
    """Document assumptions and limitations next to the results, not only in code."""
    return f'''# Step 3 - present patent-portfolio value

Sector: {cfg['sector']['name']}. Family cohort: {args.start}-{args.end}.
Observation cutoff: {args.as_of}. This is an explicit analytical assumption;
the script cannot certify that the PATSTAT edition covers every event by then.
Record --patstat-edition when available and choose a supported cutoff.

Adapted from 40_present_value_score.ipynb and IM_Theory_5_Patent_valuation.pdf.
Scope and cleaned applicant/group/JV labels are inherited from Step 2 unchanged.
Family years use Step 1's configured {cfg['family_time_column']}; they are not
recomputed as the minimum filing year of a subset of EP applications.
Historical applicant attribution is not a verified current ownership register.

## Four indicators
* Volume: full-count distinct firm families / ALL sector families in the cohort,
  including families with no known applicant and families of non-companies.
  Co-owned families count once for each distinct applicant, as in the tutorial.
* Influence: distinct external-to-family citing families in exactly five calendar
  years after first publication, including the anniversary; dated publication
  references from TLS212/TLS211, deduplicated at citing/cited family level.
  Within-company self-citations are retained, within-family references excluded.
  Families need a complete five-year window. Divide by the mature sector mean
  in each CPC subclass x project family-year cohort (minimum {args.min_cohort}).
  For multi-class families average ratios across supported recorded subclasses,
  then average families per firm. Sparse cohorts remain missing. Following the
  professor, an observed zero-mean cohort receives normalised zero, not missing.
  Report supported/recorded subclasses per family and its firm-level mean;
  sparse secondary classes do not invalidate a supported primary class.
  This benchmark is the EV sector, not all worldwide patents in each CPC.
* Success: observed granted EP applications / mature EP applications, pooling
  applications across firm families. Mature means at least {args.grant_age}
  calendar years from the application's own filing date. First-grant publication
  dates are checked against the cutoff. No recorded grant is not a proven refusal.
  Attribution to the family's applicants follows the professor's family-owner
  approach; it does not assert every owner co-filed every member application.
* Globalization: mean distinct application offices per family; exclude WO and
  kind T translations. EP counts once. It measures filing breadth, not currently
  valid countries. Unknown member dates/offices do not become zero.

Influence/globalization require >= {args.min_coverage:.0%} family coverage.
For success the whole member inventory must be usable, with at least
{args.min_ep_applications} mature EP applications. Firms with no EP sample
remain unranked; this EP-based measure can therefore limit geographic coverage.
Firms below {args.min_families} families remain visible but unranked.
Check coverage before interpreting any comparison.

## Candidate selection and scores
Automatic selection: top {args.top_n} firms by cohort family volume (type=firm),
plus requested --include names. --firms replaces automatic selection with a
team-chosen list. Selection is a discussion starting point, not a claim that
only large firms matter. Toyota is not added or excluded silently.
Selected: {len(selected)}; scored: {int(selected.present_score.notna().sum())}.

Main score: equal-weight reciprocal-rank fusion, as in the tutorial:
100 * sum(w_k * (N+1)/(N+rank_k)); N is the fixed complete candidate pool.
Ties share the minimum rank. This is a relative index, not euros or company value.
Also export weighted relative means and professor weights (influence .40,
globalization .25, success .20, volume .15). Mean scores have reference 100;
RRF scores have no population-mean interpretation. All missing values remain
missing. Scores are comparable within this frozen candidate pool, not across
separately selected pools. Do not renormalise Step 4 scores on a different list.
Leave-one-out keeps the remaining professor weights in their original proportions.
Sensitivity is descriptive, not proof of a uniquely correct investment decision.

## Additional diagnostics (not extra main-score weights)
Median five-year citations; within-cohort top-decile highly-cited family share
(positive citations required; boundary ties can exceed 10%; multi-class flags
are averaged); across-office grant fraction averaged at family level.
These are not an X/I blocking-patent score or the OECD top-1% indicator.
No claims, opposition, renewal or active-legal-status proxy is fabricated.
PEST remains the project's separate written contextual analysis.

## Files and reuse
firm_indicators.csv: all linked applicants, including institutions for reference.
selected_firms.csv: selected companies, raw indicators, coverage, score and status.
score_scenarios.csv / rank_scenarios.csv / rank_correlations.csv: sensitivity.
family_indicators.csv / citation_cohorts.csv: auditable family/cohort detail.
step4_handoff.csv: selected names, present score/rank and eligibility; join later
future scores by applicant. Keep unranked cases explicitly missing.
raw/: query data and compiled SQL. Reuse without queries using --reuse-raw.
run_manifest.json: parameters, database label, input/output hashes and versions.
This archives a rerunnable extract; live queries can change with PATSTAT editions.
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root')
    parser.add_argument('--start',type=int,default=2010)
    parser.add_argument('--end',type=int,default=2018)
    parser.add_argument('--as-of',help='YYYY-MM-DD; default: config years.max December 31')
    parser.add_argument('--patstat-edition',default='not recorded; check TIP dataset edition')
    parser.add_argument('--top-n',type=int,default=10)
    parser.add_argument('--firms',nargs='+',help='Exact cleaned company names; overrides top-N')
    parser.add_argument('--include',action='append',default=[],help='Add one exact cleaned company name')
    parser.add_argument('--min-families',type=int,default=10)
    parser.add_argument('--min-ep-applications',type=int,default=5)
    parser.add_argument('--min-cohort',type=int,default=5)
    parser.add_argument('--min-coverage',type=float,default=.8)
    parser.add_argument('--grant-age',type=int,default=5)
    parser.add_argument('--batch-size',type=int,default=1000)
    parser.add_argument('--reuse-raw',action='store_true',help='Replay archived raw CSVs without PATSTAT')
    parser.add_argument('--out',help='New run directory; relative paths are resolved from project root')
    args = parser.parse_args(argv)
    if not 0 < args.min_coverage <= 1 or any(getattr(args,k)<1 for k in
            ['top_n','min_families','min_ep_applications','min_cohort','grant_age','batch_size']):
        parser.error('Coverage must be in (0,1]; count/age/batch parameters must be positive.')
    import yaml
    root = find_root(args.root)
    cfg = yaml.safe_load((root/'config/sector.yaml').read_text(encoding='utf-8'))
    if cfg['environment'] not in ['TEST','PROD']:
        raise ValueError('environment must be TEST or PROD.')
    args.as_of = args.as_of or f'{cfg["years"]["max"]}-12-31'
    as_of = pd.Timestamp(args.as_of)
    if pd.isna(as_of) or as_of.tzinfo is not None or as_of != as_of.normalize():
        raise ValueError('--as-of must be a valid calendar date without a time zone.')
    args.as_of = as_of.date().isoformat()
    if as_of > pd.Timestamp.today().normalize():
        raise ValueError('Observation cutoff cannot be in the future.')
    if args.end > as_of.year:
        raise ValueError('Family window must end no later than the observation cutoff.')
    u,links,cpc,info,paths = load_inputs(root,cfg,args.start,args.end)
    all_candidates = links.groupby('applicant').unit_id.nunique().rename('families').to_frame().join(
        info.set_index('applicant')[['type','country']])
    company_names = all_candidates.index[all_candidates.type.eq('firm')]
    if args.firms:
        names = args.firms + args.include
    else:
        eligible = all_candidates.loc[company_names]
        eligible = eligible[eligible.families.ge(args.min_families)]
        names = eligible.sort_values(['families','applicant'],ascending=[False,True]).head(args.top_n).index.to_list()+args.include
    names = list(dict.fromkeys(names))
    if not names:
        raise ValueError('No eligible firms. Review --min-families or supply --firms with exact cleaned names.')
    unknown = [n for n in names if n not in company_names]
    if unknown:
        raise ValueError(f'Unknown/non-firm candidates: {unknown}. Check outputs/step2/applicants.csv.')
    output = Path(args.out) if args.out else Path(cfg.get('output_dir','outputs'))/'step3'
    if not output.is_absolute(): output = root/output
    raw_folder = output/'raw'
    identity = raw_identity(u,cfg,as_of,paths)
    cache_manifest = raw_folder/'extraction_manifest.json'
    if args.reuse_raw:
        saved = json.loads(cache_manifest.read_text(encoding='utf-8'))
        if saved['identity'] != identity:
            raise ValueError('Raw cache cutoff/environment/family inputs differ; use a new --out and extract again.')
        for filename in RAW_FILES:
            if sha256(raw_folder/filename) != saved['sha256'][filename]:
                raise ValueError(f'Raw cache changed: {filename}')
        raw = {Path(n).stem:pd.read_csv(raw_folder/n,keep_default_na=False,na_values=['']) for n in RAW_FILES}
        edition = saved['patstat_edition']
        if args.patstat_edition != parser.get_default('patstat_edition') and args.patstat_edition != edition:
            raise ValueError('--patstat-edition differs from the archived extraction.')
    else:
        # Existing extraction directories are never silently overwritten by a live run.
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f'{output} already contains results. Use --reuse-raw or a new --out directory.')
        raw_folder.mkdir(parents=True,exist_ok=True)
        from epo.tipdata.patstat import PatstatClient
        client = PatstatClient(env=cfg['environment'])
        db = client.orm()
        try:
            raw = fetch_raw(client,db,u.unit_id,as_of,cfg.get('ipr_type','PI'),raw_folder,args.batch_size)
        finally:
            db.close()
        edition = args.patstat_edition
        cache_manifest.write_text(json.dumps(dict(identity=identity,patstat_edition=edition,
            sha256={n:sha256(raw_folder/n) for n in RAW_FILES}),indent=2),encoding='utf-8')
    print(f'Sector: {cfg["sector"]["name"]}; family cohort {args.start}-{args.end}; cutoff {args.as_of}')
    print('Cutoff is an analytical assumption: verify coverage against your PATSTAT edition.')
    families, cohorts = family_indicators(u,cpc,raw['members'],raw['publications'],raw['citations'],
                                         as_of,5,args.grant_age,args.min_cohort)
    firms = firm_indicators(links,u,families,args.min_coverage)
    firms = firms.join(info.set_index('applicant')[['type','country']],validate='one_to_one')
    selected,scores,ranks,correlations = score_firms(firms,names,args.min_families,args.min_ep_applications)
    for name, table in [('family_indicators',families), ('firm_indicators',firms),
                        ('selected_firms',selected), ('score_scenarios',scores),
                        ('rank_scenarios',ranks), ('rank_correlations',correlations)]:
        label = 'scenario' if name == 'rank_correlations' else (table.index.name or 'applicant')
        table.to_csv(output/f'{name}.csv',index_label=label)
    cohorts.to_csv(output/'citation_cohorts.csv',index=False)
    handoff = selected[['type','country','families','present_score','present_rank','score_status',*INDICATORS]].copy()
    handoff['family_start'] = args.start; handoff['family_end'] = args.end
    handoff['as_of'] = args.as_of; handoff['score_method'] = 'rrf_equal_fixed_candidate_pool'
    handoff.to_csv(output/'step4_handoff.csv',index_label='applicant')
    figures(selected,ranks,output)
    (output/'READING_GUIDE.md').write_text(method_notes(args,cfg,selected),encoding='utf-8')
    packages = {}
    for name in ['pandas','numpy','matplotlib','SQLAlchemy','PyYAML','epo-tipdata']:
        try: packages[name] = version(name)
        except PackageNotFoundError: packages[name] = 'not available in package metadata'
    outputs = [p for p in output.rglob('*') if p.is_file() and p.name != 'run_manifest.json']
    manifest = dict(created_utc=datetime.now(timezone.utc).isoformat(),parameters=vars(args),
        patstat_edition=edition,environment=cfg['environment'],versions=packages,
        source_sha256=sha256(__file__),input_sha256={str(p.relative_to(root)):sha256(p) for p in paths},
        outputs={p.relative_to(output).as_posix():sha256(p) for p in outputs},
        sector_families=len(u),named_families=int(links.unit_id.nunique()),
        selected_firms=names,scored_firms=selected.index[selected.present_score.notna()].to_list(),
        normalisation='CPC subclass x inherited family year, within-sector benchmark',
        citation_window='exact five calendar years from first publication',
        raw_identity=identity)
    (output/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(selected[['families',*INDICATORS,'present_score','present_rank','score_status']].to_string())
    print(f'Step 3 complete: {output}')
    if selected.present_score.notna().sum()<2:
        print('Fewer than two firms scored: no meaningful comparative ranking. Inspect coverage and cohort sizes.')


if __name__ == '__main__':
    main()
