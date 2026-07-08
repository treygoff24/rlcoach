use crate::{
    model::{ComponentKind, ComponentStream},
    tracker::{raw_counter_delta, EdgeEvidence, ReconstructedEdge},
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TruthFilter {
    Unfiltered,
    CounterBackedSecondActions,
}

pub fn component_edges(stream: &ComponentStream, filter: TruthFilter) -> Vec<ReconstructedEdge> {
    let edges = crate::tracker::reconstruct_seeded_edges(stream);
    match filter {
        TruthFilter::Unfiltered => edges,
        TruthFilter::CounterBackedSecondActions => edges
            .into_iter()
            .filter(|edge| {
                !is_second_action(edge.component) || counter_backed_edge(stream, edge).is_some()
            })
            .collect(),
    }
}

pub fn counter_backed_edge(
    stream: &ComponentStream,
    edge: &ReconstructedEdge,
) -> Option<(u32, u8)> {
    if edge.source == EdgeEvidence::RawCounter {
        return edge
            .counter_delta
            .filter(|delta| delta.delta_mod_256 != 0)
            .map(|delta| (edge.frame_index, delta.delta_mod_256));
    }
    counter_delta_adjacent(stream, edge.component, edge.frame_index)
}

pub fn counter_delta_adjacent(
    stream: &ComponentStream,
    component: ComponentKind,
    frame: u32,
) -> Option<(u32, u8)> {
    let frames = component_update_frames(stream, component);
    if frames.is_empty() {
        return None;
    }

    let mut candidates = Vec::with_capacity(3);
    match frames.binary_search(&frame) {
        Ok(idx) => {
            let start = idx.saturating_sub(1);
            let end = (idx + 1).min(frames.len() - 1);
            candidates.extend(frames[start..=end].iter().copied());
        }
        Err(idx) => {
            if idx > 0 {
                candidates.push(frames[idx - 1]);
            }
            if idx < frames.len() {
                candidates.push(frames[idx]);
            }
        }
    }

    candidates.into_iter().find_map(|candidate| {
        counter_delta_at_update(stream, component, candidate)
            .filter(|delta| *delta != 0)
            .map(|delta| (candidate, delta))
    })
}

pub fn component_update_frames(stream: &ComponentStream, component: ComponentKind) -> Vec<u32> {
    let mut frames = std::collections::BTreeSet::new();
    for event in &stream.events {
        if event.component == component {
            frames.insert(event.frame_index);
        }
    }
    for (idx, pair) in raw_values(stream, component).windows(2).enumerate() {
        if raw_counter_delta(pair[0], pair[1]).delta_mod_256 != 0 {
            frames.insert(idx as u32 + 1);
        }
    }
    frames.into_iter().collect()
}

fn counter_delta_at_update(
    stream: &ComponentStream,
    component: ComponentKind,
    frame: u32,
) -> Option<u8> {
    let raw = raw_values(stream, component);
    let idx = frame as usize;
    if idx > 0 && idx < raw.len() {
        let delta = raw_counter_delta(raw[idx - 1], raw[idx]).delta_mod_256;
        if delta != 0 {
            return Some(delta);
        }
    }

    let current = stream
        .events
        .iter()
        .filter(|event| event.component == component && event.frame_index == frame)
        .filter_map(|event| event.raw_value)
        .next_back()?;
    let previous = stream
        .events
        .iter()
        .filter(|event| event.component == component && event.frame_index < frame)
        .filter_map(|event| event.raw_value)
        .next_back()
        .or_else(|| idx.checked_sub(1).and_then(|prev| raw.get(prev).copied()))?;

    Some(raw_counter_delta(previous, current).delta_mod_256)
}

fn raw_values(stream: &ComponentStream, component: ComponentKind) -> &[u8] {
    match component {
        ComponentKind::Jump => &stream.jump_raw,
        ComponentKind::DodgeTorque => &stream.dodge_raw,
        ComponentKind::DoubleJumpImpulse => &stream.double_jump_raw,
        ComponentKind::Boost => &stream.boost_raw,
    }
}

fn is_second_action(component: ComponentKind) -> bool {
    matches!(
        component,
        ComponentKind::DodgeTorque | ComponentKind::DoubleJumpImpulse
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::ComponentEventIn;

    fn stream(frames: usize) -> ComponentStream {
        ComponentStream {
            jump_raw: vec![0; frames],
            dodge_raw: vec![0; frames],
            double_jump_raw: vec![0; frames],
            boost_raw: vec![0; frames],
            events: Vec::new(),
        }
    }

    #[test]
    fn filters_vector_only_second_action_resend() {
        let mut stream = stream(4);
        stream.events.push(ComponentEventIn {
            t: 0.0,
            frame_index: 2,
            component: ComponentKind::DodgeTorque,
            vector: Some([2.6, 0.0, 0.0]),
            raw_value: Some(0),
        });

        assert_eq!(
            component_edges(&stream, TruthFilter::Unfiltered)
                .into_iter()
                .filter(|edge| edge.component == ComponentKind::DodgeTorque)
                .count(),
            1
        );
        assert!(component_edges(&stream, TruthFilter::CounterBackedSecondActions).is_empty());
    }

    #[test]
    fn keeps_vector_event_adjacent_to_counter_step() {
        let mut stream = stream(5);
        stream.dodge_raw[3] = 1;
        stream.dodge_raw[4] = 1;
        stream.events.push(ComponentEventIn {
            t: 0.0,
            frame_index: 2,
            component: ComponentKind::DodgeTorque,
            vector: Some([2.6, 0.0, 0.0]),
            raw_value: Some(0),
        });

        let edges = component_edges(&stream, TruthFilter::CounterBackedSecondActions);
        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].frame_index, 2);
    }

    #[test]
    fn keeps_raw_jump_press_edges() {
        let mut stream = stream(3);
        stream.jump_raw[1] = 1;
        stream.jump_raw[2] = 1;

        let edges = component_edges(&stream, TruthFilter::CounterBackedSecondActions);
        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].component, ComponentKind::Jump);
        assert_eq!(edges[0].frame_index, 1);
    }
}
