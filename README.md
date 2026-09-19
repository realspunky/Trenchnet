# TrenchNet — development foundation

Bot: @TrenchNetBot. This is a runnable command/settings prototype, not a finished alert service. No money is accepted and no live token alerts are sent.

## Run
Python 3.11 or newer; standard library only. Set TELEGRAM_BOT_TOKEN using a hosting provider's secret environment settings, then run `python bot.py`. Never paste the token into chat, source code or screenshots. Run only one polling process. It needs outbound HTTPS to api.telegram.org and a persistent disk. DATABASE_PATH defaults to trenchnet.sqlite3. Existing webhook configurations must be removed before using polling.

Tests: `python -m unittest -v` from this folder.

## Implemented
Private-chat /start, /help, /threshold, /status, /plans, /email and /delete_me. SQLite saves thresholds and polling offsets. Token qualification and pre-migration threshold rules are tested. Raw token metadata must come from trusted, verified adapters, not user input.

## Agreed requirements
- Pons https://www.ponsfamily.com/launchpad, Stonk https://www.stonkfun.xyz/ and Flap.
- Solana, BNB Chain, Robinhood Chain only where launchpads actually support them.
- Exactly 3% total tax including launchpad fees; a holder reward allocation must exist.
- Two event types: new launch and pre-migration bonding alert. User threshold 80–95%, default 80%; one pre-migration notification per token per subscriber.
- Fields: token name, symbol, address, chain, launchpad, tax breakdown, holder reward details, bonding progress, token and transaction links.
- Telegram delivery; optional verified email; phone and computer management.
- Requested prices: $5 monthly, $60 for 12 months, $100 lifetime.
- Requested settlement: USDT on BNB Smart Chain. Owner-supplied public address: 0x27107c28cd8573c36c42312df3917f24e3569ca3. Not verified or connected.

## Payment decision requiring correction
Telegram requires Stars for digital goods/services sold inside Telegram bots, explicitly excluding cryptocurrency. The previously proposed in-bot USDT checkout must be revised. No substitute payment method or Stars conversion has been selected or implemented. Source: https://core.telegram.org/bots/payments-stars

## Remaining work before launch
1. Verify official launchpad contracts/APIs, supported chains, tax/reward semantics and bonding calculations. Pons lookup was region-blocked and Stonk lookup failed; no adapters have been verified.
2. Build chain watchers, checkpoint/reconnect logic and historical catch-up; decide treatment of tokens discovered late or crossing a threshold between samples.
3. Add subscription entitlements, expiry/renewal reminders and the agreed compliant payment design.
4. Build durable per-user/per-token delivery queues, deduplication, retry limits and rate limiting. Handle blocked bots; current prototype retries transient errors and is not a production delivery worker.
5. Add verified email opt-in, expiring verification codes, unsubscribe and email delivery provider.
6. Add authenticated owner controls, support, terms, privacy details and database backups.
7. Provision hosting and credentials securely; perform end-to-end tests before accepting subscriptions.

The prototype stores only Telegram user ID and chosen threshold. It does not store message text or email. Duplicate command replies remain possible after an interruption; production delivery reliability is still pending.

## Updated access implementation
The superseding payment choice is Telegram Stars. USDT and the prior $70 annual plan are retired. Dollar targets are $5 / $60 / $100; Stars prices remain unset and checkout stays disabled.

access.py implements one trial per Telegram user ID, exactly five consecutive 24-hour periods from activation, one logical alert per period, persistent event deduplication, paid expiration, calendar-month/year renewal (month-end clamped) and lifetime entitlement. Telegram and email must share the same logical alert reservation. Empty days expire normally. No automatic billing is implemented.

The Start Free Trial keyboard button and /trial invoke activation. TRIALS_ENABLED defaults off to avoid consuming trials before real monitoring exists. Enable only when watchers and durable delivery are ready. /status exposes access status. /delete_me deletes preferences but retains trial-use/payment records; this retention needs to be covered in the production privacy policy.

grant_verified_payment is an internal entitlement primitive, not a payment verifier or checkout implementation. No user command can grant paid access. A future authenticated Stars handler must validate invoice ownership, amount, currency and successful payment before invoking it. Charge IDs are unique across users.

Remaining: actual Stars invoice handler and chosen prices, launchpad integrations, durable channel retry workers, proactive expiry prompts, verified email and deployment. Expired access is blocked by the access gate; /plans supplies the subscription prompt, but automatic expiry notifications are not yet wired.

## Flap BNB reader (development, not live-validated)
Install requirements.txt and set BNB_RPC_URL as a secret, then run `python flap.py TOKEN_ADDRESS`. Reads only; no wallet key needed. RPC must support finalized blocks and historical calls at that block. The reader checks chain ID 56 and contract code, reads Portal state plus TaxTokenHelper at one finalized height, and fails closed on errors. No live RPC or real token was tested in this session; tests use synthetic fixtures.

This is a token inspector, not yet an automatic launch scanner or delivery worker. It uses the documented BNB Portal getTokenV8Safe and TaxTokenHelper getTaxTokenInfoV2 interfaces. Both buy and sell rates must equal 300 basis points, with matching helper rates and a positive dividend allocation. Asymmetric tokens are conservatively excluded. Bonding progress uses the reported 1e18 scale; unknown/staged statuses are excluded. Custom vault-based rewards without dividendBps are not yet classified. The reported token tax is not proven to include every separate platform/trading fee; verify fee semantics on real tokens before enabling the user's total-fee filter. Allocation fields are reported separately from tax rate; they must not be added to it.

Remaining integration gates: live ABI compatibility (especially Tax Token V3), fee semantics, TokenCreated log ABI and cursor/reorg handling, names/symbols/creation transaction enrichment, automatic watcher, durable delivery, and Robinhood/Pons/Stonk adapters. BNB support does not imply these other chains are connected.

Official references checked:
- https://docs.flap.sh/flap/developers/deployed-contract-addresses
- https://docs.flap.sh/flap/developers/wallet-and-terminal-and-bot-developers/inspect-a-token
- https://docs.flap.sh/flap/developers/wallet-and-terminal-and-bot-developers/inspect-a-tax-token
- https://docs.flap.sh/flap/developers/wallet-and-terminal-and-bot-developers/index-token-created-events

## BNB RPC configuration and live preflight
The default read endpoint is https://bsc-dataseed.bnbchain.org, listed in BNB's official documentation. Override using the BNB_RPC_URL environment variable (use hosting secrets if the URL contains an API key). Never commit a private endpoint URL.

Run `python rpc_check.py` before enabling the reader. It verifies chain ID 56, a fresh finalized block (within five minutes with up to 60 seconds clock skew), contract presence at that block and event-log query support. It hides endpoint details on failure. `flap.py` also refuses stale finalized data.

Live read-only checks on 2026-09-19 returned chain ID 0x38, finalized block 0x751cbff (timestamp 2026-09-19T12:57:04Z), Portal bytecode 2882 bytes and Helper bytecode 2837 bytes. This confirms connectivity and contract presence only, not per-token ABI compatibility, fee correctness or automatic monitoring.

BNB explicitly documents eth_getLogs as disabled on its listed public mainnet endpoints. This default is for initial state reads; an endpoint supporting event logs is still required for the launch scanner. A configured provider must pass the capability check before monitoring is enabled. No paid provider account has been created.
Reference: https://docs.bnbchain.org/bnb-smart-chain/developers/json_rpc/json-rpc-endpoint/
