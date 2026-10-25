from __future__ import annotations

import gzip

import pytest

from scripts.prepare_data import clean_list, positive_int, read_explicit_dislikes, records


def test_value_normalization():
    assert positive_int("12.9") == 12
    assert positive_int(-4) == 0
    assert positive_int("not a number") == 0
    assert clean_list(["Action", "", None, "Action", "Puzzle"]) == ["Action", "Puzzle"]


def test_source_dictionary_lines_are_parsed_safely(tmp_path):
    file_path = tmp_path / "sample.json.gz"
    with gzip.open(file_path, "wt", encoding="utf-8") as stream:
        stream.write("{'id': '123', 'genres': ['Puzzle']}\n")
    assert list(records(file_path)) == [{"id": "123", "genres": ["Puzzle"]}]


def test_explicit_negative_reviews_are_identified_by_user_game_pair(tmp_path):
    file_path = tmp_path / "reviews.json.gz"
    with gzip.open(file_path, "wt", encoding="utf-8") as stream:
        stream.write("{'user_id': 'u1', 'reviews': [{'item_id': '10', 'recommend': False}, {'item_id': '20', 'recommend': True}]}\n")
    assert read_explicit_dislikes(file_path) == {("u1", "10")}


def test_malformed_dictionary_record_has_file_and_line(tmp_path):
    file_path = tmp_path / "bad.json.gz"
    with gzip.open(file_path, "wt", encoding="utf-8") as stream:
        stream.write("not a dictionary\n")
    with pytest.raises(ValueError, match="bad.json.gz line 1"):
        list(records(file_path))
