"""F8 Addendum — A-2 + A-6: Prompt Cache Boundary.

Static/dynamic prompt boundary for cache optimization.
Zone 1 (static, cacheable) separated from Zone 2 (dynamic, per-cycle).
Single cache_control marker on LAST content block of Zone 1.
~60 lines | Integrates with L3 context_assembler and L5 orchestrator.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from ..types.session import SessionConfig

PROMPT_BOUNDARY_MARKER = "===PROMPT_BOUNDARY==="


@dataclass(frozen=True)
class PromptZone:
    """A segment of the system prompt."""

    content: str
    scope: Optional[str] = None  # 'session' for Zone 1, None for Zone 2
    cache_control: bool = False


@dataclass(frozen=True)
class TwoZonePrompt:
    """System prompt split into cacheable and dynamic zones."""

    zone1_static: PromptZone
    zone2_dynamic: PromptZone


class CacheBoundaryBuilder:
    """Builds two-zone prompts with cache optimization.

    Zone 1 — Static (cacheable, scope='session'):
      - System identity instructions
      - Tool schemas
      - Active pattern library (sorted deterministically by pattern_id)
      - Sandbox configuration
      - Track definitions
      - Single cache_control marker on LAST content block

    Zone 2 — Dynamic (per-cycle, scope=null):
      - Current task description
      - Cycle number
      - Track context (active track, F-level, budget)
      - Economy mode flag
      - Recent failure summaries
      - Optimization brief
      - NO cache_control
    """

    def __init__(self, config: Any) -> None:
        self._config = config

    def build(
        self,
        session_config: SessionConfig,
        system_instructions: str,
        tool_schemas: str,
        patterns: list[Any],
        sandbox_config: str,
        track_definitions: str,
        task_description: str,
        cycle_number: int,
        track_context: dict[str, Any],
        economy_mode: bool,
        recent_failures: list[str],
        optimization_brief: str = "",
    ) -> TwoZonePrompt:
        """Build a two-zone prompt from session and cycle data.

        Uses latched values from SessionConfig for Zone 1 stability.
        """
        # Zone 1: Static content (uses latched values where available)
        sorted_patterns = self._sort_patterns(patterns)
        latched_economy = (
            session_config.economy_mode_latched
            if session_config.is_latched
            else economy_mode
        )
        latched_track = (
            session_config.active_track_latched
            if session_config.is_latched
            else track_context.get("active_track", "")
        )

        zone1_parts = [
            system_instructions,
            f"\n{PROMPT_BOUNDARY_MARKER}\n",
            f"Tool Schemas:\n{tool_schemas}",
            f"\nPattern Library ({len(sorted_patterns)} patterns):\n"
            + self._format_patterns(sorted_patterns),
            f"\nSandbox: {sandbox_config}",
            f"\nTracks: {track_definitions}",
        ]

        zone1_content = "\n".join(zone1_parts)

        # Zone 2: Dynamic content
        zone2_parts = [
            f"Task: {task_description}",
            f"Cycle: {cycle_number}",
            f"Track: {latched_track} (F{track_context.get('f_level', '?')})",
            f"Budget remaining: ${track_context.get('budget_remaining', '?')}",
        ]
        if latched_economy:
            zone2_parts.append("Economy mode: ACTIVE")
        if recent_failures:
            zone2_parts.append(
                "Recent failures:\n" + "\n".join(recent_failures[-3:])
            )
        if optimization_brief:
            zone2_parts.append(f"Optimization: {optimization_brief}")

        zone2_content = "\n".join(zone2_parts)

        return TwoZonePrompt(
            zone1_static=PromptZone(
                content=zone1_content,
                scope="session",
                cache_control=True,
            ),
            zone2_dynamic=PromptZone(
                content=zone2_content,
                scope=None,
                cache_control=False,
            ),
        )

    @staticmethod
    def _sort_patterns(patterns: list[Any]) -> list[Any]:
        """Sort patterns deterministically by pattern_id for cache stability.

        Batch pattern updates to session boundaries, not mid-cycle.
        """
        return sorted(
            patterns,
            key=lambda p: getattr(p, "pattern_id", ""),
        )

    @staticmethod
    def _format_patterns(patterns: list[Any]) -> str:
        """Format sorted patterns for prompt inclusion."""
        lines: list[str] = []
        for p in patterns:
            pid = getattr(p, "pattern_id", "?")
            desc = getattr(p, "description", "")
            lines.append(f"  [{pid}] {desc}")
        return "\n".join(lines) if lines else "  (none)"

    @staticmethod
    def compute_pattern_hash(patterns: list[Any]) -> str:
        """Compute hash of the sorted pattern set for latching."""
        ids = sorted(getattr(p, "pattern_id", "") for p in patterns)
        return hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:16]
