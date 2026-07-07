# S1 WP6b Noise-Floor Measurement

Date: 2026-07-07

## Method

Measured null-hypothesis residuals on the frozen S1 dev set in
`assets/s1_dev_set.json`: 6 committed fixtures plus 4 seeded 251202 replays.
No replay substitutions were made.

Export command:

```bash
source /Users/treygoff/Code/rlcoach/.venv/bin/activate
python scripts/export_series_json.py <replay> > /tmp/rlinput-dev-series-wp6b/<stem>.json
```

Measurement command:

```bash
RLINPUT_DEV_SERIES_DIR=/tmp/rlinput-dev-series-wp6b \
  cargo test -p rlinput --features sim noise_floor_measurement -- --ignored --nocapture
```

Selection is code-only in `parsers/rlinput/src/fit.rs`:

- AIR intervals from `segment_replay`.
- no segment/proximity/boundary flags on the interval.
- no component raw-counter edge and no component vector event in the interval.
- replicated zero-input guard: neutral throttle/steer raw, no handbrake, no boost-active, no boost amount drain.
- no boost acceleration signature by the existing airborne boost solver.
- angular-velocity change explainable by damping: inverse aerial controls for pitch/yaw/roll must all be within `0.12`.

Each selected interval rolls the observed frame-k state forward one interval on
`RocketSimEngine` in TheVoid with zero controls and carried-forward boost state.
Residuals are measured against observed frame k+1 for position norm, velocity
norm, geodesic rotation angle, and angular-velocity norm.

## Estimator choice

Chosen σ = pooled p68 residual for each term. p68 is a robust one-sigma-like
scale for the scoring terms while staying less tail-driven than p90/p95. The
tails are still reported because replay interpolation/sync artifacts are not
Gaussian.

## Results

Pooled quiet intervals: **1,047**.

| replay | intervals | pos p50 | pos p68 | pos p90 | pos p95 | pos p99 | vel p50 | vel p68 | vel p90 | vel p95 | vel p99 | rot p50 | rot p68 | rot p90 | rot p95 | rot p99 | ang p50 | ang p68 | ang p90 | ang p95 | ang p99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0925 | 125 | 65.134 | 73.956 | 87.904 | 96.839 | 128.269 | 21.667 | 21.667 | 27.113 | 37.843 | 43.253 | 0.006404 | 0.012956 | 0.020520 | 0.026638 | 0.028639 | 0.016404 | 0.034007 | 0.066644 | 0.099219 | 0.137620 |
| 3D6CDD7F418048C2AA2A11ACC588094D | 81 | 72.863 | 76.037 | 95.854 | 105.706 | 129.173 | 21.667 | 21.667 | 27.083 | 37.843 | 37.843 | 0.010266 | 0.014244 | 0.019317 | 0.021640 | 0.027953 | 0.029813 | 0.036323 | 0.057738 | 0.069065 | 0.108252 |
| 4985385d-2a6a-4bea-a312-8e539c7fd098 | 183 | 57.539 | 74.401 | 110.554 | 115.081 | 129.163 | 21.667 | 21.697 | 32.500 | 32.500 | 37.937 | 0.008652 | 0.015602 | 0.027222 | 0.035603 | 0.046650 | 0.024500 | 0.046504 | 0.094675 | 0.126183 | 0.197044 |
| 6804bd43-5415-49f4-b7d0-31b168c871ed | 24 | 33.661 | 38.857 | 61.728 | 61.728 | 68.547 | 21.667 | 21.667 | 21.667 | 21.667 | 27.023 | 0.014477 | 0.019224 | 0.024936 | 0.025117 | 0.028855 | 0.047658 | 0.051528 | 0.086634 | 0.091619 | 0.131294 |
| 70c0e78e-ea32-4722-a951-937baa40efc9 | 114 | 68.925 | 73.194 | 95.866 | 126.911 | 131.524 | 21.667 | 21.667 | 27.113 | 37.843 | 37.953 | 0.008429 | 0.012592 | 0.020121 | 0.025485 | 0.028161 | 0.020350 | 0.034626 | 0.061370 | 0.098135 | 0.138031 |
| 769971A8447DB11ABD813990572B53B1 | 93 | 72.794 | 76.682 | 93.020 | 129.167 | 161.073 | 21.667 | 27.023 | 37.843 | 37.953 | 48.663 | 0.005546 | 0.010415 | 0.019199 | 0.021706 | 0.024889 | 0.012537 | 0.021288 | 0.051795 | 0.063977 | 0.106594 |
| 77253f53-0654-4565-b18e-e77ddbb84282 | 135 | 71.665 | 76.694 | 95.966 | 117.411 | 132.634 | 21.667 | 21.693 | 27.117 | 37.843 | 37.953 | 0.012826 | 0.016261 | 0.025041 | 0.029485 | 0.032412 | 0.038647 | 0.055750 | 0.109670 | 0.138179 | 0.145406 |
| 7A51ECF34B1E94EFE3B049B1DC0A8F7E | 196 | 55.735 | 66.273 | 79.990 | 92.789 | 114.798 | 21.667 | 21.667 | 27.083 | 27.113 | 37.843 | 0.006888 | 0.011482 | 0.019162 | 0.020848 | 0.027570 | 0.018682 | 0.029148 | 0.045577 | 0.058702 | 0.086372 |
| F5BB1FF44EB9B29EE9EF9C9ACA51BA7C | 3 | 74.904 | 74.904 | 74.904 | 74.904 | 74.904 | 21.667 | 21.667 | 21.667 | 21.667 | 21.667 | 0.018677 | 0.018677 | 0.018677 | 0.018677 | 0.018677 | 0.054564 | 0.054564 | 0.054564 | 0.054564 | 0.054564 |
| testing_replay | 93 | 67.456 | 71.533 | 88.104 | 89.685 | 125.034 | 21.667 | 21.667 | 27.113 | 37.843 | 37.953 | 0.012430 | 0.014794 | 0.025560 | 0.029452 | 0.032589 | 0.034036 | 0.043982 | 0.095736 | 0.118445 | 0.138661 |
| **pooled** | **1,047** | **66.273** | **73.697** | **94.325** | **112.488** | **133.328** | **21.667** | **21.667** | **27.120** | **37.843** | **43.253** | **0.009239** | **0.013785** | **0.022011** | **0.027527** | **0.036349** | **0.024353** | **0.038623** | **0.074733** | **0.107891** | **0.144585** |

## Chosen σ values

| term | provisional | measured p68 σ | ratio | flag |
| --- | ---: | ---: | ---: | --- |
| position | 4 uu | 73.697 uu | 18.42x larger | **>3x** |
| velocity | 20 uu/s | 21.667 uu/s | 1.08x larger | no |
| rotation | 0.05 rad | 0.013785 rad | 3.63x smaller | **>3x** |
| angular velocity | 0.15 rad/s | 0.038623 rad/s | 3.88x smaller | **>3x** |

## Commentary

The position floor is much larger than the provisional one-tick dodge
displacement proxy. This changes discriminability: position alone cannot be
trusted for sub-tick placement when a one-tick dodge shift is about 4.67 uu.
The likely cause is replay state timebase/interpolation/net-sync mismatch:
position p68 is close to one 30 Hz frame of normal car speed, and velocity p68
is exactly one 30 Hz gravity tick (`650 / 30 = 21.667 uu/s`) in many replays.
That is plausible replicated-state noise, not physics-model noise.

Rotation and angular-velocity floors are lower than provisional, so rotational
terms should carry more event-detection weight than expected. This is also
plausible: quiet replay quaternions and angular velocities are smoother than
the deliberately conservative provisional flip-torque scales.

## Probe sanity guard

After wiring these σ values into `FitWeights::default()`, the existing
RocketSim discriminability probe was rerun:

```text
probe,dodge,samples=256,clean_accuracy=1.000,noisy_accuracy=1.000,margin_p50=2295.480,uu_shift_p50=4.665
probe,double_jump,samples=256,clean_accuracy=1.000,noisy_accuracy=0.246,margin_p50=0.033,uu_shift_p50=2.432
```

Dodge remains clean under the measured floors. Double-jump sub-tick placement
drops because the measured position floor makes the already near-degenerate
sub-tick signal weaker. This is a discriminability conclusion change; criterion
2's interval-level 30 Hz branch remains the meaningful gate-facing claim, and
WP9's oracle should report this explicitly rather than treating sub-tick
double-jump placement as reliable.
