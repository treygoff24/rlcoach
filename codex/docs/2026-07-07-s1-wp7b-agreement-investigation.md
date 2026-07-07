# S1 WP7b agreement investigation

Date: 2026-07-07

## Bottom line

0925 raw-frame agreement moved from **0.110** to **0.193**. The fixed ruler also reports the coalesced fresh-span agreement, which is **0.370** on the final run:

```text
0925_unseeded,seeded_flip_intervals=409,coalesced_seeded_flip_intervals=289,unseeded_flip_intervals=292,agreement=0.193,coalesced_agreement=0.370,raw_jaccard=0.127,coalesced_jaccard=0.226,wall_time_seconds=0.733
```

The major defect was not observation σ. It was structural:

1. the agreement ruler was still raw-frame based after fresh-span coalescing;
2. reference re-score could drop the null hypothesis, making null-vs-event margins unenforceable;
3. unseeded beam state kept rejected event branches, causing second-action tracker contamination;
4. seeded edges were pinned to frame-boundary ticks instead of fit-searching within their frame window.

## Hypothesis verdicts

### H4 — ruler mismatch: confirmed

The old harness compared `(player_id, frame_index)` only. After fresh-anchored scoring, one solved interval can span held frames, so seeded raw edge frames and solved event output frames do not coalesce identically.

Final ruler diagnostic:

```text
raw_seeded=409, coalesced_seeded=289, unseeded=292
raw_hits=79, raw_recall=0.193, raw_jaccard=0.127
coalesced_hits=107, coalesced_recall=0.370, coalesced_jaccard=0.226
```

Fix: the standard 0925 check now prints both raw and coalesced agreement/Jaccard. Raw is kept for continuity; coalesced is the better post-WP6c ruler.

### H1 — missing null/event margin: partially confirmed

A null-vs-event acceptance margin reduces quiet-interval flips, but it is not the whole defect.

Corrected dev-set calibration, using coalesced known-flip intervals:

| margin | known flips | retained | retention | solved flips | quiet hallucinations |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 3018 | 1119 | 0.371 | 3575 | 2456 |
| 64 | 3018 | 1120 | 0.371 | 3167 | 2047 |
| 128 | 3018 | 1119 | 0.371 | 3100 | 1981 |
| 256 | 3018 | 1118 | 0.370 | 3041 | 1923 |

Chosen constant: `FIT_NULL_EVENT_ACCEPT_MARGIN = 256.0`. It removes 533 dev-set quiet hallucinations versus margin 0, at a one-interval known-retention cost in the coalesced ruler.

Important fix found during instrumentation: reference re-score previously took the top two portable survivors and could omit null. That produced `NaN` null margins in diagnostics and made the margin unenforceable on some event-heavy intervals. Reference re-score now preserves null plus the best event survivor.

### H2 — tracker/beam cascade: confirmed as the largest reducer

Before fixes, 0925 unseeded emitted **725** flip intervals. With corrected null preservation and beam collapse but margin overridden to 0, it emitted **341**. Final margin 256 emitted **292**.

That split points to cascade/beam corruption as the largest component: rejected or low-rank event branches were still carried in the unseeded beam, spending the second action and making later branch states legal/attractive. The fix collapses branch options to null only when null wins the margin-adjusted rank.

Final quiet-disagreement diagnostic after the fix:

```text
count=200, margin_p50=6502.343, margin_p68=15596.985, margin_p90=44241.818
margin_le_64=0, after_prior_same_segment=0, first_half=178, second_half=22
```

`after_prior_same_segment=0` is expected after the branch-collapse fix: rejected quiet flips are no longer carried forward as open event branches.

### H3 — kinematic over-generation below floors: not primary

Final quiet-disagreement diagnostics found **0** selected quiet flip disagreements with both planar velocity delta and angular-velocity delta below the corrected measured floors.

Examples still have large angular signatures or large velocity deltas, so the remaining misses are not simply "below σ" candidate triggers:

```text
frames=187..190, margin=3709.872, planar_delta=4.963, vertical_delta=0.240, ang_delta=3.253
frames=280..281, margin=60956.914, planar_delta=3733.637, vertical_delta=0.140, ang_delta=4.164
frames=621..624, margin=842.151, planar_delta=501.272, vertical_delta=-0.270, ang_delta=0.482
```

## C18 seeded tick-search restoration

Seeded edges now search tick offsets inside the lattice interval terminating at each edge's `frame_index`, instead of pinning to `interval.tick_range.1`.

Combinatoric bound:

- up to two seeded edges in a scoring span are searched jointly;
- any further seeded edges are pinned at their frame-window start.

Added test:

```text
seeded_edge_tick_search_recovers_mid_window_tick
```

It injects a seeded dodge at tick 2 inside a 4-tick frame and asserts the solved event tick is 2, not frame boundary tick 4.

## Final re-checks

- 0925 agreement: raw **0.193**, coalesced **0.370**, unseeded flips **292**, latest warm wall-time **0.733s**.
- Discriminability probe: dodge stayed **1.000 / 1.000**; double-jump stayed **1.000 clean / 0.320 noisy**.
- Noise floor: unchanged; pooled p68 remains pos **36.285175**, vel **10.880035**, rot **0.006366**, ang_vel **0.020347**.
- Null fast path: still covered by unit tests and extended safely to `max(reject_threshold, null_event_accept_margin)`.

## Remaining ambiguity

Even after structural fixes, coalesced agreement is only 0.370. The residual quiet disagreements have high event margins and non-floor kinematic signatures, so further improvement likely needs a design decision on scoring semantics or sub-frame/phase modeling rather than another σ tweak.
