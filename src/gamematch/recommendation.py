from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np


@dataclass
class Recommendation:
    game: dict[str, Any]
    score: float
    model: str
    explanation: str


class GameRecommender:
    """Inference-only recommender over a versioned, item-based artifact."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.catalog = payload["catalog"]
        self.games_by_id = {str(game["id"]): game for game in self.catalog}
        self.active_indices = np.asarray(payload["active_item_indices"], dtype=np.int32)
        self.local_by_catalog = np.full(len(self.catalog), -1, dtype=np.int32)
        self.local_by_catalog[self.active_indices] = np.arange(len(self.active_indices), dtype=np.int32)
        self.game_to_catalog = {str(game["id"]): int(game["item_idx"]) for game in self.catalog}
        self.popularity = np.asarray(payload["popularity"], dtype=np.float32)
        self.cf_neighbors = payload["cf_neighbors"]
        self.content_neighbors = payload["content_neighbors"]
        self.weights = payload.get("hybrid_weights", {"collaborative": 0.45, "content": 0.4, "popularity": 0.15})
        self.metrics = payload.get("metrics", {})
        self.info = payload.get("info", {})

    @classmethod
    def load(cls, path: str) -> GameRecommender:
        return cls(joblib.load(path))

    def _history_indices(self, game_ids: list[str]) -> list[int]:
        local: list[int] = []
        for game_id in game_ids:
            catalog_idx = self.game_to_catalog.get(str(game_id))
            if catalog_idx is None:
                continue
            item_idx = int(self.local_by_catalog[catalog_idx])
            if item_idx >= 0:
                local.append(item_idx)
        return list(dict.fromkeys(local))

    @staticmethod
    def _normalized(values: np.ndarray) -> np.ndarray:
        maximum = float(values.max(initial=0.0))
        return values / maximum if maximum > 0 else values

    def _neighbor_scores(self, history: list[int], source: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
        neighbor_ids, neighbor_scores = source
        output = np.zeros(len(self.active_indices), dtype=np.float32)
        for item_idx in history:
            ids = neighbor_ids[item_idx]
            scores = neighbor_scores[item_idx]
            valid = (ids >= 0) & (scores > 0)
            output[ids[valid]] += scores[valid]
        return self._normalized(output)

    def _scores(self, history: list[int], model: str) -> np.ndarray:
        popular = self._normalized(np.log1p(self.popularity))
        collaborative = self._neighbor_scores(history, self.cf_neighbors)
        content = self._neighbor_scores(history, self.content_neighbors)
        if model == "popularity":
            return popular
        if model == "content":
            return content if history and content.any() else popular
        if model == "collaborative":
            return collaborative if history and collaborative.any() else popular
        if model != "hybrid":
            raise ValueError(f"Unsupported model '{model}'")
        if not history or not (content.any() or collaborative.any()):
            return popular
        return (
            self.weights["collaborative"] * collaborative
            + self.weights["content"] * content
            + self.weights["popularity"] * popular
        )

    def _shared_attribute(self, seed: dict[str, Any], candidate: dict[str, Any]) -> str | None:
        for field, label in (("genres", "genre"), ("tags", "tag")):
            common = sorted(set(seed.get(field, [])) & set(candidate.get(field, [])))
            if common:
                return f"Shares the {label} “{common[0]}” with {seed['title']}."
        return None

    def recommend(
        self,
        positive_game_ids: list[str] | None = None,
        *,
        n: int = 10,
        exclude_game_ids: list[str] | None = None,
        genre: str | None = None,
        model: str = "hybrid",
    ) -> tuple[list[Recommendation], str]:
        positive_game_ids = positive_game_ids or []
        exclude_game_ids = exclude_game_ids or []
        history = self._history_indices(positive_game_ids)
        scores = self._scores(history, model)
        excluded_catalog = {
            self.game_to_catalog[game_id]
            for game_id in set(positive_game_ids) | set(exclude_game_ids)
            if game_id in self.game_to_catalog
        }
        valid = np.ones(len(self.active_indices), dtype=bool)
        if excluded_catalog:
            valid[np.isin(self.active_indices, list(excluded_catalog))] = False
        if genre:
            needle = genre.casefold()
            valid &= np.asarray(
                [needle in {value.casefold() for value in self.catalog[index].get("genres", [])} for index in self.active_indices]
            )
        candidates = np.flatnonzero(valid)
        if not len(candidates):
            return [], "no_candidates"
        take = min(max(1, n), len(candidates))
        chosen = candidates[np.argpartition(scores[candidates], -take)[-take:]]
        chosen = chosen[np.lexsort((chosen, -scores[chosen]))]
        fallback = not history or not (self._scores(history, "content").any() or self._scores(history, "collaborative").any())
        mode = "popularity_fallback" if fallback else "personalized"
        results: list[Recommendation] = []
        for local_idx in chosen:
            game = self.catalog[int(self.active_indices[local_idx])]
            explanation = self._explanation(int(local_idx), history, model, fallback)
            results.append(Recommendation(game=game, score=float(scores[local_idx]), model=model, explanation=explanation))
        return results, mode

    def _explanation(self, item_idx: int, history: list[int], model: str, fallback: bool) -> str:
        if fallback:
            return "Popular among games in the evaluated Steam sample; no usable game history was supplied."
        recommended = self.catalog[int(self.active_indices[item_idx])]
        if model in {"content", "hybrid"}:
            ids, similarities = self.content_neighbors
            best: tuple[float, int] | None = None
            for seed_idx in history:
                matches = np.flatnonzero(ids[seed_idx] == item_idx)
                if len(matches):
                    similarity = float(similarities[seed_idx, matches[0]])
                    if best is None or similarity > best[0]:
                        best = (similarity, seed_idx)
            if best is not None:
                seed = self.catalog[int(self.active_indices[best[1]])]
                explanation = self._shared_attribute(seed, recommended)
                if explanation:
                    return explanation
                return f"Similar game metadata to {seed['title']} (content similarity {best[0]:.2f})."
        if model in {"collaborative", "hybrid"}:
            ids, similarities = self.cf_neighbors
            for seed_idx in history:
                if np.any(ids[seed_idx] == item_idx):
                    seed = self.catalog[int(self.active_indices[seed_idx])]
                    return f"Players with overlapping histories that include {seed['title']} also played this game."
        return "Ranked by the available game-history, content, and popularity signals."

    def similar(self, game_id: str, n: int = 10, model: str = "content") -> list[Recommendation]:
        catalog_idx = self.game_to_catalog.get(str(game_id))
        if catalog_idx is None:
            return []
        local_idx = int(self.local_by_catalog[catalog_idx])
        if local_idx < 0:
            return []
        neighbors = self.content_neighbors if model == "content" else self.cf_neighbors
        ids, values = neighbors
        order = np.argsort(-values[local_idx], kind="stable")
        results: list[Recommendation] = []
        for neighbor_idx in order:
            candidate = int(ids[local_idx, neighbor_idx])
            similarity = float(values[local_idx, neighbor_idx])
            if candidate < 0 or candidate == local_idx or similarity <= 0:
                continue
            game = self.catalog[int(self.active_indices[candidate])]
            seed = self.catalog[int(catalog_idx)]
            explanation = self._shared_attribute(seed, game) or f"{model.title()} similarity score {similarity:.2f} to {seed['title']}."
            results.append(Recommendation(game=game, score=similarity, model=f"{model}_similarity", explanation=explanation))
            if len(results) >= n:
                break
        return results

    def game(self, game_id: str) -> dict[str, Any] | None:
        return self.games_by_id.get(str(game_id))

    def model_info(self) -> dict[str, Any]:
        return {
            "model_version": self.info.get("model_version", "gamematch-v1"),
            "built_at_utc": self.info.get("built_at_utc"),
            "dataset": self.info.get("dataset"),
            "n_users": self.info.get("n_users"),
            "n_games": self.info.get("n_games"),
            "n_train_interactions": self.info.get("n_train_interactions"),
            "candidate_games": len(self.active_indices),
            "hybrid_weights": self.weights,
            "offline_test_metrics": self.metrics.get("test", {}),
            "limitations": self.info.get("limitations", []),
        }
