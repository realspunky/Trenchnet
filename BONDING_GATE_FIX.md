# V2 bonding gate regression fix

- Canonical V2 bonding progress is always a percentage in the 0..100 range.
- Values <= 1 are no longer guessed to be fractions. `0.98` remains `0.98%`.
- Stage-2 bypass never bypasses the mandatory >=60% bonding gate.
- Missing progress fails closed, including when a migrated flag is present. A launchpad adapter must explicitly provide verified progress (100.0 for a verified completed curve).
- PONS native adapter already calculates `realQuoteReserve / graduationThreshold * 100`, so its output is canonical percent.
- Final delivery gate re-checks the stored canonical percentage immediately before Telegram delivery.

Regression checks: 0.98 blocked; 59.99 blocked; 60.0 allowed; 98.0 allowed; missing blocked.
