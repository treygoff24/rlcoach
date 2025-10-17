use std::collections::{HashMap, VecDeque};
use std::env;

#[derive(Clone, Copy, Debug)]
pub struct BoostPadDef {
    pub id: usize,
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub is_big: bool,
}

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
    pub object_name: String,
    pub position: (f32, f32, f32),
    pub timestamp: f32,
    pub raw_state: u8,
    pub instigator_actor_id: Option<i32>,
    pub resolved_actor_id: Option<i32>,
    pub status: PadEventStatus,
    pub snap_distance: Option<f32>,
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
    pad_def: Option<BoostPadDef>,
    position: Option<(f32, f32, f32)>,
    last_state: Option<u8>,
    last_time: f32,
    pending: VecDeque<PendingEvent>,
    snap_distance: Option<f32>,
}

impl PadInstance {
    fn new(object_name: &str, pad_def: Option<BoostPadDef>) -> Self {
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
    name_to_def: HashMap<String, BoostPadDef>,
    debug_enabled: bool,
}

impl PadRegistry {
    pub fn new() -> Self {
        let raw_debug = env::var("RLCOACH_DEBUG_BOOST_EVENTS").ok();
        let debug_enabled = raw_debug
            .as_deref()
            .map(|val| {
                let trimmed = val.trim();
                matches!(trimmed, "1" | "true" | "TRUE" | "True" | "on" | "ON")
            })
            .unwrap_or(false);

        PadRegistry {
            instances: HashMap::new(),
            name_to_def: HashMap::new(),
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
        if let Some(instance) = self.instances.get_mut(&actor_id) {
            if instance.pad_def.is_some() && instance.snap_distance.is_none() {
                let def = instance.pad_def.unwrap();
                instance.snap_distance = Some(distance(position, def));
            }
        }
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
        if let Some(instance) = self.instances.get_mut(&actor_id) {
            if instance.pad_def.is_none() {
                let position_hint = instance.position.as_ref().copied().or(fallback);
                if let Some(position) = position_hint {
                    if let Some(def) = nearest_pad_def(position) {
                        self.name_to_def.insert(instance.object_name.clone(), def);
                        instance.pad_def = Some(def);
                        if instance.position.is_none() {
                            instance.position = Some((def.x, def.y, def.z));
                            instance.snap_distance = Some(0.0);
                        } else if instance.snap_distance.is_none() {
                            let recorded = instance.position.unwrap();
                            instance.snap_distance = Some(distance(recorded, def));
                        }
                    }
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
                    object_name: instance.object_name.clone(),
                    position,
                    timestamp: pending.timestamp,
                    raw_state: pending.raw_state,
                    instigator_actor_id: pending.instigator_actor_id,
                    resolved_actor_id: pending.resolved_actor_id,
                    status,
                    snap_distance: instance.snap_distance,
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

fn distance(position: (f32, f32, f32), def: BoostPadDef) -> f32 {
    let dx = position.0 - def.x;
    let dy = position.1 - def.y;
    let dz = position.2 - def.z;
    (dx * dx + dy * dy + dz * dz).sqrt()
}

fn nearest_pad_def(position: (f32, f32, f32)) -> Option<BoostPadDef> {
    BOOST_PAD_DEFS.iter().copied().min_by(|a, b| {
        let da = distance(position, *a);
        let db = distance(position, *b);
        da.partial_cmp(&db).unwrap_or(std::cmp::Ordering::Equal)
    })
}

static BOOST_PAD_DEFS: [BoostPadDef; 34] = [
    BoostPadDef {
        id: 0,
        x: -3584.0,
        y: -4096.0,
        z: 73.0,
        is_big: true,
    },
    BoostPadDef {
        id: 1,
        x: 3584.0,
        y: -4096.0,
        z: 73.0,
        is_big: true,
    },
    BoostPadDef {
        id: 2,
        x: -3584.0,
        y: 4096.0,
        z: 73.0,
        is_big: true,
    },
    BoostPadDef {
        id: 3,
        x: 3584.0,
        y: 4096.0,
        z: 73.0,
        is_big: true,
    },
    BoostPadDef {
        id: 4,
        x: 0.0,
        y: -4608.0,
        z: 73.0,
        is_big: true,
    },
    BoostPadDef {
        id: 5,
        x: 0.0,
        y: 4608.0,
        z: 73.0,
        is_big: true,
    },
    BoostPadDef {
        id: 6,
        x: 0.0,
        y: -4240.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 7,
        x: -1792.0,
        y: -4184.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 8,
        x: 1792.0,
        y: -4184.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 9,
        x: -940.0,
        y: -3308.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 10,
        x: 940.0,
        y: -3308.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 11,
        x: 0.0,
        y: -2816.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 12,
        x: -3584.0,
        y: -2484.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 13,
        x: 3584.0,
        y: -2484.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 14,
        x: -1788.0,
        y: -2300.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 15,
        x: 1788.0,
        y: -2300.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 16,
        x: -2048.0,
        y: -1036.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 17,
        x: 0.0,
        y: -1024.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 18,
        x: 2048.0,
        y: -1036.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 19,
        x: -1024.0,
        y: 0.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 20,
        x: 1024.0,
        y: 0.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 21,
        x: -2048.0,
        y: 1036.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 22,
        x: 0.0,
        y: 1024.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 23,
        x: 2048.0,
        y: 1036.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 24,
        x: -1788.0,
        y: 2300.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 25,
        x: 1788.0,
        y: 2300.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 26,
        x: -3584.0,
        y: 2484.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 27,
        x: 3584.0,
        y: 2484.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 28,
        x: 0.0,
        y: 2816.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 29,
        x: -940.0,
        y: 3310.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 30,
        x: 940.0,
        y: 3308.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 31,
        x: -1792.0,
        y: 4184.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 32,
        x: 1792.0,
        y: 4184.0,
        z: 70.0,
        is_big: false,
    },
    BoostPadDef {
        id: 33,
        x: 0.0,
        y: 4240.0,
        z: 70.0,
        is_big: false,
    },
];
