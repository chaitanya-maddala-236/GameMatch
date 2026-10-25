# GameMatch task checklist

- [x] Inspect workspace, runtimes, Git, disk, and Docker availability.
- [x] Verify official UCSD source files and inspect sample schemas.
- [x] Download the selected raw files to a location excluded from Git.
- [x] Implement schema validation, duplicate handling, positive-interaction normalization, and processed exports.
- [x] Create deterministic user-aware train/validation/test splits and data quality reports.
- [x] Train popularity, content, item-item collaborative, and validation-tuned hybrid recommenders.
- [x] Run ranked evaluation and save actual metrics, configuration, and visualizations.
- [x] Implement FastAPI catalog/recommendation/similarity/feedback/monitoring endpoints and persistence.
- [x] Implement Streamlit discovery, recommendations, similarity, evaluation, and monitoring views.
- [x] Add tests for data, ranking metrics, exclusions, fallbacks, persistence, and API contracts; run and fix them (13 passed).
- [x] Add Docker Compose, health checks, GitHub Actions, and a Render + Neon deploy Blueprint/runbook.
- [x] Run API and dashboard smoke checks, a 100-request latency benchmark, and Docker verification.
- [ ] Publish the completed source to the private GitHub repo and document cloud deployment as pending spend and secret-transfer approval.
