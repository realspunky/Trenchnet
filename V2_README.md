# TrenchNet V2 architecture

Five scanners perform discovery only. `launch_model.record()` persists canonical launches to `v2_tracking`; V2 tracker verifies bonding >=60%, collects intelligence (unless `STAGE2_REQUIRED=false` for isolated testing) and promotes to `intake`. `v2_qualification.py` enforces V2 gate, Flap/STOnK rewards policy and crossing freshness. `alert_router.py` applies user preferences, final V2 gate and Telegram delivery. `/status` displays active V2 counters.

The old V1 global/launch filter, access/trial module and scanner-direct delivery have been removed. Old database tables are left untouched to protect `/data`. The V2 gate is always mandatory, including during Stage 2 bypass testing.

No live launchpad connectivity is exercised by the included offline tests; validate each scanner and stage transition after Railway deployment.
