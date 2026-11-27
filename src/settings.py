"""Project settings, read from config/sector.yaml.

Same names as the configuration cell of the notebook, so every function below
reads exactly like the professor's tutorial.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "config" / "sector.yaml"

with CONFIG_FILE.open(encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

# ---------------------------------------------------------------- environment
ENV = _cfg["environment"]
if ENV not in ("TEST", "PROD"):
    raise ValueError("environment in config/sector.yaml must be TEST or PROD")
OUTPUT_DIR = ROOT / _cfg["output_dir"]
STEP0_DIR = OUTPUT_DIR / "step0"
STEP1_DIR = OUTPUT_DIR / "step1"

# ---------------------------------------------------------------- sector definition
SECTOR_NAME = _cfg["sector"]["name"]
SECTOR_CPC_PREFIXES = tuple(_cfg["sector"]["cpc_prefixes"])
SECTOR_KEYWORDS = tuple(_cfg["sector"]["keywords"])
EXCLUDE_CPC_PREFIXES = tuple(_cfg["sector"]["exclude_cpc_prefixes"])

# ---------------------------------------------------------------- time window
YEAR_MIN, YEAR_MAX = _cfg["years"]["min"], _cfg["years"]["max"]
FAMILY_TIME_COLUMN = _cfg["family_time_column"]
APPLN_TIME_COLUMN = _cfg["appln_time_column"]
TRUNCATED_YEARS = dict(_cfg["truncated_years"])

# ---------------------------------------------------------------- counting rules
IPR_TYPE = _cfg["ipr_type"]
IP5_OFFICES = tuple(_cfg["ip5_offices"])
SHOWN_OFFICES = IP5_OFFICES + tuple(_cfg.get("extra_offices_shown", ()))
TOP_N = _cfg["top_n"]
GROWTH_BASE_YEARS = tuple(_cfg["growth_base_years"])

# ---------------------------------------------------------------- applicant names
USE_BUSINESS_GROUPS = bool(_cfg["applicants"]["use_business_groups"])
TOP_APPLICANTS = _cfg["applicants"]["top_n"]

# ---------------------------------------------------------------- derived
LAST_COMPLETE_YEAR = YEAR_MAX - max(TRUNCATED_YEARS[FAMILY_TIME_COLUMN], TRUNCATED_YEARS[APPLN_TIME_COLUMN])
LEVELS = ("family", "application")
UNIT_LABEL = {"family": "families", "application": "applications"}

# Step 0 additions from the supplied team project.
LEGAL_FORM_CLEANING = bool(_cfg["applicants"].get("legal_form_cleaning", True))
GOLD_STANDARD_FILE = ROOT / _cfg["applicants"].get("gold_standard_file", "config/PATSTAT_500_label_datav4.csv")
