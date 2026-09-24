# TrenchNet V2

## Mandatory rule
When `TRENCHNET_V2_ENABLED=true`, no token can be approved before verified bonding progress is at least 60%.
Stage-2 intelligence is fail-closed: missing required data means no alert.

Required Stage-2 fields:
- description/lore
- at least one social presence signal
- holder count and top-10 concentration
- sniper count and combined concentration
- buys/sells and unique buyers/sellers
- volume

Additional fields shown when supplied: dev holding %, largest sniper %, snipers holding/sold,
bundled/linked wallet count, buy/sell volume, activity window, launch-to-60 time.

## Source integrity
TrenchNet does not invent missing values. Flap, STOnK and Ember use their scanner-supplied bonding progress.
PONS and Pump.fun creation events are stored as silent `v2_tracking`; creation alone is not treated as 60%.
A verified JSON adapter can be configured for any launchpad using:
`V2_<LAUNCHPAD>_INTELLIGENCE_URL=https://provider/token/{address}`.
The adapter must explicitly provide bonding progress and Stage-2 fields.

## V2 variables
TRENCHNET_V2_ENABLED=true
V2_TRACK_POLL_SECONDS=5
V2_TRACK_BATCH=250

Keep the existing beta/scanner/RPC variables. Do not delete the persistent database.

## PONS V2 direct adapter
PONS V2 now has a built-in read-only adapter using Pons Portal's public API for live `progressPercent` / graduated state. The adapter fails closed on API errors. Holder data is consumed only when the endpoint explicitly exposes aggregate holder count; page length is never treated as total holders.

Stage-2 trade/sniper metrics remain mandatory. If the direct source does not expose them, the token remains `awaiting_intelligence`; configure a verified intelligence URL rather than weakening the alert gate.

## Continued Stage-2 work
- PONS V2 now uses documented live `progressPercent` for the mandatory 60% gate.
- PONS holder analysis runs only after >=60% to preserve the documented 8 req/min holder budget.
- Complete holder pagination is required before Top-10 concentration is accepted; partial pages never become a fake total.
- Developer holding percentage is derived from the deployer address when it appears in the complete holder set.
- Tracker failures are isolated per token; a 429/API error cannot stop the whole V2 batch.
- Pump.fun remains fail-closed for direct bonding progress until a verified adapter/account decoder is configured; creation is never treated as 60%.

## All-platform Stage 2 (current build)
- Flap: verified scanner bonding progress; tax/reward gate preserved; post-60 Stage-2 collector.
- STOnK: verified API graduation progress; 1-3% reward-launch gate preserved; post-60 Stage-2 collector.
- PONS: public API bonding progress + complete paginated holder concentration collector.
- EmberCurve: public market-feed bonding progress; post-60 Stage-2 collector.
- Pump.fun: bonding-curve PDA reader with reserve-based graduation progress; optional decoded provider fallback.

### Deep intelligence sources
Exact holder count, unique buyer/seller counts and sniper/bundle labels are not exposed by one first-party endpoint across all five launchpads. TrenchNet therefore supports a read-only normalized Stage-2 provider through `V2_MARKET_INTELLIGENCE_URL`, called only after the mandatory 60% gate. It never fabricates missing fields. Solana top-10 concentration is collected directly from RPC; PONS holder count/concentration uses its public paginated API. Flap EVM exact holders can use `V2_EVM_HOLDERS_URL`.

V2 remains fail-closed: if a mandatory Stage-2 field cannot be verified, the token remains `awaiting_intelligence` and no Telegram alert is sent.

## Binance Wallet/Web3 Stage-2 enrichment
V2 now uses Binance's public read-only Web3 token endpoints after the launchpad-native 60% gate for:
- Flap / BSC (`chainId=56`)
- STOnK, EmberCurve and Pump.fun / Solana (`chainId=CT_501`)

It imports only facts actually returned: metadata/social links/creator, holder count and any concentration fields present, liquidity/market cap/price, volume and any buy/sell splits/counts present, plus the Binance token audit snapshot. Binance is never used to determine bonding progress. PONS remains native because Robinhood Chain is not in Binance token-info's supported-chain list.

Optional variables:
```
BINANCE_V2_ENABLED=true
BINANCE_V2_AUDIT=true
BINANCE_V2_TIMEOUT=12
```
No Binance API key is required for these public read-only endpoints.

The bot remains fail-closed. Binance data does not fabricate sniper/bundle/unique-trader fields that the response does not provide; missing mandatory Stage-2 facts keep the token in `awaiting_intelligence`.

## Authenticated Binance Web3 Stage-2 (recommended)
The official Binance Web3 Market API can supply holder rankings, Binance-labelled sniper/bundler wallets, developer profile/history, and token trade history for BSC/Solana. Configure read-only Web3 API credentials on Railway:

```
BINANCE_WEB3_API_KEY=<your Web3 API key>
BINANCE_WEB3_SECRET_KEY=<your Web3 API secret>
BINANCE_WEB3_TIMEOUT=15
BINANCE_WEB3_TRADE_PAGES=3
V2_TRADE_WINDOW_SECONDS=3600
```

Keep these server-side only. TrenchNet signs requests with HMAC-SHA256 and the required `/build` prefix. If credentials are absent or Binance is temporarily unavailable, V2 remains fail-closed and keeps retrying; it does not manufacture missing intelligence.

## Credential-free native intelligence (2.4)
`BINANCE_WEB3_API_KEY` and `BINANCE_WEB3_SECRET_KEY` are **not required**.
For Solana launchpads, Stage 2 now derives holder count/concentration, developer holding,
recent buyer/seller counts, unique traders, and deterministic early-buyer/sniper/bundle
heuristics from Solana RPC. The heuristic labels are explicit and are only emitted when
history pagination reaches the launch window. Missing USD volume is not fabricated.
Authenticated Binance Web3 remains optional enrichment only.

## Final credential-free Stage-2 pass
- Added public, no-key DEX Screener market enrichment for recent USD volume/social confirmation on BSC/Solana.
- Added native Flap BNB Stage-2 reconstruction from documented Portal TokenBought/TokenSold events and ERC-20 Transfer logs: holders, Top-10, dev holding, recent buys/sells, unique traders, and early-wallet/sniper concentration.
- Bonding progress is still launchpad-native/on-chain and remains the mandatory first gate.
- Unique buyer/seller counts remain a hard Stage-2 gate. If a launchpad cannot verify them, the token stays awaiting_intelligence.
- Any missing mandatory fact keeps the token in awaiting_intelligence; no placeholder zero is inserted.

### PONS Stage-2 reliability patch (2026-09-24)
- PONS bonding progress tracking now reads `realQuoteReserve/graduationThreshold` directly from each stored V2 curve over `PONS_RPC_URL`; the rate-limited Portal API is no longer polled for every below-90 token.
- Post-60 creator metadata is read on-chain from token `getTokenInfo()` (description + socials).
- Post-60 CurveBuy/CurveSell logs are decoded directly from the launch curve for buys, sells, unique traders, quote volume and early-wallet/sniper metrics.
- Successful holder pages are cached into unified metadata so retries do not repeatedly spend the Portal holder budget.
- `awaiting_intelligence` rows are prioritized ahead of the below-90 tracking backlog and retry on a 20-second default backoff (`V2_INTELLIGENCE_RETRY_SECONDS`).
- Valid zero metrics (for example zero sells or zero early wallets) are preserved as real data rather than incorrectly treated as missing.

## Stage 2 Verification Engine rebuild
Stage 2 now records independent collector states for metadata, socials, holders, trading, and snipers. Valid zero metrics remain verified; source/RPC errors remain retryable errors; only an explicit verified `*_unavailable` marker may satisfy a collector without values. The tracker now invokes the shared native/public Stage-2 enrichment path after the fixed 60% gate for Flap, STOnK, EmberCurve, and Pump.fun; PONS keeps its dedicated on-chain adapter. Awaiting tokens remain priority retry work independently of the 10-minute status display window.
