"""Layer 1 — Type validators for all Layer 0 types.

Validates field ranges, enum membership, prerequisite chains,
and cross-type consistency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..result import Result, ValidationError, ValidationErrorType
from ..types.enums import (
    EngineeringTrack, Language, TrackStatus, Trend, TaskLevel,
    FailureCategory, Severity, ArtifactStatus, ArtifactType,
    PatternStatus, ChainStatus,
)


# ---------------------------------------------------------------------------
# Validation result collector
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Collects multiple validation errors and warnings."""

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, field_name: str, message: str) -> None:
        self.errors.append(ValidationError(
            error_type=ValidationErrorType.OUT_OF_RANGE,
            message=message,
            field=field_name,
        ))

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def merge(self, other: ValidationResult) -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


# ---------------------------------------------------------------------------
# Primitive validators
# ---------------------------------------------------------------------------

def validate_range(
    value: float, min_val: float, max_val: float, field_name: str,
) -> Optional[ValidationError]:
    if not (min_val <= value <= max_val):
        return ValidationError(
            error_type=ValidationErrorType.OUT_OF_RANGE,
            message=f"{field_name} must be between {min_val} and {max_val}, got {value}",
            field=field_name,
        )
    return None


def validate_not_empty(value: str, field_name: str) -> Optional[ValidationError]:
    if not value or not value.strip():
        return ValidationError(
            error_type=ValidationErrorType.MISSING_FIELD,
            message=f"{field_name} must not be empty",
            field=field_name,
        )
    return None


def validate_positive(value: int, field_name: str) -> Optional[ValidationError]:
    if value < 0:
        return ValidationError(
            error_type=ValidationErrorType.OUT_OF_RANGE,
            message=f"{field_name} must be non-negative, got {value}",
            field=field_name,
        )
    return None


def validate_positive_strict(value: int, field_name: str) -> Optional[ValidationError]:
    if value <= 0:
        return ValidationError(
            error_type=ValidationErrorType.OUT_OF_RANGE,
            message=f"{field_name} must be positive, got {value}",
            field=field_name,
        )
    return None


def _check(result: ValidationResult, err: Optional[ValidationError]) -> None:
    if err is not None:
        result.errors.append(err)


# ---------------------------------------------------------------------------
# Track type validators
# ---------------------------------------------------------------------------

def validate_track_definition(td: Any) -> ValidationResult:
    """Validate a TrackDefinition instance."""
    r = ValidationResult()
    _check(r, validate_not_empty(td.display_name, "display_name"))
    _check(r, validate_not_empty(td.description, "description"))
    _check(r, validate_positive(td.min_activation_tier, "min_activation_tier"))
    _check(r, validate_positive(td.task_pool_size, "task_pool_size"))

    # Validate required_languages are valid Language enum values
    for lang in td.required_languages:
        if not isinstance(lang, Language):
            try:
                Language(lang.lower() if isinstance(lang, str) else lang)
            except (ValueError, AttributeError):
                r.add_error("required_languages", f"Invalid language: {lang}")

    # Validate prerequisite_tracks are valid EngineeringTrack values
    for prereq in td.prerequisite_tracks:
        if not isinstance(prereq, EngineeringTrack):
            try:
                EngineeringTrack(prereq.lower() if isinstance(prereq, str) else prereq)
            except (ValueError, AttributeError):
                r.add_error("prerequisite_tracks", f"Invalid track: {prereq}")

    # Primary language must be in required_languages
    primary_vals = {
        (l.value if isinstance(l, Language) else str(l).lower())
        for l in td.required_languages
    }
    primary_val = (
        td.primary_language.value
        if isinstance(td.primary_language, Language)
        else str(td.primary_language).lower()
    )
    if primary_val not in primary_vals:
        r.add_warning(
            f"primary_language '{td.primary_language}' not in required_languages"
        )

    if td.estimated_avg_cost_per_cycle < 0:
        r.add_error(
            "estimated_avg_cost_per_cycle",
            "Cost must be non-negative",
        )

    return r


def validate_track_config(tc: Any) -> ValidationResult:
    r = ValidationResult()
    _check(r, validate_range(tc.cycle_allocation_percent, 0.0, 1.0, "cycle_allocation_percent"))
    _check(r, validate_range(tc.min_allocation_percent, 0.0, 1.0, "min_allocation_percent"))
    _check(r, validate_range(tc.max_allocation_percent, 0.0, 1.0, "max_allocation_percent"))
    _check(r, validate_range(tc.max_budget_percent, 0.0, 1.0, "max_budget_percent"))
    _check(r, validate_range(tc.exam_allocation_percent, 0.0, 1.0, "exam_allocation_percent"))
    _check(r, validate_range(tc.exploration_budget_percent, 0.0, 1.0, "exploration_budget_percent"))

    if tc.min_allocation_percent > tc.max_allocation_percent:
        r.add_error(
            "allocation",
            "min_allocation_percent must be <= max_allocation_percent",
        )
    if tc.difficulty_ramp_rate < 0:
        r.add_error("difficulty_ramp_rate", "Must be non-negative")
    return r


def validate_track_performance(tp: Any) -> ValidationResult:
    r = ValidationResult()
    _check(r, validate_range(tp.pass_rate_overall, 0.0, 1.0, "pass_rate_overall"))
    _check(r, validate_range(tp.pass_rate_rolling_100, 0.0, 1.0, "pass_rate_rolling_100"))
    _check(r, validate_range(tp.pass_rate_rolling_500, 0.0, 1.0, "pass_rate_rolling_500"))
    _check(r, validate_range(tp.health_score, 0.0, 1.0, "health_score"))
    _check(r, validate_positive(tp.total_cycles, "total_cycles"))
    _check(r, validate_positive(tp.patterns_discovered, "patterns_discovered"))
    _check(r, validate_positive(tp.prevention_artifacts, "prevention_artifacts"))
    _check(r, validate_positive(tp.active_agents, "active_agents"))
    _check(r, validate_positive(tp.stagnation_cycles, "stagnation_cycles"))
    _check(r, validate_positive(tp.consecutive_crashes, "consecutive_crashes"))
    _check(r, validate_positive(tp.warmup_remaining, "warmup_remaining"))
    if tp.cost_spent_usd < 0:
        r.add_error("cost_spent_usd", "Must be non-negative")
    return r


def validate_track_readiness_assessment(tra: Any) -> ValidationResult:
    r = ValidationResult()
    _check(r, validate_range(tra.pattern_depth_score, 0.0, 1.0, "pattern_depth_score"))
    _check(r, validate_range(tra.resource_availability, 0.0, 1.0, "resource_availability"))
    _check(r, validate_range(tra.confidence, 0.0, 1.0, "confidence"))
    _check(r, validate_positive(tra.current_track_load, "current_track_load"))
    return r


def validate_track_graduation_state(tgs: Any) -> ValidationResult:
    r = ValidationResult()
    _check(r, validate_positive(tgs.consecutive_sessions, "consecutive_sessions"))
    _check(r, validate_positive_strict(tgs.required_sessions, "required_sessions"))
    _check(r, validate_positive(tgs.exam_cycles_completed, "exam_cycles_completed"))
    _check(r, validate_range(tgs.exam_pass_rate, 0.0, 1.0, "exam_pass_rate"))
    _check(r, validate_positive(tgs.previous_attempts, "previous_attempts"))
    _check(r, validate_positive(tgs.best_streak, "best_streak"))

    if tgs.consecutive_sessions > tgs.required_sessions:
        r.add_warning(
            f"consecutive_sessions ({tgs.consecutive_sessions}) exceeds "
            f"required_sessions ({tgs.required_sessions})"
        )
    return r


def validate_graduation_ceiling_flag(gcf: Any) -> ValidationResult:
    r = ValidationResult()
    _check(r, validate_range(gcf.blocking_track_pass_rate, 0.0, 1.0, "blocking_track_pass_rate"))
    _check(r, validate_range(gcf.blocking_track_target, 0.0, 1.0, "blocking_track_target"))
    _check(r, validate_range(gcf.system_avg_pass_rate, 0.0, 1.0, "system_avg_pass_rate"))
    _check(r, validate_range(gcf.non_blocking_tracks_pass_rate, 0.0, 1.0, "non_blocking_tracks_pass_rate"))
    _check(r, validate_range(gcf.self_assessment_confidence, 0.0, 1.0, "self_assessment_confidence"))
    _check(r, validate_positive(gcf.cycles_at_current_level, "cycles_at_current_level"))
    _check(r, validate_positive(gcf.total_track_cycles, "total_track_cycles"))
    _check(r, validate_not_empty(gcf.detailed_reasoning, "detailed_reasoning"))
    _check(r, validate_not_empty(gcf.recommendation, "recommendation"))

    valid_recommendations = {
        "HUMAN_OVERRIDE_SUGGESTED", "KEEP_TRAINING", "PAUSE_TRACK",
    }
    if gcf.recommendation not in valid_recommendations:
        r.add_error(
            "recommendation",
            f"Must be one of {valid_recommendations}, got '{gcf.recommendation}'",
        )
    return r


def validate_cross_track_insight(cti: Any) -> ValidationResult:
    r = ValidationResult()
    _check(r, validate_range(cti.confidence, 0.0, 1.0, "confidence"))
    _check(r, validate_not_empty(cti.pattern_id, "pattern_id"))

    valid_transfer_types = {"DIRECT_APPLY", "ADAPT_REQUIRED", "PRINCIPLE_ONLY"}
    if cti.transfer_type not in valid_transfer_types:
        r.add_error(
            "transfer_type",
            f"Must be one of {valid_transfer_types}, got '{cti.transfer_type}'",
        )

    if cti.effectiveness_in_target is not None:
        err = validate_range(cti.effectiveness_in_target, 0.0, 1.0, "effectiveness_in_target")
        if err:
            r.errors.append(err)

    if cti.generalization_quality is not None:
        err = validate_range(cti.generalization_quality, 0.0, 1.0, "generalization_quality")
        if err:
            r.errors.append(err)
    return r


def validate_task_verification_result(tvr: Any) -> ValidationResult:
    r = ValidationResult()
    _check(r, validate_range(tvr.novelty_score, 0.0, 1.0, "novelty_score"))
    _check(r, validate_not_empty(tvr.candidate_id, "candidate_id"))

    # overall_pass should be consistent with individual checks
    all_checks = [
        tvr.is_solvable, tvr.tests_valid, tvr.difficulty_appropriate,
        tvr.difficulty_verified, tvr.description_clear, tvr.tests_comprehensive,
    ]
    expected_pass = all(all_checks)
    if tvr.overall_pass != expected_pass:
        r.add_warning(
            f"overall_pass={tvr.overall_pass} inconsistent with individual checks "
            f"(expected {expected_pass})"
        )
    return r


def validate_task_generation_capability(tgc: Any) -> ValidationResult:
    r = ValidationResult()
    _check(r, validate_range(tgc.acceptance_rate, 0.0, 1.0, "acceptance_rate"))
    _check(r, validate_positive(tgc.total_generated, "total_generated"))
    _check(r, validate_positive(tgc.total_accepted, "total_accepted"))
    _check(r, validate_positive(tgc.total_rejected, "total_rejected"))

    # acceptance_rate should be recomputable
    if tgc.total_generated > 0:
        expected_rate = tgc.total_accepted / tgc.total_generated
        if abs(tgc.acceptance_rate - expected_rate) > 0.01:
            r.add_error(
                "acceptance_rate",
                f"Expected {expected_rate:.4f} (accepted/generated), "
                f"got {tgc.acceptance_rate:.4f}",
            )

    if tgc.total_accepted + tgc.total_rejected > tgc.total_generated:
        r.add_error(
            "totals",
            "accepted + rejected cannot exceed generated",
        )
    return r


def validate_generated_task_candidate(gtc: Any) -> ValidationResult:
    r = ValidationResult()
    _check(r, validate_not_empty(gtc.candidate_id, "candidate_id"))
    _check(r, validate_not_empty(gtc.generated_description, "generated_description"))
    _check(r, validate_not_empty(gtc.generated_tests, "generated_tests"))
    _check(r, validate_not_empty(gtc.generated_solution, "generated_solution"))

    if gtc.quality_score is not None:
        err = validate_range(gtc.quality_score, 0.0, 1.0, "quality_score")
        if err:
            r.errors.append(err)
    return r


def validate_graduation_override(go: Any) -> ValidationResult:
    r = ValidationResult()
    _check(r, validate_not_empty(go.override_id, "override_id"))
    _check(r, validate_range(go.original_threshold, 0.0, 1.0, "original_threshold"))
    _check(r, validate_range(go.actual_pass_rate, 0.0, 1.0, "actual_pass_rate"))
    _check(r, validate_not_empty(go.approved_by, "approved_by"))
    _check(r, validate_not_empty(go.justification, "justification"))

    if go.actual_pass_rate >= go.original_threshold:
        r.add_warning(
            "Override not needed: actual_pass_rate >= original_threshold"
        )
    return r


# ---------------------------------------------------------------------------
# Prerequisite chain validation (cycle detection)
# ---------------------------------------------------------------------------

def validate_prerequisite_chain(
    tracks: dict[str, Any],
) -> ValidationResult:
    """Detect circular dependencies in track prerequisites using DFS."""
    r = ValidationResult()

    adjacency: dict[str, list[str]] = {}
    for track_name, track_obj in tracks.items():
        prereqs = getattr(track_obj, "prerequisite_tracks", [])
        adjacency[track_name] = [
            (p.value if isinstance(p, EngineeringTrack) else str(p))
            for p in prereqs
        ]

    # Validate all prerequisites exist
    all_tracks = set(adjacency.keys())
    for track_name, prereqs in adjacency.items():
        for prereq in prereqs:
            if prereq.upper() not in all_tracks and prereq not in all_tracks:
                r.add_error(
                    "prerequisite_tracks",
                    f"Track '{track_name}' has prerequisite '{prereq}' "
                    f"which does not exist",
                )

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {t: WHITE for t in adjacency}

    def dfs(node: str, path: list[str]) -> None:
        color[node] = GRAY
        path.append(node)
        for neighbor in adjacency.get(node, []):
            norm = neighbor.upper() if neighbor.upper() in color else neighbor
            if norm not in color:
                continue
            if color[norm] == GRAY:
                cycle_start = path.index(norm)
                cycle = " -> ".join(path[cycle_start:] + [norm])
                r.add_error(
                    "prerequisite_tracks",
                    f"Circular dependency detected: {cycle}",
                )
                return
            if color[norm] == WHITE:
                dfs(norm, path)
        path.pop()
        color[node] = BLACK

    for track in adjacency:
        if color[track] == WHITE:
            dfs(track, [])

    return r


# ---------------------------------------------------------------------------
# Cross-type ecosystem validation
# ---------------------------------------------------------------------------

def validate_track_ecosystem(
    tracks_config: Any,
    track_definitions: list[Any],
) -> ValidationResult:
    """Validate the entire track ecosystem is consistent."""
    r = ValidationResult()

    # Check max_active_tracks constraint
    active_count = sum(
        1 for td in track_definitions
        if hasattr(td, "status") and td.status == TrackStatus.ACTIVE
    )
    max_active = getattr(tracks_config, "max_active_tracks", 3)
    if active_count > max_active:
        r.add_error(
            "max_active_tracks",
            f"Active tracks ({active_count}) exceeds max ({max_active})",
        )

    # Validate initial_active_tracks exist in definitions
    initial = getattr(tracks_config, "initial_active_tracks", [])
    defined_ids = {
        (td.track_id.value if isinstance(td.track_id, EngineeringTrack) else str(td.track_id))
        for td in track_definitions
    }
    for track in initial:
        track_val = track.value if isinstance(track, EngineeringTrack) else str(track)
        if track_val not in defined_ids:
            r.add_error(
                "initial_active_tracks",
                f"Initial track '{track_val}' not found in definitions",
            )

    return r
