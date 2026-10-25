from __future__ import annotations

from gamematch.settings import ARTIFACT_DIR, PROCESSED_DIR, RAW_DIR
from scripts.download_data import main as download
from scripts.prepare_data import main as prepare
from scripts.train import main as train


def main() -> None:
    if ARTIFACT_DIR.exists():
        print(f"Using existing model artifact: {ARTIFACT_DIR}")
        return
    required_raw = (
        RAW_DIR / "australian_users_items.json.gz",
        RAW_DIR / "steam_games.json.gz",
        RAW_DIR / "australian_user_reviews.json.gz",
    )
    if not all(path.exists() and path.stat().st_size > 0 for path in required_raw):
        download()
    required_processed = (
        PROCESSED_DIR / "interactions.csv.gz",
        PROCESSED_DIR / "catalog.json",
        PROCESSED_DIR / "train.csv.gz",
        PROCESSED_DIR / "validation.csv.gz",
        PROCESSED_DIR / "test.csv.gz",
        PROCESSED_DIR / "data_quality_report.json",
    )
    if not all(path.exists() and path.stat().st_size > 0 for path in required_processed):
        prepare()
    train()


if __name__ == "__main__":
    main()
