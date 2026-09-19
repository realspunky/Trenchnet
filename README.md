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
