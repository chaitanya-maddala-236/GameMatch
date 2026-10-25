# GameMatch project plan

## Objective

Build an explainable top-N Steam game recommender, measure it against non-personalized and individual model baselines, serve it through FastAPI, and provide a responsive Streamlit dashboard with actual offline and operational metrics.

## Initial inspection (2026-10-26)

- The workspace contains an unrelated, uncommitted `PlayerPulse` telemetry project. It is being left untouched; GameMatch has its own repository.
- Python 3.13.1 and Git are available. Docker Desktop is installed but its Linux engine is not running.
- GitHub is signed in through the browser, but no `gh` CLI, GitHub remote, or deployment credentials were found in the workspace.
- D: has about 215 GB free. The UCSD Steam files are downloaded to `D:\GameMatch-data\raw` (outside Git).
- The selected source has line-delimited Python-dictionary records. Verified source fields are documented in `docs/data-card.md`.

## Dataset and task

Use the UCSD/McAuley Version 1 Steam Australian users/items sample for game interactions, the matching Steam game metadata file for titles/genres/tags/specifications, and the matching review file to identify explicit negative recommendations. Define an implicit positive as `playtime_forever > 0` unless the same user explicitly reviewed that game with `recommend == False`. Zero-playtime ownership and unobserved pairs are not treated as dislikes. The Australian sample is old and is not representative of current Steam users.

The user-items snapshot has no event timestamps. Use deterministic per-user random holdouts: training history, one validation interaction, and one final-test interaction for users with at least three positives. Other sparse users remain in training and are excluded from ranking evaluation. Candidate games must have at least five training positives. Tune hybrid weights on validation only.

## Architecture

`UCSD source → streaming validation / pseudonymous interaction export → chronological-unavailable, user-aware split → popularity + content + item-item CF + validation-tuned hybrid → versioned artifact → FastAPI + SQLite/PostgreSQL metrics and feedback → Streamlit dashboard`

## Delivery phases

1. Inspect environment and verify dataset. *(Complete.)*
2. Implement reproducible acquisition, schema checks, processing, split, models, and evaluation report. *(Complete; reports and model artifacts generated locally.)*
3. Implement recommendation API, persistence, metrics, feedback, and safe inputs. *(Complete; local Compose smoke checked.)*
4. Implement API-backed discovery/evaluation/monitoring dashboard. *(Complete; opened against local API.)*
5. Add tests, Docker, CI, Render Blueprint, and deployment runbook; verify local app. *(Complete; 13 tests pass and images build.)*
6. Publish to private GitHub and deploy if authorized. *(GitHub push pending this turn; cloud provisioning held at user's direction.)*
