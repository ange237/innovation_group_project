"""Focused, offline international PEST evidence for the EV charging sector.

Run: python src/global_pest.py
No PATSTAT connection, runtime web requests or language model are required.
"""
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
import argparse
import hashlib
import json
import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COUNTRIES = {
    'China':'East Asia', 'USA':'North America', 'Japan':'East Asia',
    'Germany':'Europe', 'India':'South Asia', 'Brazil':'Latin America',
    'Mexico':'Latin America', 'Indonesia':'Southeast Asia', 'Thailand':'Southeast Asia',
    'Australia':'Oceania', 'South Africa':'Africa', 'United Arab Emirates':'Middle East',
}
AGGREGATES = ['World','Europe','Latin America','Southeast Asia','Africa','Middle East and Caspian']
MARKET_METRICS = ['car_sales','car_stock','car_sales_share_pct','public_charging_points',
                  'capacity_per_ev_kw','fast_ultrafast_share_pct']
DELOITTE_MARKETS = ['China','Germany','India','Japan','South Korea','Southeast Asia','UK','US']
DELOITTE_SAMPLE = [859,1280,1346,683,909,5196,1363,944]
CHARGING_SAMPLE = [312,327,266,74,196,1247,307,116]


def normalise(text):
    """Remove layout whitespace without changing substantive source wording."""
    return ' '.join(str(text).replace('\u00ad','').split())


class PageText(HTMLParser):
    """Read source HTML instead of trusting an unregistered derived TXT file."""
    def __init__(self):
        super().__init__(); self.parts=[]; self.hidden=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','noscript'): self.hidden += 1
        if tag in ('p','div','br','li','h1','h2','h3'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style','noscript') and self.hidden: self.hidden -= 1
    def handle_data(self, text):
        if not self.hidden: self.parts.append(text)


class SourceArchive:
    """Verify each active original file against the download manifest before use."""
    def __init__(self, folder):
        self.folder=Path(folder)
        rows=json.loads((self.folder/'source_manifest.json').read_text(encoding='utf-8'))
        self.records={row['source_id']:row for row in rows}
        if len(self.records)!=len(rows): raise ValueError('Duplicate archived source identifiers.')
        self.used={}; self.readers={}

    def path(self, identifier):
        record=self.records[identifier]
        if record.get('status')!='downloaded':
            raise FileNotFoundError(f'{identifier} was not downloaded. No substitute is inferred.')
        path=(self.folder/record['file']).resolve()
        if not path.is_relative_to(self.folder.resolve()): raise ValueError('Source path escapes archive.')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError(f'Archived source missing or changed: {identifier}')
        self.used[identifier]=record
        return path

    def page(self, identifier, number):
        if identifier not in self.readers:
            try: from pypdf import PdfReader
            except ImportError as exc:
                raise ImportError('Install the PDF reader first: pip install pypdf') from exc
            self.readers[identifier]=PdfReader(self.path(identifier))
        return self.readers[identifier].pages[number-1].extract_text()

    def html(self, identifier):
        parser=PageText(); parser.feed(self.path(identifier).read_text(encoding='utf-8',errors='replace'))
        return normalise(' '.join(parser.parts))

    def reference(self, identifier, page=None):
        self.path(identifier)
        row=self.records[identifier]
        return dict(source_id=identifier,source_url=row['url'],source_file=row['file'],
                    source_sha256=row['sha256'],pdf_page_1based=page,
                    retrieved_utc=row.get('retrieved_utc',''))


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


def exact_growth(data, metric, first, last):
    """Use exact endpoints; never replace missing years or a zero base."""
    values=data.set_index('year')[metric]
    if values.index.duplicated().any(): raise ValueError('Repeated years in growth series.')
    if first not in values.index or last not in values.index or last<=first: return np.nan
    start,end=values.loc[first],values.loc[last]
    if pd.isna(start) or pd.isna(end) or start<=0 or end<0: return np.nan
    return 100*((end/start)**(1/(last-first))-1)


def compact_market(workbook, first=2020, last=2025):
    """Keep six descriptive metrics and explicitly separate countries from aggregates."""
    raw,validation=iea_read_workbook(workbook)
    panel=iea_country_panel(raw)
    known=set(panel.region_country)
    missing=set(COUNTRIES).difference(known)
    if missing: raise ValueError(f'Configured countries not found: {sorted(missing)}')
    chosen=panel[panel.region_country.isin(list(COUNTRIES)+AGGREGATES) & panel.year.between(first,last)].copy()
    chosen['geography_type']=np.where(chosen.region_country.isin(COUNTRIES),'country','aggregate')
    chosen['macroarea']=chosen.region_country.map(COUNTRIES).fillna('IEA aggregate')
    history=chosen[['region_country','geography_type','macroarea','year']+MARKET_METRICS].copy()
    history['source_id']='IEA_LOCAL_2026'
    snapshot=history[history.year.eq(last)].copy()
    expected=set(COUNTRIES).union(AGGREGATES)
    missing_latest=expected.difference(snapshot.region_country)
    if missing_latest:
        # Keep absent geographies as missing rows instead of selecting an older year.
        additional=pd.DataFrame({'region_country':sorted(missing_latest),'year':last})
        additional['geography_type']=np.where(additional.region_country.isin(COUNTRIES),'country','aggregate')
        additional['macroarea']=additional.region_country.map(COUNTRIES).fillna('IEA aggregate')
        additional['source_id']='IEA_LOCAL_2026'
        snapshot=pd.concat([snapshot,additional],ignore_index=True)
    growth={geo:exact_growth(group,'car_sales',first,last) for geo,group in history.groupby('region_country')}
    snapshot['sales_cagr_pct']=snapshot.region_country.map(growth)
    baselines=history[history.year.eq(first)].set_index('region_country').car_sales
    snapshot['cagr_base_sales']=snapshot.region_country.map(baselines)
    snapshot['cagr_base_year']=first; snapshot['cagr_end_year']=last
    snapshot['metrics_available']=snapshot[MARKET_METRICS].notna().sum(axis=1)
    return history,snapshot,validation


def extract_percent_row(text, label, count):
    """Select one labelled PDF table row; fail if the layout becomes ambiguous."""
    flattened=normalise(text)
    pattern=re.escape(label)+r'\s+((?:\d+(?:\.\d+)?%\s*){'+str(count)+r'})(?!\s*\d+(?:\.\d+)?%)'
    matches=re.findall(pattern,flattened)
    if len(matches)!=1: raise ValueError(f'Cannot unambiguously extract PDF row: {label}')
    values=[float(v) for v in re.findall(r'(\d+(?:\.\d+)?)%',matches[0])]
    if len(values)!=count or any(v<0 or v>100 for v in values): raise ValueError('Invalid survey percentages.')
    return values


def consumer_evidence(archive):
    """Read four Q48 barriers and Q46 price sensitivity, keeping their different bases."""
    rows=[]
    text=archive.page('DELOITTE_GACS_PDF',10)
    if 'Q48.' not in text: raise ValueError('Deloitte question numbering changed.')
    factors={
        'Time required to charge':'charging_time_concern',
        'Lack of public EV charging infrastructure':'public_charging_concern',
        'Lack of charger at home':'home_charging_concern',
        'Cost/price premium':'vehicle_price_concern',
    }
    for label,indicator in factors.items():
        values=extract_percent_row(text,label,8)
        for geo,value,sample in zip(DELOITTE_MARKETS,values,DELOITTE_SAMPLE):
            rows.append(dict(geography=geo,geography_type='regional_sample' if geo=='Southeast Asia' else 'country',
                indicator=indicator,value_pct=value,question='Q48',sample_n=sample,
                population='Survey respondents asked about BEV concerns; multiple responses allowed',
                observation_period='2025-10 to 2025-11',publication_year=2026,
                limitation='Survey intentions/perceptions, not measured charging availability; no cross-country significance test.',
                extraction_method='labelled PDF table row',**archive.reference('DELOITTE_GACS_PDF',10)))
    # The public-cost chart has eight ordered stacks. The order was visually
    # checked against page 9; a changed question or stack length must fail.
    cost=archive.page('DELOITTE_GACS_PDF',9)
    if 'Q46.' not in cost or 'Important Neutral Not important' not in cost:
        raise ValueError('Deloitte cost chart layout changed.')
    prefix=cost.split('Across markets surveyed')[0]
    numbers=[float(v) for v in re.findall(r'(\d+(?:\.\d+)?)%',prefix)]
    if len(numbers)!=24: raise ValueError('Deloitte cost chart no longer contains eight three-part stacks.')
    stacks=np.array(numbers).reshape(8,3)
    if not np.all(np.abs(stacks.sum(axis=1)-100)<=1): raise ValueError('Deloitte cost stacks do not reconcile.')
    cost_order=['India','Japan','UK','China','Southeast Asia','Germany','US','South Korea']
    for geo,value in zip(cost_order,stacks[:,0]):
        rows.append(dict(geography=geo,geography_type='regional_sample' if geo=='Southeast Asia' else 'country',
            indicator='public_charging_cost_important',value_pct=value,question='Q46',
            sample_n=CHARGING_SAMPLE[DELOITTE_MARKETS.index(geo)],
            population='BEV/PHEV intenders asked about public charging; very or somewhat important',
            observation_period='2025-10 to 2025-11',publication_year=2026,
            limitation='Different question base from Q48; perceived importance is not a tariff or willingness-to-pay estimate.',
            extraction_method='PDF chart stacks; market order visually verified',**archive.reference('DELOITTE_GACS_PDF',9)))
    # Ipsos page 27 is deliberately excluded: its signed values are not a
    # clearly defined approval percentage. Use the explicit narrative instead.
    ipsos=normalise(archive.page('IPSOS_2026',26))
    specs=[('31-country average',r'Across 31 countries, (\d+)% say','Unweighted country average'),
           ('Rural respondents',r'Four in ten \((\d+)%\)','Cross-country rural subgroup'),
           ('Urban respondents',r'compared to (\d+)% of people living in an urban area','Cross-country urban subgroup')]
    for geo,pattern,population in specs:
        match=re.search(pattern,ipsos)
        if not match: raise ValueError(f'Ipsos narrative changed: {geo}')
        rows.append(dict(geography=geo,geography_type='multicountry_context',indicator='ev_appeal',
            value_pct=float(match.group(1)),question='Driving an EV appeals to me',sample_n=None,
            population=population,observation_period='2025-11-21 to 2025-12-05',publication_year=2026,
            limitation='Not a world-population estimate. Connected/urban sampling biases in several markets; see Ipsos page 39.',
            extraction_method='Explicit percentage in PDF narrative',**archive.reference('IPSOS_2026',26)))
    return pd.DataFrame(rows)


POLICIES = [
    ('European Union','Europe',11,'Alternative Fuels Infrastructure Regulation:','Legislation',2023,
     'Minimum coverage and charging-power requirements', 'Coverage obligations can support deployment; compliance requirements also affect design.'),
    ('China','East Asia',8,'Three-Year Action Plan for Doubling','Legislation',2025,
     'National charging service-capacity expansion plan','Large deployment targets indicate policy direction, not installations already achieved.'),
    ('USA','North America',32,'Alternative Fuel Vehicle Refueling Property Credit','Legislation',2023,
     'Federal charging-equipment credit with June 2026 sunset','Eligibility deadlines create policy exposure; this is not continuing support after the sunset.'),
    ('India','South Asia',17,'The revised EV charging guidelines','Announced target',2024,
     'Charging connection timelines and supply-tariff guidelines','Connection rules and input tariffs may affect rollout economics; retain the source classification.'),
    ('Brazil','Latin America',4,'National Green Mobility and Innovation Program','Legislation',2024,
     'Automotive industrial innovation programme','Industrial support is broader than BEV charging; do not treat the total budget as charging funding.'),
    ('Kenya','Africa',19,'National Building Code 2024 mandates','Legislation',2024,
     'Charging provision in new-building parking','Building rules can support residential access; this case does not describe the whole of Africa.'),
    ('United Arab Emirates','Middle East',31,'Increase EV charging stations to 10 000','Announced target',2023,
     'Long-term charging-station expansion target','Targets indicate ambition; they are not observed station counts or proof of delivery.'),
    ('Australia','Oceania',1,'Driving the Nation Fund','Legislation',2021,
     'Support for charging-infrastructure rollout','Funding programmes can support rollout; this row does not estimate actual annual disbursements.'),
]


def context_evidence(archive):
    """Retrieve selected passages and attach explicit, curated analyst interpretations."""
    rows=[]
    for geo,area,page,anchor,status,year,factor,interpretation in POLICIES:
        text=normalise(archive.page('IEA_POLICY_PDF',page))
        if anchor not in text: raise ValueError(f'Policy evidence not found: {geo}')
        # The excerpt is only a locator; the full cited row/page is authoritative.
        excerpt=' '.join(text[text.index(anchor):].split()[:22])
        rows.append(dict(pillar='Political',geography=geo,macroarea=area,factor=factor,
            source_classification=status,policy_record_year=year,observation_period='IEA snapshot 2026-05-20',
            source_locator=excerpt,analyst_interpretation=interpretation,
            limitation='Selected case, not exhaustive policy coverage or country ranking. Later changes are not automatically revalidated.',
            **archive.reference('IEA_POLICY_PDF',page)))
    contexts=[
        ('Economic','International context','IEA_CHARGING','Home charging has consistently offered running cost savings',
         'Private versus public charging economics','Cost advantages depend on location and charging channel; public-fast prices can reduce the benefit.',
         'Not a harmonized tariff table or a new TCO calculation.'),
        ('Technological','International context','OCA_OCPP','between charging stations and charging management systems',
         'Interoperability and smart charging','Open communication standards can reduce proprietary integration barriers; OCPP is not a physical connector.',
         'Protocol capability is not evidence of deployed adoption or interoperability at every station.'),
        ('Technological','International context','OCA_OCPP','bidirectional power transfer',
         'Bidirectional charging capability','Bidirectional communication support creates an integration pathway; vehicle, hardware and grid rules must also permit it.',
         'Technical availability does not establish V2G revenues or widespread deployment.'),
        ('Economic','Developing-country context','WB_EMOBILITY','analysis across 40 countries',
         'Segment-specific economics in emerging markets','Analyze financing and vehicle use separately; high-use buses and two/three-wheelers are adjacent segments.',
         'Landing-page qualitative finding only; full report was not downloaded. Do not transfer segment results to Toyota passenger cars.'),
    ]
    for pillar,geo,sid,anchor,factor,interpretation,limitation in contexts:
        text=archive.html(sid)
        if anchor not in text: raise ValueError(f'Context passage missing: {factor}')
        reference=archive.reference(sid)
        period='Source snapshot retrieved '+reference['retrieved_utc'][:10]+'; underlying periods vary'
        if sid=='OCA_OCPP':
            period+='; publication date not stated; OCPP 2.1 released in 2025'
        rows.append(dict(pillar=pillar,geography=geo,macroarea='International context',factor=factor,
            source_classification='Qualitative source evidence',policy_record_year=None,
            observation_period=period,
            source_locator=anchor,analyst_interpretation=interpretation,limitation=limitation,
            **reference))
    return pd.DataFrame(rows)


def synthesis(history, snapshot, consumers, contexts):
    """Link eight PEST factors to evidence; do not manufacture a weighted score."""
    rows=[
        ('P1','Political','Policy direction and durability','context_evidence.csv','IEA_POLICY_PDF',
         'Compare policy type, scope and expiry across the eight documented cases.',
         'Check incentives, grid rules and building requirements before proposing a market entry.'),
        ('E1','Economic','Charging-demand development','market_history.csv; market_snapshot.csv','IEA_LOCAL_2026',
         'Use EV sales, stock, adoption and exact-endpoint CAGR; countries and aggregates are separate.',
         'Assess demand growth alongside the existing vehicle base; sales are not charger revenue.'),
        ('E2','Economic','Price sensitivity and charging economics','consumer_evidence.csv; context_evidence.csv','DELOITTE_GACS_PDF; IEA_CHARGING',
         'Q46 measures public-charging cost importance; IEA describes channel-dependent economics.',
         'Evaluate charging affordability and business models without assuming domestic tariffs equal public prices.'),
        ('S1','Social','Acceptance and settlement differences','consumer_evidence.csv','IPSOS_2026',
         'Use the explicitly reported country average and urban/rural context, without a world-population inference.',
         'Consider residential access and user context; the urban/rural gap is descriptive, not causal.'),
        ('S2','Social','Practical and financial adoption barriers','consumer_evidence.csv','DELOITTE_GACS_PDF',
         'Compare four Q48 concerns across eight focus markets; keep Q46 denominators separate.',
         'Distinguish hardware need, installation access, charging time and vehicle-price barriers.'),
        ('T1','Technological','Infrastructure scale and power','market_snapshot.csv; market_history.csv','IEA_LOCAL_2026',
         'Use public charging points, fast-share and estimated kW per EV; retain missing components.',
         'Evaluate charging mix with home-charging context; capacity is not measured utilization or coverage.'),
        ('T2','Technological','Interoperability and energy integration','context_evidence.csv','OCA_OCPP',
         'Separate documented protocol functionality from real-world deployment.',
         'Consider interoperable software and smart/bidirectional integration alongside physical charging hardware.'),
        ('E3','Economic','Emerging-market segment differences','context_evidence.csv','WB_EMOBILITY',
         'Use the source as qualitative context for segment-dependent economics.',
         'Keep passenger-car conclusions separate from bus, motorcycle and battery-swapping opportunities.'),
    ]
    return pd.DataFrame(rows,columns=['factor_id','pillar','factor','evidence_table','source_id','reading_rule','analyst_implication'])


def figures(output, history, snapshot, consumers):
    """Plot exported observations; missing points stay missing and no survey average is added."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    names=[]
    def save(fig,name,note):
        fig.text(.015,.015,note,fontsize=8)
        fig.tight_layout(rect=(0,.07,1,1)); fig.savefig(output/name,dpi=170,bbox_inches='tight')
        plt.close(fig); names.append(name)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for geo in ['World','China','Europe','USA','India','Latin America','Southeast Asia']:
        group=history[history.region_country.eq(geo)]
        axes[0].plot(group.year,group.car_sales_share_pct,marker='o',ms=3,label=geo)
        axes[1].plot(group.year,group.car_stock/1e6,marker='o',ms=3,label=geo)
    axes[0].set(title='Plug-in share of new car sales',ylabel='%',ylim=(0,100),xlabel='year')
    axes[1].set(title='Plug-in electric car stock',ylabel='million cars',xlabel='year')
    for ax in axes: ax.grid(alpha=.2); ax.legend(fontsize=8)
    save(fig,'01_demand.png','IEA workbook, historical only. EV = BEV + PHEV. World/regions and countries are separate series; never sum them.')
    countries=snapshot[snapshot.geography_type.eq('country')].sort_values('region_country')
    fig,axes=plt.subplots(1,2,figsize=(13,6))
    for ax,metric,title,label in [
        (axes[0],'capacity_per_ev_kw','Public charging capacity per EV','estimated kW per plug-in LDV'),
        (axes[1],'fast_ultrafast_share_pct','Fast and ultra-fast public share','% of public charging points')]:
        positions=np.arange(len(countries))
        ax.barh(positions,countries[metric]);ax.set(title=title,xlabel=label,
            yticks=positions,yticklabels=countries.region_country,ylim=(-.6,len(countries)-.4))
        for index,(_,row) in enumerate(countries.iterrows()):
            if pd.isna(row[metric]): ax.text(0,index,'not available',va='center',fontsize=8)
    save(fig,'02_infrastructure.png','IEA workbook, common year 2025. Missing is not zero; power and charger mix do not measure utilization or station reliability.')
    labels=['charging_time_concern','public_charging_concern','home_charging_concern','vehicle_price_concern']
    matrix=consumers[consumers.question.eq('Q48')].pivot(index='geography',columns='indicator',values='value_pct').reindex(index=DELOITTE_MARKETS,columns=labels)
    fig,ax=plt.subplots(figsize=(11,6)); image=ax.imshow(matrix,cmap='Blues',vmin=0,vmax=60,aspect='auto')
    ax.set(xticks=range(4),xticklabels=['Charging\ntime','Public\ninfrastructure','Home\ncharger','Vehicle\nprice'],yticks=range(8),yticklabels=DELOITTE_MARKETS,title='Reported BEV concerns across focus markets')
    for i in range(8):
        for j in range(4): ax.text(j,i,f'{matrix.iloc[i,j]:.0f}%',ha='center',va='center',color='white' if matrix.iloc[i,j]>35 else 'black')
    fig.colorbar(image,ax=ax,label='% selecting concern (multiple responses)')
    save(fig,'03_consumer_barriers.png','Deloitte 2026, Q48; fieldwork Oct-Nov 2025. Samples differ by market. Southeast Asia is a regional sample, not a country.')
    cost=consumers[consumers.question.eq('Q46')].sort_values('geography')
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    axes[0].barh(cost.geography,cost.value_pct);axes[0].set(title='Public-charging cost is important',xlabel='% of BEV/PHEV intenders asked (Q46)',xlim=(0,100))
    appeal=consumers[consumers.indicator.eq('ev_appeal')]
    axes[1].barh(appeal.geography,appeal.value_pct,color=['#507da5','#73a9b0','#3c7e78']);axes[1].set(title='EV appeal: multicountry context',xlabel='% agreeing, as reported by Ipsos',xlim=(0,100))
    save(fig,'04_cost_and_acceptance.png','Separate surveys, questions and populations. Ipsos fieldwork Nov-Dec 2025; country average is not population weighted. No pooled percentage.')
    return names


def run_global_pest(root=ROOT, results=None, workbook=None, make_figures=True):
    """Build the selected PEST evidence independently from patent database stages."""
    root=Path(root).resolve()
    results=Path(results).resolve() if results is not None else root/'outputs/step2'
    output=results/'pest_global';output.mkdir(parents=True,exist_ok=True)
    archive=SourceArchive(root/'data/external/global_pest_sources')
    workbook=Path(workbook) if workbook is not None else root/'data/external/EV data by country 2026.xlsx'
    history,snapshot,validation=compact_market(workbook)
    consumers=consumer_evidence(archive);contexts=context_evidence(archive)
    matrix=synthesis(history,snapshot,consumers,contexts)
    tables={'market_history.csv':history,'market_snapshot.csv':snapshot,
            'consumer_evidence.csv':consumers,'context_evidence.csv':contexts,'pest_matrix.csv':matrix}
    for name,data in tables.items(): data.to_csv(output/name,index=False)
    registry=list(archive.used.values())
    registry.append(dict(source_id='IEA_LOCAL_2026',file=str(workbook.relative_to(root)) if workbook.is_relative_to(root) else str(workbook),
        url='https://www.iea.org/reports/global-ev-outlook-2026/',sha256=hashlib.sha256(workbook.read_bytes()).hexdigest(),
        status='local_workbook_read',notes='GEVO_EV_2026 sheet; Historical only; six selected metrics.'))
    pd.DataFrame(registry).to_csv(output/'pest_sources.csv',index=False)
    coverage=snapshot[['region_country','geography_type','macroarea','year','metrics_available']].copy()
    coverage['missing_metrics']=snapshot[MARKET_METRICS].apply(lambda row:'; '.join(row.index[row.isna()]),axis=1)
    coverage['deloitte_q48_available']=coverage.region_country.replace({'USA':'US','United Kingdom':'UK','Korea':'South Korea'}).isin(DELOITTE_MARKETS)
    coverage['policy_case_available']=coverage.region_country.isin(contexts.loc[contexts.pillar.eq('Political'),'geography'])
    coverage.to_csv(output/'coverage.csv',index=False)
    chart_names=figures(output,history,snapshot,consumers) if make_figures else []
    guide='''# Global EV charging PEST: reading guide

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
'''
    (output/'READING_GUIDE.md').write_text(guide,encoding='utf-8')
    owned=list(tables)+['pest_sources.csv','coverage.csv','READING_GUIDE.md']+chart_names
    manifest=dict(method='focused_global_pest_v1',run_utc=datetime.now(timezone.utc).isoformat(),
        runtime_network_access=False,patstat_required=False,history_years=[2020,2025],snapshot_year=2025,
        countries=list(COUNTRIES),aggregates=AGGREGATES,market_validation=validation,
        evidence_rows={name:len(frame) for name,frame in tables.items()},
        used_sources=[row['source_id'] for row in registry],
        unused_archived_sources=sorted(set(archive.records)-set(archive.used)),
        outputs=[dict(file=name,sha256=hashlib.sha256((output/name).read_bytes()).hexdigest()) for name in owned])
    (output/'pest_run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f'Global PEST saved in {output}: {len(snapshot)} geographical comparisons, {len(consumers)} survey observations, {len(contexts)} context findings.')
    return dict(matrix=matrix,evidence=consumers,sources=registry,output=output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,help='Existing Step 2 output folder; only pest_global is written.')
    parser.add_argument('--no-figures',action='store_true',help='Build tables only.')
    args=parser.parse_args()
    run_global_pest(results=args.results,make_figures=not args.no_figures)


if __name__=='__main__': main()
