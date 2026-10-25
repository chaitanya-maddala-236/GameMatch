# Deployment status

**Status as of 2026-10-26:** implementation and local evaluation are complete. The repository has been prepared for a private GitHub push. The user asked to hold cloud provisioning, so Render and Neon resources remain uncreated and there is no public URL.

## Verified locally

- 14 unit/API tests pass; Ruff and Python compilation pass.
- Docker Compose starts PostgreSQL, FastAPI, and Streamlit. API `/ready` and dashboard health both pass.
- Catalog, recommendation, similar-game, feedback, profile-interaction, and operational-metrics requests were exercised. Feedback remained after an API container restart.
- Hybrid test NDCG@10 is 0.1389 over 4,987 held-out users (95% user-bootstrap interval 0.1310–0.1469). Training plus evaluation took 570 seconds with sampled peak process RSS of 1,412.9 MiB.
- A 100-request, concurrency-5 local API run returned 100/100 HTTP 200 responses at 57.0 requests/second, p50 82.7 ms and p95 128.5 ms.

These local results describe this host and request mix; they are not a hosted capacity guarantee. Raw data, processed user rows, and the fitted model stay outside Git.

## Hosted plan

The Render Blueprint uses a 1 CPU / 2 GB API, free dashboard, 5 GB disk, and a Neon PostgreSQL connection supplied as a Render secret. Current Render baseline is estimated at $26.25/month; Neon Free is $0 while usage stays within 100 compute-hours and 1 GB per project. Cloud provisioning and secret transfer are held at the user's direction. See the [deployment runbook](deployment.md).
