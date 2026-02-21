use crate::arena_tables::{lookup_arena_slug, pad_table_for_slug, snap_to_pad, ArenaPadDef};
use std::collections::{HashMap, VecDeque};
use std::env;

#[derive(Clone, Copy, Debug)]
pub enum PadEventStatus {
    Collected,
    Respawned,
}

impl PadEventStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            PadEventStatus::Collected => "COLLECTED",
            PadEventStatus::Respawned => "RESPAWNED",
        }
    }
}

#[derive(Clone, Debug)]
pub struct PadEvent {
    pub pad_id: usize,
    pub is_big: bool,
    /// "blue" | "orange" | "mid"
    pub pad_side: &'static str,
    /// Canonical arena slug (e.g. "soccar") or "unknown".
    pub arena: &'static str,
    /// True when the arena was recognised and pad metadata comes from a verified
    /// canonical table. False when the arena slug is "unknown" — callers should
    /// treat pad_id / pad_side / is_big as unreliable in that case.
    pub arena_supported: bool,
    pub object_name: String,
    pub position: (f32, f32, f32),
    pub timestamp: f32,
    pub raw_state: u8,
    pub instigator_actor_id: Option<i32>,
    pub resolved_actor_id: Option<i32>,
    pub status: PadEventStatus,
    /// Snap distance from observed position to canonical pad centre (uu).
    pub snap_distance: Option<f32>,
    /// Alias for snap_distance, exposed as snap_error_uu in Python payload.
    pub snap_error_uu: Option<f32>,
}

#[derive(Clone, Debug)]
struct PendingEvent {
    raw_state: u8,
    timestamp: f32,
    instigator_actor_id: Option<i32>,
    resolved_actor_id: Option<i32>,
}

#[derive(Clone, Debug)]
struct PadInstance {
    object_name: String,
    pad_def: Option<ArenaPadDef>,
    position: Option<(f32, f32, f32)>,
    last_state: Option<u8>,
    last_time: f32,
    pending: VecDeque<PendingEvent>,
    snap_distance: Option<f32>,
}

impl PadInstance {
    fn new(object_name: &str, pad_def: Option<ArenaPadDef>) -> Self {
        PadInstance {
            object_name: object_name.to_string(),
            pad_def,
            position: None,
            last_state: None,
            last_time: f32::NEG_INFINITY,
            pending: VecDeque::new(),
            snap_distance: None,
        }
    }
}

pub struct PadRegistry {
    instances: HashMap<i32, PadInstance>,
    name_to_def: HashMap<String, ArenaPadDef>,
    /// Active arena slug — resolved from header map name.
    arena_slug: &'static str,
    /// Pad table for the active arena (None for unsupported arenas).
    pad_table: Option<&'static [ArenaPadDef]>,
    debug_enabled: bool,
}

impl PadRegistry {
    pub fn new() -> Self {
        Self::new_with_arena("unknown")
    }

    /// Construct a PadRegistry pre-loaded with the correct pad table for `map_name`.
    pub fn new_with_arena(map_name: &str) -> Self {
        let raw_debug = env::var("RLCOACH_DEBUG_BOOST_EVENTS").ok();
        let debug_enabled = raw_debug
            .as_deref()
            .map(|val| {
                let trimmed = val.trim();
                matches!(trimmed, "1" | "true" | "TRUE" | "True" | "on" | "ON")
            })
            .unwrap_or(false);

        let arena_slug = lookup_arena_slug(map_name).unwrap_or("unknown");
        let pad_table = pad_table_for_slug(arena_slug);

        PadRegistry {
            instances: HashMap::new(),
            name_to_def: HashMap::new(),
            arena_slug,
            pad_table,
            debug_enabled,
        }
    }

    pub fn track_new_actor(&mut self, actor_id: i32, object_name: &str) {
        if !object_name.contains("VehiclePickup_Boost_TA") {
            return;
        }
        let seed_def = self.name_to_def.get(object_name).copied();
        self.instances
            .insert(actor_id, PadInstance::new(object_name, seed_def));
    }

    pub fn remove_actor(&mut self, actor_id: i32) {
        self.instances.remove(&actor_id);
    }

    pub fn update_position(&mut self, actor_id: i32, position: (f32, f32, f32)) -> Vec<PadEvent> {
        if let Some(instance) = self.instances.get_mut(&actor_id) {
            instance.position = Some(position);
        }
        self.assign_pad_def(actor_id, Some(position));
        // snap_distance is set inside assign_pad_def; no extra calculation needed here.
        self.flush_actor(actor_id)
    }

    pub fn handle_pickup(
        &mut self,
        actor_id: i32,
        raw_state: u8,
        timestamp: f32,
        instigator_actor_id: Option<i32>,
        resolved_actor_id: Option<i32>,
        fallback_position: Option<(f32, f32, f32)>,
    ) -> Vec<PadEvent> {
        if let Some(instance) = self.instances.get_mut(&actor_id) {
            instance.pending.push_back(PendingEvent {
                raw_state,
                timestamp,
                instigator_actor_id,
                resolved_actor_id,
            });
        } else {
            // Register a placeholder so we can capture the pending event.
            let mut placeholder = PadInstance::new("VehiclePickup_Boost_TA", None);
            placeholder.pending.push_back(PendingEvent {
                raw_state,
                timestamp,
                instigator_actor_id,
                resolved_actor_id,
            });
            self.instances.insert(actor_id, placeholder);
        }
        self.assign_pad_def(actor_id, fallback_position);
        self.flush_actor(actor_id)
    }

    pub fn flush_ready_events(&mut self) -> Vec<PadEvent> {
        let keys: Vec<i32> = self.instances.keys().copied().collect();
        let mut out = Vec::new();
        for aid in keys {
            out.extend(self.flush_actor(aid));
        }
        out
    }

    fn assign_pad_def(&mut self, actor_id: i32, fallback: Option<(f32, f32, f32)>) {
        let pad_table = self.pad_table;
        if let Some(instance) = self.instances.get_mut(&actor_id) {
            if instance.pad_def.is_none() {
                let position_hint = instance.position.as_ref().copied().or(fallback);
                if let Some((px, py, pz)) = position_hint {
                    if let Some(table) = pad_table {
                        if let Some(snap) = snap_to_pad(table, px, py, pz) {
                            let def = snap.pad_def;
                            self.name_to_def.insert(instance.object_name.clone(), def);
                            instance.pad_def = Some(def);
                            if instance.position.is_none() {
                                instance.position = Some((def.x, def.y, def.z));
                                instance.snap_distance = Some(0.0);
                            } else {
                                instance.snap_distance = Some(snap.snap_error_uu);
                            }
                        }
                    }
                    // Unsupported arenas: do NOT assign a pad_def. Leaving pad_def as None
                    // prevents flush_actor from emitting events with fabricated Soccar
                    // metadata for non-standard maps (Hoops, Dropshot, etc.).
                }
            }
        }
    }

    fn flush_actor(&mut self, actor_id: i32) -> Vec<PadEvent> {
        let mut ready: Vec<PadEvent> = Vec::new();

        let mut should_log = false;
        if let Some(instance) = self.instances.get_mut(&actor_id) {
            let can_emit = instance.pad_def.is_some() && instance.position.is_some();
            if !can_emit {
                return ready;
            }

            while let Some(pending) = instance.pending.front() {
                let same_state = instance.last_state == Some(pending.raw_state)
                    && (pending.timestamp - instance.last_time).abs() < 1e-3;
                if same_state {
                    instance.pending.pop_front();
                    continue;
                }

                let pad_def = instance.pad_def.unwrap();
                let position = instance.position.unwrap();
                let pending = instance.pending.pop_front().unwrap();
                let status = if pending.instigator_actor_id.is_some() {
                    PadEventStatus::Collected
                } else {
                    PadEventStatus::Respawned
                };
                ready.push(PadEvent {
                    pad_id: pad_def.id,
                    is_big: pad_def.is_big,
                    pad_side: pad_def.side,
                    arena: self.arena_slug,
                    arena_supported: self.arena_slug != "unknown",
                    object_name: instance.object_name.clone(),
                    position,
                    timestamp: pending.timestamp,
                    raw_state: pending.raw_state,
                    instigator_actor_id: pending.instigator_actor_id,
                    resolved_actor_id: pending.resolved_actor_id,
                    status,
                    snap_distance: instance.snap_distance,
                    snap_error_uu: instance.snap_distance,
                });
                instance.last_state = Some(pending.raw_state);
                instance.last_time = pending.timestamp;
                should_log = true;
            }
        }

        if should_log && self.debug_enabled {
            for event in &ready {
                let instigator = event
                    .instigator_actor_id
                    .map(|id| id.to_string())
                    .unwrap_or_else(|| "None".to_string());
                let resolved = event
                    .resolved_actor_id
                    .map(|id| id.to_string())
                    .unwrap_or_else(|| "None".to_string());
                let distance = event
                    .snap_distance
                    .map(|d| format!("{:.3}", d))
                    .unwrap_or_else(|| "None".to_string());
                let position = format!(
                    "({:.1},{:.1},{:.1})",
                    event.position.0, event.position.1, event.position.2
                );
                eprintln!(
                    "[pad_registry] ts={:.3} pad_id={} actor_id={} instigator_actor_id={} position={} snap_distance={} state={} status={}",
                    event.timestamp,
                    event.pad_id,
                    resolved,
                    instigator,
                    position,
                    distance,
                    event.raw_state,
                    event.status.as_str()
                );
            }
        }

        ready
    }
}

