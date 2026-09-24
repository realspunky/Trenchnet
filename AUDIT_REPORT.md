# TrenchNet V2 full code audit

## Removed
- `binance_web3_v2.py` and authenticated Binance wallet intelligence.
- `binance_v2_intelligence.py` and credential-free Binance token/audit enrichment.
- Binance tests and every Binance call/import in Stage 2 and the tracker.
- V1-named `global_filter_decisions` / `global_filter_health` from the active code. V2 now writes `v2_qualification_decisions` / `v2_qualification_health`.
- `BETA_TESTING_ENABLED` from routing. `PUBLIC_ALERTS_ENABLED` is the only public-delivery switch.
- Flap private-pilot outbox/delivery coupling. Telegram delivery is now a standalone V2 transport module.
- Old creator/duplicate presentation inherited from the V1 global filter.

## Root causes found
1. The tracker used one global `LIMIT 250` ordered by `last_seen`. EmberCurve refreshes thousands of rows every poll, so it could monopolize the batch and starve other launchpads.
2. The tracker heartbeat was written only after the whole batch completed, so slow RPC refreshes made `/status` report stale.
3. Binance enrichment was still active in two separate Stage-2 paths despite no longer being part of the intended V2 architecture.
4. V2 qualification still persisted decisions in tables named `global_filter_*`, preserving unnecessary V1 coupling/ambiguity.
5. The router still honored `BETA_TESTING_ENABLED`, another legacy switch that could affect delivery independently of V2.

## Preserved
- Persistent `/data` database. New V2 tables are additive; old tables may remain on disk but are not active decision inputs.
- Five launchpad detector implementations.
- Mandatory verified bonding >=60%.
- Stage 2 bypass switch for isolated testing.
- Flap/STOnK holder-reward policy.
- Per-user launchpad preferences and final pre-send V2 gate.
