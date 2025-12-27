# Rocket League Competitive Benchmarks: Master Reference (C2 → SSL)

> **Purpose**: This document consolidates research from multiple sources to provide the definitive benchmark data for the RLCoach AI Coaching System. It maps directly to the `benchmarks` table in `SPEC.md` and provides the coaching context needed for meaningful player analysis.

---

## Executive Summary

Building an AI coaching tool that compares player statistics against rank benchmarks requires understanding both the **numbers** and the **meaning** behind them. This master reference provides:

1. **Concrete numeric benchmarks** by rank (C2 through SSL) for import into the benchmarks table
2. **Engine-level constants** that define metric thresholds
3. **Coaching context** explaining when "more" isn't better
4. **Mode-specific adjustments** for 2v2, 3v3, and 1v1
5. **The C3→GC1 transition** patterns that predict breakthrough

### The Efficiency Paradox

The prevailing narrative suggests progression is a linear function of speed and mechanics. The data reveals otherwise: as players ascend from C2 to SSL, the correlation between raw input volume and success **inverts**. Elite players don't simply move faster—they move with greater intent, maintaining higher velocities while consuming fewer resources per momentum unit gained.

---

## Part 1: Technical Foundations

### Engine Constants

These **hard values** define how the game engine categorizes player behavior:

| Constant | Value | Unit | Purpose |
|----------|-------|------|---------|
| **Maximum speed** | 2,300 | uu/s | Hard cap for all cars |
| **Supersonic threshold** | ~2,200 | uu/s | Speed at which trail appears |
| **Boost speed threshold** | ~1,400 | uu/s | Speed achievable only with boost/dodge |
| **Slow speed threshold** | <1,400 | uu/s | Throttle-only velocity |
| **Small pad boost** | 12 | boost | 28 total on map, 5s respawn |
| **Large pad boost** | 100 | boost | 6 total on map, 10s respawn |
| **Maximum boost capacity** | 100 | boost | Tank limit |

### Rank Distribution (Season 19-20)

Understanding the **population pyramid** is critical for calibrating AI grading scales:

#### 2v2 Doubles (Primary Mode)
| Rank | Cumulative Percentile | Population Share | MMR Range |
|------|----------------------|------------------|-----------|
| Champion 2 | ~6.5% | ~3.1% | 1251-1350 |
| Champion 3 | ~3.4% | ~2.1% | 1351-1450 |
| Grand Champion 1 | ~1.27% | ~0.85% | 1451-1535 |
| Grand Champion 2 | ~0.42% | ~0.35% | 1536-1635 |
| Grand Champion 3 | ~0.09% | ~0.05% | 1636-1835 |
| Supersonic Legend | ~0.043% | ~0.04% | 1835+ |

**Critical Insight**: The C3→GC1 transition eliminates ~50% of players. The skill gap between low-GC1 and SSL is statistically wider than Gold to Champion.

---

## Part 2: Benchmark Tables by Rank

### Import Format for SPEC.md

These tables are structured for direct import into the `benchmarks` table. Each metric includes:
- **Median**: The 50th percentile for that rank
- **p25/p75**: Normal range bounds
- **Elite**: Top 10% threshold (exceptional performance)

---

### Boost Economy Metrics

#### BCPM (Boost Collected Per Minute)

> Higher ranks collect and use more boost per minute, but efficiency matters more than volume.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 300 | 250 | 330 | 350 |
| C3 | 330 | 280 | 370 | 380 |
| GC1 | 380 | 330 | 420 | 420 |
| GC2 | 400 | 350 | 450 | 450 |
| GC3 | 420 | 370 | 470 | 470 |
| SSL | 440 | 400 | 500 | 500 |

**Coaching Note**: GC teams use ~20-25% more boost/min than Champ teams. However, extreme BCPM outliers can indicate boost waste rather than efficiency.

**Mode Adjustments**:
- 3v3: Expect ~10% less per player (three players share pads)
- 1v1: BCPM is much lower (200-300) as players must be boost-frugal

#### Average Boost Amount (in tank)

> Higher-ranked players hold less boost because they spend it immediately on speed.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 35 | 30 | 40 | 25 |
| C3 | 32 | 28 | 36 | 22 |
| GC1 | 30 | 25 | 34 | 20 |
| GC2 | 28 | 24 | 32 | 18 |
| GC3 | 26 | 22 | 30 | 15 |
| SSL | 25 | 20 | 30 | 10-15 |

**Coaching Note**: Low average boost (~20 or less) indicates efficient usage—the player isn't hoarding. But near-zero could mean boost-starved. Pro players often average ~20 in tank.

**⚠️ Direction**: Lower is generally better for this metric (elite threshold is LOWER than median).

#### Time at 0 Boost (%)

> Time with no boost decreases at higher ranks—elite players mitigate empty tanks quickly.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 15% | 12% | 18% | <12% |
| C3 | 14% | 10% | 17% | <10% |
| GC1 | 12% | 8% | 15% | <8% |
| GC2 | 11% | 7% | 14% | <7% |
| GC3 | 10% | 6% | 13% | <6% |
| SSL | 8% | 5% | 10% | <5% |

**Coaching Note**: Even pros occasionally hit 0 boost—they're just quicker to grab more. High % here indicates overusing boost or poor pad collection.

**Surprising Finding**: SSL players are often comfortable operating with 0-12 boost for extended periods ("Low-Boost Confidence"). A C2 with 0 boost panics and retreats; an SSL recognizes they still have momentum and positioning presence.

#### Time at 100 Boost (%)

> Higher ranks spend very little time sitting at full boost—they spend it immediately.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 9% | 7% | 11% | <7% |
| C3 | 7% | 5% | 9% | <5% |
| GC1 | 5.5% | 4% | 7% | <4% |
| GC2 | 5% | 3% | 6% | <3% |
| GC3 | 4% | 2% | 5% | <2% |
| SSL | 3% | 1% | 4% | <2% |

**Coaching Note**: Sitting at 100 boost = missed opportunities. "Boost is only useful when spent." SSLs almost never sit on a full tank for more than a second or two.

#### Big Pads Collected (per game)

> Number of 100-boost pads DECREASES as rank rises—elite players rely on small pads.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 5.5 | 4 | 8 | N/A |
| C3 | 5 | 4 | 7 | N/A |
| GC1 | 4.5 | 3 | 6 | <4 |
| GC2 | 4 | 3 | 5 | <3 |
| GC3 | 3.5 | 2 | 5 | <3 |
| SSL | 3 | 2 | 4 | <3 |

**Coaching Note**: High big-pad count may mean over-rotating for boost. Elite players get by with very few, supplementing with small pads. "Boost starvation" tactics at high level mean opponents guard big pads.

**Mode Adjustments**:
- 3v3: Slightly more big pads (~5 for GC3 vs ~4 in 2v2) due to longer rotations
- 1v1: Big pads are critical; top players time routes to control most 100s

#### Small Pads Collected (per game)

> Small pad pickups SKYROCKET with rank—elite players "pad hop" continuously.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 25 | 20 | 30 | 35 |
| C3 | 32 | 28 | 38 | 42 |
| GC1 | 38 | 32 | 45 | 50 |
| GC2 | 45 | 38 | 52 | 55 |
| GC3 | 52 | 45 | 60 | 65 |
| SSL | 60 | 50 | 75 | 75+ |

**Coaching Note**: A Champ grabs ~25 pads/game; an SSL grabs 60+. Top players collect a pad nearly every 2 seconds during active play. Low small-pad count is a clear improvement area.

#### Boost Stolen (amount from opponent's side)

> Higher ranks make boost starving part of their game plan.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 200 | 150 | 280 | 300 |
| C3 | 300 | 220 | 380 | 420 |
| GC1 | 400 | 320 | 480 | 500 |
| GC2 | 450 | 380 | 520 | 550 |
| GC3 | 500 | 420 | 580 | 600 |
| SSL | 550 | 480 | 650 | 700 |

**Coaching Note**: GC1 typically steals ~400 boost/game (~20% of all boost consumed). By GC3/SSL, ~25-30% comes from opponent's side. Champions steal ~10-15%, often opportunistically rather than strategically.

---

### Movement Metrics

#### Average Speed (uu/s)

> Speed climbs steadily with rank—GCs are 10-20% faster than Champs on average.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 1400 | 1300 | 1500 | 1550 |
| C3 | 1500 | 1400 | 1600 | 1650 |
| GC1 | 1600 | 1500 | 1700 | 1750 |
| GC2 | 1650 | 1550 | 1750 | 1800 |
| GC3 | 1700 | 1600 | 1800 | 1850 |
| SSL | 1800 | 1700 | 1900 | 1900+ |

**Context**: Max speed is 2300 uu/s. A C3 averages ~65% of max; an SSL averages ~78% of max.

**Scientific Finding**: A 2021 study found high-ranked players play significantly faster, but within the same rank, greater speed alone didn't always predict winning. Speed must be controlled.

**Mode Adjustments**:
- 1v1: Average speed is ~100-200 uu/s lower (players deliberately slow down for control/fakes)

#### Time Supersonic (%)

> Elite players spend a larger share of the game at max speed—this is the dominant predictor of rank.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 7% | 5% | 10% | 12% |
| C3 | 10% | 7% | 14% | 16% |
| GC1 | 15% | 11% | 19% | 22% |
| GC2 | 18% | 14% | 22% | 25% |
| GC3 | 22% | 17% | 26% | 28% |
| SSL | 27% | 22% | 32% | 32%+ |

**Academic Validation**: Time spent at supersonic speed was identified as the **most predictive metric of player rank** in a 2021 scientific study (Smithies et al., 21,588 matches analyzed).

**⚠️ Non-Linear Warning**: If supersonic % is excessively high relative to peers, it may indicate ball-chasing rather than efficient play. Target 18-25% at GC level; >35% is a red flag.

#### Time at Slow Speed (%)

> Higher-ranked players have less "downtime"—hesitating, parking, or recovering slowly.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 40% | 35% | 45% | <32% |
| C3 | 35% | 30% | 40% | <28% |
| GC1 | 30% | 25% | 35% | <22% |
| GC2 | 28% | 23% | 33% | <20% |
| GC3 | 25% | 20% | 30% | <18% |
| SSL | 20% | 15% | 25% | <15% |

**Coaching Note**: Reducing slow/stationary time through better recovery mechanics and decision-making is a hallmark of reaching GC. If >33% of replay time is at very low speed, it's a sign of inefficient movement.

#### Time on Ground (%)

> As skill rises, less time is spent on the ground—more aerial and wall play.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 70% | 65% | 75% | <65% |
| C3 | 68% | 63% | 73% | <62% |
| GC1 | 65% | 60% | 70% | <58% |
| GC2 | 63% | 58% | 68% | <55% |
| GC3 | 60% | 55% | 65% | <52% |
| SSL | 57% | 50% | 62% | <50% |

**Coaching Note**: Being glued to the ground ~80% of the time is a sign of lower-ranked play. The biggest change is increased "low aerial" time—small jumps for recovery and ball control.

#### Time Low Air (%)

> Time spent in air up to ~2 car heights—increases significantly with rank.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 25% | 20% | 30% | 32% |
| C3 | 27% | 22% | 32% | 35% |
| GC1 | 30% | 25% | 35% | 38% |
| GC2 | 32% | 27% | 37% | 40% |
| GC3 | 34% | 29% | 39% | 42% |
| SSL | 36% | 30% | 42% | 45% |

#### Time High Air (%)

> Time at ceiling height or above—modest increase with rank.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 5% | 3% | 7% | 8% |
| C3 | 5% | 4% | 7% | 9% |
| GC1 | 5% | 4% | 7% | 10% |
| GC2 | 6% | 4% | 8% | 10% |
| GC3 | 6% | 5% | 9% | 11% |
| SSL | 8% | 5% | 11% | 12% |

---

### Positioning Metrics

#### Time Offensive Third (%)

> Higher ranks spend more time pressuring the opponent's end.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 20% | 15% | 25% | 28% |
| C3 | 22% | 17% | 27% | 30% |
| GC1 | 25% | 20% | 30% | 33% |
| GC2 | 27% | 22% | 32% | 35% |
| GC3 | 30% | 25% | 35% | 38% |
| SSL | 32% | 27% | 38% | 40% |

**⚠️ Non-Linear Warning**: >45% offensive third time without proportional goals indicates "Empty Pressure" and often predicts a loss via counter-attack.

#### Time Defensive Third (%)

> Defensive time doesn't drop drastically—even SSLs spend ~27% defending.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 30% | 25% | 35% | <25% |
| C3 | 30% | 25% | 35% | <25% |
| GC1 | 30% | 25% | 34% | <24% |
| GC2 | 28% | 23% | 33% | <22% |
| GC3 | 27% | 22% | 32% | <21% |
| SSL | 26% | 21% | 31% | <20% |

**Surprising Finding**: Spending MORE time in defensive third is correlated with winning in certain high-level metas. This reflects a "Counter-Attack Meta"—elite teams absorb pressure, conserve boost, then explode for transition goals.

**Coaching Logic**: Don't penalize defensive third time blindly. Analyze "Goals Conceded per Minute of Defensive Pressure." High defensive time with 0 conceded = Fortress Defense.

#### Behind Ball % (Goalside)

> Higher-level players stay behind the ball far more consistently—this predicts rank strongly.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 65% | 58% | 72% | 75% |
| C3 | 70% | 63% | 77% | 80% |
| GC1 | 75% | 68% | 82% | 85% |
| GC2 | 80% | 73% | 85% | 88% |
| GC3 | 83% | 76% | 88% | 90% |
| SSL | 86% | 80% | 90% | 92% |

**Academic Validation**: Time spent goalside of the ball was identified as a key differentiator of rank (Smithies et al., 2021).

**Coaching Note**: If >40% of time you're ahead of the ball at C3, that's likely contributing to being "hard stuck"—frequent overextensions. GCs are goalside ~80%+ of the time.

#### Average Distance to Ball (uu)

> Distance to ball shrinks at higher ranks—tighter positioning and faster challenges.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 2750 | 2400 | 3100 | <2400 |
| C3 | 2400 | 2100 | 2700 | <2100 |
| GC1 | 2200 | 1900 | 2500 | <1900 |
| GC2 | 2100 | 1850 | 2400 | <1850 |
| GC3 | 2000 | 1750 | 2300 | <1750 |
| SSL | 1900 | 1650 | 2150 | <1650 |

**⚠️ Non-Linear Warning**: Sweet spot is ~8,500-9,500 uu for RLCS. Too low = ball-chasing/crowding; too high = passive/slow to support.

#### Average Distance to Teammate (uu)

> Higher-level 2v2 teams have slightly CLOSER spacing—but not too close.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 4000 | 3500 | 4500 | <3500 |
| C3 | 3650 | 3200 | 4100 | <3200 |
| GC1 | 3250 | 2800 | 3700 | <2800 |
| GC2 | 3000 | 2600 | 3400 | <2600 |
| GC3 | 2900 | 2500 | 3300 | <2500 |
| SSL | 2700 | 2300 | 3100 | <2300 |

**Coaching Note**: ~3000 uu (one-third of field) is common in solid GC play. Many "stuck C3" duos have huge gaps—one sits in net while the other attacks 2v1. Closing that gap enables sustained pressure.

---

### Fundamentals Metrics

#### Goals per Game

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 0.6 | 0.3 | 0.9 | 1.0 |
| C3 | 0.65 | 0.35 | 0.95 | 1.05 |
| GC1 | 0.7 | 0.4 | 1.0 | 1.1 |
| GC2 | 0.75 | 0.45 | 1.05 | 1.2 |
| GC3 | 0.8 | 0.5 | 1.1 | 1.25 |
| SSL | 0.9 | 0.55 | 1.25 | 1.4 |

**RLCS Reference**: Pro players average 0.85-1.5 goals/game, with elite being 1.0+.

#### Assists per Game

> Assists increase linearly with rank—higher-level play relies more on passing.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 0.35 | 0.15 | 0.55 | 0.65 |
| C3 | 0.4 | 0.2 | 0.6 | 0.7 |
| GC1 | 0.45 | 0.25 | 0.65 | 0.75 |
| GC2 | 0.5 | 0.3 | 0.7 | 0.8 |
| GC3 | 0.55 | 0.35 | 0.75 | 0.85 |
| SSL | 0.65 | 0.4 | 0.9 | 1.0 |

**RLCS Reference**: Pro players average 0.5-1.0 assists/game, with elite being 0.75+.

#### Saves per Game

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 1.4 | 0.9 | 1.9 | 2.2 |
| C3 | 1.5 | 1.0 | 2.0 | 2.4 |
| GC1 | 1.6 | 1.1 | 2.1 | 2.5 |
| GC2 | 1.7 | 1.2 | 2.2 | 2.6 |
| GC3 | 1.8 | 1.3 | 2.3 | 2.7 |
| SSL | 2.0 | 1.4 | 2.6 | 3.0 |

**RLCS Reference**: Pro players average 1.4-2.6 saves/game, with elite being 2.0+.

#### Shots per Game

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 2.4 | 1.6 | 3.2 | 3.8 |
| C3 | 2.6 | 1.8 | 3.4 | 4.0 |
| GC1 | 2.8 | 2.0 | 3.6 | 4.2 |
| GC2 | 3.0 | 2.2 | 3.8 | 4.5 |
| GC3 | 3.2 | 2.4 | 4.0 | 4.7 |
| SSL | 3.5 | 2.6 | 4.4 | 5.0 |

**RLCS Reference**: Pro players average 3.0-4.5 shots/game, with elite being 3.5+.

**⚠️ Non-Linear Warning**: >5 shots without proportional goals = poor shot selection. Quality over quantity.

#### Shooting Percentage

> Shooting percentage actually stabilizes or slightly decreases at higher ranks.

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 25% | 18% | 32% | 35% |
| C3 | 25% | 18% | 32% | 35% |
| GC1 | 25% | 19% | 31% | 35% |
| GC2 | 26% | 19% | 33% | 36% |
| GC3 | 27% | 20% | 34% | 37% |
| SSL | 28% | 21% | 35% | 40% |

**Counter-Intuitive Finding**: Shot percentage peaks in Gold (due to poor defense) and stabilizes ~25% in Champion+. Higher-ranked defenders can save "crazy shots," reducing conversion rates across the board.

**RLCS Reference**: Pro shooting percentage ranges 25-40%, with elite being 30%+.

#### Demos Inflicted

| Rank | Median | p25 | p75 | Elite |
|------|--------|-----|-----|-------|
| C2 | 0.8 | 0.3 | 1.3 | 1.8 |
| C3 | 0.9 | 0.4 | 1.4 | 2.0 |
| GC1 | 1.0 | 0.5 | 1.5 | 2.2 |
| GC2 | 1.1 | 0.6 | 1.6 | 2.4 |
| GC3 | 1.2 | 0.7 | 1.7 | 2.5 |
| SSL | 1.4 | 0.8 | 2.0 | 2.8 |

---

## Part 3: The C3 → GC1 Transition ("Valley of Death")

### What Separates C3 from GC1

The jump from Champion 3 to Grand Champion 1 is widely considered the **hardest hurdle** in Rocket League. The primary difference is not what they CAN do, but what they DON'T do.

#### Quantified Barriers
- **MMR gap**: ~120 MMR points (approximately 12-15 net wins)
- **Population reduction**: ~50% of C3 players never reach GC1
- **Time stuck**: Players commonly report 3+ months at C3 plateau

#### Statistical Deltas

| Metric | C3 Value | GC1 Value | Delta | Coaching Implication |
|--------|----------|-----------|-------|---------------------|
| Major mistakes/game | 1.2 | 0.4 | -0.8 | GC1s make 3x fewer game-losing errors |
| Supersonic time | 10% | 15% | +5% | Significant speed advantage |
| Behind ball % | 70% | 75% | +5% | Fewer overcommits |
| Small pads/game | 32 | 38 | +6 | Better boost management |
| Avg distance to ball | 2400 | 2200 | -200 | Tighter positioning |

#### Top 7 "Hardstuck C3" Patterns

1. **Double commits** — Even 1-2 per game correlates with ~5% higher loss rate
2. **Poor pressure decisions** — Risky passes instead of taking shots
3. **Failure to self-analyze** — Justifying mistakes rather than identifying patterns
4. **Inappropriate prejumping** — Freestyle attempts without chemistry
5. **Scoreboard focus** — Using points to measure skill
6. **Ego/blame mindset** — Inability to identify own mistakes
7. **Speed without purpose** — Playing fast but inefficiently

#### GC Breakthrough Characteristics

- **Back-post rotation mastery** — Universal in high-level play
- **Consistent fast aerials** — Not optional at GC level
- **Fake challenge proficiency** — "Let them hit it to you" mindset
- **Reading random teammates** — Quick adaptation to playstyles

---

## Part 4: Mode-Specific Adjustments

### 2v2 Doubles (Primary Focus)

The hybrid meta—balance of solo mechanics and team play.

| Adjustment | Direction | Reason |
|------------|-----------|--------|
| Touches/goals per player | Higher | 2 players sharing ball vs 3 |
| Boost denial importance | More impactful | Fewer opponents to starve |
| Challenge risk | More severe | One bad challenge = open net |
| Aerial frequency | Lower | More ground play, strategic aerials |
| Dribble importance | Higher | Giving away possession is fatal |

**Key Metric**: Dribble Success Rate and Turnover Rate. High-risk aerials that result in turnover are penalized heavily.

### 3v3 Standard

High speed, aerial play, and rotation efficiency.

| Adjustment | Direction | Reason |
|------------|-----------|--------|
| Boost per player | ~10% lower | Three players share pads |
| Third man % | Track separately | Only meaningful in 3v3 |
| Aerial efficiency | Critical | Constant aerial pressure required |
| Rotation discipline | More important | 33/33/33 time split is ideal |

**Key Metric**: Aerial Efficiency (challenges won / boost used). "Winning" a challenge often just means forcing opponent to throw ball away.

**Note**: Rank inflation—a GC1 in 3v3 might only be Diamond 3 in 1v1.

### 1v1 Duel

The crucible of volatility—pure skill test.

| Adjustment | Direction | Reason |
|------------|-----------|--------|
| BCPM | Much lower (200-300) | Boost frugal to avoid overcommit |
| Average speed | Lower (~100-200 uu/s) | Deliberate slowing for control |
| Supersonic time | Lower (~10%) | Shadow defense, mind games |
| Goals per game | Higher (8-10 vs 3-5) | More scoring opportunities |

**Key Metric**: Recovery Speed ("Time to Ground"). A failed mechanic without fast recovery = guaranteed goal against.

**Note**: C2 in 1v1 is statistically much harder than C2 in 2v2—represents higher percentile.

---

## Part 5: Non-Linear Metrics (When More Isn't Better)

The AI must implement **non-linear scoring** for these metrics:

| Metric | Sweet Spot | Red Flag if Too High | Reasoning |
|--------|-----------|---------------------|-----------|
| Supersonic time % | 18-25% | >35% | May indicate ball-chasing |
| Time offensive third | 25-35% | >45% | Indicates poor rotation, open to counters |
| BCPM | Mode-appropriate | Extreme outliers | Boost waste, chasing pads not ball |
| Avg distance to ball | ~2000-2500 uu | <1500 | Ball-chasing, crowding |
| Avg distance to ball | ~2000-2500 uu | >3500 | Too passive, slow to support |
| Shots per game | 2.5-4.0 | >5 without goals | Poor shot selection |
| Big pads collected | 3-5 | >8 | Over-rotating for boost |

---

## Part 6: Win/Loss Predictors

### Statistically Significant Variables (p < 0.001)

From academic analysis of 21,588+ matches:

1. **Time at supersonic speed** — Most predictive of rank
2. **Time on ground** — Lower is better at higher ranks
3. **Shots conceded** — Fewer at higher ranks
4. **Time goalside of ball** — Defensive positioning quality

### Shot Quality > Quantity

- Number of shots is a highly significant predictor of winning
- But Shot Placement matters more than raw shots in C2-SSL
- **Solo goals** are slightly more significant predictors than assisted goals

### Classification Accuracy

A Random Forest model predicting rank from single-game statistics:
- Bronze: 69.81% accuracy
- Gold: 74.65% accuracy
- Diamond: 70.87% accuracy
- Grand Champion: 73.61% accuracy

When averaging 10-15 games, accuracy improves substantially.

---

## Part 7: Data Sources & Methodology

### Primary Sources

1. **Ballchasing.com** — 144+ million replays, all metrics available via API
   - Rate limits: 2-16 calls/second depending on Patreon tier
   - Rank filter uses legacy tiers; filter by MMR for GC1/2/3/SSL

2. **Academic Research** — Smithies et al. (2021), Scientific Reports
   - 21,588 matches analyzed
   - 65+ in-match metrics via Random Forest classification

3. **RLCS Statistics** — Professional player benchmarks (SSL ceiling)

4. **Community Analysis** — Calculated.gg archives, coaching analyses

### Benchmark Refresh Cadence

Rank benchmarks shift due to:
- Seasonal rank resets and inflation
- Meta changes (demos, bump plays, ground play emphasis)
- Overall skill progression of playerbase

**Recommendation**: Regenerate benchmarks each ranked season using fresh ballchasing data from the previous 30-60 days.

### API Methodology for Custom Extraction

```bash
Endpoint: https://ballchasing.com/api
Filters: playlist=ranked-doubles, min-rank=champion-2, max-rank=ssl

# For GC subdivision, use MMR ranges:
# GC1: 1435-1535 MMR
# GC2: 1535-1635 MMR
# GC3: 1635-1835 MMR
# SSL: 1835+ MMR

# Minimum sample: 1,000+ replays per rank tier for statistical validity
```

---

## Appendix A: Quick Reference Tables

### Benchmark Import JSON Structure

```json
{
  "metadata": {
    "source": "Master Research Compilation",
    "collected_date": "2025-01",
    "notes": "Compiled from ballchasing.com, academic research, RLCS data"
  },
  "benchmarks": [
    {
      "metric": "bcpm",
      "playlist": "DOUBLES",
      "rank_tier": "GC1",
      "median": 380,
      "p25": 330,
      "p75": 420,
      "elite": 420
    }
  ]
}
```

### Metric Direction Reference

| Metric | Direction | Notes |
|--------|-----------|-------|
| `bcpm` | ↑ | Higher is better, but watch for waste |
| `avg_boost` | ↓ | Lower is better (spending, not hoarding) |
| `time_zero_boost_s` | ↓ | Lower is better |
| `time_full_boost_s` | ↓ | Lower is better |
| `avg_speed_kph` | ↑ | Higher is better |
| `time_supersonic_s` | ↑ | Higher is better (with limits) |
| `time_slow_s` | ↓ | Lower is better |
| `behind_ball_pct` | ↑ | Higher is better |
| `goals` | ↑ | Higher is better |
| `assists` | ↑ | Higher is better |
| `saves` | ↑ | Higher is better |
| `shots` | ↑ | Higher is better (with quality) |
| `shooting_pct` | ↑ | Higher is better |
| `demos_inflicted` | ↑ | Higher is better |
| `demos_taken` | ↓ | Lower is better |

---

## Appendix B: RLCS Pro Ceiling Reference (SSL+)

These establish the **upper bound** for the coaching tool's comparison range:

### Per-Game Statistics (Individual Player, 3v3)
| Metric | Pro Range | Elite (Top Tier) |
|--------|-----------|------------------|
| Goals/game | 0.85 - 1.5 | 1.0+ |
| Assists/game | 0.5 - 1.0 | 0.75+ |
| Saves/game | 1.4 - 2.6 | 2.0+ |
| Shots/game | 3.0 - 4.5 | 3.5+ |
| Shooting % | 25% - 40% | 30%+ |
| Score/game | 350 - 550 | 450+ |

### Pro Speed & Positioning (Team Totals)
| Metric | Pro Range |
|--------|-----------|
| Average speed | 1,522 - 1,552 uu/s |
| Time at supersonic | 125 - 190 seconds |
| High air time | 37 - 75 seconds |
| Average distance to ball | 8,800 - 9,300 uu |

### xG Finding
When applying an Expected Goals model trained on high-MMR ranked games to RLCS matches, pro teams averaged only **0.6 goals per expected goal** — demonstrating RLCS defenders are ~40% more effective than even Grand Champion ranked players.

---

*This document synthesizes research from: ballchasing.com community analysis, Smithies et al. (2021) Scientific Reports study, RLCS 2024 statistics, calculated.gg archives, and coaching community analyses. Last updated: January 2025.*
