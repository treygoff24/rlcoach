"""Unit tests for report metadata helpers."""

from rlcoach import report
from rlcoach.events import TimelineEvent


class TestNormalizePlaylistId:
    def test_known_playlist_normalizes_without_warning(self):
        value, warnings = report._normalize_playlist_id("standard")
        assert value == "STANDARD"
        assert warnings == []

    def test_unknown_playlist_falls_back_to_unknown_with_warning(self):
        value, warnings = report._normalize_playlist_id("ranked_hoops")
        assert value == "UNKNOWN"
        assert warnings and "ranked_hoops" in warnings[0]


class TestTimelineEventToDict:
    def test_optional_fields_with_none_are_omitted(self):
        ev = TimelineEvent(t=1.0, type="KICKOFF")
        entry = report._timeline_event_to_dict(ev)
        assert entry == {"t": 1.0, "type": "KICKOFF"}
