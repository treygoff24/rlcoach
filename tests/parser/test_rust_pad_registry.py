from pathlib import Path

import pytest


def _has_rust_core():
    try:
        import rlreplay_rust  # type: ignore

        return bool(getattr(rlreplay_rust, "RUST_CORE", False))
    except Exception:
        return False


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
def test_rust_pad_registry_event_completeness():
    from rlcoach.parser import get_adapter

    adapter = get_adapter("rust")
    frames = adapter.parse_network(Path("testing_replay.replay"))

    pad_events = []
    for frame in frames.frames:
        pad_events.extend(frame.get("boost_pad_events", []))

    assert pad_events, "expected boost pad events from Rust adapter"

    required_keys = {
        "pad_id",
        "is_big",
        "object_name",
        "timestamp",
        "status",
        "position",
    }
    for event in pad_events:
        missing = required_keys - event.keys()
        assert not missing, f"event missing keys {missing}: {event}"
        assert isinstance(event["pad_id"], int)
        assert isinstance(event["is_big"], bool)
        assert isinstance(event["timestamp"], float)
        assert event["status"] in {"COLLECTED", "RESPAWNED"}
        position = event["position"]
        for axis in ("x", "y", "z"):
            assert axis in position, f"missing {axis} in position payload"

    collected_events = [event for event in pad_events if event["status"] == "COLLECTED"]
    assert collected_events, "expected collected pad events"

    for event in collected_events:
        assert "actor_id" in event, f"missing actor_id on collected event: {event}"
        if "instigator_actor_id" in event:
            assert isinstance(event["instigator_actor_id"], int)

    resolved_player = [event for event in collected_events if "player_id" in event]
    coverage = len(resolved_player) / len(collected_events)
    assert coverage >= 0.9, f"player_id resolution below threshold: {coverage:.2%}"
