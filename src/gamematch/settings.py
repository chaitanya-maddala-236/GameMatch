from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
DATA_DIR = Path(os.getenv("GAMEMATCH_DATA_DIR", PROJECT_ROOT / "data")).expanduser().resolve()
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
ARTIFACT_DIR = Path(
    os.getenv(
        "GAMEMATCH_MODEL_PATH",
        str(PROJECT_ROOT / "artifacts" / "models" / "gamematch-v1" / "model.joblib"),
    )
).expanduser().resolve()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(PROJECT_ROOT / 'gamematch.sqlite3').as_posix()}")
LOG_LEVEL = os.getenv("GAMEMATCH_LOG_LEVEL", "INFO").upper()
