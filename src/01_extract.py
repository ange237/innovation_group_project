"""Extract the existing sector size, optional review sample and raw applicants.

Run from the project root: python src/01_extract.py
Optional review sample: python src/01_extract.py --validation-sample 100
Then run src/02_clean.py.
"""
import argparse
import hashlib
import json
import sys
from importlib.metadata import version, PackageNotFoundError
from datetime import date

import pandas as pd

from settings import ROOT, ENV, STEP0_DIR, TOP_APPLICANTS, USE_BUSINESS_GROUPS
from patstat_queries import (
    applicants_by_family, count_rows, sector_family_ids, sector_ids, validation_sample,
)
from harmonise import (
    family_applicants, harmonise, joint_ventures_found, merge_report, name_version_comparison, top_applicants,
)
from helpers import save_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-sample", type=int, default=0,
                        help="draw a new random sample of N families for manual review (default: none)")
    args = parser.parse_args()
    STEP0_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ 1. sector size
    print("\n=== 1. Sector size (all years, before the time window) ===")
    n_before = count_rows(sector_family_ids())
    n_after = count_rows(sector_ids)
    size = pd.DataFrame({
        "families": [n_before, n_after, n_before - n_after],
    }, index=["CPC or keywords", "after excluding B63/B64/F03D", "excluded"])
    print(size.to_string())
    save_table(size, STEP0_DIR / "sector_size.csv")

    # ------------------------------------------------------------ 2. validation sample (optional)
    if args.validation_sample > 0:
        print(f"\n=== 2. New validation sample of {args.validation_sample} families ===")
        path = STEP0_DIR / f"validation_sample_{ENV}_{date.today():%Y%m%d}.xlsx"
        if path.exists():
            raise FileExistsError(f"{path} already exists; it is never overwritten.")
        review_data = validation_sample(args.validation_sample)
        review_data.to_excel(path, index=False)
        print("Excel file created:", path, "| families:", len(review_data))
    else:
        print("\n=== 2. Validation sample: skipped (reviewed samples are not bundled in the submitted archive) ===")

    raw = applicants_by_family()
    raw_path = STEP0_DIR / "raw_applicants.pkl"
    raw.to_pickle(raw_path)
    sources = ["config/sector.yaml", "src/patstat_queries.py", "src/settings.py"]
    manifest = {"source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
                "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest()}
    (STEP0_DIR / "extraction_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Extraction done. Run python src/02_clean.py next.")


if __name__ == "__main__":
    main()
