# 2024-09-25 – Ballchasing Parity Harness

## What changed
- Implemented player identity utilities that emit canonical `{platform}:{id}` keys with sanitized display-name fallbacks and alias maps for legacy IDs.
- Updated normalization/report pipelines plus golden fixtures to consume the new identities end-to-end.
- Added reusable parity helpers that ingest Ballchasing CSVs, flatten rlcoach outputs, and compute tolerance-aware metric deltas.
- Introduced `tests/analysis/test_ballchasing_parity.py` (xfail) to highlight current analyzer gaps against Ballchasing baselines.
- Regenerated `out/0925.json` and `out/0925.md` with the new identity plumbing.

## Decisions & Rationale
- **Canonical IDs first:** Using `{platform}:{id}` avoids fragile index-based player IDs and makes cross-source joins deterministic.
- **Slug fallback kept but prefixed:** `slug:display-name` preserves readability while staying distinguishable from platform IDs.
- **Parity harness xfail for now:** The test prints actionable deltas yet avoids blocking CI until analyzers reach parity; once metrics converge we can drop the xfail.
- **Reusable helpers:** Housing CSV loaders and delta calculators under `rlcoach.utils.parity` avoids duplicating logic in future analyzer tickets.
