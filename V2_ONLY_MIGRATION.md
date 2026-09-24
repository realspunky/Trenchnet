# TrenchNet V2-only architecture

Five original scanner implementations retained. New detections enter unified_launches as `v2_tracking` before tax, rewards, freshness or intelligence qualification. The V2 tracker independently verifies bonding >=60%; V2 qualification alone handles launchpad reward rules and intelligence; alert_router retains user preferences and the final V2 bonding gate. No V1 filter process is started.

**Railway:** keep DATABASE_PATH and the persistent `/data` volume. Set TRENCHNET_V2_ENABLED=true. `STAGE2_REQUIRED=false` is a delivery-pipeline test only; switch to true for intelligence qualification. Old V1 filter env vars `GLOBAL_FILTER_ENABLED`, `DUPLICATE_WINDOW_SECONDS`, `CREATOR_WINDOW_SECONDS`, `CREATOR_LAUNCH_LIMIT`, and user `threshold` no longer control V2 qualification. `V2_QUALIFY_POLL_SECONDS` defaults to 3; `V2_CROSSING_FRESH_SECONDS` defaults to 600.

Existing historical database rows are preserved, not replayed. This build is not live-chain verified: check `/status` and Railway scanner logs for all five pads before widening public delivery.

**Cold-start protection:** EmberCurve's first API snapshot is used as a baseline, not treated as fresh launches; subsequent market rows enter V2 at any progress. Historical V1 outbox tables remain in the persistent database for safe migration but are never drained by this V2 runtime. Flap and STOnK record raw detections before tax/reward eligibility is assessed.
