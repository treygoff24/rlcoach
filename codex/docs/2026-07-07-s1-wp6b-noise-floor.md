# S1 WP6b Noise-Floor Measurement

Date: 2026-07-07

## Verification verdict

**STOPPED: solver-affecting replay-frame convention found.** The first WP6b
measurement below reproduced, but phase probes show the dominant position and
velocity residuals are not genuine noise floors. They carry a systematic
timebase signature: most high-velocity residual buckets have position residuals
strongly proportional to `|v_k| * Δt`, and the largest bucket has velocity p68
exactly equal to one 30 Hz gravity interval.

Do not merge the first-measurement σ values as gate-facing constants until the
solver lane decides how teacher-forced frame pairing should handle stale or
phase-shifted replay kinematics. The harness now includes
`noise_floor_phase_probes` to reproduce the evidence.

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

## First-measurement σ values (not merge-ready)

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

## Phase verification probes

Command:

```bash
RLINPUT_DEV_SERIES_DIR=/tmp/rlinput-dev-series-wp6b \
  cargo test -p rlinput --features sim noise_floor_phase_probes -- --ignored --nocapture
```

The harness also emits per-interval
`(pos_residual, vel_residual, |v_k|, N_ticks)` records when
`RLINPUT_NOISE_FLOOR_DUMP_POINTS=1` is set.

### Residual vs speed

```text
phase_correlation,count=1047,slope=0.705293,intercept=14.695380,pearson_r=0.518694
residual_bucket,name=near_zero_vel,count=16,slope=0.000138,pearson_r=0.244341,pos_p68=0.019992,vel_p68=0.016602,speed_dt_p68=79.089119
residual_bucket,name=low_vel,count=218,slope=0.314450,pearson_r=0.462657,pos_p68=38.359707,vel_p68=16.190002,speed_dt_p68=76.929733
residual_bucket,name=gravity_interval_vel,count=531,slope=0.863022,pearson_r=0.950905,pos_p68=71.576164,vel_p68=21.666687,speed_dt_p68=74.402992
residual_bucket,name=above_gravity_vel,count=282,slope=0.919519,pearson_r=0.697083,pos_p68=95.904358,vel_p68=32.426758,speed_dt_p68=76.045456
```

This is not a flat residual cloud. The largest bucket has a near-linear
position residual with slope `0.86` and `r=0.95` against `|v_k| * Δt`, while its
velocity p68 is exactly `21.6667 uu/s = 650 / 30`.

### Tick and pairing probes

```text
tick_probe,offset=-1,count=1047,pos_p50=53.459011,pos_p68=57.552464,pos_p90=107.116470,vel_p50=16.250008,vel_p68=21.666626,vel_p90=32.529938,rot_p68=0.011901,ang_vel_p68=0.033098
tick_probe,offset=0,count=1047,pos_p50=66.272842,pos_p68=73.697411,pos_p90=94.324684,vel_p50=21.666672,vel_p68=21.666748,vel_p90=27.120056,rot_p68=0.013785,ang_vel_p68=0.038623
tick_probe,offset=1,count=1047,pos_p50=73.506447,pos_p68=89.000923,pos_p90=100.686584,vel_p50=27.083282,vel_p68=27.083374,vel_p90=32.500000,rot_p68=0.015656,ang_vel_p68=0.044111
tick_probe,ticks=0,count=1047,pos_p50=0.000244,pos_p68=60.200722,pos_p90=165.981705,vel_p50=0.000122,vel_p68=27.099976,vel_p90=48.780003,rot_p68=0.006000,ang_vel_p68=0.014800
pairing_probe,kind=prev_to_frame,count=1047,pos_p50=66.272842,pos_p68=73.697411,pos_p90=94.324684,vel_p50=21.666672,vel_p68=21.666748,vel_p90=27.120056,rot_p68=0.013785,ang_vel_p68=0.038623
pairing_probe,kind=frame_to_next,count=1046,pos_p50=71.249367,pos_p68=76.695099,pos_p90=115.086266,vel_p50=21.666687,vel_p68=27.023376,vel_p90=37.893333,rot_p68=0.016486,ang_vel_p68=0.051292
pairing_probe,kind=prev_to_next,count=1046,pos_p50=28.085039,pos_p68=52.904987,pos_p90=128.058105,vel_p50=10.866730,vel_p68=16.296539,vel_p90=43.333374,rot_p68=0.009568,ang_vel_p68=0.031142
```

`N-1` improves position but does not collapse velocity; `N+1` worsens both.
`N=0` shows some frames are effectively sample-held (`pos_p50` and `vel_p50`
near zero), but p68 remains large, so this is a mixed replay-frame convention
rather than a single harness off-by-one tick. The lattice contract says
`frame_index` is the terminating observation; the baseline prev-to-frame
measurement follows that contract. The remaining issue is how replay kinematics
are sampled relative to physics and therefore affects solver scoring, not only
the measurement harness.

### Near-static subset

```text
static_subset,max_speed=100,count=0,pos_p50=NaN,pos_p68=NaN,pos_p90=NaN,vel_p50=NaN,vel_p68=NaN,vel_p90=NaN,rot_p68=NaN,ang_vel_p68=NaN
static_subset,max_speed=500,count=13,pos_p50=10.802691,pos_p68=12.039071,pos_p90=14.968403,vel_p50=21.666641,vel_p68=27.083282,vel_p90=32.499939,rot_p68=0.021295,ang_vel_p68=0.057793
```

There are no `<100 uu/s` quiet aerial intervals. The `<500 uu/s` subset is tiny
but its position p68 drops from `73.7 uu` to `12.0 uu`, matching the phase-error
prediction. Velocity does not collapse, reinforcing that the convention is not
just a position-only measurement artifact.
