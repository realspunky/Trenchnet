# TrenchNet V2-only migration

All five detection implementations remain; V1 qualification, trial caps and launchpad-specific pilot outbox delivery are inactive. `run.py` always starts V2 tracker, V2 qualification and V2 router. Legacy scanner direct-delivery paths are removed.

New measured launches from Flap, STOnK and EmberCurve enter `v2_tracking` even below 60%. PONS and Pump.fun enter tracking on detection. STOnK requires real metadata before its unified record is created. V2 is responsible for >=60%, Stage 2, reward/tax policy, preferences and Telegram delivery.

Keep Railway `/data` and existing scanner/RPC variables. Keep `STAGE2_REQUIRED=false` ONLY during isolated gate/delivery testing; restore `true` before normal public operation. Legacy environment variables `DUPLICATE_WINDOW_SECONDS`, `CREATOR_WINDOW_SECONDS`, `CREATOR_LAUNCH_LIMIT`, `TRIALS_ENABLED`, and `BETA_TESTING_ENABLED` no longer control V2 qualification. `MAX_LAUNCH_AGE_SECONDS` is measured from 60% crossing.

Existing V1 approved/outbox rows are not migrated into V2: the router only handles V2-approved rows. No historical alerts are replayed. No persistent tables are dropped.
