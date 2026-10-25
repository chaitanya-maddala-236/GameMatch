from __future__ import annotations

import ast
import csv
import gzip
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from gamematch.settings import PROCESSED_DIR, RAW_DIR


def records(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = ast.literal_eval(line)
            except (ValueError, SyntaxError) as exc:
                raise ValueError(f"Could not parse {path.name} line {line_number}") from exc
            if not isinstance(value, dict):
                raise TypeError(f"Expected a dictionary at {path.name}:{line_number}")
            yield value


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    result = str(value).strip()
    return "" if result.lower() in {"nan", "none", "null"} else result


def clean_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        items = value
    elif isinstance(value, str):
        items = re.split(r"[,;|]", value)
    else:
        return []
    return list(dict.fromkeys(text for item in items if (text := clean_text(item))))


def positive_int(value: Any) -> int:
    try:
        number = int(float(value))
        return max(0, number)
    except (TypeError, ValueError, OverflowError):
        return 0


def read_metadata(path: Path) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for row in records(path):
        game_id = clean_text(row.get("id"))
        if not game_id:
            continue
        title = clean_text(row.get("title")) or clean_text(row.get("app_name")) or f"Steam game {game_id}"
        catalog[game_id] = {
            "id": game_id,
            "title": title,
            "genres": clean_list(row.get("genres")),
            "tags": clean_list(row.get("tags")),
            "specs": clean_list(row.get("specs")),
            "release_date": clean_text(row.get("release_date")),
            "price": row.get("price") if isinstance(row.get("price"), (int, float)) and math.isfinite(row["price"]) else None,
            "metadata_source": "steam_games.json.gz",
        }
    return catalog


def read_explicit_dislikes(path: Path) -> set[tuple[str, str]]:
    dislikes: set[tuple[str, str]] = set()
    for row in records(path):
        user_id = clean_text(row.get("user_id"))
        reviews = row.get("reviews")
        if not user_id or not isinstance(reviews, list):
            continue
        for review in reviews:
            if isinstance(review, dict) and review.get("recommend") is False:
                game_id = clean_text(review.get("item_id"))
                if game_id:
                    dislikes.add((user_id, game_id))
    return dislikes


def source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    interactions_path = RAW_DIR / "australian_users_items.json.gz"
    metadata_path = RAW_DIR / "steam_games.json.gz"
    reviews_path = RAW_DIR / "australian_user_reviews.json.gz"
    missing = [path.name for path in (interactions_path, metadata_path, reviews_path) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing raw files {missing}. Run: python -m scripts.download_data")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    completion_report = PROCESSED_DIR / "data_quality_report.json"
    completion_report.unlink(missing_ok=True)
    catalog = read_metadata(metadata_path)
    explicit_dislikes = read_explicit_dislikes(reviews_path)
    user_index: dict[str, int] = {}
    counts: Counter[str] = Counter()
    staged = PROCESSED_DIR / "interactions_staged.csv.gz"

    with gzip.open(staged, "wt", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("user_idx", "game_id", "playtime_mins"))
        for row in records(interactions_path):
            counts["user_records"] += 1
            user_id = clean_text(row.get("user_id"))
            items = row.get("items")
            if not user_id or not isinstance(items, list):
                counts["invalid_user_records"] += 1
                continue
            user_idx = user_index.setdefault(user_id, len(user_index))
            per_user: dict[str, tuple[int, str]] = {}
            for item in items:
                if not isinstance(item, dict):
                    counts["invalid_item_records"] += 1
                    continue
                game_id = clean_text(item.get("item_id"))
                if not game_id:
                    counts["missing_game_ids"] += 1
                    continue
                playtime = positive_int(item.get("playtime_forever"))
                counts["library_rows"] += 1
                name = clean_text(item.get("item_name"))
                if game_id not in catalog:
                    catalog[game_id] = {
                        "id": game_id,
                        "title": name or f"Steam game {game_id}",
                        "genres": [],
                        "tags": [],
                        "specs": [],
                        "release_date": "",
                        "price": None,
                        "metadata_source": "user library title fallback",
                    }
                    counts["games_without_metadata"] += 1
                elif name and catalog[game_id]["title"].startswith("Steam game "):
                    catalog[game_id]["title"] = name
                previous = per_user.get(game_id)
                if previous is not None:
                    counts["duplicate_user_game_rows"] += 1
                    playtime = max(playtime, previous[0])
                per_user[game_id] = (playtime, name)
            for game_id, (playtime, _) in per_user.items():
                if playtime == 0:
                    counts["zero_playtime_ownerships"] += 1
                    continue
                if (user_id, game_id) in explicit_dislikes:
                    counts["explicit_negative_reviews_excluded"] += 1
                    continue
                writer.writerow((user_idx, game_id, playtime))
                counts["positive_interactions"] += 1

    game_ids = sorted(catalog)
    game_index = {game_id: index for index, game_id in enumerate(game_ids)}
    final_interactions = PROCESSED_DIR / "interactions.csv.gz"
    with gzip.open(staged, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        with gzip.open(final_interactions, "wt", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(("user_idx", "item_idx", "playtime_mins"))
            for row in reader:
                writer.writerow((row["user_idx"], game_index[row["game_id"]], row["playtime_mins"]))
    staged.unlink()

    games = []
    for index, game_id in enumerate(game_ids):
        row = catalog[game_id]
        row["item_idx"] = index
        games.append(row)
    (PROCESSED_DIR / "catalog.json").write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8")

    frame = pd.read_csv(final_interactions, dtype={"user_idx": "int32", "item_idx": "int32", "playtime_mins": "int32"})
    source_rows = len(frame)
    frame = frame.groupby(["user_idx", "item_idx"], as_index=False, sort=False)["playtime_mins"].max()
    counts["duplicate_pairs_after_normalization"] = source_rows - len(frame)
    import numpy as np

    rng = np.random.default_rng(2026)
    frame["_split_random"] = rng.random(len(frame))
    frame = frame.sort_values(["user_idx", "_split_random"], kind="stable")
    group_sizes = frame.groupby("user_idx", sort=False)["item_idx"].transform("size")
    group_positions = frame.groupby("user_idx", sort=False).cumcount()
    train_mask = (group_sizes < 3) | (group_positions >= 2)
    validation_mask = (group_sizes >= 3) & (group_positions == 0)
    test_mask = ((group_sizes >= 3) & (group_positions == 1)) | ((group_sizes == 2) & (group_positions == 0))
    train = frame.loc[train_mask].drop(columns="_split_random").copy()
    validation = frame.loc[validation_mask].drop(columns="_split_random").copy()
    test = frame.loc[test_mask].drop(columns="_split_random").copy()
    candidate_indices = set(train.groupby("item_idx").size().loc[lambda values: values >= 5].index.astype(int))
    validation = validation[validation["item_idx"].isin(candidate_indices)]
    test = test[test["item_idx"].isin(candidate_indices)]

    for name, split in (("train", train), ("validation", validation), ("test", test)):
        split.sort_values(["user_idx", "item_idx"], kind="stable").to_csv(
            PROCESSED_DIR / f"{name}.csv.gz", index=False, compression="gzip"
        )
    counts["unique_user_game_pairs"] = len(frame)
    counts["users"] = int(frame["user_idx"].nunique())
    counts["games"] = int(frame["item_idx"].nunique())
    counts["catalog_games"] = len(games)
    counts["training_interactions"] = len(train)
    counts["validation_targets"] = len(validation)
    counts["test_targets"] = len(test)
    counts["validation_users"] = int(validation["user_idx"].nunique())
    counts["test_users"] = int(test["user_idx"].nunique())
    counts["candidate_games"] = len(candidate_indices)
    counts["catalog_games_with_genre_or_tags"] = sum(bool(game["genres"] or game["tags"]) for game in games)
    counts["metadata_missing_fields"] = {
        "title": sum(not game["title"] for game in games),
        "genre_and_tags": counts["catalog_games"] - counts["catalog_games_with_genre_or_tags"],
    }
    manifest_path = RAW_DIR / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest["source_files_sha256"] = {
        path.name: source_hash(path) for path in (interactions_path, metadata_path, reviews_path)
    }
    report = {
        "dataset": "UCSD/McAuley Steam Australian users/items sample",
        "processed_at_utc": datetime.now(UTC).isoformat(),
        "seed": 2026,
        "split_strategy": "deterministic per-user random holdout; no source timestamps in user-items snapshot",
        "positive_definition": "playtime_forever > 0 minutes, except an explicit recommend=False review for the same pair",
        "candidate_definition": "games with at least 5 training positives",
        "counts": counts,
        "source": manifest,
    }
    completion_report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    dictionary = [
        ["field", "meaning", "source/processing"],
        ["user_idx", "Local pseudonymous integer index; original Steam IDs are not exported", "Assigned in source order during processing"],
        ["item_idx", "Stable integer index for a game in catalog.json", "Sorted game ID mapping"],
        ["playtime_mins", "Total recorded playtime in minutes", "Source playtime_forever; positive interactions only"],
        ["game.id", "Steam application ID", "Steam metadata ID or library item_id"],
        ["game.title", "Display title", "Metadata title/app_name; fallback to library item_name"],
        ["game.genres/tags/specs", "Available game descriptors", "Steam game metadata; empty when unavailable"],
        ["review.recommend", "Whether a review recommended the game", "Used only to exclude explicit negative review pairs"],
        ["review.posted", "Text review date", "Present in review file; not used to order library interactions"],
    ]
    with (PROCESSED_DIR / "data_dictionary.csv").open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(dictionary)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
