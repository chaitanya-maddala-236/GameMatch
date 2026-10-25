# GameMatch decisions

| Date | Decision | Reason |
|---|---|---|
| 2026-10-26 | Create a new `GameMatch/` repository rather than modifying `PlayerPulse/`. | The existing uncommitted starter is an unrelated telemetry project; preserve it. |
| 2026-10-26 | Use the UCSD Version 1 Australian Steam interaction, game, and review files. | The 71 MB compressed library snapshot provides enough repeated user-game signals for a resource-conscious ranking experiment; metadata and explicit review recommendations are also available. |
| 2026-10-26 | Define positives as games with `playtime_forever > 0`, except explicitly not-recommended reviews. | Library ownership alone is weak evidence; any positive playtime is a verified interaction. Unobserved pairs remain unknown. |
| 2026-10-26 | Keep source files and row-level processed interactions outside Git. | The source page requests citation but publishes no explicit reuse license; do not redistribute raw or per-user data. |
| 2026-10-26 | Use deterministic per-user random holdouts, not a temporal split. | The library snapshot contains no interaction timestamps. This evaluates held-out known-user ranking but cannot model future-time drift. |
| 2026-10-26 | Use SQLite locally and PostgreSQL when persistent deployment storage is available. | Simple local startup with a production-ready relational option. |
| 2026-10-26 | Use Neon PostgreSQL for hosted persistence and Render for application hosting. | Follow the user's provider choice; keep the connection URL as a Render secret. |
| 2026-10-26 | Use a free Render dashboard, paid 1 CPU / 2 GB API, and 5 GB disk. | The local model training peak RSS was about 1.4 GiB; durable model artifacts avoid repeated long bootstraps. |
| 2026-10-26 | Prefer private GitHub repository visibility by default. | The user requested GitHub but did not specify visibility; public sharing is an access expansion. |
