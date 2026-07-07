# Missing Mechanics Detection

Mechanics we should add to `src/rlcoach/analysis/mechanics.py`.

## Currently Detected
- Jump
- Double Jump
- Flip (with direction: forward/backward/left/right/diagonal)
- Wavedash
- Flip Cancel
- Half-flip
- Speedflip
- Aerial

## Missing - High Priority

| Mechanic | Detection Approach |
|----------|-------------------|
| **Fast Aerial** | Jump + boost + second jump in quick succession (<0.3s), gaining height rapidly |
| **Flip Reset** | Ball contact while airborne restores flip availability (detect flip after ball touch mid-air) |
| **Air Roll** | Sustained roll input during aerial (continuous roll rate while airborne) |

## Missing - Medium Priority

| Mechanic | Detection Approach |
|----------|-------------------|
| **Ceiling Shot** | Contact with ceiling (z near 2044) followed by aerial play |
| **Musty Flick** | Backflip with ball on car nose, ball gains significant upward velocity |
| **Dribble** | Ball on car roof (low relative velocity, ball z slightly above car z) for sustained period |
| **Flick** (generic) | Ball leaves car roof with significant velocity change during flip |
| **Power Slide** | Sideways velocity relative to car facing direction while grounded |

## Missing - Lower Priority / Freestyle

| Mechanic | Detection Approach |
|----------|-------------------|
| **Stall** | Tornado spin (air roll + opposite direction) causing hover effect |
| **Breezi Flick** | Tornado spin into flick |
| **45 Degree Flick** | Specific flip angle during dribble |
| **Bounce Dribble** | Repeated controlled ball bounces |
| **Ground Pinch** | Ball pinched between car and ground with high exit velocity |
| **Double Touch** | Two aerial touches on same possession |
| **Redirect** | Aerial touch that changes ball direction toward goal |

## Data Requirements

Some mechanics need additional tracking:
- Ball contact events (for flip resets, flicks, redirects)
- Ball-to-car relative position (for dribbles)
- Ceiling contact detection (for ceiling shots)
- Boost usage per frame (for fast aerial detection)
