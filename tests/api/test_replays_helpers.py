"""Tests for replay router helper functions."""


from rlcoach.api.routers.replays import (
    _is_path_within_directory,
    _is_valid_uuid,
    _validate_replay_content,
)


def test_replays_uuid_and_path_helpers(tmp_path):
    assert _is_valid_uuid("123e4567-e89b-12d3-a456-426614174000") is True
    assert _is_valid_uuid("not-a-uuid") is False

    root = tmp_path / "uploads"
    root.mkdir()
    inside = root / "file.replay"
    inside.write_bytes(b"x")
    outside = tmp_path / "outside.replay"
    outside.write_bytes(b"x")

    assert _is_path_within_directory(inside, root) is True
    assert _is_path_within_directory(outside, root) is False


def test_validate_replay_content():
    assert _validate_replay_content(b"short") is False
    assert _validate_replay_content(b"A" * 200 + b"TAGame" + b"B" * 800) is True
    assert _validate_replay_content(b"A" * 1200) is False
