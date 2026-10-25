from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def toy_payload():
    games = [
        {"id": "10", "item_idx": 0, "title": "Portal 2", "genres": ["Action", "Adventure"], "tags": ["Puzzle", "First-Person"], "specs": ["Single-player"]},
        {"id": "20", "item_idx": 1, "title": "Portal", "genres": ["Action", "Adventure"], "tags": ["Puzzle", "First-Person"], "specs": ["Single-player"]},
        {"id": "30", "item_idx": 2, "title": "Left 4 Dead", "genres": ["Action"], "tags": ["Co-op", "FPS"], "specs": ["Co-op"]},
        {"id": "40", "item_idx": 3, "title": "Stardew Valley", "genres": ["Indie", "RPG"], "tags": ["Farming Sim"], "specs": ["Single-player"]},
    ]
    neighbors = np.array([[1, 2], [0, 2], [0, 1], [0, 1]], dtype=np.int32)
    scores = np.array([[0.9, 0.3], [0.9, 0.2], [0.3, 0.2], [0.1, 0.05]], dtype=np.float32)
    cf_scores = np.array([[0.8, 0.25], [0.8, 0.2], [0.25, 0.2], [0.1, 0.03]], dtype=np.float32)
    return {
        "artifact_schema_version": 1,
        "catalog": games,
        "active_item_indices": np.arange(4, dtype=np.int32),
        "popularity": np.array([100, 80, 60, 50], dtype=np.float32),
        "cf_neighbors": (neighbors.copy(), cf_scores),
        "content_neighbors": (neighbors.copy(), scores),
        "hybrid_weights": {"collaborative": 0.45, "content": 0.4, "popularity": 0.15},
        "metrics": {"test": {"popularity": {"ndcg@10": 0.1}, "hybrid": {"ndcg@10": 0.2}}},
        "info": {"model_version": "gamematch-test-v1", "built_at_utc": "2026-10-26T00:00:00+00:00", "dataset": "test fixture", "n_users": 1, "n_games": 4, "n_train_interactions": 3, "limitations": []},
    }
