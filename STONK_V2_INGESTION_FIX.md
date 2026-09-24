# STOnK V2 ingestion fix

STOnK launch-feed detections are now written to the canonical V2 launch table immediately, before metadata, tax/reward, or bonding progress is resolved.

- Missing bonding progress remains fail-closed and cannot alert.
- Verified STOnK source `graduationProgress` is explicitly converted from its 0..1 source fraction to canonical 0..100 percent in `stonk.normalize`.
- Metadata resolution enriches the existing V2 detection instead of controlling whether V2 can see it.
- The 1%-3% transfer-fee + holder-reward rule remains in V2 qualification, not scanner intake.
- No changes were made to the other four launchpad scanners.
