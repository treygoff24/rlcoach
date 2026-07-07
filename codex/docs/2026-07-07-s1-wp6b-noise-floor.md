# S1 WP6b/WP6c Noise-Floor Measurement

Date: 2026-07-07

## Current verdict

**Corrected σ values are fresh-anchored, but residual sub-interval structure remains.**

The first WP6b measurement scored every replay frame and was rejected by the
WP6b checkpoint ruling because normalized kinematics forward-fill sample-held
`TAGame.RBActor_TA:ReplicatedRBState` frames. WP6c changes the harness and
solver scoring to score only fresh RB-state anchors: a frame is fresh when the
full `(pos, vel, quat_xyzw, ang_vel)` tuple differs bit-for-bit from the
previous frame; frame 0 and each segment's first frame are forced anchors.

Fresh anchoring collapses the old dominant phase signature: the pooled
position-residual correlation against `|v| * Δt` falls from `r=0.519` to
`r=0.075`, and the dominant velocity p68 falls from one 30 Hz gravity interval
(`21.667 uu/s`) to `10.880 uu/s`. It does **not** reach pure quantization scale
outside the near-zero residual bucket. Per the design ruling, no sub-tick offset
model is added here; the remaining structure is reported for orchestrator
follow-up.

## Method

Dev set: frozen `assets/s1_dev_set.json` — 6 committed fixtures plus 4 seeded
251202 replays. No substitutions.

Exports reused from `/tmp/rlinput-dev-series-wp6b`:

```bash
source /Users/treygoff/Code/rlcoach/.venv/bin/activate
python scripts/export_series_json.py <replay> > /tmp/rlinput-dev-series-wp6b/<stem>.json
```

Fresh-anchored measurement command:

```bash
RLINPUT_DEV_SERIES_DIR=/tmp/rlinput-dev-series-wp6b \
  cargo test -p rlinput --features sim noise_floor_measurement -- --ignored --nocapture
```

Selection remains code-only in `parsers/rlinput/src/fit.rs`:

- AIR spans from `segment_replay`.
- all constituent intervals have no segment/proximity/boundary flags.
- no component raw-counter edge and no component vector event in the span.
- replicated zero-input guard: neutral throttle/steer raw, no handbrake, no boost-active, no boost amount drain.
- no boost acceleration signature by the existing airborne boost solver.
- angular-velocity change explainable by damping: inverse aerial controls for pitch/yaw/roll must all be within `0.12`.

Each selected span rolls the observed previous fresh anchor to the next fresh
anchor on `RocketSimEngine` in TheVoid with zero controls and carried-forward
boost state. Residuals are measured for position norm, velocity norm, geodesic
rotation angle, and angular-velocity norm.

Chosen σ remains pooled p68 residual for each term: robust one-sigma-like scale,
less tail-driven than p90/p95. Tails are reported because the residuals are not
Gaussian.

## Corrected fresh-anchored results

Pooled fresh-anchored quiet spans: **400**. The count is lower than the first
measurement's 1,047 intervals because held frame terminators are collapsed into
the next fresh anchor; `F5BB1...` contributes zero qualifying fresh quiet spans.

| replay | spans | pos p50 | pos p68 | pos p90 | pos p95 | pos p99 | vel p50 | vel p68 | vel p90 | vel p95 | vel p99 | rot p50 | rot p68 | rot p90 | rot p95 | rot p99 | ang p50 | ang p68 | ang p90 | ang p95 | ang p99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0925 | 38 | 22.062 | 32.314 | 47.394 | 48.180 | 65.636 | 10.810 | 10.847 | 16.280 | 19.505 | 21.673 | 0.002930 | 0.005282 | 0.014915 | 0.017346 | 0.027108 | 0.007576 | 0.014388 | 0.047316 | 0.057698 | 0.102741 |
| 3D6CDD7F418048C2AA2A11ACC588094D | 26 | 30.134 | 37.281 | 55.590 | 60.894 | 74.187 | 10.827 | 10.847 | 16.203 | 21.727 | 21.727 | 0.004200 | 0.007469 | 0.013837 | 0.021273 | 0.027458 | 0.012033 | 0.025089 | 0.042948 | 0.063432 | 0.064944 |
| 4985385d-2a6a-4bea-a312-8e539c7fd098 | 110 | 36.128 | 52.030 | 73.481 | 91.862 | 111.131 | 10.857 | 16.263 | 21.680 | 27.010 | 32.420 | 0.003347 | 0.007934 | 0.019230 | 0.028727 | 0.036158 | 0.011159 | 0.023730 | 0.057660 | 0.093264 | 0.175500 |
| 6804bd43-5415-49f4-b7d0-31b168c871ed | 7 | 18.981 | 26.814 | 29.083 | 33.651 | 33.651 | 5.464 | 16.257 | 16.263 | 21.727 | 21.727 | 0.011472 | 0.019224 | 0.024936 | 0.028855 | 0.028855 | 0.036200 | 0.063799 | 0.091619 | 0.131294 | 0.131294 |
| 70c0e78e-ea32-4722-a951-937baa40efc9 | 28 | 26.974 | 38.347 | 57.521 | 69.501 | 72.681 | 10.847 | 16.057 | 16.310 | 21.613 | 21.693 | 0.002441 | 0.005144 | 0.015097 | 0.021815 | 0.027318 | 0.006418 | 0.012628 | 0.060017 | 0.085936 | 0.092866 |
| 769971A8447DB11ABD813990572B53B1 | 35 | 19.206 | 36.148 | 54.606 | 56.837 | 73.333 | 10.760 | 10.847 | 16.203 | 21.727 | 71.400 | 0.000691 | 0.002537 | 0.012554 | 0.013957 | 0.024889 | 0.002096 | 0.005398 | 0.030964 | 0.041056 | 0.077790 |
| 77253f53-0654-4565-b18e-e77ddbb84282 | 49 | 18.270 | 34.293 | 53.565 | 54.170 | 74.087 | 5.490 | 10.870 | 16.247 | 21.667 | 21.727 | 0.002930 | 0.005259 | 0.016950 | 0.023110 | 0.047901 | 0.009082 | 0.019097 | 0.044280 | 0.101857 | 0.109670 |
| 7A51ECF34B1E94EFE3B049B1DC0A8F7E | 73 | 18.242 | 32.413 | 49.041 | 54.776 | 61.573 | 10.827 | 10.847 | 16.247 | 16.273 | 21.637 | 0.004114 | 0.006215 | 0.019665 | 0.021295 | 0.027570 | 0.008970 | 0.015450 | 0.058158 | 0.069954 | 0.095880 |
| F5BB1FF44EB9B29EE9EF9C9ACA51BA7C | 0 | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN | NaN |
| testing_replay | 34 | 18.211 | 24.813 | 53.318 | 53.680 | 57.528 | 5.490 | 10.827 | 16.257 | 16.273 | 16.310 | 0.003010 | 0.007042 | 0.019261 | 0.027038 | 0.032589 | 0.018176 | 0.028421 | 0.054663 | 0.085460 | 0.138909 |
| **pooled** | **400** | **21.272** | **36.285** | **57.481** | **71.537** | **92.199** | **10.827** | **10.880** | **21.613** | **21.680** | **27.090** | **0.003010** | **0.006366** | **0.017974** | **0.024936** | **0.032589** | **0.008634** | **0.020347** | **0.057660** | **0.077790** | **0.131294** |

## Span-length buckets

| fresh-anchor span | count | pos p50 | pos p68 | pos p90 | pos p95 | pos p99 | vel p50 | vel p68 | vel p90 | vel p95 | vel p99 | rot p50 | rot p68 | rot p90 | rot p95 | rot p99 | ang p50 | ang p68 | ang p90 | ang p95 | ang p99 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 frame | 202 | 32.530 | 37.543 | 64.551 | 73.631 | 107.151 | 10.847 | 16.203 | 21.680 | 21.697 | 32.420 | 0.007580 | 0.013655 | 0.024936 | 0.028855 | 0.036158 | 0.024145 | 0.040676 | 0.075963 | 0.105993 | 0.141118 |
| 2 frames | 153 | 17.340 | 18.897 | 49.247 | 54.026 | 57.537 | 5.447 | 5.477 | 16.177 | 16.220 | 16.310 | 0.001544 | 0.002762 | 0.005282 | 0.006329 | 0.012554 | 0.004477 | 0.007854 | 0.017412 | 0.023730 | 0.054972 |
| 3 frames | 45 | 33.306 | 53.318 | 65.367 | 73.333 | 75.756 | 10.907 | 16.220 | 21.727 | 21.727 | 21.740 | 0.001292 | 0.005524 | 0.008816 | 0.011472 | 0.023110 | 0.003408 | 0.013253 | 0.033515 | 0.045436 | 0.101857 |

Residuals still vary materially with span. Two-frame anchors are materially
cleaner than one- or three-frame anchors, which is consistent with remaining
sub-interval phase structure. This is reported only; no sub-tick offset model is
introduced in WP6c.

## σ values now wired into `FitWeights::default()`

| term | provisional | first measurement | corrected fresh p68 σ | first -> corrected | provisional -> corrected |
| --- | ---: | ---: | ---: | ---: | ---: |
| position | 4 uu | 73.697 uu | 36.285 uu | 0.49x | 9.07x larger |
| velocity | 20 uu/s | 21.667 uu/s | 10.880 uu/s | 0.50x | 0.54x smaller |
| rotation | 0.05 rad | 0.013785 rad | 0.006366 rad | 0.46x | 7.85x smaller |
| angular velocity | 0.15 rad/s | 0.038623 rad/s | 0.020347 rad/s | 0.53x | 7.37x smaller |

The first-measurement constants remain here as audit-trail only. They were
rejected because they scored held kinematic observations as if they were fresh
physics samples.

## Phase verification probes

Fresh-anchored command:

```bash
RLINPUT_DEV_SERIES_DIR=/tmp/rlinput-dev-series-wp6b \
  cargo test -p rlinput --features sim noise_floor_phase_probes -- --ignored --nocapture
```

Before / first measurement:

```text
phase_correlation,count=1047,slope=0.705293,intercept=14.695380,pearson_r=0.518694
residual_bucket,name=near_zero_vel,count=16,pos_p68=0.019992,vel_p68=0.016602
residual_bucket,name=gravity_interval_vel,count=531,slope=0.863022,pearson_r=0.950905,pos_p68=71.576164,vel_p68=21.666687
```

After / fresh-anchored:

```text
phase_correlation,count=400,slope=0.028007,intercept=25.348014,pearson_r=0.075073
residual_bucket,name=near_zero_vel,count=59,slope=0.000152,pearson_r=0.469765,pos_p68=0.033171,vel_p68=0.059875
residual_bucket,name=low_vel,count=294,slope=0.059559,pearson_r=0.235322,pos_p68=36.035557,vel_p68=10.856689
residual_bucket,name=gravity_interval_vel,count=38,slope=0.171454,pearson_r=0.605624,pos_p68=71.940659,vel_p68=21.680115
residual_bucket,name=above_gravity_vel,count=9,slope=0.887495,pearson_r=0.862139,pos_p68=95.228691,vel_p68=32.419800
```

Interpretation: the old dominant linear position signature is largely gone, and
near-zero residuals are now near quantization scale with more samples. The
low/gravity/above-gravity buckets still show phase-structured residuals, so
sub-tick offset modeling remains an orchestrator decision.

## Discriminability sanity guard

Command:

```bash
cargo test -p rlinput --features sim discriminability_probe_dodges_and_double_jumps -- --ignored --nocapture
```

Fresh-anchored σ results:

```text
probe,dodge,samples=256,clean_accuracy=1.000,noisy_accuracy=1.000,margin_p50=8283.572,uu_shift_p50=4.665
probe,double_jump,samples=256,clean_accuracy=1.000,noisy_accuracy=0.320,margin_p50=0.130,uu_shift_p50=2.432
```

Dodge remains perfect. Double-jump noisy sub-tick placement improves from the
first-measurement run (`0.246`) to `0.320`, but remains near-degenerate relative
to its ~2.4 uu one-tick shift.

## 0925 seeded-vs-unseeded flip agreement

Command:

```bash
RLINPUT_SERIES_JSON=/tmp/rlinput-dev-series-wp6b/0925.json \
  cargo test -p rlinput --features sim exported_0925_unseeded_flip_agreement_and_wall_time -- --ignored --nocapture
```

Result:

```text
0925_unseeded,seeded_flip_intervals=409,unseeded_flip_intervals=725,agreement=0.110,wall_time_seconds=0.604
```

This does **not** rise materially from the recorded `0.108`. Per the checkpoint
ruling, that is critical information: fresh anchoring and corrected σ do not by
themselves fix WP7's unseeded flip agreement; the likely remaining defect is in
candidate generation/ranking rather than the WP6b held-sample noise floor.
