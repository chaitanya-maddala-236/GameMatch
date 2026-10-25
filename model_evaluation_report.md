# GameMatch offline model evaluation

Generated at: 2026-10-25T19:46:33.625844+00:00

## Protocol

- Positive: playtime_forever > 0 minutes, except an explicit recommend=False review for the same pair.
- Split: deterministic per-user random holdout; no source timestamps in user-items snapshot.
- Candidates: 5 or more training positives, capped at 6000 most-supported games.
- Validation selected hybrid weights by NDCG@10: `{"collaborative": 0.7, "content": 0.2, "popularity": 0.1}`.
- Final test users scored: 4,987; candidate games: 6,000.
- One random held-out item per user is the relevance target. Unobserved games are unknown, not negatives.
- The final test set did not choose model weights. A bootstrap interval varies users within this one split; it does not measure split-to-split or time-period uncertainty.

## Final test results

| Model | Precision@5 | Recall@10 | NDCG@10 | MAP@10 | Coverage@10 | Diversity@10 | Novelty (bits) |
|---|---:|---:|---:|---:|---:|---:|---:|
| popularity | 0.0265 | 0.1841 | 0.1106 | 0.0880 | 0.010 | 0.939 | 7.27 |
| content | 0.0036 | 0.0329 | 0.0164 | 0.0115 | 0.277 | 0.700 | 12.67 |
| collaborative | 0.0328 | 0.2208 | 0.1360 | 0.1100 | 0.086 | 0.954 | 7.56 |
| hybrid | 0.0340 | 0.2268 | 0.1389 | 0.1119 | 0.084 | 0.938 | 7.58 |

Hybrid NDCG@10 user bootstrap 95% interval: 0.1310–0.1469.

## Test users by training history

| History size | Users | Hybrid NDCG@10 |
|---|---:|---:|
| 1-5 games | 777 | 0.1598 |
| 6-20 games | 1,181 | 0.1787 |
| 21+ games | 3,029 | 0.1180 |

## Runtime and limitations

- Training plus evaluation wall time: 570.0 seconds on this machine.
- Resident set size before/after/observed peak: 139.4 / 229.6 / 1412.9 MiB; peak sampling interval was 100 ms.
- This historical Australian Steam sample is sparse and selected; ranking results do not establish real user satisfaction, purchases, or business outcomes.
- There are no trustworthy timestamps in the library snapshot, so this is a user-aware random holdout, not a future-time evaluation.
- Popularity and collaborative signals reproduce historical exposure patterns. Content metadata is incomplete.
- No formal reuse license is stated on the dataset page. Raw files, per-user rows, and trained artifacts are excluded from the public source repository by default.

See `results.json` for full metrics, configuration, environment, and source quality counts. `metrics.html` contains the interactive comparison chart.
