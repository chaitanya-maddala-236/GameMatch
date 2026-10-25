# Architecture

```text
UCSD gzip files
  └─ streaming parser / schema checks / duplicate and missing-value report
       ├─ catalog.json (game metadata, metadata source recorded)
       ├─ pseudonymous interactions.csv.gz
       └─ train / validation / test CSVs (user-aware random holdout)
            └─ training runner
                 ├─ smoothed interaction-count popularity baseline
                 ├─ TF-IDF genre/tag/spec content neighbors
                 ├─ binary user-item item-item cosine neighbors
                 ├─ hybrid with weights chosen on validation only
                 └─ joblib versioned inference artifact + aggregate report

FastAPI ── SQLAlchemy ── SQLite (local) / Neon PostgreSQL (hosted)
  ├─ recommendations, catalog, similar games
  ├─ profile picks stored under HMAC user keys
  ├─ feedback, request count/errors/latency
  └─ readiness and model/evaluation metadata
       └─ Streamlit + Plotly reads the API
```

Model fitting is an offline command (`python -m scripts.train`), never an API request. `python -m gamematch.bootstrap` is an explicit startup task for first deploy; it downloads and fits only when the versioned artifact is absent. Replace an artifact by training into a new versioned directory, reviewing the held-out report, then pointing `GAMEMATCH_MODEL_PATH` at it. Roll back by restoring the previous path or deployment revision. Keep model/data files on a persistent disk or object store if the host uses ephemeral containers.
