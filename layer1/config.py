"""Layer 1 — Configuration loading and management.

Loads defaults.yaml, applies optional overrides, constructs SystemConfig,
and validates all configuration constraints.
"""
from __future__ import annotations

import json
import copy
from dataclasses import fields, MISSING
from pathlib import Path
from typing import Any, Optional, Type, TypeVar

import yaml

from ..result import Result, ConfigLoadError
from ..types.config import (
    SystemConfig, LLMConfig, SandboxConfig, BudgetConfig, ScoringConfig,
    CurriculumConfig, FailureConfig, StrategyConfig, AgentConfig,
    BenchmarkConfig, ObservabilityConfig, GraduationSystemConfig,
    OptimizationConfig, ExplorationConfig, CompressionConfig, SafetyConfig,
    RecoveryConfig, TracksConfig, TrackSchedulingConfig, TrackGraduationConfig,
    CrossDomainConfig, TrackDefinitionConfig, TrackReadinessCriteria,
    QEMUSandboxConfig, TaskGenerationConfig,
)
from ..types.enums import EngineeringTrack, Language

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Change safety classification
# ---------------------------------------------------------------------------

_SAFE_PATHS = frozenset({
    "project.log_level", "observability.trace_enabled", "observability.digest_interval",
    "observability.alert_retention_cycles", "observability.max_active_alerts",
    "observability.health_check_interval", "compression.warm_tier_cycles",
    "compression.cold_tier_cycles", "compression.enabled",
})

_DANGEROUS_PATHS = frozenset({
    "project.max_cycles", "graduation.default_gate_pass_rates",
    "safety.halt_on_violation", "safety.max_invariant_violations",
    "tracks.enabled", "tracks.max_active_tracks",
    "tracks.graduation.system_graduation_rule",
    "tracks.graduation.ceiling_detection_enabled",
})


class ConfigManager:
    """Loads, validates, and manages system configuration."""

    def __init__(
        self,
        defaults_path: Path,
        config_path: Optional[Path] = None,
    ) -> None:
        self._defaults_path = defaults_path
        self._config_path = config_path
        self._config: Optional[SystemConfig] = None
        self._raw: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> Result[SystemConfig, ConfigLoadError]:
        """Execute the 8-step config loading sequence."""
        # Step 1: Load defaults
        defaults = self._load_yaml(self._defaults_path)
        if defaults.error is not None:
            return Result(error=defaults.error)

        raw = defaults.value or {}

        # Step 2: Load optional overrides
        if self._config_path and self._config_path.exists():
            overrides = self._load_yaml(self._config_path)
            if overrides.error is not None:
                return Result(error=overrides.error)
            raw = self._deep_merge(raw, overrides.value or {})

        self._raw = raw

        # Step 3–7: Build SystemConfig
        try:
            config = self._build_system_config(raw)
        except Exception as exc:
            return Result(error=ConfigLoadError(
                path=str(self._defaults_path),
                message=f"Failed to construct SystemConfig: {exc}",
            ))

        # Step 8: Validate constraints
        validation = self.validate_tracks_config(config.tracks)
        if validation.error is not None:
            return validation

        self._config = config
        return Result(value=config)

    def get_config(self) -> Result[SystemConfig, ConfigLoadError]:
        if self._config is None:
            return Result(error=ConfigLoadError(
                path=str(self._defaults_path),
                message="Config not loaded. Call load() first.",
            ))
        return Result(value=self._config)

    def apply_override(
        self, path: str, value: Any,
    ) -> Result[None, ConfigLoadError]:
        """Apply a runtime config override and reclassify safety."""
        keys = path.split(".")
        old_value = self._resolve_path(self._raw, keys)
        classification = self.classify_change(path, old_value, value)

        # Apply to raw dict
        target = self._raw
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

        # Rebuild config
        result = self.load()
        if result.error is not None:
            return Result(error=result.error)

        return Result(value=None)

    def classify_change(
        self, path: str, old_value: Any, new_value: Any,
    ) -> str:
        """Classify a config change as SAFE, CAUTION, or DANGEROUS."""
        if path in _DANGEROUS_PATHS:
            return "DANGEROUS"
        if path in _SAFE_PATHS:
            return "SAFE"
        # Anything touching tracks activation/deactivation is dangerous
        if "track" in path and ("activat" in path or "deactivat" in path):
            return "DANGEROUS"
        # Budget and scoring changes are cautious
        if any(seg in path for seg in ("budget", "scoring", "strategy", "agent")):
            return "CAUTION"
        return "CAUTION"

    def validate_tracks_config(
        self, config: TracksConfig,
    ) -> Result[None, ConfigLoadError]:
        """Validate all track configuration constraints."""
        if not config.enabled:
            return Result(value=None)

        # Validate prerequisite chains (no circular deps)
        prereq_result = self._validate_prerequisites(config.track_definitions)
        if prereq_result.error is not None:
            return prereq_result

        # Validate stagnation_threshold > warmup_cycles
        if config.stagnation_threshold_cycles <= config.warmup_cycles_per_track:
            return Result(error=ConfigLoadError(
                path="tracks",
                message=(
                    f"stagnation_threshold_cycles ({config.stagnation_threshold_cycles}) "
                    f"must exceed warmup_cycles_per_track ({config.warmup_cycles_per_track})"
                ),
            ))

        # Scheduling weight sum should be ~1.0
        sched = config.scheduling
        weight_sum = (
            sched.priority_weight_performance
            + sched.priority_weight_stagnation
            + sched.priority_weight_graduation_proximity
        )
        if abs(weight_sum - 1.0) > 0.01:
            return Result(error=ConfigLoadError(
                path="tracks.scheduling",
                message=f"Priority weights sum to {weight_sum}, expected ~1.0",
            ))

        return Result(value=None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_yaml(self, path: Path) -> Result[dict, ConfigLoadError]:
        try:
            with open(path, "r") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                return Result(error=ConfigLoadError(
                    path=str(path), message="YAML root must be a mapping",
                ))
            return Result(value=data)
        except FileNotFoundError:
            return Result(error=ConfigLoadError(
                path=str(path), message="File not found",
            ))
        except yaml.YAMLError as exc:
            return Result(error=ConfigLoadError(
                path=str(path), message=f"YAML parse error: {exc}",
            ))

    def _deep_merge(self, base: dict, override: dict) -> dict:
        merged = copy.deepcopy(base)
        for key, value in override.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    def _build_sub_config(self, cls: Type[T], data: dict) -> T:
        """Construct a dataclass from a dict, ignoring unknown keys."""
        valid_fields = {f.name for f in fields(cls)}
        filtered = {}
        for key, value in data.items():
            if key in valid_fields:
                filtered[key] = value
        return cls(**filtered)

    def _build_system_config(self, raw: dict) -> SystemConfig:
        """Build the full SystemConfig from raw YAML data."""
        project = raw.get("project", {})

        # Build leaf configs
        llm = self._build_sub_config(LLMConfig, raw.get("llm", {}))
        qemu_data = raw.get("sandbox", {}).get("qemu", {})
        qemu = self._build_sub_config(QEMUSandboxConfig, qemu_data) if qemu_data else None
        sandbox_data = {**raw.get("sandbox", {})}
        sandbox_data.pop("qemu", None)
        sandbox_data["qemu"] = qemu
        sandbox = self._build_sub_config(SandboxConfig, sandbox_data)
        budget = self._build_sub_config(BudgetConfig, raw.get("budget", {}))
        scoring = self._build_sub_config(ScoringConfig, raw.get("scoring", {}))
        curriculum = self._build_sub_config(CurriculumConfig, raw.get("curriculum", {}))
        failure = self._build_sub_config(FailureConfig, raw.get("failure", {}))
        strategy = self._build_sub_config(StrategyConfig, raw.get("strategy", {}))
        agents = self._build_sub_config(AgentConfig, raw.get("agents", {}))
        benchmarks = self._build_sub_config(BenchmarkConfig, raw.get("benchmarks", {}))
        observability = self._build_sub_config(ObservabilityConfig, raw.get("observability", {}))
        graduation = self._build_sub_config(GraduationSystemConfig, raw.get("graduation", {}))
        optimization = self._build_sub_config(OptimizationConfig, raw.get("optimization", {}))
        exploration = self._build_sub_config(ExplorationConfig, raw.get("exploration", {}))
        compression = self._build_sub_config(CompressionConfig, raw.get("compression", {}))
        safety = self._build_sub_config(SafetyConfig, raw.get("safety", {}))
        recovery = self._build_sub_config(RecoveryConfig, raw.get("recovery", {}))

        # Build tracks config hierarchy
        tracks_raw = raw.get("tracks", {})
        scheduling = self._build_sub_config(
            TrackSchedulingConfig, tracks_raw.get("scheduling", {}),
        )
        track_graduation = self._build_sub_config(
            TrackGraduationConfig, tracks_raw.get("graduation", {}),
        )
        cross_domain = self._build_sub_config(
            CrossDomainConfig, tracks_raw.get("cross_domain", {}),
        )
        readiness = self._build_sub_config(
            TrackReadinessCriteria, tracks_raw.get("readiness_criteria", {}),
        )

        # Build per-track definition configs
        track_defs: dict[str, TrackDefinitionConfig] = {}
        for track_name, track_data in tracks_raw.get("definitions", {}).items():
            if isinstance(track_data, dict):
                track_defs[track_name] = self._build_sub_config(
                    TrackDefinitionConfig, track_data,
                )

        tracks_top = {k: v for k, v in tracks_raw.items()
                      if k not in ("scheduling", "graduation", "cross_domain",
                                   "readiness_criteria", "definitions")}
        tracks_top["scheduling"] = scheduling
        tracks_top["graduation"] = track_graduation
        tracks_top["cross_domain"] = cross_domain
        tracks_top["readiness_criteria"] = readiness
        tracks_top["track_definitions"] = track_defs

        # Handle list of EngineeringTrack for initial_active_tracks
        iat = tracks_top.get("initial_active_tracks", [])
        if iat and isinstance(iat[0], str):
            tracks_top["initial_active_tracks"] = [
                EngineeringTrack(t.lower()) if hasattr(EngineeringTrack, t)
                else EngineeringTrack(t.lower())
                for t in iat
            ]

        tracks = self._build_sub_config(TracksConfig, tracks_top)

        # Build task generation config
        task_gen = self._build_sub_config(
            TaskGenerationConfig, raw.get("task_generation", {}),
        )

        return SystemConfig(
            project_name=project.get("name", "self_improving_ai"),
            version=project.get("version", "0.1.0"),
            max_cycles=project.get("max_cycles", 100000),
            log_level=project.get("log_level", "INFO"),
            data_dir=project.get("data_dir", "data/"),
            llm=llm, sandbox=sandbox, budget=budget, scoring=scoring,
            curriculum=curriculum, failure=failure, strategy=strategy,
            agents=agents, benchmarks=benchmarks, observability=observability,
            graduation=graduation, optimization=optimization,
            exploration=exploration, compression=compression,
            safety=safety, recovery=recovery, tracks=tracks,
            task_generation=task_gen,
        )

    def _validate_prerequisites(
        self, definitions: dict[str, TrackDefinitionConfig],
    ) -> Result[None, ConfigLoadError]:
        """Detect circular dependencies in track prerequisites via DFS."""
        # Build adjacency from the raw YAML definitions data
        raw_defs = self._raw.get("tracks", {}).get("definitions", {})

        adjacency: dict[str, list[str]] = {}
        for track_name, track_data in raw_defs.items():
            if isinstance(track_data, dict):
                prereqs = track_data.get("prerequisite_tracks", [])
                adjacency[track_name] = prereqs if isinstance(prereqs, list) else []

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {t: WHITE for t in adjacency}

        def dfs(node: str) -> Optional[str]:
            color[node] = GRAY
            for neighbor in adjacency.get(node, []):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    return f"Circular dependency: {node} -> {neighbor}"
                if color[neighbor] == WHITE:
                    result = dfs(neighbor)
                    if result:
                        return result
            color[node] = BLACK
            return None

        for track in adjacency:
            if color[track] == WHITE:
                cycle = dfs(track)
                if cycle:
                    return Result(error=ConfigLoadError(
                        path="tracks.definitions",
                        message=cycle,
                    ))

        return Result(value=None)

    def _resolve_path(self, data: dict, keys: list[str]) -> Any:
        """Resolve a dotted path in a nested dict."""
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
