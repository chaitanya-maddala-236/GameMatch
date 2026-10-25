from __future__ import annotations

import pytest

from gamematch.evaluation import ranking_metrics


def test_ranking_metrics_for_one_relevant_item():
    result = ranking_metrics(["x", "target", "z"], {"target"}, 3)
    assert result["precision"] == pytest.approx(1 / 3)
    assert result["recall"] == 1
    assert result["ndcg"] == pytest.approx(1 / 1.5849625007)
    assert result["map"] == pytest.approx(0.5)


def test_ranking_metrics_multiple_hits_and_empty_relevance():
    result = ranking_metrics(["a", "b", "c"], {"a", "c"}, 3)
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == 1
    assert result["map"] == pytest.approx((1 + 2 / 3) / 2)
    assert ranking_metrics(["a", "b"], set(), 2)["ndcg"] == 0


def test_ranking_metrics_requires_positive_cutoff():
    with pytest.raises(ValueError, match="at least 1"):
        ranking_metrics(["a"], {"a"}, 0)
