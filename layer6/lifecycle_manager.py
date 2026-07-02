"""Layer 6 — Lifecycle Manager.

State machine for agent lifecycle: PROPOSED → TRAINING → PROBATION → ACTIVE
→ MERGING/DISSOLVING → DISSOLVED. Handles probation evaluation, AG1-AG3
graduation, and dissolution triggers.
~260 lines | Category: AGENT_SYSTEM
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AgentLifecycle(StrEnum):
    """Agent lifecycle states — 7 states."""

    PROPOSED = "PROPOSED"
    TRAINING = "TRAINING"
    PROBATION = "PROBATION"
    ACTIVE = "ACTIVE"
    MERGING = "MERGING"
    DISSOLVING = "DISSOLVING"
    DISSOLVED = "DISSOLVED"


class AgentGraduation(StrEnum):
    """Agent graduation levels — independent of G1-G5 system graduation."""

    AG1 = "AG1"  # Consistent pass rate → independent strategy proposals
    AG2 = "AG2"  # Cross-skill transfer → pattern sharing, help provision
    AG3 = "AG3"  # Frontier performance → taxonomy extension proposals


@dataclass(frozen=True)
class AgentStateTransition:
    """Records a state transition for audit trail."""

    agent_id: str
    from_state: AgentLifecycle
    to_state: AgentLifecycle
    reason: str
    triggered_at: str
    cycle_number: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProbationResult:
    """Result of probation evaluation."""

    agent_id: str
    passed: bool
    agent_pass_rate: float
    generalist_pass_rate: float
    margin: float
    cycles_evaluated: int
    detail: str


class LifecycleManager:
    """Manages agent lifecycle state machine and graduation.

    Evaluates transition conditions, applies state changes,
    handles probation (head-to-head vs generalist), AG1-AG3
    graduation, and dissolution triggers.
    """

    def __init__(self, ledger: Any, config: Any) -> None:
        self._ledger = ledger
        self._config = config

    # ── Public API ───────────────────────────────────────────────────────────

    def check_transitions(
        self, agent_id: str, agent_state: Any, cycle_number: int
    ) -> Optional[AgentStateTransition]:
        """Evaluate current state against transition conditions.

        Called after every agent cycle. Returns a transition if one
        is warranted, or None if the agent stays in current state.
        """
        current = AgentLifecycle(agent_state.lifecycle_state)

        if current == AgentLifecycle.TRAINING:
            if self.evaluate_training_complete(agent_id, agent_state):
                return AgentStateTransition(
                    agent_id=agent_id,
                    from_state=AgentLifecycle.TRAINING,
                    to_state=AgentLifecycle.PROBATION,
                    reason="Training metrics meet threshold",
                    triggered_at=datetime.now(timezone.utc).isoformat(),
                    cycle_number=cycle_number,
                )

        elif current == AgentLifecycle.PROBATION:
            result = self.evaluate_probation(agent_id, agent_state)
            if result is not None:
                target = (
                    AgentLifecycle.ACTIVE if result.passed
                    else AgentLifecycle.DISSOLVING
                )
                return AgentStateTransition(
                    agent_id=agent_id,
                    from_state=AgentLifecycle.PROBATION,
                    to_state=target,
                    reason=result.detail,
                    triggered_at=datetime.now(timezone.utc).isoformat(),
                    cycle_number=cycle_number,
                    metadata={
                        "agent_rate": result.agent_pass_rate,
                        "generalist_rate": result.generalist_pass_rate,
                        "margin": result.margin,
                    },
                )

        elif current == AgentLifecycle.ACTIVE:
            if self.check_dissolution_trigger(agent_id, agent_state):
                return AgentStateTransition(
                    agent_id=agent_id,
                    from_state=AgentLifecycle.ACTIVE,
                    to_state=AgentLifecycle.DISSOLVING,
                    reason="Generalist caught up on agent's skill cluster",
                    triggered_at=datetime.now(timezone.utc).isoformat(),
                    cycle_number=cycle_number,
                )

        elif current == AgentLifecycle.DISSOLVING:
            if self._dissolution_complete(agent_id):
                return AgentStateTransition(
                    agent_id=agent_id,
                    from_state=AgentLifecycle.DISSOLVING,
                    to_state=AgentLifecycle.DISSOLVED,
                    reason="Dissolution and archival complete",
                    triggered_at=datetime.now(timezone.utc).isoformat(),
                    cycle_number=cycle_number,
                )

        return None

    def apply_transition(
        self, agent_id: str, transition: AgentStateTransition
    ) -> None:
        """Execute a state change via Ledger and record the transition."""
        self._ledger.update_agent_registry_state(
            agent_id, transition.to_state.value
        )
        self._ledger.insert_agent_state_transition(
            agent_id=transition.agent_id,
            from_state=transition.from_state.value,
            to_state=transition.to_state.value,
            reason=transition.reason,
            triggered_at=transition.triggered_at,
            cycle_number=transition.cycle_number,
            metadata=transition.metadata,
        )
        logger.info(
            "Agent %s: %s → %s (%s)",
            agent_id,
            transition.from_state.value,
            transition.to_state.value,
            transition.reason,
        )

    def evaluate_training_complete(
        self, agent_id: str, agent_state: Any
    ) -> bool:
        """Check if agent has completed training phase.

        Conditions:
          - cycle count >= min_training_cycles (config)
          - pass rate above training_threshold (config)
        """
        min_cycles = getattr(self._config, "min_training_cycles", 100)
        threshold = getattr(self._config, "training_threshold", 0.3)

        cycle_count = self._ledger.get_agent_cycle_count(agent_id)
        if cycle_count < min_cycles:
            return False

        pass_rate = self._ledger.get_agent_pass_rate(agent_id)
        return pass_rate >= threshold

    def evaluate_probation(
        self, agent_id: str, agent_state: Any
    ) -> Optional[ProbationResult]:
        """Head-to-head comparison: agent vs generalist on same tasks.

        Fairness requirements:
          - Same skill profile, same difficulty, same track.
          - Minimum probation_min_cycles before evaluation.
          - Agent must exceed generalist by probation_margin.
          - If margin not met after max_probation_cycles: agent fails.

        Returns ProbationResult if a decision is reached, None if
        probation is still in progress.
        """
        min_cycles = getattr(self._config, "probation_min_cycles", 50)
        max_cycles = getattr(self._config, "max_probation_cycles", 200)
        margin = getattr(self._config, "probation_margin", 5.0)

        probation_cycles = self._ledger.get_agent_probation_cycle_count(agent_id)

        if probation_cycles < min_cycles:
            return None  # Not enough data yet

        # Get skill cluster for this agent
        skill_cluster = self._ledger.get_agent_skill_cluster(agent_id)

        # Get matched pass rates (same tasks, same conditions)
        agent_rate = self._ledger.get_agent_pass_rate_for_skills(
            agent_id, skill_cluster
        )
        generalist_rate = self._ledger.get_generalist_pass_rate_for_skills(
            skill_cluster
        )

        actual_margin = agent_rate - generalist_rate

        # Agent passes probation
        if actual_margin >= margin:
            return ProbationResult(
                agent_id=agent_id,
                passed=True,
                agent_pass_rate=agent_rate,
                generalist_pass_rate=generalist_rate,
                margin=actual_margin,
                cycles_evaluated=probation_cycles,
                detail=(
                    f"Agent exceeds generalist by {actual_margin:.1f}pp "
                    f"(threshold: {margin:.1f}pp)"
                ),
            )

        # Max cycles reached without passing
        if probation_cycles >= max_cycles:
            return ProbationResult(
                agent_id=agent_id,
                passed=False,
                agent_pass_rate=agent_rate,
                generalist_pass_rate=generalist_rate,
                margin=actual_margin,
                cycles_evaluated=probation_cycles,
                detail=(
                    f"Max probation cycles ({max_cycles}) reached. "
                    f"Margin {actual_margin:.1f}pp < {margin:.1f}pp threshold"
                ),
            )

        return None  # Still in progress

    def check_agent_graduation(
        self, agent_id: str, agent_state: Any
    ) -> Optional[AgentGraduation]:
        """Check if an ACTIVE agent qualifies for AG1/AG2/AG3 graduation.

        AG1: Consistent pass rate above threshold on skill cluster.
             Unlocks: independent strategy proposals.
        AG2: Cross-skill transfer within domain demonstrated.
             Unlocks: pattern sharing, help provision to other agents.
        AG3: Frontier performance reached.
             Unlocks: taxonomy extension proposals (human-reviewed).

        Returns the new graduation level if earned, None otherwise.
        """
        current_level = getattr(agent_state, "graduation_level", None)

        pass_rate = self._ledger.get_agent_pass_rate(agent_id)
        ag1_threshold = getattr(self._config, "ag1_threshold", 0.6)
        ag2_threshold = getattr(self._config, "ag2_threshold", 0.75)
        ag3_threshold = getattr(self._config, "ag3_threshold", 0.9)

        # Check AG3 first (highest)
        if current_level == AgentGraduation.AG2:
            if pass_rate >= ag3_threshold:
                frontier_evidence = self._check_frontier_performance(agent_id)
                if frontier_evidence:
                    return AgentGraduation.AG3

        # Check AG2
        if current_level == AgentGraduation.AG1:
            if pass_rate >= ag2_threshold:
                transfer_evidence = self._check_cross_skill_transfer(agent_id)
                if transfer_evidence:
                    return AgentGraduation.AG2

        # Check AG1
        if current_level is None:
            if pass_rate >= ag1_threshold:
                consistency = self._check_pass_rate_consistency(agent_id)
                if consistency:
                    return AgentGraduation.AG1

        return None

    def check_dissolution_trigger(
        self, agent_id: str, agent_state: Any
    ) -> bool:
        """Check if generalist has caught up to the agent.

        If generalist pass rate >= agent pass rate on the agent's
        skill cluster for a sustained window, triggers dissolution.
        Before triggering, runs a generalist probe to confirm.
        """
        dissolution_window = getattr(self._config, "dissolution_window_cycles", 100)
        skill_cluster = self._ledger.get_agent_skill_cluster(agent_id)

        agent_rate = self._ledger.get_agent_pass_rate_for_skills(
            agent_id, skill_cluster
        )
        generalist_rate = self._ledger.get_generalist_pass_rate_for_skills(
            skill_cluster
        )

        if generalist_rate < agent_rate:
            return False

        # Check sustained window
        sustained = self._ledger.get_generalist_sustained_advantage(
            skill_cluster, window=dissolution_window
        )
        if not sustained:
            return False

        # Generalist probe: confirm true catch-up
        return self._generalist_probe(agent_id, skill_cluster)

    # ── Internal Helpers ─────────────────────────────────────────────────────

    def _generalist_probe(
        self, agent_id: str, skills: tuple[str, ...]
    ) -> bool:
        """Run generalist on agent's best tasks to confirm catch-up.

        Prevents premature dissolution from noisy data.
        """
        probe_tasks = self._ledger.get_agent_best_tasks(agent_id, limit=10)
        if not probe_tasks:
            return False

        generalist_results = self._ledger.get_generalist_results_for_tasks(
            [t.task_id for t in probe_tasks]
        )
        if not generalist_results:
            return False

        generalist_pass_count = sum(
            1 for r in generalist_results if r.passed
        )
        probe_rate = generalist_pass_count / len(generalist_results)

        agent_rate = self._ledger.get_agent_pass_rate(agent_id)
        return probe_rate >= agent_rate

    def _check_frontier_performance(self, agent_id: str) -> bool:
        """Check if agent has reached frontier performance (AG3)."""
        skill_cluster = self._ledger.get_agent_skill_cluster(agent_id)
        agent_rate = self._ledger.get_agent_pass_rate_for_skills(
            agent_id, skill_cluster
        )
        frontier_threshold = getattr(self._config, "frontier_rate", 0.9)
        return agent_rate >= frontier_threshold

    def _check_cross_skill_transfer(self, agent_id: str) -> bool:
        """Check if agent demonstrates cross-skill transfer within domain (AG2).

        Evidence: improving pass rate on skills that weren't in the
        original skill cluster but are in the same domain.
        """
        skill_cluster = self._ledger.get_agent_skill_cluster(agent_id)
        domain = self._ledger.get_agent_domain_track(agent_id)
        domain_skills = self._ledger.get_skills_for_domain(domain)

        adjacent_skills = [s for s in domain_skills if s not in skill_cluster]
        if not adjacent_skills:
            return False

        agent_rates = self._ledger.get_agent_pass_rate_for_skills(
            agent_id, tuple(adjacent_skills)
        )
        baseline_rates = self._ledger.get_generalist_pass_rate_for_skills(
            tuple(adjacent_skills)
        )

        # Agent must show measurable improvement on adjacent skills
        transfer_margin = getattr(self._config, "transfer_margin", 3.0)
        return (agent_rates - baseline_rates) >= transfer_margin

    def _check_pass_rate_consistency(self, agent_id: str) -> bool:
        """Check if agent has consistent pass rate (AG1 requirement).

        Requires pass rate above threshold for a sustained window,
        not just a single measurement.
        """
        consistency_window = getattr(self._config, "ag1_consistency_window", 50)
        ag1_threshold = getattr(self._config, "ag1_threshold", 0.6)

        recent_rates = self._ledger.get_agent_rolling_pass_rates(
            agent_id, window=consistency_window
        )
        if len(recent_rates) < consistency_window:
            return False

        return all(r >= ag1_threshold for r in recent_rates)

    def _dissolution_complete(self, agent_id: str) -> bool:
        """Check if dissolution process is complete (archive created, tables renamed)."""
        return self._ledger.is_agent_dissolution_complete(agent_id)
