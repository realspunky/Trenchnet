# TrenchNet — Flap BNB private pilot

@TrenchNetBot. This update adds an automatic Flap BNB scanner and private owner test alerts. Public alerts, payments and email are not ready. The code is tested with simulated events; the event ABI and tax helper still require validation against a real newly launched token on the owner's Alchemy endpoint. Deployment is performed by the owner; this ZIP does not update Railway automatically.

## Update the existing Railway deployment

1. Extract the ZIP and upload its contents to the existing GitHub repository root, replacing matching files. `bot.py`, `scanner.py`, `run.py` and `requirements.txt` must be at the root, not inside another folder. Commit the changes.
2. Keep the existing persistent volume mounted at `/data` (lowercase). Keep `DATABASE_PATH=/data/trenchnet.sqlite3`, your existing `TELEGRAM_BOT_TOKEN` and `BNB_RPC_URL` secrets, and `PYTHONUNBUFFERED=1`. The Telegram token is the raw BotFather token; the Alchemy endpoint is its full HTTPS URL. Do not commit either secret.
3. Set `TRIALS_ENABLED=false` and `SCANNER_ENABLED=false`. Set the Railway service start command to exactly `python run.py`. Allow the new deployment to finish.
4. In a private chat with your bot, send `/myid`. Copy the number into a Railway variable named `ADMIN_CHAT_ID`. This must be your own positive private Telegram user ID, not a bot username or group ID.
5. Set `SCANNER_ENABLED=true` and deploy the variable changes. Keep one replica, no HTTP healthcheck and service sleeping off: this is a background worker.
6. Send `/threshold 85` (or any whole number 80–95), then `/status`. The owner's status includes checkpoint/lag, last scanner update, token states and private delivery counts. Initially no tokens/alerts is normal: the scanner starts at the current finalized block and waits for new launches.

To stop pilot alerts, set `SCANNER_ENABLED=false` and deploy. Leave the volume in place. Do not enable public trials yet: the private pilot bypasses subscriber access and sends only to ADMIN_CHAT_ID.

## What the pilot does

- Watches the documented Portal TokenCreated event on BNB mainnet, using finalized blocks and log batches of at most ten blocks.
- Saves launches and a block/hash checkpoint atomically in SQLite. Restarts resume the saved cursor. A changed checkpoint hash stops scanning for operator review; it does not silently skip data.
- Reads Portal and TaxTokenHelper state at one finalized height. Requires equal buy and sell token tax of 100, 200 or 300 basis points, positive dividend allocation, and tradable status. Migrated and nonmatching tokens do not receive new pilot alerts.
- Queues a launch alert only for discoveries within ten minutes of creation; queues one pre-migration alert when observed bonding progress reaches the owner's threshold but remains below 100%. This is sampled monitoring: rapid crossings/migrations can be missed. A threshold alert is not migration confirmation.
- Shows token name, symbol, address, chain, launchpad, token tax, reward asset, minimum holder balance converted using the token’s decimals, observed bonding progress/block and explorer links. Metadata is untrusted text, stripped of control characters; Telegram formatting and previews are disabled.
- Deduplicates events across restarts. Pending messages expire after five minutes. Explicit Telegram 429 responses get bounded retries; ambiguous timeouts/interrupted sends are marked uncertain and are not automatically resent. This avoids blind duplicate delivery but can lose an alert. There is no exactly-once guarantee or automatic manual-review interface yet.
- Uses bounded work per cycle (100 blocks, five token inspections, one delivery). Large backlogs can delay alerts; inspect `/status` for lag and Alchemy for usage. Continuous monitoring may exceed provider free quotas. No automatic provider upgrade is configured.

## Fee interpretation still needs resolution

Accepted pilot token-tax rates are now 1%, 2% and 3%, with equal buy/sell rates and holder rewards required. The distinction between token tax and total fees remains unresolved. Flap documents protocol fees separately from token tax. Therefore the pilot's token-tax candidates are explicitly labeled **total trading fees not yet verified**. `total_tax_bps` remains unknown, so the public qualification function rejects them. Dividend allocations describe how tax is allocated; they are not additional trading-tax percentages. We need a real-token fee breakdown before enabling public eligibility. Custom vault reward mechanisms without dividendBps are excluded for now.

## Troubleshooting

- `unable to open database file`: verify the attached persistent volume mount and DATABASE_PATH exactly match `/data`. SQLite requires a writable parent directory.
- `Scanner paused/retrying`: `/status` shows scanner error; verify BNB mainnet endpoint, provider quota, finalized-block support and log support. `python rpc_check.py` runs a separate capability check. Exception text containing secret URLs is deliberately not printed.
- Token status `review`: five state-read attempts failed, potentially due to unsupported ABI/token version. Token addresses appear in logs; inspect a token using `python flap.py TOKEN_ADDRESS`. No candidate is emitted on failed reads.
- Delivery state `uncertain` or `review`: inspect privately before any manual action. Don't delete outbox rows to force a resend.
- Stale status: inspect Railway logs. `run.py` supervises the command bot and scanner; unexpected child exit stops the service so Railway can restart it. A stalled RPC times out.
- Persistent checkpoint mismatch: stop the scanner and investigate RPC consistency; do not casually delete the database because it contains trial/payment history.

## Access and payment status

The payment choice is Telegram Stars, superseding USDT. Dollar targets are $5 monthly, $60 for 12 months and $100 lifetime. Stars amounts, invoices and successful-payment verification are not implemented; checkout remains disabled.

`access.py` implements trial/entitlement primitives: one trial per Telegram user, five consecutive 24-hour periods, up to one logical alert per period, expiration, event deduplication and unique payment charge IDs. Empty trial days expire normally. No automatic billing. The private scanner is not connected to subscriber delivery. `grant_verified_payment` is an internal primitive, not a payment verifier.

`/delete_me` removes preferences but retains trial/payment history; production privacy documentation and retention controls remain to be completed. Optional verified email, expiry reminders, backups, Pons/Stonk adapters and Solana/Robinhood support remain pending.

## Local checks

Python 3.11+. Install `python -m pip install -r requirements.txt` and run `python -m unittest -v` from this folder. Run `python run.py` after setting secrets in the environment. Only one polling bot instance is allowed. A previous Telegram webhook must be removed before polling.

30 tests cover access rules, token parsing/filtering, checkpoint rollback, restart deduplication, threshold crossing, stale-message expiry, Telegram retry/uncertain delivery and RPC checks. These tests do not prove live event/ABI compatibility or end-to-end Telegram delivery.

The owner's Railway preflight screenshot showed chain_id 56, contracts_present true and log_query_supported true. That verifies RPC capabilities, not a complete token monitoring pipeline. Next acceptance check: observe a real new Flap token, compare its decoded tax/reward/progress against official data, receive private alerts, restart and confirm the checkpoint/deduplication, then resolve the total-fee requirement.

## Official references

- https://docs.flap.sh/dev/launch-a-token
- https://docs.flap.sh/flap/developers/wallet-and-terminal-and-bot-developers/index-token-created-events
- https://docs.flap.sh/flap/developers/wallet-and-terminal-and-bot-developers/inspect-a-token
- https://docs.flap.sh/flap/developers/wallet-and-terminal-and-bot-developers/inspect-a-tax-token
- https://docs.flap.sh/flap/developers/deployed-contract-addresses
- https://docs.flap.sh/flap/developers/basic-and-mechanism/protocol-economics
- https://core.telegram.org/bots/payments-stars
- https://web3py.readthedocs.io/en/stable/middleware.html#proof-of-authority

Alert display update: removed the Other allocations line. Minimum holder balance uses on-chain token decimals and comma-separated units; if decimals cannot be read it displays unavailable. Existing sent/queued messages are not rewritten. The screenshot token has 18 decimals: raw 10000000000000000000000 equals 10,000 units; raw 100000000000000000000000 equals 100,000 units.

Alerts now include only the BscScan token link. The creation transaction remains stored internally but is not shown in the message.

## Expansion update
The 1%/2%/3% filter applies to newly discovered tokens and ongoing tracked-token inspections after deployment. Previously excluded tokens are not automatically replayed. Mixed buy/sell rates (such as buy 1%, sell 2%) remain excluded. Holder dividends must be positive. All earlier alert layout edits and the hidden /myid menu entry are retained.

Network scope is BNB, Solana and Robinhood Chain (three total). Only Flap BNB is connected. Pons documentation currently redirects this research environment to a regional restriction; Stonk could not be retrieved. No guessed contract addresses or fake adapters have been added. To complete those adapters, obtain the launchpads' published factory/program IDs, creation/migration event schemas or IDLs, reward/tax state definitions and bonding formulas. Providing an accessible official document/export is sufficient; no wallet keys are needed. Solana RPC alone cannot establish a launchpad's tax and holder-reward semantics.


## StonkFun / Solana private launch pilot — September 20 update

Upload the entire ZIP contents to the repository root, including the new `stonk.py`. Existing `run.py`, `bot.py` and `scanner.py` have changed together. Keep the start command `python run.py`. Add `STONK_ENABLED=true` in Railway and deploy. Keep `SCANNER_ENABLED=true` for BNB, your existing ADMIN_CHAT_ID, the same database/volume and `TRIALS_ENABLED=false`. No additional API key, Solana RPC or wallet is needed for this API-based pilot. Set STONK_ENABLED=false to stop only Stonk.

The worker uses the official https://www.stonkfun.xyz/developers API, specifically the launches ledger and token detail endpoints. Live read-only calls returned real mainnet reward launches at 100 and 300 basis points and token details with network mainnet-beta. The program accepts reported reward transfer tax of 100/200/300 bps only, for LaunchLab launches adopted by Stonk. Older pool-fee-only rewards and standard creator-fee tokens are excluded. This is platform-reported qualification, not independent Solana contract verification or a promise of actual payouts.

The owner receives a launch alert with the requested emojis, reward asset and a single Stonk token-page link. Minimum holder balance and allocation percentages are omitted because these API responses do not establish them. Public subscriptions/payments remain off. Telegram delivery from this worker has not yet been tested on the owner's Railway service.

Bonding delivery is deliberately disabled in the production entry point. Sample responses carry graduationProgress between zero and one, but the published OpenAPI schema does not define the scale, and the website display logic could not yet be verified. The internal threshold logic is covered by simulated tests using a provisional 0–1 interpretation; this does not establish live percentage accuracy. Alerts show 'awaiting scale verification' rather than a guessed percentage. A graduated API status stops tracking; no migration-confirmation alert is sent. Validate the progress scale against a real launch before enabling bonding in code.

Restart checkpoints, tokens, health and outbox are stored in separate stonk_* tables on the existing volume. The first run starts now; older launches are not replayed. The discovery cursor overlaps ten minutes to accommodate index delays and page movement. At most five pages of 100 records are read per cycle. A larger backlog pauses without advancing the checkpoint. Late indexing beyond the overlap can miss launches; this is a bounded API pilot, not a complete on-chain indexer. Tracking checks eight due tokens per cycle and delivers up to five messages with spacing, then waits 60 seconds. Large token queues and network delays slow observation. API response timestamps older than five minutes are rejected; this tests response freshness, not per-token on-chain freshness. Explicit 429s respect Retry-After. Five failed token inspections require review. Ambiguous Telegram sends are not blindly resent, and pending alerts expire after five minutes.

/status includes Stonk status, last update, token counts and delivery counts for the configured owner. The same /threshold setting is reserved for both networks, but only BNB currently emits bonding alerts. No database deletion or second Telegram bot is required.

Tests: 39 automated checks across BNB, access and Stonk, including rate/tax gates, stale API rejection, pagination limits, restart deduplication, chain/token identity, production launch-only behavior and isolated delivery. Pons/Robinhood remains pending.

Copy-contract update: all new BNB and Stonk alert deliveries format the contract as code and add a native Telegram Copy contract button. The button copies only the address. Existing sent messages are unchanged. No extra callback handler is needed.

## PONS / Robinhood Chain private pilot

Set `PONS_ENABLED=true` to start the read-only PONS listener. Optional settings:

- `PONS_RPC_URL` — defaults to Robinhood Chain public mainnet RPC.
- `DUPLICATE_WINDOW_SECONDS` — same normalized name+symbol cluster window; default `900` (15 min).
- `CREATOR_WINDOW_SECONDS` — creator multi-launch window; default `1800` (30 min).
- `CREATOR_LAUNCH_LIMIT` — first N distinct launches are allowed in the creator window; default `3`.

The listener starts at the current chain head on first boot, so enabling it will not flood Telegram with historical launches. It indexes the active and legacy PONS factories, reads token name/symbol on-chain, applies duplicate-name and creator multi-launch filtration, and queues only the first qualifying launch for the private admin. Filtered launches remain in SQLite for testing/analysis.

## EmberCurve intake (pre-filtration phase)
Set `EMBER_ENABLED=true` to enable the EmberCurve launch intake. It polls Ember's public market data and snapshots the current market set on first startup so existing launches do not flood Telegram. New mints observed after startup are queued as private-pilot alerts.

Optional settings:
- `EMBER_MARKETS_URL` (default `https://embercurve.fun/api/solana/markets`)
- `EMBER_POLL_SECONDS` (default `15`)

Per the current build plan, shared duplicate/creator filtration is intentionally not applied to Ember yet. We will finish launchpad intake first, add Pump.fun, then route all launchpads through one global filter and user launchpad preferences.

## Pump.fun intake
Pump.fun launch intake is intentionally upstream of the future shared filtration layer.

Environment:
- `PUMPFUN_ENABLED=true`
- `SOLANA_RPC_URL=<your Solana JSON-RPC endpoint>` (recommended: a dedicated provider; public RPC may rate-limit)
- `PUMPFUN_POLL_SECONDS=8`
- `PUMPFUN_SIGNATURE_LIMIT=100`

The scanner watches the official Pump program, decodes `create_v2`, stores mint/name/symbol/creator/URI, snapshots the current head on first boot, and only alerts on launches observed after initialization. Duplicate/creator filtration is deliberately not applied here yet.

## Unified launch model
All five launchpads now write discoveries into `unified_launches` through `launch_model.py`.
The canonical fields are chain, launchpad, contract/mint, creator, name, symbol, pair,
source transaction/height, launch time, bonding progress, migration state and source metadata.

This is intentionally an intake layer only. Global duplicate-name clustering, creator rapid-launch
filtration and per-user launchpad routing should consume `unified_launches` in the next stage instead
of being implemented separately inside each scanner. The earlier PONS-only filter has been removed
from its alert path so all launchpads reach the same intake stage first.

Canonical launchpads: `flap`, `stonk`, `pons`, `embercurve`, `pumpfun`.
Canonical chains: `bnb`, `solana`, `robinhood`.

## Global filtration pipeline

Launch scanners write every detected launch to `unified_launches`. `global_filter.py` consumes rows in `pipeline_state=intake` and applies the shared rules across all launchpads before creating the canonical `global_outbox` alert.

Defaults:
- `GLOBAL_FILTER_ENABLED=true`
- `GLOBAL_FILTER_POLL_SECONDS=3`
- `DUPLICATE_WINDOW_SECONDS=900` (15 minutes)
- `CREATOR_WINDOW_SECONDS=1800` (30 minutes)
- `CREATOR_LAUNCH_LIMIT=3` (first three distinct launches allowed; fourth+ in-window filtered)

Decisions are persisted in `global_filter_decisions`; unified rows become `approved` or `filtered`. New creator wallets are not penalized merely for having no history. Duplicate clustering is chain-wide, so the same normalized name+symbol appearing through two launchpads on the same chain is treated as one cluster while each contract address remains its own token identity.

The legacy launchpad outboxes are still populated for backward-compatible scanner tests/rollback, but with the global pipeline enabled they should be treated as non-canonical launch queues. `global_outbox` is the canonical filtered launch-alert queue. Existing launchpad-specific bonding alerts remain separate until lifecycle events are unified.

## Per-user launchpad alert selection
Approved launches are now routed by `alert_router.py` after the global filter. Users can run `/alerts` and toggle Flap, STOnK, PONS, EmberCurve, or Pump.fun independently, or enable/disable all. New users default to all launchpads enabled so existing behavior is preserved.

Routing order: scanners -> `unified_launches` -> global filter -> alert router -> `global_outbox` -> Telegram.

`PUBLIC_ALERTS_ENABLED=false` (default) keeps routing private to `ADMIN_CHAT_ID` for testing. When public routing is intentionally enabled, set `PUBLIC_ALERTS_ENABLED=true`; registered users then receive only approved launches from launchpads they enabled. `ALERT_ROUTER_POLL_SECONDS` defaults to 3 seconds.

## Token X + website metadata links

The unified launch model now normalizes optional token-supplied social links into `social_x_url` and `website_url`. X links are accepted only from x.com/twitter.com and website links must be HTTP(S). Approved global alerts add Telegram `𝕏 X` and/or `🌐 Website` buttons only when those links are present in launch metadata. Pump.fun `create_v2` metadata URIs are fetched as bounded public JSON (including `ipfs://` via an HTTPS gateway) so its optional `twitter` and `website` fields can flow into the unified model. No social link is guessed from a token name or ticker.

## Alert preference routing fix
When `GLOBAL_FILTER_ENABLED=true`, launchpad scanners no longer deliver their legacy per-launchpad outboxes directly. All launch alerts are delivered only by `alert_router.py`, which applies each user's `/alerts` launchpad preferences. This prevents disabled launchpads (for example Flap) from bypassing a Pump.fun-only selection.

### Alert delivery schema migration fix
The unified alert router now migrates older persistent `global_outbox` tables to the delivery schema used by `scanner.deliver()`. Existing `queued` rows are converted to `pending`, and missing `next_attempt` / `message_id` columns are added automatically. This fixes the case where `/alerts` selections saved correctly but approved alerts were never delivered after routing.


### Alert preference enforcement fix
The `/alerts` preference is now checked twice for all five launchpads: once when a globally-approved launch is routed, and again immediately before Telegram delivery. Pending alerts queued before a user changes selection are marked `preference_blocked` and cannot leak through. This applies equally to Flap, STOnK, PONS, EmberCurve and Pump.fun.

## 2026-09-21 reliability fix
- Alert preferences remain authoritative for all five launchpads at routing and immediately before Telegram delivery.
- Global outbox now drains without an artificial per-alert sleep, reducing cross-launchpad latency (for example STOnK + Flap together).
- Flap enters unified intake only after its contract inspection succeeds, preserving bonding progress in the unified alert and keeping the existing verified-candidate gate.
- PONS token name/symbol reads are best-effort: broken metadata no longer blocks the factory launch event from entering unified intake.
- PONS health now reports new logs plus unified intake/approved counts.
- EmberCurve first poll is a baseline only; it no longer turns every pre-existing market into a fresh unified launch. New markets after initialization enter the pipeline normally.
- Pump.fun keeps its first-run head snapshot behavior and metadata social-link extraction.

## 2026-09-21 scanner reliability repair

- PONS now watches the current V2 factory `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e` and V2 `TokenLaunched` topic, while retaining V1 readers.
- Pump.fun signature ingestion is paginated (up to 1000 signatures/page, configurable pages) so high program traffic does not silently push launches outside a 100-signature window.
- Pump.fun exposes `PUMPFUN_MAX_PAGES` (default 10) and accepts `PUMPFUN_SIGNATURE_LIMIT` up to 1000.
- Ember market parsing accepts additional public API response shapes/field names and isolates malformed rows instead of aborting the whole polling cycle.
- Health rows now expose scanner-specific counts useful for Railway diagnostics.

Recommended Railway values:
`PUMPFUN_SIGNATURE_LIMIT=1000`
`PUMPFUN_MAX_PAGES=10`
`PUMPFUN_POLL_SECONDS=5`
`EMBER_POLL_SECONDS=15`
Use dedicated `SOLANA_RPC_URL` and `PONS_RPC_URL` endpoints for production reliability.

## Reliability hotfix: fresh launches only
- `MAX_LAUNCH_AGE_SECONDS` defaults to `600`. Unified filtering and routing reject older launch records so Railway redeploys cannot replay old Flap/STOnK listings as new launches.
- Existing pending unified alerts older than the freshness window are marked `stale` before delivery.
- PONS `eth_getLogs` requests default to 10-block chunks (`PONS_LOG_BLOCK_CHUNK=10`) for provider compatibility.
- EmberCurve now uses the public `/markets` developer surface and transparently falls back from the older `/api/solana/markets` setting.
- `/status` now includes EmberCurve and Pump.fun scanner health in addition to Flap, STOnK and PONS.

## Pipeline recovery build (2026-09-21)
- STOnK now prioritizes fresh pending launches over historical tracking/retry maintenance rows.
- Global filter uses fair per-launchpad intake under backlog pressure, preventing PONS/STOnK/Pump/Ember/Flap starvation.
- Global filter errors and backlog are visible in /status.
- Pump.fun RPC calls retry temporary HTTP 408/425/429/5xx and common transient Solana RPC errors with backoff; cursor is not advanced on a failed scan.
- Ember validates JSON responses, uses browser-compatible request headers, and tries canonical API variants before reporting a detailed source error.
- Existing freshness and preference gates remain enabled; no database reset is required.

## Targeted live-pipeline fix (2026-09-22)
- Pump.fun `getTransaction` now opts into Solana transaction version 1 with `maxSupportedTransactionVersion: 1`, preventing RPC -32015 on v1 transactions.
- EmberCurve response cap is configurable with `EMBER_MAX_RESPONSE_BYTES` (default 25,000,000) so the live market feed is not rejected at the former 5 MB limit.
- PONS detects inherited cursor lag and skips historical replay beyond `PONS_MAX_CURSOR_LAG_BLOCKS` (default 200), while preserving a recent lookback for live launches. Existing historical filtered rows stay filtered.
- STOnK registers genuinely fresh launch mints in unified intake before optional token-detail enrichment, so temporary token-detail read failures cannot suppress the launch itself.

## STOnK metadata-required alert gate
STOnK launch mints are retained immediately, but a launch is not admitted to the unified alert pipeline until the token detail response contains a real name and symbol. Failed metadata reads remain in the existing retry/review flow. The global router also refuses unresolved STOnK records, and legacy pending STOnK outbox rows with missing/placeholder metadata are marked `metadata_blocked` before Telegram delivery.


## Open beta mode
Set `BETA_TESTING_ENABLED=true` to open unlimited beta alert routing to registered bot users. In beta mode `/status`, `/plans`, and `/price` are hidden from non-admin users, trial limits are not used for alert routing, and the Start Free Trial keyboard is removed. The configured `ADMIN_CHAT_ID` retains `/status` for diagnostics. `/alerts` remains available so each tester controls launchpad preferences. Keep `GLOBAL_FILTER_ENABLED=true`.
