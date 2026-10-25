# API reference

Interactive schema: `/docs`; OpenAPI JSON: `/openapi.json`.

| Method | Endpoint | Behavior |
|---|---|---|
| `GET` | `/health` | Process liveness |
| `GET` | `/ready` | Model and database readiness |
| `GET` | `/v1/model/info` | Model version, actual offline results, data counts, limitations, and hybrid weights |
| `GET` | `/v1/games?search=&genre=&limit=25&offset=0` | Search/paginate catalog, limit 100 |
| `GET` | `/v1/games/{game_id}` | Catalog details |
| `GET` | `/v1/games/{game_id}/similar?model=content&n=10` | Content or co-play neighbors |
| `GET` | `/v1/users/{user_id}/recommendations?n=10&genre=` | Recommendations using stored profile picks |
| `PUT` | `/v1/users/{user_id}/interactions` | Upsert 1–100 explicitly supplied positive game IDs |
| `POST` | `/v1/recommendations` | Rank a supplied history, optional profile, genre filter, exclusions, and `n` 1–50 |
| `POST` | `/v1/feedback` | Record `useful`, `not_relevant`, or `already_played` |
| `GET` | `/v1/metrics/summary` | Actual last-24-hour API counts/latency/errors/feedback plus offline test summary |

Recommendation request:

```json
{
  "user_id": "my-demo-profile",
  "positive_game_ids": ["620", "400"],
  "exclude_game_ids": ["10"],
  "genre": "Puzzle",
  "n": 10
}
```

The response includes `model_version`, `fallback_mode`, ranked `game_id`/title, a rank score, and explanation. Scores are not probabilities. Unknown supplied IDs are ignored as history; explicit profile updates reject unknown games. Existing profile history and request history are combined, and already-seen IDs are always excluded. User IDs are never returned and are HMAC-hashed before persistence. Request logs store route templates, status, duration, and generated request IDs, not request bodies or path identifiers.

Inputs are size-limited: request body 1 MB, IDs at most 128 characters, history/exclusion lists at most 100, recommendation count at most 50, catalog page size at most 100, and an in-process cap of 120 API requests per minute per peer IP. This in-memory limiter is per process and is not a distributed abuse-control service. Callers should use a 15-second timeout; only CPU-bounded inference occurs in request handlers.
