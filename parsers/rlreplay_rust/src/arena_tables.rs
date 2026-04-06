/// Canonical per-arena boost pad tables and fuzzy snapping helpers.
///
/// All pad positions are in Unreal Units (uu). The standard Soccar field has 34 pads
/// (6 big, 28 small). Unsupported arenas (Hoops, Dropshot) return None from
/// `lookup_arena_slug`.
///
/// Side classification:
///   "blue"   — pad is in the blue team's half (y < -2000 approximately)
///   "orange" — pad is in the orange team's half (y > 2000 approximately)
///   "mid"    — pad is in the midfield zone (abs(y) <= 2000)
///
/// Snap tolerances (default):
///   big pads:   200 uu
///   small pads: 160 uu

#[derive(Clone, Copy, Debug)]
pub struct ArenaPadDef {
    pub id: usize,
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub is_big: bool,
    /// "blue" | "orange" | "mid"
    pub side: &'static str,
}

pub struct SnapResult {
    pub pad_def: ArenaPadDef,
    /// Distance from the observed position to the canonical pad centre (uu).
    pub snap_error_uu: f32,
}

/// Default snap tolerances in uu.
pub const SNAP_TOLERANCE_BIG_UU: f32 = 200.0;
pub const SNAP_TOLERANCE_SMALL_UU: f32 = 160.0;

fn distance_3d(ax: f32, ay: f32, az: f32, b: &ArenaPadDef) -> f32 {
    let dx = ax - b.x;
    let dy = ay - b.y;
    let dz = az - b.z;
    (dx * dx + dy * dy + dz * dz).sqrt()
}

/// Try to snap an observed pad position to the nearest canonical pad definition.
/// Returns `None` if no candidate is within the snap tolerance.
pub fn snap_to_pad(pads: &[ArenaPadDef], x: f32, y: f32, z: f32) -> Option<SnapResult> {
    let mut best: Option<(f32, usize)> = None;
    for (idx, pad) in pads.iter().enumerate() {
        let dist = distance_3d(x, y, z, pad);
        let tolerance = if pad.is_big {
            SNAP_TOLERANCE_BIG_UU
        } else {
            SNAP_TOLERANCE_SMALL_UU
        };
        if dist <= tolerance {
            match best {
                None => best = Some((dist, idx)),
                Some((best_dist, _)) if dist < best_dist => best = Some((dist, idx)),
                _ => {}
            }
        }
    }
    best.map(|(dist, idx)| SnapResult {
        pad_def: pads[idx],
        snap_error_uu: dist,
    })
}

/// Map a raw map name (as reported in the replay header) to a canonical arena slug
/// used internally for table lookup. Returns `None` for unsupported arena types.
pub fn lookup_arena_slug(map_name: &str) -> Option<&'static str> {
    let lower = map_name.to_ascii_lowercase();
    // Unsupported arena types — Hoops, Dropshot, Rumble.
    if lower.contains("hoops") || lower.contains("dropshot") || lower.contains("shattershot") {
        return None;
    }
    // All standard Soccar-layout arenas share the same pad table.
    Some("soccar")
}

/// Return the canonical pad table for a given arena slug.
/// Currently only "soccar" is supported.
pub fn pad_table_for_slug(slug: &str) -> Option<&'static [ArenaPadDef]> {
    match slug {
        "soccar" => Some(SOCCAR_PADS),
        _ => None,
    }
}

/// Canonical pad table for all standard Soccar arenas.
/// Covers: DFH Stadium, Champions Field, Mannfield, Beckwith Park, Urban Central,
/// Utopia Coliseum, Wasteland, Neo Tokyo, Aqua Dome, Farmstead, Sunset Stadium,
/// Sovereign, and all their variants.
///
/// Side boundaries:
///   blue   : y < -2000
///   orange : y >  2000
///   mid    : -2000 <= y <= 2000
pub static SOCCAR_PADS: &[ArenaPadDef] = &[
    ArenaPadDef { id: 0,  x: -3584.0, y: -4096.0, z: 73.0, is_big: true,  side: "blue" },
    ArenaPadDef { id: 1,  x:  3584.0, y: -4096.0, z: 73.0, is_big: true,  side: "blue" },
    ArenaPadDef { id: 2,  x: -3584.0, y:  4096.0, z: 73.0, is_big: true,  side: "orange" },
    ArenaPadDef { id: 3,  x:  3584.0, y:  4096.0, z: 73.0, is_big: true,  side: "orange" },
    ArenaPadDef { id: 4,  x:     0.0, y: -4608.0, z: 73.0, is_big: true,  side: "blue" },
    ArenaPadDef { id: 5,  x:     0.0, y:  4608.0, z: 73.0, is_big: true,  side: "orange" },
    ArenaPadDef { id: 6,  x:     0.0, y: -4240.0, z: 70.0, is_big: false, side: "blue" },
    ArenaPadDef { id: 7,  x: -1792.0, y: -4184.0, z: 70.0, is_big: false, side: "blue" },
    ArenaPadDef { id: 8,  x:  1792.0, y: -4184.0, z: 70.0, is_big: false, side: "blue" },
    ArenaPadDef { id: 9,  x:  -940.0, y: -3308.0, z: 70.0, is_big: false, side: "blue" },
    ArenaPadDef { id: 10, x:   940.0, y: -3308.0, z: 70.0, is_big: false, side: "blue" },
    ArenaPadDef { id: 11, x:     0.0, y: -2816.0, z: 70.0, is_big: false, side: "blue" },
    ArenaPadDef { id: 12, x: -3584.0, y: -2484.0, z: 70.0, is_big: false, side: "blue" },
    ArenaPadDef { id: 13, x:  3584.0, y: -2484.0, z: 70.0, is_big: false, side: "blue" },
    ArenaPadDef { id: 14, x: -1788.0, y: -2300.0, z: 70.0, is_big: false, side: "blue" },
    ArenaPadDef { id: 15, x:  1788.0, y: -2300.0, z: 70.0, is_big: false, side: "blue" },
    ArenaPadDef { id: 16, x: -2048.0, y: -1036.0, z: 70.0, is_big: false, side: "mid" },
    ArenaPadDef { id: 17, x:     0.0, y: -1024.0, z: 70.0, is_big: false, side: "mid" },
    ArenaPadDef { id: 18, x:  2048.0, y: -1036.0, z: 70.0, is_big: false, side: "mid" },
    ArenaPadDef { id: 19, x: -1024.0, y:     0.0, z: 70.0, is_big: false, side: "mid" },
    ArenaPadDef { id: 20, x:  1024.0, y:     0.0, z: 70.0, is_big: false, side: "mid" },
    ArenaPadDef { id: 21, x: -2048.0, y:  1036.0, z: 70.0, is_big: false, side: "mid" },
    ArenaPadDef { id: 22, x:     0.0, y:  1024.0, z: 70.0, is_big: false, side: "mid" },
    ArenaPadDef { id: 23, x:  2048.0, y:  1036.0, z: 70.0, is_big: false, side: "mid" },
    ArenaPadDef { id: 24, x: -1788.0, y:  2300.0, z: 70.0, is_big: false, side: "orange" },
    ArenaPadDef { id: 25, x:  1788.0, y:  2300.0, z: 70.0, is_big: false, side: "orange" },
    ArenaPadDef { id: 26, x: -3584.0, y:  2484.0, z: 70.0, is_big: false, side: "orange" },
    ArenaPadDef { id: 27, x:  3584.0, y:  2484.0, z: 70.0, is_big: false, side: "orange" },
    ArenaPadDef { id: 28, x:     0.0, y:  2816.0, z: 70.0, is_big: false, side: "orange" },
    ArenaPadDef { id: 29, x:  -940.0, y:  3310.0, z: 70.0, is_big: false, side: "orange" },
    ArenaPadDef { id: 30, x:   940.0, y:  3308.0, z: 70.0, is_big: false, side: "orange" },
    ArenaPadDef { id: 31, x: -1792.0, y:  4184.0, z: 70.0, is_big: false, side: "orange" },
    ArenaPadDef { id: 32, x:  1792.0, y:  4184.0, z: 70.0, is_big: false, side: "orange" },
    ArenaPadDef { id: 33, x:     0.0, y:  4240.0, z: 70.0, is_big: false, side: "orange" },
];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_soccar_pad_count() {
        assert_eq!(SOCCAR_PADS.len(), 34);
    }

    #[test]
    fn test_soccar_big_pad_count() {
        let big_count = SOCCAR_PADS.iter().filter(|p| p.is_big).count();
        assert_eq!(big_count, 6);
    }

    #[test]
    fn test_soccar_small_pad_count() {
        let small_count = SOCCAR_PADS.iter().filter(|p| !p.is_big).count();
        assert_eq!(small_count, 28);
    }

    #[test]
    fn test_side_classification_coverage() {
        let blue_count = SOCCAR_PADS.iter().filter(|p| p.side == "blue").count();
        let orange_count = SOCCAR_PADS.iter().filter(|p| p.side == "orange").count();
        let mid_count = SOCCAR_PADS.iter().filter(|p| p.side == "mid").count();
        assert!(blue_count > 0);
        assert!(orange_count > 0);
        assert!(mid_count > 0);
        assert_eq!(blue_count + orange_count + mid_count, 34);
    }

    #[test]
    fn test_snap_exact_match() {
        let pad = &SOCCAR_PADS[0];
        let result = snap_to_pad(SOCCAR_PADS, pad.x, pad.y, pad.z);
        assert!(result.is_some());
        let r = result.unwrap();
        assert_eq!(r.pad_def.id, pad.id);
        assert!(r.snap_error_uu < 1e-3);
    }

    #[test]
    fn test_snap_within_tolerance() {
        // Slight offset from big pad 0 — within 200 uu
        let result = snap_to_pad(SOCCAR_PADS, -3584.0 + 50.0, -4096.0 + 50.0, 73.0);
        assert!(result.is_some());
        let r = result.unwrap();
        assert_eq!(r.pad_def.id, 0);
        assert!(r.snap_error_uu < SNAP_TOLERANCE_BIG_UU);
    }

    #[test]
    fn test_snap_outside_tolerance() {
        // Far from any pad
        let result = snap_to_pad(SOCCAR_PADS, 0.0, 0.0, 500.0);
        assert!(result.is_none());
    }

    #[test]
    fn test_lookup_arena_slug_standard() {
        assert_eq!(lookup_arena_slug("DFHStadium"), Some("soccar"));
        assert_eq!(lookup_arena_slug("cs_day_p"), Some("soccar"));
        assert_eq!(lookup_arena_slug("Wasteland_GRS_P"), Some("soccar"));
        assert_eq!(lookup_arena_slug("CHN_Stadium_P"), Some("soccar"));
    }

    #[test]
    fn test_lookup_arena_slug_unsupported() {
        assert_eq!(lookup_arena_slug("HoopsStadium_P"), None);
        assert_eq!(lookup_arena_slug("Dropshot_P"), None);
    }
}
