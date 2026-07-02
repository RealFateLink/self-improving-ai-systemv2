"""Layer 6 — Router.

Entity-task routing with skill coverage analysis and collaboration mode
selection. Routes tasks to the best entity (generalist or specialist agent)
and determines collaboration type.
~180 lines | Category: AGENT_SYSTEM
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Optional

logger = logging.getLogger(__name__)

GENERALIST_ENTITY_ID = "MAIN"


class CollaborationType(StrEnum):
    """Collaboration modes between entities."""

    SOLO = "SOLO"             # No supporters; single entity handles task
    GUIDED = "GUIDED"         # Supporters provide pre-generation guidance (~$0.001/supporter)
    REVIEWED = "REVIEWED"     # Supporters review after evaluation (~$0.001/supporter)
    FULL_COLLAB = "FULL_COLLAB"  # Both guidance AND review (~$0.002/supporter)


@dataclass(frozen=True)
class RoutingCase:
    """Analysis of a single skill's coverage across entities."""

    skill_tag: str
    best_entity_id: str
    coverage_score: float  # Combined pass rate + attempt count weight
    is_primary_skill: bool


@dataclass(frozen=True)
class CollaborativeRoutingDecision:
    """Final routing decision with collaboration details."""

    task_id: str
    primary_entity_id: str
    supporters: tuple[str, ...]
    collaboration_type: CollaborationType
    routing_cases: tuple[RoutingCase, ...]
    rationale: str


class Router:
    """Routes tasks to entities with skill-based coverage analysis.

    Determines which entity (generalist or specialist agent) should
    handle a task as primary, selects supporting entities for
    collaboration, and chooses the collaboration mode.
    """

    def __init__(self, ledger: Any, config: Any) -> None:
        self._ledger = ledger
        self._config = config

    def route(
        self,
        task: Any,
        track: str,
        agents: list[Any],
        ctx: Any,
    ) -> CollaborativeRoutingDecision:
        """Route a task to the best entity with collaboration plan.

        Steps:
          1. If agents disabled, return SOLO to generalist.
          2. Compute skill coverage map across all entities.
          3. Select primary entity (must cover task's PRIMARY skill).
          4. Select supporting entities for uncovered skills.
          5. Determine collaboration mode.

        Args:
            task: TaskSpec with skill_tags and primary_skill.
            track: Domain track identifier.
            agents: List of AgentState objects for this track.
            ctx: CycleContext with runtime info.

        Returns CollaborativeRoutingDecision.
        """
        agents_enabled = getattr(self._config, "agents_enabled", True)
        if not agents_enabled:
            return self._solo_generalist(task, "Agent system disabled")

        # Filter to eligible agents for this track
        eligible = [
            a for a in agents
            if self._agent_eligible(a, track, ctx)
        ]

        if not eligible:
            return self._solo_generalist(task, "No eligible agents for track")

        # Compute skill coverage
        skill_tags = getattr(task, "skill_tags", ())
        primary_skill = getattr(task, "primary_skill", skill_tags[0] if skill_tags else None)

        coverage_map = self._compute_skill_coverage(
            task, eligible, primary_skill
        )

        # Select primary entity
        primary_id = self._select_primary(coverage_map, primary_skill)

        # Select supporters
        supporters = self._select_supporters(coverage_map, primary_id)

        # Determine collaboration mode
        collab_type = self._determine_collaboration(
            primary_id, supporters, task
        )

        cases = tuple(coverage_map.values())

        return CollaborativeRoutingDecision(
            task_id=getattr(task, "task_id", ""),
            primary_entity_id=primary_id,
            supporters=tuple(supporters),
            collaboration_type=collab_type,
            routing_cases=cases,
            rationale=self._build_rationale(primary_id, supporters, collab_type),
        )

    # ── Internal Methods ─────────────────────────────────────────────────────

    def _compute_skill_coverage(
        self,
        task: Any,
        agents: list[Any],
        primary_skill: Optional[str],
    ) -> dict[str, RoutingCase]:
        """Map each skill_tag to the entity with best coverage.

        Coverage score = pass_rate_weight * pass_rate + attempt_weight * log(attempts + 1).
        """
        skill_tags = getattr(task, "skill_tags", ())
        pass_rate_weight = getattr(self._config, "routing_pass_rate_weight", 0.7)
        attempt_weight = getattr(self._config, "routing_attempt_weight", 0.3)

        coverage: dict[str, RoutingCase] = {}

        for skill in skill_tags:
            best_entity = GENERALIST_ENTITY_ID
            best_score = self._entity_skill_score(
                GENERALIST_ENTITY_ID, skill, pass_rate_weight, attempt_weight
            )

            for agent in agents:
                agent_id = getattr(agent, "agent_id", "")
                score = self._entity_skill_score(
                    agent_id, skill, pass_rate_weight, attempt_weight
                )
                if score > best_score:
                    best_score = score
                    best_entity = agent_id

            coverage[skill] = RoutingCase(
                skill_tag=skill,
                best_entity_id=best_entity,
                coverage_score=best_score,
                is_primary_skill=(skill == primary_skill),
            )

        return coverage

    def _entity_skill_score(
        self,
        entity_id: str,
        skill: str,
        pass_rate_weight: float,
        attempt_weight: float,
    ) -> float:
        """Compute coverage score for an entity on a skill."""
        import math

        pass_rate = self._ledger.get_entity_skill_pass_rate(entity_id, skill)
        attempts = self._ledger.get_entity_skill_attempts(entity_id, skill)

        return (
            pass_rate_weight * pass_rate
            + attempt_weight * math.log(attempts + 1)
        )

    def _select_primary(
        self,
        coverage_map: dict[str, RoutingCase],
        primary_skill: Optional[str],
    ) -> str:
        """Select the primary entity for this task.

        Must cover the task's PRIMARY skill. If no agent covers
        the primary skill, generalist is primary.
        """
        if primary_skill and primary_skill in coverage_map:
            return coverage_map[primary_skill].best_entity_id
        return GENERALIST_ENTITY_ID

    def _select_supporters(
        self,
        coverage_map: dict[str, RoutingCase],
        primary_id: str,
    ) -> list[str]:
        """Select supporting entities for skills not covered by primary.

        Only ACTIVE agents eligible as supporters.
        """
        supporters: list[str] = []
        seen: set[str] = {primary_id}

        for skill, case in coverage_map.items():
            if case.best_entity_id != primary_id and case.best_entity_id not in seen:
                supporters.append(case.best_entity_id)
                seen.add(case.best_entity_id)

        return supporters

    def _determine_collaboration(
        self,
        primary_id: str,
        supporters: list[str],
        task: Any,
    ) -> CollaborationType:
        """Select collaboration mode based on supporter availability and task complexity.

        SOLO: no supporters needed or available.
        GUIDED: supporters provide pre-generation guidance.
        REVIEWED: supporters review after evaluation.
        FULL_COLLAB: both guidance and review (maximum quality).
        """
        if not supporters:
            return CollaborationType.SOLO

        # Check if collaboration adds value (from historical data)
        collab_disable_threshold = getattr(
            self._config, "collaboration_disable_threshold", 2.0
        )
        collab_delta = self._ledger.get_collaboration_improvement_delta()
        if collab_delta < collab_disable_threshold:
            return CollaborationType.SOLO

        task_complexity = getattr(task, "complexity", "MEDIUM")
        num_skills = len(getattr(task, "skill_tags", ()))

        # Full collaboration for complex multi-skill tasks
        if task_complexity == "HIGH" or num_skills >= 4:
            return CollaborationType.FULL_COLLAB

        # Reviewed for moderate complexity
        if task_complexity == "MEDIUM" or num_skills >= 2:
            return CollaborationType.REVIEWED

        # Guided for simpler tasks with supporters
        return CollaborationType.GUIDED

    def _agent_eligible(self, agent: Any, track: str, ctx: Any) -> bool:
        """Check if an agent is eligible for routing.

        Conditions:
          - agent.state == ACTIVE
          - agent.track == track
          - Track readiness allows routing (FULL or DEGRADED)

        TRAINING agents cannot receive routed tasks or provide collaboration.
        """
        agent_state = getattr(agent, "lifecycle_state", "")
        if agent_state != "ACTIVE":
            return False

        agent_track = getattr(agent, "domain_track", "")
        if agent_track != track:
            return False

        # Check track readiness
        track_readiness = getattr(ctx, "track_readiness", "FULL")
        if track_readiness in ("MAINTENANCE", "BLOCKED"):
            return False

        return True

    def _solo_generalist(
        self, task: Any, reason: str
    ) -> CollaborativeRoutingDecision:
        """Create a SOLO routing decision to the generalist."""
        return CollaborativeRoutingDecision(
            task_id=getattr(task, "task_id", ""),
            primary_entity_id=GENERALIST_ENTITY_ID,
            supporters=(),
            collaboration_type=CollaborationType.SOLO,
            routing_cases=(),
            rationale=reason,
        )

    @staticmethod
    def _build_rationale(
        primary_id: str, supporters: list[str], collab_type: CollaborationType
    ) -> str:
        """Build human-readable routing rationale."""
        if collab_type == CollaborationType.SOLO:
            return f"SOLO to {primary_id}"
        supporter_str = ", ".join(supporters)
        return f"{collab_type.value}: primary={primary_id}, supporters=[{supporter_str}]"
