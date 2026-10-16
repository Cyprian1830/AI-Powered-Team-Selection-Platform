import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = Path(os.getenv("TS_RAW_DIR", ROOT / "data" / "raw"))
STAGING_DIR = Path(os.getenv("TS_STAGING_DIR", ROOT / "data" / "staging"))
DB_PATH = Path(os.getenv("TS_DB_PATH", ROOT / "data" / "team_selection.db"))
LLM_MODEL = os.getenv("TS_LLM_MODEL", "claude-sonnet-5-5")
