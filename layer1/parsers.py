"""Layer 1 — Parsing utilities.

Converts raw data (strings, dicts, DB rows) to typed Layer 0 objects.
Handles enum coercion with aliases and timestamp normalization.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional, Type, TypeVar

from ..result import Result, ValidationError, ValidationErrorType
from ..types import enums
from ..types.enums import (
    EngineeringTrack, Language, TaskLevel, TrackStatus, SandboxType,
    Domain, TaskSource, Severity, Trend,
)
from ..types.track import (
    TrackDefinition, TrackConfig, GeneratedTaskCandidate,
    TaskVerificationResult,
)
from ..types.common import GateSet

T = TypeVar("T")


class EnumParser:
    """Parses string values to enum types with alias support."""

    ALIASES: dict[str, str] = {
        "asm": "assembly",
        "c++": "cpp",
        "js": "javascript",
        "ts": "typescript",
        "py": "python",
        "golang": "go",
    }

    @classmethod
    def _normalize(cls, value: str) -> str:
        """Normalize a string value: lowercase, apply aliases."""
        normalized = value.strip().lower()
        return cls.ALIASES.get(normalized, normalized)

    @classmethod
    def parse_language(cls, value: str) -> Result[Language, ValidationError]:
        normalized = cls._normalize(value)
        try:
            return Result(value=Language(normalized))
        except ValueError:
            return Result(error=ValidationError(
                error_type=ValidationErrorType.INVALID_INPUT,
                message=f"Invalid language: '{value}' (normalized: '{normalized}')",
                field="language",
            ))

    @classmethod
    def parse_engineering_track(
        cls, value: str,
    ) -> Result[EngineeringTrack, ValidationError]:
        normalized = cls._normalize(value)
        try:
            return Result(value=EngineeringTrack(normalized))
        except ValueError:
            return Result(error=ValidationError(
                error_type=ValidationErrorType.INVALID_INPUT,
                message=f"Invalid engineering track: '{value}'",
                field="engineering_track",
            ))

    @classmethod
    def parse_task_level(cls, value: str) -> Result[TaskLevel, ValidationError]:
        normalized = cls._normalize(value)
        try:
            return Result(value=TaskLevel(normalized))
        except ValueError:
            return Result(error=ValidationError(
                error_type=ValidationErrorType.INVALID_INPUT,
                message=f"Invalid task level: '{value}'",
                field="task_level",
            ))

    @classmethod
    def parse_enum(
        cls, enum_cls: Type[T], value: str,
    ) -> Result[T, ValidationError]:
        """Generic enum parser with alias support."""
        normalized = cls._normalize(value)
        try:
            return Result(value=enum_cls(normalized))
        except (ValueError, KeyError):
            # Try uppercase member name as fallback
            try:
                return Result(value=enum_cls[value.upper()])
            except (KeyError, AttributeError):
                return Result(error=ValidationError(
                    error_type=ValidationErrorType.INVALID_INPUT,
                    message=f"Invalid {enum_cls.__name__}: '{value}'",
                    field=enum_cls.__name__.lower(),
                ))


# ---------------------------------------------------------------------------
# Composite parsers
# ---------------------------------------------------------------------------

def parse_track_definition(data: dict[str, Any]) -> Result[TrackDefinition, ValidationError]:
    """Parse a raw dict into a TrackDefinition."""
    try:
        # Parse enum fields
        track_id_result = EnumParser.parse_engineering_track(
            data.get("track_id", data.get("name", "")),
        )
        if track_id_result.error:
            return Result(error=track_id_result.error)

        primary_lang_result = EnumParser.parse_language(
            data.get("primary_language", "python"),
        )
        if primary_lang_result.error:
            return Result(error=primary_lang_result.error)

        # Parse required_languages
        req_langs = []
        for lang_str in data.get("required_languages", ["python"]):
            lang_result = EnumParser.parse_language(lang_str)
            if lang_result.error:
                return Result(error=lang_result.error)
            req_langs.append(lang_result.value)

        # Parse prerequisite_tracks
        prereqs = []
        for track_str in data.get("prerequisite_tracks", []):
            track_result = EnumParser.parse_engineering_track(track_str)
            if track_result.error:
                return Result(error=track_result.error)
            prereqs.append(track_result.value)

        # Parse f_level_range
        f_range_raw = data.get("f_level_range", ("F1", "F8"))
        if isinstance(f_range_raw, (list, tuple)) and len(f_range_raw) == 2:
            f_min = EnumParser.parse_task_level(str(f_range_raw[0]))
            f_max = EnumParser.parse_task_level(str(f_range_raw[1]))
            if f_min.error:
                return Result(error=f_min.error)
            if f_max.error:
                return Result(error=f_max.error)
            f_level_range = (f_min.value, f_max.value)
        else:
            f_level_range = (TaskLevel.F1, TaskLevel.F8)

        # Parse sandbox_requirements
        sandbox_reqs = []
        for sb in data.get("sandbox_requirements", []):
            sb_result = EnumParser.parse_enum(SandboxType, str(sb))
            if sb_result.error:
                return Result(error=sb_result.error)
            sandbox_reqs.append(sb_result.value)

        # Parse priority
        priority_result = EnumParser.parse_enum(
            enums.TrackPriority,
            data.get("priority", "medium"),
        )
        priority = priority_result.value if priority_result.value else enums.TrackPriority.MEDIUM

        # Parse status
        status_result = EnumParser.parse_enum(
            TrackStatus,
            data.get("status", "inactive"),
        )
        status = status_result.value if status_result.value else TrackStatus.INACTIVE

        td = TrackDefinition(
            track_id=track_id_result.value,
            display_name=data.get("display_name", ""),
            description=data.get("description", ""),
            priority=priority,
            status=status,
            min_activation_tier=int(data.get("min_activation_tier", 1)),
            required_languages=req_langs,
            prerequisite_tracks=prereqs,
            primary_language=primary_lang_result.value,
            task_pool_size=int(data.get("task_pool_size", 0)),
            task_sources=data.get("task_sources", []),
            f_level_range=f_level_range,
            f_level_sandbox_overrides=data.get("f_level_sandbox_overrides"),
            sandbox_requirements=sandbox_reqs,
            context_preamble=data.get("context_preamble", ""),
            estimated_avg_cost_per_cycle=float(
                data.get("estimated_avg_cost_per_cycle", 0.05),
            ),
            estimated_months_to_g1=float(
                data.get("estimated_months_to_g1", 3.0),
            ),
            readiness_overrides=data.get("readiness_overrides"),
        )
        return Result(value=td)

    except Exception as exc:
        return Result(error=ValidationError(
            error_type=ValidationErrorType.INVALID_INPUT,
            message=f"Failed to parse TrackDefinition: {exc}",
        ))


def parse_graduation_gate(data: dict[str, Any]) -> Result[GateSet, ValidationError]:
    """Parse graduation gate configuration."""
    try:
        gate = GateSet(
            gate_name=data.get("gate_name", data.get("name", "")),
            required_pass_rate=float(data.get("pass_rate", data.get("required_pass_rate", 0.90))),
            required_consecutive_sessions=int(data.get("sessions", data.get("required_consecutive_sessions", 15))),
            exam_size=int(data.get("exam_size", 200)),
            min_cycles_at_level=int(data.get("min_cycles_at_level", 1000)),
        )
        return Result(value=gate)
    except Exception as exc:
        return Result(error=ValidationError(
            error_type=ValidationErrorType.INVALID_INPUT,
            message=f"Failed to parse graduation gate: {exc}",
        ))


def parse_timestamp(value: str) -> Result[str, ValidationError]:
    """Validate and normalize an ISO 8601 timestamp."""
    if not value or not value.strip():
        return Result(error=ValidationError(
            error_type=ValidationErrorType.MISSING_FIELD,
            message="Timestamp is empty",
            field="timestamp",
        ))

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return Result(value=dt.isoformat())
    except ValueError:
        return Result(error=ValidationError(
            error_type=ValidationErrorType.INVALID_INPUT,
            message=f"Invalid ISO 8601 timestamp: '{value}'",
            field="timestamp",
        ))


def parse_json_field(
    value: str, field_name: str,
) -> Result[Any, ValidationError]:
    """Parse a JSON string field from the database."""
    if not value:
        return Result(value=None)
    try:
        parsed = json.loads(value)
        return Result(value=parsed)
    except json.JSONDecodeError as exc:
        return Result(error=ValidationError(
            error_type=ValidationErrorType.INVALID_INPUT,
            message=f"Invalid JSON in field '{field_name}': {exc}",
            field=field_name,
        ))


def parse_cycle_record(data: dict[str, Any]) -> Result[dict[str, Any], ValidationError]:
    """Parse a raw dict (e.g., from DB row) into a structured cycle record.

    Converts string enum fields to proper enum types and JSON fields to dicts.
    """
    try:
        parsed = dict(data)

        # Parse enum fields if present
        if "domain_track" in parsed and isinstance(parsed["domain_track"], str):
            track_result = EnumParser.parse_engineering_track(parsed["domain_track"])
            if track_result.value:
                parsed["domain_track"] = track_result.value

        if "status" in parsed and isinstance(parsed["status"], str):
            status_result = EnumParser.parse_enum(enums.CycleStatus, parsed["status"])
            if status_result.value:
                parsed["status"] = status_result.value

        if "task_level" in parsed and isinstance(parsed["task_level"], str):
            level_result = EnumParser.parse_task_level(parsed["task_level"])
            if level_result.value:
                parsed["task_level"] = level_result.value

        # Parse JSON string fields
        for json_field in ("metadata", "review_scores", "test_results"):
            if json_field in parsed and isinstance(parsed[json_field], str):
                json_result = parse_json_field(parsed[json_field], json_field)
                if json_result.value is not None:
                    parsed[json_field] = json_result.value

        return Result(value=parsed)

    except Exception as exc:
        return Result(error=ValidationError(
            error_type=ValidationErrorType.INVALID_INPUT,
            message=f"Failed to parse cycle record: {exc}",
        ))
