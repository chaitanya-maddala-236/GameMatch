from __future__ import annotations

import json
import os
import platform
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import psutil
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

from gamematch.evaluation import ranking_metrics
from gamematch.recommendation import GameRecommender
from gamematch.settings import ARTIFACT_DIR, PROCESSED_DIR

SEED = 2026
MIN_TRAIN_SUPPORT = 5
MAX_CANDIDATE_GAMES = 6000
NEIGHBORS = 100
MAX_EVAL_USERS = 5000
K_VALUES = (5, 10, 20)
WEIGHT_GRID = (
    {"collaborative": 0.70, "content": 0.20, "popularity": 0.10},
    {"collaborative": 0.50, "content": 0.40, "popularity": 0.10},
    {"collaborative": 0.35, "content": 0.50, "popularity": 0.15},
    {"collaborative": 0.45, "content": 0.30, "popularity": 0.25},
    {"collaborative": 0.30, "content": 0.30, "popularity": 0.40},
    {"collaborative": 0.25, "content": 0.55, "popularity": 0.20},
    {"collaborative": 0.20, "content": 0.20, "popularity": 0.60},
)


def top_neighbors(similarities: csr_matrix, n_neighbors: int) -> tuple[np.ndarray, np.ndarray]:
    n_items = similarities.shape[0]
    ids = np.full((n_items, n_neighbors), -1, dtype=np.int32)
    scores = np.zeros((n_items, n_neighbors), dtype=np.float32)
    similarities.setdiag(0)
    similarities.eliminate_zeros()
    similarities.sort_indices()
    for row in range(n_items):
        start, end = similarities.indptr[row : row + 2]
        row_ids = similarities.indices[start:end]
        row_scores = similarities.data[start:end]
        if len(row_ids) == 0:
            continue
        keep = min(n_neighbors, len(row_ids))
        picked = np.argpartition(row_scores, -keep)[-keep:]
        picked = picked[np.lexsort((row_ids[picked], -row_scores[picked]))]
        ids[row, :keep] = row_ids[picked]
        scores[row, :keep] = row_scores[picked]
    return ids, scores


def normalized_eval_users(split: pd.DataFrame, history_counts: np.ndarray, seed: int) -> list[tuple[int, int]]:
    eligible = split.groupby("user_idx", sort=False)["item_idx"].first()
    pairs = [(int(user), int(item)) for user, item in eligible.items()]
    rng = np.random.default_rng(seed)
    if len(pairs) > MAX_EVAL_USERS:
        selected = rng.choice(len(pairs), size=MAX_EVAL_USERS, replace=False)
        pairs = [pairs[int(i)] for i in selected]
    return pairs


def metrics_for_users(
    recommender: GameRecommender,
    split: pd.DataFrame,
    history_rows: csr_matrix,
    model: str,
    *,
    weights: dict[str, float] | None = None,
    limit_users: int = MAX_EVAL_USERS,
    seed: int = SEED,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    model_users = split.groupby("user_idx", sort=False)["item_idx"].agg(list)
    pairs = [(int(user), [int(item) for item in items]) for user, items in model_users.items()]
    rng = np.random.default_rng(seed)
    if len(pairs) > limit_users:
        chosen = rng.choice(len(pairs), size=limit_users, replace=False)
        pairs = [pairs[int(index)] for index in chosen]
    per_user: list[dict[str, Any]] = []
    metric_rows = {cutoff: {name: [] for name in ("precision", "recall", "ndcg", "map")} for cutoff in K_VALUES}
    recommended_items: set[str] = set()
    per_user_diversities: list[float] = []
    per_user_novelties: list[float] = []
    top_popularity = set(np.argsort(-recommender.popularity)[: max(1, len(recommender.popularity) // 10)].tolist())
    popularity_hits = 0
    shown_count = 0
    active_catalog_indices = {int(value) for value in recommender.active_indices}
    content_ids, content_scores = recommender.content_neighbors
    content_lookup = [
        {int(neighbor): float(score) for neighbor, score in zip(row_ids, row_scores) if neighbor >= 0}
        for row_ids, row_scores in zip(content_ids, content_scores)
    ]
    for user_idx, targets in pairs:
        history_catalog = history_rows.getrow(user_idx).indices
        history_ids = [str(recommender.catalog[int(recommender.active_indices[idx])]["id"]) for idx in history_catalog if idx < len(recommender.active_indices)]
        target_ids = {str(recommender.catalog[int(item)]["id"]) for item in targets if int(item) in active_catalog_indices}
        # Only targets in the common train-support candidate set are scored.
        if not target_ids:
            continue
        recommendations, _ = recommender.recommend(history_ids, n=20, model=model, exclude_game_ids=history_ids)
        ranked = [str(row.game["id"]) for row in recommendations]
        recommended_items.update(ranked[:10])
        local_ranked = [recommender.local_by_catalog[recommender.game_to_catalog[game_id]] for game_id in ranked[:10]]
        local_ranked = [int(index) for index in local_ranked if index >= 0]
        pair_sims = [
            content_lookup[left].get(right, content_lookup[right].get(left, 0.0))
            for i, left in enumerate(local_ranked)
            for right in local_ranked[i + 1 :]
        ]
        if pair_sims:
            per_user_diversities.append(1 - float(np.mean(pair_sims)))
        total_popularity = max(1.0, float(recommender.popularity.sum()))
        for local_idx in local_ranked:
            probability = (float(recommender.popularity[local_idx]) + 1) / (total_popularity + len(recommender.popularity))
            per_user_novelties.append(-float(np.log2(probability)))
            popularity_hits += local_idx in top_popularity
            shown_count += 1
        row: dict[str, Any] = {"user_idx": user_idx, "targets": len(target_ids), "hit_ranks": []}
        ranks: list[int] = []
        for target in target_ids:
            if target in ranked:
                ranks.append(ranked.index(target) + 1)
        row["hit_ranks"] = ranks
        row["history_size"] = int(history_rows.getrow(user_idx).nnz)
        row["recommended_indices"] = local_ranked
        per_user.append(row)
        for cutoff in K_VALUES:
            values = ranking_metrics(ranked, target_ids, cutoff)
            for name, value in values.items():
                metric_rows[cutoff][name].append(value)

    summary: dict[str, Any] = {"n_users": len(per_user), "catalog_coverage_at_10": 0.0}
    n_candidates = max(1, len(recommender.active_indices))
    summary["catalog_coverage_at_10"] = len(recommended_items) / n_candidates
    for cutoff in K_VALUES:
        for name in ("precision", "recall", "ndcg", "map"):
            values = metric_rows[cutoff][name]
            summary[f"{name}@{cutoff}"] = float(np.mean(values)) if values else 0.0
    summary["intra_list_diversity@10"] = float(np.mean(per_user_diversities)) if per_user_diversities else 0.0
    summary["novelty_bits@10"] = float(np.mean(per_user_novelties)) if per_user_novelties else 0.0
    summary["top_decile_popularity_share@10"] = popularity_hits / shown_count if shown_count else 0.0
    return summary, per_user


def diversity_at_10(recommender: GameRecommender, ids: set[str]) -> float:
    local_by_game = recommender.game_to_catalog
    content_ids, content_scores = recommender.content_neighbors
    active_lookup = {int(catalog_idx): local for local, catalog_idx in enumerate(recommender.active_indices)}
    selected = [active_lookup[local_by_game[game_id]] for game_id in ids if game_id in local_by_game and local_by_game[game_id] in active_lookup]
    sims: dict[tuple[int, int], float] = {}
    for row in selected:
        for neighbor, score in zip(content_ids[row], content_scores[row]):
            if neighbor >= 0:
                sims[(row, int(neighbor))] = float(score)
    pair_values = [sims.get((left, right), sims.get((right, left), 0.0)) for i, left in enumerate(selected) for right in selected[i + 1 :]]
    return float(1 - np.mean(pair_values)) if pair_values else 0.0


def novelty_at_10(recommender: GameRecommender, ids: set[str]) -> float:
    total = max(1.0, float(recommender.popularity.sum()))
    lookup = {int(catalog_idx): local for local, catalog_idx in enumerate(recommender.active_indices)}
    values: list[float] = []
    for game_id in ids:
        catalog_idx = recommender.game_to_catalog.get(game_id)
        if catalog_idx in lookup:
            local = lookup[catalog_idx]
            probability = (float(recommender.popularity[local]) + 1) / (total + len(recommender.popularity))
            values.append(-float(np.log2(probability)))
    return float(np.mean(values)) if values else 0.0


def bootstrap_ci(per_user: list[dict[str, Any]], seed: int = SEED, resamples: int = 1000) -> dict[str, float]:
    if not per_user:
        return {"lower_95": 0.0, "upper_95": 0.0}
    scores = np.asarray(
        [1.0 / np.log2(row["hit_ranks"][0] + 1) if row["hit_ranks"] and row["hit_ranks"][0] <= 10 else 0.0 for row in per_user],
        dtype=np.float32,
    )
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(scores), size=(resamples, len(scores)))
    means = scores[indices].mean(axis=1)
    lower, upper = np.quantile(means, [0.025, 0.975])
    return {"lower_95": float(lower), "upper_95": float(upper)}


def main() -> None:
    started = time.perf_counter()
    process = psutil.Process(os.getpid())
    baseline_rss = process.memory_info().rss
    peak_rss = [baseline_rss]
    stop_sampling = threading.Event()

    def sample_rss() -> None:
        while not stop_sampling.wait(0.1):
            peak_rss[0] = max(peak_rss[0], process.memory_info().rss)

    sampler = threading.Thread(target=sample_rss, daemon=True)
    sampler.start()
    interaction_path = PROCESSED_DIR / "interactions.csv.gz"
    if not interaction_path.exists():
        raise FileNotFoundError("Run python -m scripts.prepare_data before training")
    train = pd.read_csv(PROCESSED_DIR / "train.csv.gz", dtype={"user_idx": "int32", "item_idx": "int32", "playtime_mins": "int32"})
    validation = pd.read_csv(PROCESSED_DIR / "validation.csv.gz", dtype={"user_idx": "int32", "item_idx": "int32", "playtime_mins": "int32"})
    test = pd.read_csv(PROCESSED_DIR / "test.csv.gz", dtype={"user_idx": "int32", "item_idx": "int32", "playtime_mins": "int32"})
    catalog = json.loads((PROCESSED_DIR / "catalog.json").read_text(encoding="utf-8"))

    n_users = int(train["user_idx"].max()) + 1
    all_item_count = len(catalog)
    full_support = np.bincount(train["item_idx"].to_numpy(), minlength=all_item_count)
    active = np.flatnonzero(full_support >= MIN_TRAIN_SUPPORT)
    if len(active) > MAX_CANDIDATE_GAMES:
        active = active[np.argsort(-full_support[active], kind="stable")[:MAX_CANDIDATE_GAMES]]
        active.sort()
    local_for_catalog = np.full(all_item_count, -1, dtype=np.int32)
    local_for_catalog[active] = np.arange(len(active), dtype=np.int32)
    train_local = local_for_catalog[train["item_idx"].to_numpy()]
    keep_train = train_local >= 0
    train_rows = train["user_idx"].to_numpy()[keep_train]
    train_cols = train_local[keep_train]
    matrix = csr_matrix((np.ones(len(train_rows), dtype=np.float32), (train_rows, train_cols)), shape=(n_users, len(active)))
    matrix.data[:] = 1
    matrix.sum_duplicates()
    matrix.data[:] = 1
    support = np.asarray(matrix.sum(axis=0)).ravel().astype(np.float32)
    for catalog_idx, count in zip(active, support):
        catalog[int(catalog_idx)]["interaction_count"] = int(count)

    collaborative_cooccurrence = (matrix.T @ matrix).tocsr().astype(np.float32)
    inv_norm = 1 / np.sqrt(np.maximum(support, 1))
    collaborative_similarity = collaborative_cooccurrence.multiply(inv_norm[:, None]).multiply(inv_norm[None, :]).tocsr()
    collaborative_neighbors = top_neighbors(collaborative_similarity, NEIGHBORS)

    content_rows = []
    for catalog_idx in active:
        game = catalog[int(catalog_idx)]
        fields = game.get("genres", []) + game.get("tags", []) + game.get("specs", [])
        content_rows.append(" ".join(str(value) for value in fields))
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=40000, min_df=1)
    features = vectorizer.fit_transform(content_rows)
    content_similarity = (features @ features.T).tocsr().astype(np.float32)
    content_neighbors = top_neighbors(content_similarity, NEIGHBORS)

    payload: dict[str, Any] = {
        "artifact_schema_version": 1,
        "catalog": catalog,
        "active_item_indices": active.astype(np.int32),
        "popularity": support,
        "cf_neighbors": collaborative_neighbors,
        "content_neighbors": content_neighbors,
        "hybrid_weights": {"collaborative": 0.45, "content": 0.40, "popularity": 0.15},
        "metrics": {},
        "info": {},
    }
    recommender = GameRecommender(payload)
    history_rows = matrix

    validation_eval, _ = metrics_for_users(recommender, validation, history_rows, "hybrid", limit_users=2000, seed=SEED)
    best_weights = WEIGHT_GRID[0]
    best_score = -1.0
    validation_rows: list[dict[str, Any]] = []
    for candidate_weights in WEIGHT_GRID:
        recommender.weights = candidate_weights
        result, _ = metrics_for_users(recommender, validation, history_rows, "hybrid", weights=candidate_weights, limit_users=2000, seed=SEED)
        score = result.get("ndcg@10", 0.0)
        validation_rows.append({"weights": candidate_weights, "validation_ndcg@10": score})
        if score > best_score:
            best_score = score
            best_weights = candidate_weights
    recommender.weights = best_weights
    payload["hybrid_weights"] = best_weights

    evaluation: dict[str, Any] = {"validation": {"tuning_users": validation_eval["n_users"], "weight_grid": validation_rows, "selected_weights": best_weights}}
    test_results: dict[str, Any] = {}
    test_users_by_model: dict[str, list[dict[str, Any]]] = {}
    for name in ("popularity", "content", "collaborative", "hybrid"):
        scores, per_user = metrics_for_users(recommender, test, history_rows, name, limit_users=MAX_EVAL_USERS, seed=SEED + 2)
        test_results[name] = scores
        test_users_by_model[name] = per_user
    evaluation["test"] = test_results
    evaluation["test"]["hybrid"]["ndcg@10_user_bootstrap_95ci"] = bootstrap_ci(test_users_by_model["hybrid"])

    hybrid_users = test_users_by_model["hybrid"]
    grouped: dict[str, Any] = {}
    bands = (("1-5 games", 1, 5), ("6-20 games", 6, 20), ("21+ games", 21, 10**9))
    for label, low, high in bands:
        rows = [row for row in hybrid_users if low <= row["history_size"] <= high]
        ndcg = [1 / np.log2(row["hit_ranks"][0] + 1) if row["hit_ranks"] and row["hit_ranks"][0] <= 10 else 0.0 for row in rows]
        grouped[label] = {"users": len(rows), "ndcg@10": float(np.mean(ndcg)) if ndcg else 0.0}
    evaluation["test"]["hybrid"]["history_groups"] = grouped

    rss = process.memory_info().rss
    stop_sampling.set()
    sampler.join(timeout=1)
    peak_rss[0] = max(peak_rss[0], rss)
    elapsed = time.perf_counter() - started
    source_report = json.loads((PROCESSED_DIR / "data_quality_report.json").read_text(encoding="utf-8"))
    source_user_count = int(source_report["counts"]["users"])
    payload["metrics"] = evaluation
    payload["info"] = {
        "model_version": "gamematch-v1",
        "built_at_utc": datetime.now(UTC).isoformat(),
        "dataset": "UCSD/McAuley Australian Steam sample, processed from downloaded source files",
        "n_users": source_user_count,
        "user_matrix_rows": n_users,
        "n_games": len(catalog),
        "n_train_interactions": int(matrix.nnz),
        "n_validation_users": int(validation_eval["n_users"]),
        "n_test_users": int(test_results["hybrid"]["n_users"]),
        "candidate_games": len(active),
        "min_training_support": MIN_TRAIN_SUPPORT,
        "training_seconds_including_evaluation": round(elapsed, 3),
        "process_rss_before_bytes": baseline_rss,
        "process_rss_after_bytes": rss,
        "process_peak_rss_bytes": peak_rss[0],
        "limitations": [
            "Historical Australian sample; it is not representative of current Steam users.",
            "The user-items snapshot has no reliable interaction timestamps; evaluation uses random per-user holdouts.",
            "Zero-playtime ownership and unobserved games are not treated as dislikes.",
            "Offline ranking metrics are not evidence of satisfaction, engagement, purchases, or retention.",
            "The dataset page requests citation but does not state a formal reuse license; raw and per-user data are excluded from Git.",
        ],
        "data_quality_counts": source_report["counts"],
    }

    output_dir = ARTIFACT_DIR.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary_artifact = ARTIFACT_DIR.with_suffix(ARTIFACT_DIR.suffix + ".tmp")
    joblib.dump(payload, temporary_artifact, compress=3)
    temporary_artifact.replace(ARTIFACT_DIR)
    experiment_dir = Path(__file__).resolve().parents[1] / "reports" / "gamematch-v1"
    experiment_dir.mkdir(parents=True, exist_ok=True)
    results = {
        "experiment": "gamematch-v1",
        "seed": SEED,
        "configuration": {
            "positive_definition": source_report["positive_definition"],
            "split_strategy": source_report["split_strategy"],
            "min_train_support": MIN_TRAIN_SUPPORT,
            "max_candidate_games": MAX_CANDIDATE_GAMES,
            "neighbors_per_item": NEIGHBORS,
            "evaluation_user_cap": MAX_EVAL_USERS,
            "k_values": K_VALUES,
            "hybrid_weight_selection": "validation NDCG@10",
            "selected_hybrid_weights": best_weights,
        },
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
        "runtime_and_memory": payload["info"],
        "metrics": evaluation,
    }
    (experiment_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_report(experiment_dir, results)
    write_plot(experiment_dir, test_results)
    print(json.dumps({"artifact": str(ARTIFACT_DIR), "results": str(experiment_dir), "info": payload["info"], "test_metrics": test_results}, indent=2))


def write_report(directory: Path, results: dict[str, Any]) -> None:
    test = results["metrics"]["test"]
    config = results["configuration"]
    lines = [
        "# GameMatch offline model evaluation",
        "",
        f"Generated at: {results['runtime_and_memory']['built_at_utc']}",
        "",
        "## Protocol",
        "",
        f"- Positive: {config['positive_definition']}.",
        f"- Split: {config['split_strategy']}.",
        f"- Candidates: {config['min_train_support']} or more training positives, capped at {config['max_candidate_games']} most-supported games.",
        f"- Validation selected hybrid weights by NDCG@10: `{json.dumps(config['selected_hybrid_weights'])}`.",
        f"- Final test users scored: {results['runtime_and_memory']['n_test_users']:,}; candidate games: {results['runtime_and_memory']['candidate_games']:,}.",
        "- One random held-out item per user is the relevance target. Unobserved games are unknown, not negatives.",
        "- The final test set did not choose model weights. A bootstrap interval varies users within this one split; it does not measure split-to-split or time-period uncertainty.",
        "",
        "## Final test results",
        "",
        "| Model | Precision@5 | Recall@10 | NDCG@10 | MAP@10 | Coverage@10 | Diversity@10 | Novelty (bits) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in ("popularity", "content", "collaborative", "hybrid"):
        metric = test[model]
        lines.append(
            f"| {model} | {metric.get('precision@5', 0):.4f} | {metric.get('recall@10', 0):.4f} | {metric.get('ndcg@10', 0):.4f} | {metric.get('map@10', 0):.4f} | {metric.get('catalog_coverage_at_10', 0):.3f} | {metric.get('intra_list_diversity@10', 0):.3f} | {metric.get('novelty_bits@10', 0):.2f} |"
        )
    ci = test["hybrid"].get("ndcg@10_user_bootstrap_95ci", {})
    lines += [
        "",
        f"Hybrid NDCG@10 user bootstrap 95% interval: {ci.get('lower_95', 0):.4f}–{ci.get('upper_95', 0):.4f}.",
        "",
        "## Test users by training history",
        "",
        "| History size | Users | Hybrid NDCG@10 |",
        "|---|---:|---:|",
    ]
    for label, stats in test["hybrid"].get("history_groups", {}).items():
        lines.append(f"| {label} | {stats['users']:,} | {stats['ndcg@10']:.4f} |")
    lines += [
        "",
        "## Runtime and limitations",
        "",
        f"- Training plus evaluation wall time: {results['runtime_and_memory']['training_seconds_including_evaluation']:.1f} seconds on this machine.",
        f"- Resident set size before/after/observed peak: {results['runtime_and_memory']['process_rss_before_bytes'] / (1024**2):.1f} / {results['runtime_and_memory']['process_rss_after_bytes'] / (1024**2):.1f} / {results['runtime_and_memory']['process_peak_rss_bytes'] / (1024**2):.1f} MiB; peak sampling interval was 100 ms.",
        "- This historical Australian Steam sample is sparse and selected; ranking results do not establish real user satisfaction, purchases, or business outcomes.",
        "- There are no trustworthy timestamps in the library snapshot, so this is a user-aware random holdout, not a future-time evaluation.",
        "- Popularity and collaborative signals reproduce historical exposure patterns. Content metadata is incomplete.",
        "- No formal reuse license is stated on the dataset page. Raw files, per-user rows, and trained artifacts are excluded from the public source repository by default.",
        "",
        "See `results.json` for full metrics, configuration, environment, and source quality counts. `metrics.html` contains the interactive comparison chart.",
    ]
    report = "\n".join(lines) + "\n"
    (directory / "model_evaluation_report.md").write_text(report, encoding="utf-8")
    (Path(__file__).resolve().parents[1] / "model_evaluation_report.md").write_text(report, encoding="utf-8")


def write_plot(directory: Path, test: dict[str, Any]) -> None:
    models = ("popularity", "content", "collaborative", "hybrid")
    fig = go.Figure()
    for metric_name, label in (("precision@5", "Precision@5"), ("recall@10", "Recall@10"), ("ndcg@10", "NDCG@10"), ("map@10", "MAP@10")):
        fig.add_trace(go.Bar(name=label, x=list(models), y=[test[m].get(metric_name, 0.0) for m in models]))
    fig.update_layout(title="GameMatch ranked recommendation metrics", barmode="group", yaxis_title="Metric value", template="plotly_dark")
    fig.write_html(directory / "metrics.html", include_plotlyjs="cdn")


if __name__ == "__main__":
    main()
