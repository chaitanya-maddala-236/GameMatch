from __future__ import annotations

import math
from collections.abc import Sequence


def ranking_metrics(ranked: Sequence[str], relevant: set[str], k: int) -> dict[str, float]:
    """Compute hand-checkable top-k metrics; unknown items are absent from relevant."""
    if k < 1:
        raise ValueError("k must be at least 1")
    positions = {item: rank for rank, item in enumerate(ranked[:k], start=1)}
    hits = sorted(positions[item] for item in relevant if item in positions)
    ideal_count = min(len(relevant), k)
    dcg = sum(1.0 / math.log2(rank + 1) for rank in hits)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    average_precision = sum((index + 1) / rank for index, rank in enumerate(hits)) / ideal_count if ideal_count else 0.0
    return {
        "precision": len(hits) / k,
        "recall": len(hits) / len(relevant) if relevant else 0.0,
        "ndcg": dcg / ideal if ideal else 0.0,
        "map": average_precision,
    }
