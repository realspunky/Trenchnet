# TrenchNet V2 — single pipeline

Run on Railway with `python run.py`. Preserve `/data` and `DATABASE_PATH=/data/trenchnet.sqlite3`.

The five launchpad detectors remain; all V1 qualification, creator/duplicate filters, trial access, and scanner direct-delivery paths are retired. V2 owns tracking, bonding verification, Stage 2, launchpad reward policy, preferences and delivery.

**Required:** `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`, `DATABASE_PATH`; scanner enable flags and existing RPC URLs.

**V2:** `STAGE2_REQUIRED=true` for normal operations (temporarily `false` ONLY for isolated bonding/delivery tests), `PUBLIC_ALERTS_ENABLED=false` until verified live, `V2_TRACK_POLL_SECONDS=5`, `V2_TRACK_BATCH=250`, `V2_QUALIFICATION_POLL_SECONDS=3`, `ALERT_ROUTER_POLL_SECONDS=3`.

Obsolete settings: `GLOBAL_FILTER_ENABLED`, `DUPLICATE_WINDOW_SECONDS`, `CREATOR_WINDOW_SECONDS`, `CREATOR_LAUNCH_LIMIT`, `TRIALS_ENABLED`, `BETA_TESTING_ENABLED`, user bonding thresholds. Remove these from Railway when convenient. `TRENCHNET_V2_ENABLED` is forced on by run.py; keep it `true` explicitly for direct worker execution.

See `V2_ONLY_MIGRATION.md` for migration details. No DB tables are dropped and no old outbox entries are replayed.
