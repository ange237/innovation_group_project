"""Clean the extracted applicants with the existing company rules and calculations.

Run from the project root: python src/02_clean.py
Requires the unchanged local DataFrame handoff written by src/01_extract.py.
Then run src/landscape.py.
"""
import argparse
import hashlib
import json
import sys
from importlib.metadata import version, PackageNotFoundError
from datetime import date

import pandas as pd

from settings import (ROOT, ENV, STEP0_DIR, TOP_APPLICANTS, USE_BUSINESS_GROUPS,
                      LEGAL_FORM_CLEANING, GOLD_STANDARD_FILE, LAST_COMPLETE_YEAR)

from harmonise import (
    family_applicants, harmonise, joint_ventures_found, merge_report, name_version_comparison, top_applicants,
    applicant_info, applicant_psn_ids, evaluate_on_gold,
)
from helpers import save_table


def main():
    # Reload the exact DataFrame produced by this project's 01_extract.py.
    raw_path = STEP0_DIR / "raw_applicants.pkl"
    manifest_path = STEP0_DIR / "extraction_manifest.json"
    if not raw_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Run python src/01_extract.py first.")
    extraction = json.loads(manifest_path.read_text(encoding="utf-8"))
    for filename, expected in extraction["source_sha256"].items():
        if hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() != expected:
            raise ValueError("Extraction settings changed: rerun 01_extract.py.")
    if hashlib.sha256(raw_path.read_bytes()).hexdigest() != extraction["raw_sha256"]:
        raise ValueError("Extracted data changed: rerun 01_extract.py.")
    raw = pd.read_pickle(raw_path)
    # ------------------------------------------------------------ 3. applicant names
    print("\n=== 3. Applicant name harmonisation ===")
    harmonised = harmonise(raw, use_business_groups=USE_BUSINESS_GROUPS,
                           legal_forms=LEGAL_FORM_CLEANING)
    print(f"{len(harmonised):,} family-applicant rows, {harmonised['family_id'].nunique():,} families "
          f"| business groups merged: {USE_BUSINESS_GROUPS}")

    comparison = name_version_comparison(harmonised)
    print(comparison.round(1).to_string(index=False))
    save_table(comparison, STEP0_DIR / "applicant_name_versions.csv", index=False)

    merges = merge_report(harmonised)
    save_table(merges, STEP0_DIR / "applicant_name_merges.csv", index=False)
    print(f"{len(merges):,} PSN names merged into {merges['applicant'].nunique()} groups "
          f"(check applicant_name_merges.csv by eye)")

    jv = joint_ventures_found(harmonised)
    print(f"{len(jv)} joint ventures kept separate:", *jv, sep="\n  ")

    fam_app = family_applicants(harmonised)
    # Preserve 1/n credits exactly; report-table rounding would corrupt Step 2.
    handoff = STEP0_DIR / "sector_family_applicants.csv"
    fam_app.to_csv(handoff, index=False)
    source_files = ["config/sector.yaml", "src/harmonise.py", "src/patstat_queries.py", "src/settings.py"]
    # Keep applicant-sector metadata from the same extraction for collaboration analysis.
    metadata_path = STEP0_DIR / "sector_family_applicant_sectors.csv"
    harmonised[["family_id", "year", "applicant", "psn_sector"]].drop_duplicates().to_csv(metadata_path, index=False)
    # Country/type summaries use complete years, while all mapped PSN IDs
    # remain available for the all-field patent-history lookup.
    info_path = STEP0_DIR / "applicant_info.csv"
    ids_path = STEP0_DIR / "applicant_psn_ids.csv"
    audit_path = STEP0_DIR / "name_normalisation_audit.csv"
    info = applicant_info(harmonised[harmonised.year.le(LAST_COMPLETE_YEAR)])
    info.to_csv(info_path)
    applicant_psn_ids(harmonised).to_csv(ids_path,index=False)
    harmonised[["person_name","psn_name","applicant"]].drop_duplicates().to_csv(audit_path,index=False)
    if GOLD_STANDARD_FILE.is_file():
        gold_check = evaluate_on_gold(pd.read_csv(GOLD_STANDARD_FILE))
        gold_check.to_csv(STEP0_DIR / "harmonisation_gold_standard.csv")
        print("Gold-standard check:\n",gold_check.round(3).to_string())
    else:
        print("Optional gold-standard CSV not supplied; no measured precision/recall claim is generated.")
    manifest = {"metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(), "environment": ENV, "python": sys.version,
                "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_files},
                "applicants_sha256": hashlib.sha256(handoff.read_bytes()).hexdigest(),
                "legal_form_cleaning": LEGAL_FORM_CLEANING,
                "context_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [info_path,ids_path,audit_path]}}
    (STEP0_DIR / "handoff_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Capture versions on the machine that actually runs the pipeline (TIP), never the author's laptop.
    packages = ["epo-tipdata", "pandas", "numpy", "matplotlib", "SQLAlchemy", "PyYAML", "openpyxl", "scipy"]
    installed = []
    for package in packages:
        try:
            installed.append(f"{package}=={version(package)}")
        except PackageNotFoundError:
            print(f"Version metadata unavailable for {package}; check TIP with pip show.")
    (ROOT / "requirements-tip.txt").write_text("# Captured on the pipeline runtime\n" + "\n".join(installed) + "\n", encoding="utf-8")

    top = top_applicants(harmonised, TOP_APPLICANTS).drop(columns="type").join(info)
    print(top.round(1).to_string())
    save_table(top, STEP0_DIR / f"applicants_top{TOP_APPLICANTS}.csv")

    print("\nStep 0 done. Outputs in", STEP0_DIR)


if __name__ == "__main__":
    main()
