# GameMatch dataset card

## Source and collection

- Source: [UCSD/McAuley Recommender Systems Datasets, Steam Video Game and Bundle Data](https://cseweb.ucsd.edu/~jmcauley/datasets.html#steam_data).
- Download directory: [UCSD-hosted Steam files](https://mcauleylab.ucsd.edu/public_datasets/data/steam/).
- Downloaded: 2026-10-25 UTC (2026-10-26 local time). Exact compressed sizes and SHA-256 checksums are listed below; raw data are excluded from this Git repository.
- Citation requested by the source page: Wang-Cheng Kang and Julian McAuley, “Self-Attentive Sequential Recommendation,” IEEE International Conference on Data Mining (ICDM), 2018; Mengting Wan and Julian McAuley, “Item Recommendation on Monotonic Behavior Chains,” ACM RecSys, 2018. The source page also lists the Steam bundle paper by Apurva Pathak, Kshitiz Gupta, and Julian McAuley, SIGIR 2017.
- License/terms: the dataset page requests citation but does not state an explicit license for these files. GameMatch does not commit raw files or user-level processed rows. Confirm the source's current terms before redistribution or broader commercial use; no such license is claimed here.

## Selected files and inspected schemas

| File | Compressed size | SHA-256 | Fields inspected | Role |
|---|---:|---|---|---|
| `australian_users_items.json.gz` | 74,035,391 bytes | `0b329f79ddf450aba0aad923c8cb6d1affac0c98efaf70242d22fd10987a8d99` | Top-level `user_id`, `items_count`, `steam_id`, `user_url`, `items`; nested `item_id`, `item_name`, `playtime_forever`, `playtime_2weeks` | Main game-library/playtime interactions |
| `australian_user_reviews.json.gz` | 6,935,922 bytes | `a934bf74d8579bb25bc7bf24e652a87e2ccc91064e429a4cb4af5809178687a8` | Top-level `user_id`, `user_url`, `reviews`; nested `funny`, `posted`, `last_edited`, `item_id`, `helpful`, `recommend`, `review` | Explicit negative recommendation exclusion; review text is not modeled |
| `steam_games.json.gz` | 2,664,464 bytes | `20aaed0cbbb35a8a7e481b6941c18ad515c5808b5cf32767c163bcb36e3c7e0a` | Observed `id`, `title`, `app_name`, `genres`, `tags`, `specs`, `release_date`, `price`, `developer`, `publisher`, `url`; nulls and missing values occur | Game catalog and content features |

The source directory lists the Australian files as Version 1 samples. The metadata file is a separate Steam game information file; it is joined on Steam app ID, so metadata may not cover every library game or be contemporaneous with every interaction. The parser uses `ast.literal_eval` for the source's line-delimited Python-dictionary serialization; it never evaluates arbitrary code.

## Data processing and target

- One row in the normalized implicit matrix represents a user-game pair with `playtime_forever > 0` minutes.
- If a matching review explicitly has `recommend == False`, that pair is excluded from positive interactions. Positive reviews are not required for a played game.
- `playtime_2weeks` is retained in the documented source schema but not used because it is sparse and has no reliable event sequence for this ranking task.
- Zero-playtime ownership, missing pairs, and unobserved games are not dislikes.
- Duplicate user-game rows are counted and normalized to the maximum lifetime playtime. Original Steam IDs and URLs are not written to processed files; `user_idx` is a local integer mapping assigned in memory.
- Games absent from metadata retain the library `item_name` as a title fallback and have empty genre/tag/spec lists.
- Candidate games have at least five training positives, with a maximum of 6,000 candidates for bounded item-item computation.

## Processed data quality counts

The download produced 88,310 library records and 5,153,209 ownership rows. Processing retained 3,280,258 positive rows before duplicate normalization, excluded 4,988 explicit negative review pairs, and counted 1,867,963 zero-playtime ownerships. After keeping the maximum playtime for duplicate user-game pairs, the matrix contains 3,241,440 unique positives across 68,401 users and 10,046 games. The catalog contains 33,918 IDs, including 1,786 games without a matching metadata row. Of these pairs, 7,582 games meet the minimum training-support threshold before the model's 6,000-candidate cap.

## Split and evaluation

The user-items snapshot contains no reliable event timestamp. For users with at least three positive games, one game is held out for validation, one for final test, and the rest for training, with deterministic seed 2026. Users with two positive games contribute one train and one test item; users with one remain in training only. Test targets outside the train-support candidate set are omitted. Hybrid weights are selected by validation NDCG@10; the final test set is not used for tuning.

This user-aware random split prevents each evaluated user's held-out game from appearing in its own training history, but does not simulate time-forward deployment. Missing interactions remain unknown, not negative. Uncertainty intervals bootstrap users within the single held-out split; they do not measure split-to-split or period variation.

## Intended and prohibited claims

The data supports a retrospective ranking demo for games in the observed historical sample. It does not establish a person's current tastes, player satisfaction, purchases, retention, or business lift. The sample is regional, historical, and selected; use population-level and contemporary claims only with new validated evidence.
