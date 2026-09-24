# TrenchNet V2-only

Run `python run.py` with your existing Railway service and persistent `/data` volume. See `V2_ONLY_MIGRATION.md` for architecture and environment changes. Five original launchpad detectors remain, but the V1 filtering engine and its Python files are removed. V2 handles intake, verified >=60% bonding, Stage 2, launchpad-specific reward qualification, user preferences and final Telegram safety checks.

Do not delete `/data`. Start with `STAGE2_REQUIRED=false` only for the isolated bonding/delivery test. For full intelligence qualification, set `STAGE2_REQUIRED=true` after live collector validation. This ZIP has local test coverage but has not been deployed or verified against live launchpad/RPC data.
