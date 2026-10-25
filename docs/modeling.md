# Modeling and experiment protocol

## Signals

The user-items library has 5.15 million source rows, including many owned games with zero recorded playtime. A positive implicit signal is `playtime_forever > 0` minutes unless a matching review explicitly recommends against the game. The model binarizes each remaining user-game pair; extreme playtime cannot dominate the score. This treats activity as preference evidence, not proof of enjoyment. Unobserved pairs are unknown.

## Models

- **Popularity:** training positive count, smoothed with `log(1 + count)` for recommendation score.
- **Content:** TF-IDF over verified genres, tags, and specifications. Recommendations aggregate cosine neighbors of supplied/known positive games. Missing metadata has no fabricated attributes.
- **Collaborative:** binary user-item matrix, cosine item-item co-occurrence, and up to 100 neighbors per item. It requires overlap and does not solve true cold-start.
- **Hybrid:** normalized sum of collaborative, content, and popularity scores. A seven-point weight grid is selected using validation NDCG@10. The independent final test split is used only once for the report.

## Metrics

Each user has held-out relevant games and a shared candidate pool of apps with at least five training interactions, up to 6,000 most-supported games. Training history and all explicit exclusions are removed from recommendations.

- Precision@K: relevant recommendations in first K divided by K.
- Recall@K: relevant recommendations in first K divided by held-out relevant games for that user.
- NDCG@K: discounted gain with log2 rank discount, normalized by the user's ideal ranking.
- MAP@K: mean precision at each relevant hit, normalized by the number of relevant test items up to K.
- Catalog coverage@10: fraction of candidate apps shown at least once across evaluated users.
- Intra-list diversity@10: mean pairwise `1 - content cosine similarity` among one user's top-10 list.
- Novelty@10: mean `-log2((train count + 1)/(total train interactions + candidate count))`, in bits.
- Top-decile popularity share@10: fraction of shown games from the most popular 10% of candidates.

The report includes user-bootstrap 95% bounds for hybrid NDCG@10, split sample sizes, performance by train-history length, training wall time, and observed process peak RSS. A bootstrap over users within one split does not capture split/time variation. The single dataset snapshot cannot support a temporal drift analysis.
