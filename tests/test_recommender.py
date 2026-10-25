from __future__ import annotations

from gamematch.recommendation import GameRecommender


def test_popularity_fallback_and_seen_game_exclusion(toy_payload):
    recommender = GameRecommender(toy_payload)
    rows, mode = recommender.recommend(n=3, exclude_game_ids=["10"])
    assert mode == "popularity_fallback"
    assert rows[0].game["id"] == "20"
    assert all(row.game["id"] != "10" for row in rows)
    assert "Popular among games" in rows[0].explanation


def test_personalized_recommendations_exclude_history_and_explain_content(toy_payload):
    recommender = GameRecommender(toy_payload)
    rows, mode = recommender.recommend(["10"], n=3)
    assert mode == "personalized"
    assert all(row.game["id"] != "10" for row in rows)
    portal = next(row for row in rows if row.game["id"] == "20")
    assert "Shares the genre" in portal.explanation


def test_game_similarity_excludes_query_game(toy_payload):
    recommender = GameRecommender(toy_payload)
    rows = recommender.similar("10", n=2)
    assert [row.game["id"] for row in rows] == ["20", "30"]
    assert all(row.score > 0 for row in rows)


def test_unknown_history_falls_back_and_genre_filter_works(toy_payload):
    recommender = GameRecommender(toy_payload)
    rows, mode = recommender.recommend(["unknown"], n=5, genre="RPG")
    assert mode == "popularity_fallback"
    assert rows
    assert all("RPG" in row.game["genres"] for row in rows)
