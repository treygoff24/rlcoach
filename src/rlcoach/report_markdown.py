"""Markdown composer for RLCoach replay reports.

Transforms the schema-aligned JSON replay report into a deterministic
Markdown dossier that mirrors the metric catalogue exposed by the
analysis pipeline. The composer keeps rendering logic pure so the CLI
can reuse it for file output or stdout streaming.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_NUMBER_EPSILON = 1e-9


def load_report(path: str | Path) -> dict[str, Any]:
    """Load a replay report JSON file."""
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def render_markdown(report: dict[str, Any]) -> str:
    """Render a Markdown dossier from the provided report payload."""
    if "error" in report:
        return _render_error_markdown(report)
    composer = _MarkdownComposer(report)
    return composer.build()


def write_markdown(report: dict[str, Any], out_path: Path) -> None:
    """Write Markdown output to a file atomically."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = render_markdown(report)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
        tmp_path.replace(out_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _render_error_markdown(report: dict[str, Any]) -> str:
    """Render a small Markdown document for error payloads."""
    lines = [
        "# RLCoach Replay Dossier - Error",
        "",
        "## Error Summary",
        "",
        f"- Type: {report.get('error', 'unknown_error')}",
    ]
    source = report.get("source_file") or report.get("replay_id")
    if source:
        lines.append(f"- Source: {source}")
    details = report.get("details")
    if details:
        lines.extend(["", "```", str(details), "```"])
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class _TeamEntry:
    name: str
    score: int
    players: list[str]


class _MarkdownComposer:
    """Stateful helper that constructs the Markdown output."""

    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        self.lines: list[str] = []
        self.metadata = report.get("metadata", {})
        self.quality = report.get("quality", {})
        self.teams = self._load_teams(report.get("teams", {}))
        self.players = report.get("players", [])
        self.player_index = {p.get("player_id"): p for p in self.players}
        self.analysis = report.get("analysis", {})
        self.events = report.get("events", {})
        self.match_seconds = float(self.metadata.get("duration_seconds", 0.0))
        self.match_minutes = max(self.match_seconds / 60.0, _NUMBER_EPSILON)

    def build(self) -> str:
        self._emit_heading()
        self._emit_table_of_contents()
        self._emit_front_matter()
        self._emit_team_metrics()
        self._emit_player_metrics()
        self._emit_event_timeline()
        self._emit_heatmaps()
        self._emit_appendices()
        return "\n".join(self.lines) + "\n"

    # ------------------------------------------------------------------
    # Section helpers
    # ------------------------------------------------------------------

    def _emit(self, text: str = "") -> None:
        self.lines.append(text)

    def _emit_heading(self) -> None:
        title = self.metadata.get("map") or "Rocket League Replay"
        guid = self.metadata.get("match_guid", "unknown")
        heading = f"# RLCoach Replay Dossier - {title} ({guid})"
        self._emit(heading)
        self._emit()

    def _emit_table_of_contents(self) -> None:
        toc_items = [
            "- [Front Matter](#front-matter)",
            "- [Team Metrics](#team-metrics)",
            "- [Player Metrics](#player-metrics)",
            "- [Event Timeline](#event-timeline)",
            "- [Heatmap Summaries](#heatmap-summaries)",
            "- [Appendices](#appendices)",
        ]
        self._emit("## Table of Contents")
        self._emit()
        self.lines.extend(toc_items)
        self._emit()

    def _emit_front_matter(self) -> None:
        self._emit("## Front Matter")
        self._emit()
        self._emit("### Replay Summary")
        self._emit(
            self._tabulate(
                [
                    ("Replay ID", self.report.get("replay_id", "unknown")),
                    ("Source File", self.report.get("source_file", "unknown")),
                    ("Schema Version", self.report.get("schema_version", "unknown")),
                    ("Generated At", self.report.get("generated_at_utc", "unknown")),
                ]
            )
        )
        self._emit()

        self._emit("### Match Overview")
        mutators = self.metadata.get("mutators", {})
        mutator_value = (
            "None"
            if not mutators
            else ", ".join(f"{k}:{v}" for k, v in sorted(mutators.items()))
        )
        overview_rows = [
            ("Map", self.metadata.get("map", "unknown")),
            ("Playlist", self.metadata.get("playlist", "UNKNOWN")),
            ("Team Size", str(self.metadata.get("team_size", "?"))),
            ("Duration (s)", self._fmt_num(self.match_seconds)),
            (
                "Recorded Frame Hz",
                self._fmt_num(self.metadata.get("recorded_frame_hz", 0.0)),
            ),
            ("Total Frames", str(self.metadata.get("total_frames", 0))),
            ("Overtime", "Yes" if self.metadata.get("overtime") else "No"),
            ("Engine Build", self.metadata.get("engine_build", "unknown")),
            ("Match GUID", self.metadata.get("match_guid", "unknown")),
            ("Mutators", mutator_value),
        ]
        self._emit(self._tabulate(overview_rows))
        self._emit()

        self._emit("### Parser Quality")
        parser_info = self.quality.get("parser", {})
        quality_rows = [
            ("Adapter", parser_info.get("name", "unknown")),
            ("Version", parser_info.get("version", "unknown")),
            ("Parsed Header", self._fmt_bool(parser_info.get("parsed_header", False))),
            (
                "Parsed Network",
                self._fmt_bool(parser_info.get("parsed_network_data", False)),
            ),
            ("CRC Checked", self._fmt_bool(parser_info.get("crc_checked", False))),
        ]
        self._emit(self._tabulate(quality_rows))
        warnings = list(self.quality.get("warnings", []) or [])
        if warnings:
            self._emit()
            self._emit("**Quality Warnings**")
            for warning in warnings:
                self._emit(f"- {warning}")
        self._emit()

        self._emit("### Roster Overview")
        roster_rows = []
        for team in ("BLUE", "ORANGE"):
            for player_id in self._team_player_ids(team):
                pdata = self.player_index.get(player_id, {})
                roster_rows.append(
                    (
                        pdata.get("display_name", player_id),
                        team,
                        pdata.get("player_id", player_id),
                    )
                )
        self._emit(
            self._tabulate(roster_rows, headers=("Display Name", "Team", "Player ID"))
        )
        self._emit()

    def _emit_team_metrics(self) -> None:
        self._emit("## Team Metrics")
        self._emit()
        self._emit(self._scoreboard_table())
        self._emit()
        categories = (
            (
                "Fundamentals",
                "fundamentals",
                {
                    "goals": ("Goals", "count"),
                    "assists": ("Assists", "count"),
                    "shots": ("Shots", "count"),
                    "saves": ("Saves", "count"),
                    "demos_inflicted": ("Demos For", "count"),
                    "demos_taken": ("Demos Against", "count"),
                    "score": ("Score", "score"),
                    "shooting_percentage": ("Shooting %", "percentage"),
                },
            ),
            (
                "Boost Economy",
                "boost",
                {
                    "boost_collected": ("Boost Collected", "count"),
                    "boost_stolen": ("Boost Stolen", "count"),
                    "avg_boost": ("Average Boost", "avg"),
                    "bpm": ("BPM", "rate"),
                    "bcpm": ("BCPM", "rate"),
                    "time_zero_boost_s": ("Time Zero Boost (s)", "seconds"),
                    "time_full_boost_s": ("Time 100 Boost (s)", "seconds"),
                    "big_pads": ("Big Pads", "count"),
                    "small_pads": ("Small Pads", "count"),
                    "stolen_big_pads": ("Stolen Big Pads", "count"),
                    "stolen_small_pads": ("Stolen Small Pads", "count"),
                    "overfill": ("Overfill", "count"),
                    "waste": ("Waste", "count"),
                },
            ),
            (
                "Movement",
                "movement",
                {
                    "avg_speed_kph": ("Average Speed (kph)", "avg"),
                    "time_slow_s": ("Slow Time (s)", "seconds"),
                    "time_boost_speed_s": ("Boost Speed Time (s)", "seconds"),
                    "time_supersonic_s": ("Supersonic Time (s)", "seconds"),
                    "time_ground_s": ("Ground Time (s)", "seconds"),
                    "time_low_air_s": ("Low Air Time (s)", "seconds"),
                    "time_high_air_s": ("High Air Time (s)", "seconds"),
                    "powerslide_count": ("Powerslides", "count"),
                    "powerslide_duration_s": ("Powerslide Time (s)", "seconds"),
                    "aerial_count": ("Aerials", "count"),
                    "aerial_time_s": ("Aerial Time (s)", "seconds"),
                },
            ),
            (
                "Positioning",
                "positioning",
                {
                    "time_offensive_half_s": ("Offensive Half Time (s)", "seconds"),
                    "time_defensive_half_s": ("Defensive Half Time (s)", "seconds"),
                    "time_offensive_third_s": ("Offensive Third Time (s)", "seconds"),
                    "time_middle_third_s": ("Middle Third Time (s)", "seconds"),
                    "time_defensive_third_s": ("Defensive Third Time (s)", "seconds"),
                    "behind_ball_pct": ("Behind Ball %", "percentage"),
                    "ahead_ball_pct": ("Ahead Ball %", "percentage"),
                    "avg_distance_to_ball_m": ("Avg Dist To Ball (m)", "avg"),
                    "avg_distance_to_teammate_m": ("Avg Dist To Teammate (m)", "avg"),
                    "first_man_pct": ("First Man %", "percentage"),
                    "second_man_pct": ("Second Man %", "percentage"),
                    "third_man_pct": ("Third Man %", "percentage"),
                },
            ),
            (
                "Possession & Passing",
                "passing",
                {
                    "passes_completed": ("Passes Completed", "count"),
                    "passes_attempted": ("Passes Attempted", "count"),
                    "passes_received": ("Passes Received", "count"),
                    "turnovers": ("Turnovers", "count"),
                    "give_and_go_count": ("Give & Go", "count"),
                    "possession_time_s": ("Possession Time (s)", "seconds"),
                },
            ),
            (
                "Challenges",
                "challenges",
                {
                    "contests": ("Contests", "count"),
                    "wins": ("Wins", "count"),
                    "losses": ("Losses", "count"),
                    "neutral": ("Neutral", "count"),
                    "first_to_ball_pct": ("First To Ball %", "percentage"),
                    "challenge_depth_m": ("Challenge Depth (m)", "avg"),
                    "risk_index_avg": ("Risk Index", "avg"),
                },
            ),
            (
                "Kickoffs",
                "kickoffs",
                {
                    "count": ("Kickoffs", "count"),
                    "first_possession": ("First Possession", "count"),
                    "neutral": ("Neutral", "count"),
                    "goals_for": ("Goals For", "count"),
                    "goals_against": ("Goals Against", "count"),
                    "avg_time_to_first_touch_s": (
                        "Avg Time To First Touch (s)",
                        "seconds",
                    ),
                },
            ),
            (
                "Mechanics",
                "mechanics",
                {
                    "total_flips": ("Total Flips", "count"),
                    "total_aerials": ("Total Aerials", "count"),
                    "total_wavedashes": ("Total Wavedashes", "count"),
                    "total_halfflips": ("Total Half-Flips", "count"),
                    "total_speedflips": ("Total Speedflips", "count"),
                    "total_flip_cancels": ("Total Flip Cancels", "count"),
                },
            ),
        )

        per_team = self.analysis.get("per_team", {})
        for label, key, metrics in categories:
            self._emit(f"### {label}")
            blue = per_team.get("blue", {}).get(key, {})
            orange = per_team.get("orange", {}).get(key, {})
            table_rows = []
            for metric_key, (metric_label, mtype) in metrics.items():
                row = self._format_team_metric_row(
                    metric_label, blue.get(metric_key), orange.get(metric_key), mtype
                )
                table_rows.append(row)
            headers = (
                "Metric",
                "Blue",
                "Blue Rate",
                "Orange",
                "Orange Rate",
                "Delta Blue-Orange",
            )
            self._emit(self._tabulate(table_rows, headers=headers))
            self._emit()

            # Kickoff approach distribution deserves its own breakdown
            if key == "kickoffs":
                self._emit(self._kickoff_approach_table(blue, orange))
                self._emit()

        insights = self.analysis.get("coaching_insights", []) or []
        if insights:
            self._emit("### Coaching Insights")
            for insight in insights:
                severity = insight.get("severity", "INFO")
                message = insight.get("message", "")
                self._emit(f"- **{severity}** {message}")
            self._emit()

    def _emit_player_metrics(self) -> None:
        self._emit("## Player Metrics")
        self._emit()
        per_player = self.analysis.get("per_player", {})
        ordered_players = self._ordered_player_ids()
        for pid in ordered_players:
            pdata = per_player.get(pid, {})
            roster_entry = self.player_index.get(pid, {})
            display_name = roster_entry.get("display_name", pid)
            team = roster_entry.get("team", "?")
            self._emit(f"### {display_name} ({team})")
            self._emit()
            self._emit(self._player_overview_table(pid, pdata))
            self._emit()
            self._emit(
                self._player_metric_section(
                    "Fundamentals", pdata.get("fundamentals", {})
                )
            )
            self._emit(self._player_metric_section("Boost", pdata.get("boost", {})))
            self._emit(
                self._player_metric_section("Movement", pdata.get("movement", {}))
            )
            self._emit(
                self._player_metric_section("Positioning", pdata.get("positioning", {}))
            )
            self._emit(
                self._player_metric_section(
                    "Possession & Passing", pdata.get("passing", {})
                )
            )
            self._emit(
                self._player_metric_section("Challenges", pdata.get("challenges", {}))
            )
            self._emit(
                self._player_metric_section(
                    "Kickoffs",
                    pdata.get("kickoffs", {}),
                    extra=self._player_kickoff_breakdown(pdata.get("kickoffs", {})),
                )
            )
            self._emit(self._player_mechanics_section(pdata.get("mechanics", {})))
            rotation = pdata.get("rotation_compliance", {})
            self._emit(self._player_rotation_section(rotation))
            insights = pdata.get("insights", []) or []
            if insights:
                self._emit("**Insights**")
                for insight in insights:
                    severity = insight.get("severity", "INFO")
                    message = insight.get("message", "")
                    self._emit(f"- **{severity}** {message}")
                self._emit()
            self._emit(self._player_key_value_block(pid, pdata))
            self._emit()

    def _emit_event_timeline(self) -> None:
        self._emit("## Event Timeline")
        self._emit()
        timeline_rows = []
        for event in self.events.get("timeline", []) or []:
            timeline_rows.append(self._format_timeline_row(event))
        headers = ("Time (s)", "Frame", "Event", "Player", "Details")
        self._emit(self._tabulate(timeline_rows, headers=headers))
        self._emit()

        self._emit(
            self._event_subtable(
                "Goals",
                self.events.get("goals", []),
                self._format_goal_row,
                ("Time (s)", "Frame", "Team", "Scorer", "Assist"),
            )
        )
        self._emit()
        self._emit(
            self._event_subtable(
                "Demos",
                self.events.get("demos", []),
                self._format_demo_row,
                ("Time (s)", "Attacker", "Victim", "Location"),
            )
        )
        self._emit()
        self._emit(
            self._event_subtable(
                "Boost Pickups",
                self.events.get("boost_pickups", []),
                self._format_boost_pickup_row,
                ("Time (s)", "Player", "Pad", "Stolen", "Location"),
            )
        )
        self._emit()
        self._emit(
            self._event_subtable(
                "Challenges",
                self.events.get("challenges", []),
                self._format_challenge_row,
                ("Time (s)", "Outcome", "Winner", "Loser", "Depth (m)"),
            )
        )
        self._emit()
        self._emit(
            self._event_subtable(
                "Kickoffs",
                self.events.get("kickoffs", []),
                self._format_kickoff_row,
                ("Phase", "Time Start (s)", "Outcome", "First Touch", "Approach Types"),
            )
        )
        self._emit()
        self._emit(
            self._event_subtable(
                "Touches",
                self.events.get("touches", []),
                self._format_touch_row,
                ("Time (s)", "Player", "Outcome", "Ball Speed (kph)", "Location"),
            )
        )
        self._emit()

    def _emit_heatmaps(self) -> None:
        self._emit("## Heatmap Summaries")
        self._emit()
        per_player = self.analysis.get("per_player", {})
        for pid in self._ordered_player_ids():
            pdata = per_player.get(pid, {})
            heatmaps = pdata.get("heatmaps", {}) or {}
            if not heatmaps:
                continue
            roster_entry = self.player_index.get(pid, {})
            display_name = roster_entry.get("display_name", pid)
            self._emit(f"### {display_name}")
            self._emit()
            for key in (
                "position_occupancy_grid",
                "touch_density_grid",
                "boost_pickup_grid",
                "boost_usage_grid",
            ):
                grid = heatmaps.get(key)
                label = key.replace("_", " ").title()
                if not grid:
                    self._emit(f"**{label}:** not available")
                    self._emit()
                    continue
                values = grid.get("values") or []
                self._emit(f"**{label}**")
                self._emit(self._heatmap_table(values))
                self._emit(self._heatmap_summary(values, grid))
                self._emit()
        self._emit()

    def _emit_appendices(self) -> None:
        self._emit("## Appendices")
        self._emit()
        self._emit("### Schema & Coordinate Reference")
        coord = self.metadata.get("coordinate_reference", {})
        coord_rows = [
            ("Schema Version", self.report.get("schema_version", "unknown")),
            ("Side Wall X", self._fmt_num(coord.get("side_wall_x", 0))),
            ("Back Wall Y", self._fmt_num(coord.get("back_wall_y", 0))),
            ("Ceiling Z", self._fmt_num(coord.get("ceiling_z", 0))),
        ]
        self._emit(self._tabulate(coord_rows))
        self._emit()

        self._emit("### Derived Metric Formulas")
        derived_rows = [
            ("Per Minute", "value / match_minutes"),
            ("Per Five Minutes", "value / max(match_minutes/5, eps)"),
            ("Opponent Delta", "blue_value - orange_value"),
            ("Completion %", "completed / max(attempted, 1) * 100"),
            ("Kickoff Win %", "first_possession / max(count, 1) * 100"),
        ]
        self._emit(self._tabulate(derived_rows, headers=("Metric", "Formula")))
        self._emit()

        warnings = list(self.quality.get("warnings", []) or [])
        if warnings:
            self._emit("### Quality Warnings (Copy)")
            for warning in warnings:
                self._emit(f"- {warning}")
            self._emit()

        raw_json = json.dumps(self.report, indent=2, sort_keys=True)
        self._emit("### Raw JSON Snapshot")
        self._emit("```json")
        self._emit(raw_json)
        self._emit("```")
        self._emit()

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _tabulate(
        self,
        rows: Iterable[Sequence[str | float | int]],
        headers: Sequence[str] | None = None,
    ) -> str:
        table_rows: list[list[str]] = []
        if headers:
            table_rows.append([str(h) for h in headers])
        for row in rows:
            table_rows.append([self._stringify_cell(cell) for cell in row])
        if not table_rows:
            return "*No data*"
        widths = [max(len(cell) for cell in column) for column in zip(*table_rows)]
        lines = []
        for idx, row in enumerate(table_rows):
            padded = [cell.ljust(widths[col]) for col, cell in enumerate(row)]
            line = "| " + " | ".join(padded) + " |"
            lines.append(line)
            if idx == 0 and headers:
                sep = (
                    "| "
                    + " | ".join("-" * widths[col] for col in range(len(widths)))
                    + " |"
                )
                lines.append(sep)
        return "\n" + "\n".join(lines) + "\n"

    def _stringify_cell(self, value: Any) -> str:
        if isinstance(value, (int, float)):
            if isinstance(value, float):
                return self._fmt_num(value)
            return str(value)
        if value is None or value == "":
            return "-"
        return str(value)

    def _fmt_num(self, value: Any, digits: int = 2) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "-"
        if abs(number - round(number)) < _NUMBER_EPSILON:
            return str(int(round(number)))
        return f"{number:.{digits}f}"

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _rate_per_minute_value(self, value: Any) -> float:
        base = self._safe_float(value)
        return base / self.match_minutes if self.match_minutes > 0 else 0.0

    def _rate_per_five_minutes_value(self, value: Any) -> float:
        base = self._safe_float(value)
        window = self.match_minutes / 5.0
        return base / window if window > 0 else 0.0

    def _share_pct_value(self, numerator: Any, denominator: Any) -> float:
        num = self._safe_float(numerator)
        denom = self._safe_float(denominator)
        if denom <= 0:
            return 0.0
        return (num / denom) * 100.0

    def _percentage_of_match(self, seconds_value: Any) -> float:
        seconds = self._safe_float(seconds_value)
        if self.match_seconds <= 0:
            return 0.0
        return (seconds / self.match_seconds) * 100.0

    def _fmt_bool(self, flag: Any) -> str:
        return "Yes" if bool(flag) else "No"

    def _team_player_ids(self, team_name: str) -> list[str]:
        key = "blue" if team_name == "BLUE" else "orange"
        team = self.teams.get(key)
        if not team:
            return []
        return team.players

    def _scoreboard_table(self) -> str:
        rows = []
        for key in ("blue", "orange"):
            team = self.teams.get(key)
            if not team:
                continue
            rows.append((team.name, team.score, ", ".join(team.players)))
        return self._tabulate(rows, headers=("Team", "Score", "Players"))

    def _format_team_metric_row(
        self, label: str, blue_value: Any, orange_value: Any, mtype: str
    ) -> tuple[str, str, str, str, str, str]:
        blue = self._normalize_metric_value(blue_value, mtype)
        orange = self._normalize_metric_value(orange_value, mtype)
        blue_rate = self._compute_metric_rate(blue_value, mtype)
        orange_rate = self._compute_metric_rate(orange_value, mtype)
        delta = self._metric_delta(blue_value, orange_value, mtype)
        return (
            label,
            blue,
            blue_rate,
            orange,
            orange_rate,
            delta,
        )

    def _normalize_metric_value(self, value: Any, mtype: str) -> str:
        if mtype == "percentage":
            return self._fmt_num(value) + "%"
        return self._fmt_num(value)

    def _compute_metric_rate(self, value: Any, mtype: str) -> str:
        if mtype in {"count", "seconds"}:
            base = float(value or 0.0)
            per_minute = base / self.match_minutes if self.match_minutes > 0 else 0.0
            return self._fmt_num(per_minute)
        return "-"

    def _metric_delta(self, blue_value: Any, orange_value: Any, mtype: str) -> str:
        if mtype == "percentage":
            try:
                delta = float(blue_value or 0.0) - float(orange_value or 0.0)
            except (TypeError, ValueError):
                delta = 0.0
            return self._fmt_num(delta) + "%"
        try:
            delta = float(blue_value or 0.0) - float(orange_value or 0.0)
        except (TypeError, ValueError):
            delta = 0.0
        return self._fmt_num(delta)

    def _kickoff_approach_table(
        self, blue: dict[str, Any], orange: dict[str, Any]
    ) -> str:
        b_approach = blue.get("approach_types", {}) or {}
        o_approach = orange.get("approach_types", {}) or {}
        labels = sorted({*b_approach.keys(), *o_approach.keys()})
        # Use total_approaches as denominator (total per-player entries), not kickoff count
        b_total = blue.get("total_approaches", sum(b_approach.values()) or 1)
        o_total = orange.get("total_approaches", sum(o_approach.values()) or 1)
        rows = []
        for label in labels:
            b_value = b_approach.get(label, 0)
            o_value = o_approach.get(label, 0)
            b_share = self._percentage_share(b_value, b_total)
            o_share = self._percentage_share(o_value, o_total)
            rows.append(
                (
                    label,
                    self._fmt_num(b_value),
                    f"{b_share}",
                    self._fmt_num(o_value),
                    f"{o_share}",
                )
            )
        return self._tabulate(
            rows,
            headers=("Approach", "Blue Count", "Blue %", "Orange Count", "Orange %"),
        )

    def _percentage_share(self, subset: Any, total: Any) -> str:
        try:
            value = float(subset or 0.0)
            denom = max(float(total or 0.0), 1.0)
            return f"{(value / denom) * 100:.1f}%"
        except (TypeError, ValueError):
            return "-"

    def _ordered_player_ids(self) -> list[str]:
        # Preserve team order: blue roster first, then orange.
        ordered = []
        for team in ("BLUE", "ORANGE"):
            ordered.extend(self._team_player_ids(team))
        # Add any players not captured in teams (fallback)
        for player in self.players:
            pid = player.get("player_id")
            if pid and pid not in ordered:
                ordered.append(pid)
        return ordered

    def _player_overview_table(self, pid: str, pdata: dict[str, Any]) -> str:
        roster_entry = self.player_index.get(pid, {})
        platform = roster_entry.get("platform_ids") or {}
        camera = roster_entry.get("camera") or {}
        loadout = roster_entry.get("loadout") or {}
        rows = [
            ("Player ID", pid),
            (
                "Platform IDs",
                ", ".join(f"{k}:{v}" for k, v in sorted(platform.items())) or "-",
            ),
            (
                "Camera Settings",
                ", ".join(f"{k}:{v}" for k, v in sorted(camera.items())) or "-",
            ),
            (
                "Loadout",
                ", ".join(f"{k}:{v}" for k, v in sorted(loadout.items())) or "-",
            ),
        ]
        return self._tabulate(rows)

    def _player_metric_section(
        self, title: str, metrics: dict[str, Any], extra: str | None = None
    ) -> str:
        if not metrics:
            return f"**{title}:** no data\n"
        rows = []
        for key in sorted(metrics):
            value = metrics[key]
            if isinstance(value, dict) and key == "approach_types":
                # Rendered separately in kickoff breakdown table
                continue
            label = key.replace("_", " ").title()
            formatted_value = self._fmt_metric_value(key, value)
            rate = self._player_rate_value(value, key)
            rows.append((label, formatted_value, rate))
        table = self._tabulate(rows, headers=(title, "Value", "Per Minute"))
        if extra:
            return table + extra
        return table

    def _player_rate_value(self, value: Any, key: str) -> str:
        if isinstance(value, (dict, list)):
            return "-"
        if key.endswith("_pct") or key.endswith("percentage"):
            return "-"
        if key.startswith("avg_") or key.startswith("risk"):
            return "-"
        if value is None or value == "":
            return "-"
        try:
            base = float(value)
        except (TypeError, ValueError):
            return "-"
        per_minute = base / self.match_minutes if self.match_minutes > 0 else 0.0
        return self._fmt_num(per_minute)

    def _fmt_metric_value(self, key: str, value: Any) -> str:
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True)
        if isinstance(value, list):
            return ", ".join(str(v) for v in value) if value else "-"
        if key.endswith("_pct") or key.endswith("percentage"):
            return self._fmt_num(value) + "%"
        if key.endswith("_s"):
            return self._fmt_num(value)
        return self._fmt_num(value)

    def _player_kickoff_breakdown(self, kickoffs: dict[str, Any]) -> str:
        if not kickoffs:
            return ""
        approaches = kickoffs.get("approach_types", {}) or {}
        # For per-player, the denominator is the player's total kickoffs (count)
        # since each player has exactly one approach per kickoff
        total = kickoffs.get("count", sum(approaches.values()) or 1)
        rows = []
        for approach, count in sorted(approaches.items()):
            share = self._percentage_share(count, total)
            rows.append((approach.title(), self._fmt_num(count), share))
        if rows:
            return self._tabulate(rows, headers=("Approach", "Count", "Share"))
        return ""

    def _player_mechanics_section(self, mechanics: dict[str, Any]) -> str:
        """Render player mechanics table."""
        if not mechanics:
            return "**Mechanics:** no data\n"
        rows = [
            ("Jumps", self._fmt_num(mechanics.get("jump_count", 0))),
            ("Double Jumps", self._fmt_num(mechanics.get("double_jump_count", 0))),
            ("Flips", self._fmt_num(mechanics.get("flip_count", 0))),
            ("Wavedashes", self._fmt_num(mechanics.get("wavedash_count", 0))),
            ("Aerials", self._fmt_num(mechanics.get("aerial_count", 0))),
            ("Half-Flips", self._fmt_num(mechanics.get("halfflip_count", 0))),
            ("Speedflips", self._fmt_num(mechanics.get("speedflip_count", 0))),
            ("Flip Cancels", self._fmt_num(mechanics.get("flip_cancel_count", 0))),
            ("Total Mechanics", self._fmt_num(mechanics.get("total_mechanics", 0))),
        ]
        return self._tabulate(rows, headers=("Mechanic", "Count"))

    def _player_rotation_section(self, rotation: dict[str, Any]) -> str:
        if not rotation:
            return "**Rotation Compliance:** no data\n"
        score = rotation.get("score_0_to_100", 0)
        flags = rotation.get("flags", []) or []
        lines = [f"**Rotation Compliance Score:** {self._fmt_num(score)}"]
        if flags:
            for flag in flags:
                lines.append(f"- {flag}")
        return "\n".join(lines) + "\n"

    def _player_derived_metrics(self, pdata: dict[str, Any]) -> dict[str, Any]:
        derived: dict[str, Any] = {}
        fundamentals = pdata.get("fundamentals", {}) or {}
        if fundamentals:
            derived["fundamentals"] = {
                "goals_per_min": round(
                    self._rate_per_minute_value(fundamentals.get("goals")), 4
                ),
                "shots_per_min": round(
                    self._rate_per_minute_value(fundamentals.get("shots")), 4
                ),
                "saves_per_min": round(
                    self._rate_per_minute_value(fundamentals.get("saves")), 4
                ),
                "demos_inflicted_per_min": round(
                    self._rate_per_minute_value(fundamentals.get("demos_inflicted")), 4
                ),
                "goals_per_5_min": round(
                    self._rate_per_five_minutes_value(fundamentals.get("goals")), 4
                ),
                "shooting_pct": round(
                    self._safe_float(fundamentals.get("shooting_percentage")), 2
                ),
            }
        boost = pdata.get("boost", {}) or {}
        if boost:
            derived["boost"] = {
                "collected_per_min": round(
                    self._rate_per_minute_value(boost.get("boost_collected")), 3
                ),
                "stolen_per_min": round(
                    self._rate_per_minute_value(boost.get("boost_stolen")), 3
                ),
                "zero_boost_pct": round(
                    self._percentage_of_match(boost.get("time_zero_boost_s")), 2
                ),
                "hundred_boost_pct": round(
                    self._percentage_of_match(boost.get("time_full_boost_s")), 2
                ),
            }
        movement = pdata.get("movement", {}) or {}
        if movement:
            movement_percentages = {}
            for key, value in movement.items():
                if key.startswith("time_") and key.endswith("_s"):
                    movement_percentages[f"{key}_pct"] = round(
                        self._percentage_of_match(value), 2
                    )
            if movement_percentages:
                derived["movement"] = movement_percentages
        passing = pdata.get("passing", {}) or {}
        if passing:
            derived["passing"] = {
                "completion_pct": round(
                    self._share_pct_value(
                        passing.get("passes_completed"), passing.get("passes_attempted")
                    ),
                    2,
                ),
                "possession_per_min": round(
                    self._rate_per_minute_value(passing.get("possession_time_s")), 3
                ),
                "turnovers_per_min": round(
                    self._rate_per_minute_value(passing.get("turnovers")), 3
                ),
            }
        challenges = pdata.get("challenges", {}) or {}
        if challenges:
            contests = challenges.get("contests", 0)
            derived["challenges"] = {
                "win_pct": round(
                    self._share_pct_value(challenges.get("wins"), contests), 2
                ),
                "loss_pct": round(
                    self._share_pct_value(challenges.get("losses"), contests), 2
                ),
                "neutral_pct": round(
                    self._share_pct_value(challenges.get("neutral"), contests), 2
                ),
            }
        kickoffs = pdata.get("kickoffs", {}) or {}
        if kickoffs:
            count = kickoffs.get("count", 0)
            derived["kickoffs"] = {
                "first_possession_pct": round(
                    self._share_pct_value(kickoffs.get("first_possession"), count), 2
                ),
                "neutral_pct": round(
                    self._share_pct_value(kickoffs.get("neutral"), count), 2
                ),
                "goals_for_per_kickoff": round(
                    self._share_pct_value(kickoffs.get("goals_for"), count), 2
                ),
                "goals_against_per_kickoff": round(
                    self._share_pct_value(kickoffs.get("goals_against"), count), 2
                ),
            }
        return derived

    def _player_key_value_block(self, pid: str, pdata: dict[str, Any]) -> str:
        payload = {
            "player_id": pid,
            "fundamentals": pdata.get("fundamentals", {}),
            "boost": pdata.get("boost", {}),
            "movement": pdata.get("movement", {}),
            "positioning": pdata.get("positioning", {}),
            "passing": pdata.get("passing", {}),
            "challenges": pdata.get("challenges", {}),
            "kickoffs": pdata.get("kickoffs", {}),
            "rotation_compliance": pdata.get("rotation_compliance", {}),
            "derived": self._player_derived_metrics(pdata),
        }
        return "```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```"

    def _format_timeline_row(
        self, event: dict[str, Any]
    ) -> tuple[str, str, str, str, str]:
        t = self._fmt_num(event.get("t"))
        frame = self._fmt_num(event.get("frame"))
        etype = event.get("type", "-")
        player = event.get("player_id", "-")
        details = self._summarize_event_data(event.get("data"))
        return (t, frame, etype, player, details)

    def _summarize_event_data(self, data: Any) -> str:
        if not isinstance(data, dict):
            return "-"
        items = []
        for key in sorted(data.keys()):
            value = data[key]
            if isinstance(value, dict):
                items.append(f"{key}:{'/'.join(str(v) for v in value.values())}")
            elif isinstance(value, list):
                items.append(f"{key}:{len(value)} items")
            else:
                items.append(f"{key}:{value}")
        return ", ".join(items)

    def _event_subtable(
        self, title: str, events: list[Any], formatter, headers: Sequence[str]
    ) -> str:
        self._emit(f"### {title}")
        rows = [formatter(ev) for ev in events or []]
        if not rows:
            return "*No events*"
        return self._tabulate(rows, headers=headers)

    def _format_goal_row(self, event: dict[str, Any]) -> tuple[str, str, str, str, str]:
        t = self._fmt_num(event.get("t"))
        frame = self._fmt_num(event.get("frame"))
        team = event.get("team", "-")
        scorer = event.get("scorer", "-")
        assist = event.get("assist", "-")
        return (t, frame, team, scorer, assist)

    def _format_demo_row(self, event: dict[str, Any]) -> tuple[str, str, str, str]:
        t = self._fmt_num(event.get("t"))
        attacker = event.get("attacker", "-")
        victim = event.get("victim", "-")
        loc = event.get("location") or {}
        location = self._format_location(loc)
        return (t, attacker, victim, location)

    def _format_boost_pickup_row(
        self, event: dict[str, Any]
    ) -> tuple[str, str, str, str, str]:
        t = self._fmt_num(event.get("t"))
        player = event.get("player_id", "-")
        pad = event.get("pad_type", "-")
        stolen = "Yes" if event.get("stolen") else "No"
        location = self._format_location(event.get("location") or {})
        return (t, player, pad, stolen, location)

    def _format_challenge_row(
        self, event: dict[str, Any]
    ) -> tuple[str, str, str, str, str]:
        t = self._fmt_num(event.get("t"))
        outcome = event.get("outcome", "-")
        winner = event.get("winner", "-")
        loser = event.get("loser", "-")
        depth = self._fmt_num(event.get("challenge_depth", 0))
        return (t, outcome, winner, loser, depth)

    def _format_kickoff_row(
        self, event: dict[str, Any]
    ) -> tuple[str, str, str, str, str]:
        phase = event.get("phase", "-")
        t_start = self._fmt_num(event.get("t_start"))
        outcome = event.get("outcome", "-")
        first_touch = event.get("first_touch_player", "-")
        approaches = event.get("players", []) or []
        approach_map = {}
        for approver in approaches:
            approach_map.setdefault(approver.get("approach_type", "UNKNOWN"), 0)
            approach_map[approver.get("approach_type", "UNKNOWN")] += 1
        approach_summary = (
            ", ".join(f"{k}:{v}" for k, v in sorted(approach_map.items())) or "-"
        )
        return (phase, t_start, outcome, first_touch, approach_summary)

    def _format_touch_row(
        self, event: dict[str, Any]
    ) -> tuple[str, str, str, str, str]:
        t = self._fmt_num(event.get("t"))
        player = event.get("player_id", "-")
        outcome = event.get("outcome", "-")
        speed = self._fmt_num(event.get("ball_speed_kph"))
        location = self._format_location(event.get("location") or {})
        return (t, player, outcome, speed, location)

    def _format_location(self, location: dict[str, Any]) -> str:
        if not location:
            return "-"
        x = self._fmt_num(location.get("x"))
        y = self._fmt_num(location.get("y"))
        z = self._fmt_num(location.get("z"))
        return f"(x:{x}, y:{y}, z:{z})"

    def _heatmap_table(self, values: list[list[float]]) -> str:
        if not values:
            return "*No heatmap data*"
        rows = []
        for row in values:
            rows.append(tuple(self._fmt_num(v, digits=3) for v in row))
        return self._tabulate(rows)

    def _heatmap_summary(self, values: list[list[float]], grid: dict[str, Any]) -> str:
        flattened = [val for row in values for val in row]
        total = sum(flattened) or 0.0
        if total <= 0:
            return "*No occupancy recorded*"
        x_bins = int(grid.get("x_bins") or (len(values[0]) if values else 0))
        y_bins = int(grid.get("y_bins") or len(values))
        extent = grid.get("extent", {}) or {}
        xmin = float(extent.get("xmin", -4096))
        xmax = float(extent.get("xmax", 4096))
        ymin = float(extent.get("ymin", -5120))
        ymax = float(extent.get("ymax", 5120))
        x_span = xmax - xmin
        y_span = ymax - ymin
        x_step = x_span / x_bins if x_bins else 0.0
        y_step = y_span / y_bins if y_bins else 0.0
        offensive_total = 0.0
        defensive_total = 0.0
        for y_idx, row in enumerate(values):
            for _x_idx, val in enumerate(row):
                if not val:
                    continue
                y_center = ymin + (y_idx + 0.5) * y_step if y_bins else 0.0
                if y_center >= 0:
                    offensive_total += val
                else:
                    defensive_total += val
        denom = total or 1.0
        offensive_pct = (offensive_total / denom) * 100.0
        defensive_pct = (defensive_total / denom) * 100.0
        top = sorted(((val, idx) for idx, val in enumerate(flattened)), reverse=True)[
            :3
        ]
        top_cells: list[str] = []
        for position, (val, cell_index) in enumerate(top):
            if x_bins:
                row_idx = cell_index // x_bins
                col_idx = cell_index % x_bins
            else:
                row_idx = 0
                col_idx = cell_index
            x_center = xmin + (col_idx + 0.5) * x_step if x_bins else 0.0
            y_center = ymin + (row_idx + 0.5) * y_step if y_bins else 0.0
            top_cells.append(
                f"#{position + 1} (row {row_idx}, col {col_idx}, x {self._fmt_num(x_center)}, y {self._fmt_num(y_center)}): {self._fmt_num(val)}"
            )
        rows = [
            ("Total", self._fmt_num(total)),
            ("Offensive Half %", f"{self._fmt_num(offensive_pct)}%"),
            ("Defensive Half %", f"{self._fmt_num(defensive_pct)}%"),
            ("Top Cells", "; ".join(top_cells)),
        ]
        return self._tabulate(rows)

    def _load_teams(self, teams: dict[str, Any]) -> dict[str, _TeamEntry]:
        result: dict[str, _TeamEntry] = {}
        for key in ("blue", "orange"):
            raw = teams.get(key)
            if not raw:
                continue
            result[key] = _TeamEntry(
                name=raw.get("name", key.upper()),
                score=int(raw.get("score", 0)),
                players=list(raw.get("players", []) or []),
            )
        return result


__all__ = ["load_report", "render_markdown", "write_markdown"]
