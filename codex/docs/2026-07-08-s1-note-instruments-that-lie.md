# Engineering note: instruments that lie — the sample-held saga and the ruler bugs

*Internal note, 2026-07-08. Written between waves during the S1 overnight run. Not a design doc — the rulings live in `2026-07-07-s1-estimator-design.md`. This is the story, kept because the pattern will recur.*

## The pattern

Across one night of the S1 input-reconstruction sprint, nearly every "solver failure" we chased turned out to be a **measurement artifact** — either the observations weren't what we assumed, or the ruler comparing solver output to truth was comparing incompatible conventions. The solver was wrong less often than the instruments judging it.

Chronology:

1. **Sample-held observations (WP6b).** Fit residuals looked impossibly noisy; σ calibration wouldn't converge. Root cause: `ReplicatedRBState` is one atomic attribute, not resent every recorded frame — the normalizer forward-fills, so **52.6% of airborne frames are bit-identical holds**, not fresh physics samples. Every residual computed against a held frame was measuring the *hold*, not the car. Fix: bit-identity freshness mask, fresh-anchored teacher forcing, residuals only at fresh frames. Phase correlation in the noise floor fell from r=0.519 to 0.075.

2. **The agreement ruler (H4/WP7b).** Seeded-vs-unseeded agreement was computed raw-frame while events were placed on coalesced intervals. Apples to oranges; the coalesced number was the honest one.

3. **The press ruler (C19/Wave A2).** Unseeded jump-press recall read **0/539** after presses were implemented. Not a solver failure — the ruler exact-matched a coalesced component key against a raw solved frame across a known ground/air boundary convention gap: zero *by construction*. With a coalesced ±2-frame ruler: 0.577. Lesson encoded: **a literal zero after a targeted fix means the fix and the ruler are disconnected**, not that the fix failed.

4. **The null fast path (WP7b→A3).** Our own precision fix (margin-widened null fast path) became the dominant blocker of candidate enumeration on 601/1311 missed flips — the instrument-fix itself distorted the next measurement. Reverted; taxonomy shifted honestly.

5. **The adjacency hypothesis (A4) — where the pattern finally broke.** Given 1–4, the natural bet was that the flip ruler (still exact coalesced-key) was the last lying instrument. Pre-registered prediction: recall jumps and hallucinations collapse at ±1 interval. **Killed**: only 10.3% of misses have an adjacent hallucination; ±1-interval recall moves 0.370→0.434. The solver only emits 1951 flips against 3018 known — no ruler can manufacture the missing 1100. The remaining deficit is real solver work (candidate generation, tracker resource state, segment boundaries — Wave A5).

## What to keep

- **Calibrate the instrument before the model.** Before tuning anything against a metric, verify what the metric actually compares: key spaces, frame conventions, fresh-vs-held provenance, masking tautologies.
- **Replay "observations" are network state, not sensor samples.** Atomic attributes, forward-fills, replication lag (component edges lead kinematic effect by ~+2 frames, one-sided). Any truth key derived from one attribute stream and matched against another must state its convention.
- **Pre-register falsifiable predictions.** Every hypothesis this night was written down with a number before the probe ran. The confirmations were cheap wins; the *kill* (A4) was the most valuable single result — it ended the ruler saga in one probe and redirected the sprint, instead of letting a plausible story absorb another three waves.
- **Suspect any coin-flip metric.** 0.52 on a sign-agreement metric is not "52% good", it's "probably measuring noise or a dead channel". Zero and one-half are the two most suspicious numbers an evaluation can print.
- **When a precision fix lands, re-run the taxonomy.** Fixes to scoring/gating change what downstream diagnostics can see (the fast-path incident). Diagnosis order matters: probe → one fix → re-probe.
