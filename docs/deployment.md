# Deployment runbook

## Prepared host

`render.yaml` is a Render Blueprint with a 1 CPU / 2 GB API, a free dashboard, a 5 GB disk attached to the API, and Neon Postgres. The API needs 2 GB RAM because the observed local training peak was about 1.4 GiB. Current official Render pricing lists the API at $25/month and disk at $0.25/GB/month, for an estimated fixed baseline of $26.25/month. The dashboard uses Render's free tier and can sleep after inactivity. Neon Free currently includes 100 compute-hours and 1 GB of storage per project, with compute scaling to zero after five idle minutes. Recheck [Render pricing](https://render.com/pricing) and [Neon pricing](https://neon.com/pricing) before provisioning. No cloud resources have been created yet.

The API uses a paid Render plan and persistent disk. Request metrics and feedback are stored in Neon; model and data bootstrap outputs are stored on the API disk. Neon Free is suitable only while the application stays within its current quotas. The dashboard is a free Render web service and may spin down after inactivity.

## Deploy steps

1. Push the private `GameMatch` repository to GitHub.
2. Create a Neon project in a region near the Render services. Copy its pooled connection string from the Neon dashboard. Keep the URL private; use Render's environment editor to set it as the API service's `DATABASE_URL` secret. The application accepts Neon's `postgres://` or `postgresql://` URL formats and selects Psycopg 3. The value is not stored in this repository.
3. In Render, connect the repository and choose **New → Blueprint**. Review the paid API, free dashboard, 5 GB persistent disk, and estimated $26.25/month Render baseline before applying. The Blueprint leaves `DATABASE_URL` unsynced so the Neon secret is supplied through Render.
4. Set/retain the generated `PLAYER_ID_HASH_SECRET`; keep it private. Apply the Blueprint. Uvicorn starts immediately so Render's 15-minute start limit is not consumed by data preparation. The first API process downloads and processes the UCSD files, trains/evaluates once in a background bootstrap thread, and writes `model.joblib` to `/var/data`. `/health` checks liveness; `/ready` stays 503 until the model and Neon database are available. Monitor startup logs until `/ready` returns 200 before testing recommendations.
5. Verify API `/health`, `/ready`, `/v1/model/info`, `/v1/games`, a POST `/v1/recommendations`, and `/v1/metrics/summary`; open the dashboard and verify its API calls.
6. Confirm a feedback or interaction row remains after an API restart. Verify database backup settings and set a spending alert in the host console.
7. Record both public service URLs in `docs/deployment-status.md` only after the checks pass.

## Model replacement and rollback

Train a new artifact version offline and inspect its independent test report. Copy the validated artifact to persistent storage, update `GAMEMATCH_MODEL_PATH`, and deploy. Roll back by restoring the previous environment path/artifact or the previous Render deploy. The API never trains from feedback or user requests.

## Local checks

`docker compose up --build` creates a local PostgreSQL volume and uses `GAMEMATCH_HOST_DATA` (default `./data`) for the source files, processed tables, and model. Back up `gamematch_postgres` and the data directory before deleting them. The API health check uses `/ready`, so Compose does not start the dashboard until first-time bootstrap finishes.
