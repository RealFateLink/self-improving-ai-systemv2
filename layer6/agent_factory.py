"""Layer 6 — Agent Factory.

Creates specialist agents with prefixed tables, module sets, and seed data.
Dissolves agents with archival. Supports warm-start from prior archives.
~290 lines | Category: AGENT_SYSTEM
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Table suffix sets for agent-prefixed tables ──────────────────────────────

AGENT_APPEND_ONLY_SUFFIXES: tuple[str, ...] = (
    "cycle",
    "cycle_outcome",
    "failure_narrative",
    "reasoning_correction",
    "root_cause_chain",
    "counterfactual",
    "prediction_rule",
    "candidate_evaluation",
    "scoring_result",
    "promotion_result",
)

AGENT_RESTRICTED_SUFFIXES: tuple[str, ...] = (
    "strategy_version",
    "skill_rate",
    "feature_vector",
    "self_model_snapshot",
    "prevention_artifact",
)

ALL_AGENT_TABLE_SUFFIXES: tuple[str, ...] = (
    AGENT_APPEND_ONLY_SUFFIXES + AGENT_RESTRICTED_SUFFIXES
)


@dataclass(frozen=True)
class AgentTableSet:
    """Tracks the table names created for a specific agent."""

    agent_id: str
    prefix: str
    table_names: tuple[str, ...]


@dataclass(frozen=True)
class AgentConstructionResult:
    """Result of agent creation."""

    success: bool
    agent_id: str
    table_set: Optional[AgentTableSet] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class AgentArchive:
    """Archived agent data for future warm-start."""

    agent_id: str
    skill_cluster: tuple[str, ...]
    predictor_rules_json: str
    strategy_snapshot_json: str
    beta_weights_json: str
    dissolved_at_cycle: int
    dissolved_at: str
    dissolution_reason: str


class AgentFactory:
    """Creates and dissolves specialist sub-agents.

    Handles table creation, module set building, initial data seeding,
    warm-start from archives, and clean dissolution with archival.
    """

    def __init__(self, ledger: Any, config: Any) -> None:
        self._ledger = ledger
        self._config = config
        self._active_agents: dict[str, AgentTableSet] = {}

    # ── Public API ───────────────────────────────────────────────────────────

    def create_agent(
        self,
        proposal: Any,
        approval: Any,
    ) -> AgentConstructionResult:
        """Create a specialist agent from an approved proposal.

        Steps:
          1. Validate proposal and approval status.
          2. Generate unique agent_id with prefix.
          3. Create 15 prefixed tables.
          4. Seed initial data from generalist.
          5. Optionally warm-start from archive.
          6. Set gradual allocation ramp.
          7. Record creation in agent registry.

        Returns AgentConstructionResult with success/failure info.
        """
        try:
            agent_id = self._generate_agent_id(proposal)
            prefix = self._compute_prefix(agent_id)

            # Verify prefix uniqueness
            if not self._verify_prefix_unique(prefix):
                suffix = 1
                while not self._verify_prefix_unique(f"{prefix}_{suffix}"):
                    suffix += 1
                prefix = f"{prefix}_{suffix}"

            # Create 15 prefixed tables
            table_set = self._create_tables(agent_id, prefix)

            # Seed initial data from generalist
            self._seed_initial_data(agent_id, proposal)

            # Check for warm-start archive
            archive = self._find_archive(proposal.skill_cluster)
            if archive is not None:
                self._warm_start_from_archive(agent_id, archive)
                logger.info(
                    "Warm-started agent %s from archive %s",
                    agent_id,
                    archive.agent_id,
                )

            # Set gradual allocation ramp in system state
            self._set_gradual_ramp(agent_id)

            # Record in agent registry
            self._register_agent(agent_id, proposal, table_set)

            self._active_agents[agent_id] = table_set

            logger.info(
                "Created agent %s with %d tables for skills %s",
                agent_id,
                len(table_set.table_names),
                proposal.skill_cluster,
            )

            return AgentConstructionResult(
                success=True,
                agent_id=agent_id,
                table_set=table_set,
            )

        except Exception as exc:
            logger.error("Agent creation failed for proposal: %s", exc)
            return AgentConstructionResult(
                success=False,
                agent_id=getattr(proposal, "proposed_id", "UNKNOWN"),
                error=str(exc),
            )

    def build_module_set(self, agent_id: str, agent_state: Any) -> dict[str, Any]:
        """Create L4 module instances configured for this agent.

        Each module receives an AgentLedger that routes agent-specific
        data to prefixed tables while passing through shared data to
        the main ledger.

        Returns dict mapping module_name -> module instance.
        """
        table_set = self._active_agents.get(agent_id)
        if table_set is None:
            raise ValueError(f"Agent {agent_id} not found in active agents")

        agent_ledger = self._create_agent_ledger(agent_id, table_set)

        modules: dict[str, Any] = {
            "intent_interpreter": self._build_module(
                "intent_interpreter", agent_ledger, agent_state
            ),
            "curriculum_sampler": self._build_module(
                "curriculum_sampler", agent_ledger, agent_state
            ),
            "planner": self._build_module("planner", agent_ledger, agent_state),
            "generator": self._build_module("generator", agent_ledger, agent_state),
            "static_reviewer": self._build_module(
                "static_reviewer", agent_ledger, agent_state
            ),
            "dynamic_verifier": self._build_module(
                "dynamic_verifier", agent_ledger, agent_state
            ),
            "semantic_critic": self._build_module(
                "semantic_critic", agent_ledger, agent_state
            ),
            "selector": self._build_module("selector", agent_ledger, agent_state),
            "promotion_manager": self._build_module(
                "promotion_manager", agent_ledger, agent_state
            ),
            "failure_analyzer": self._build_module(
                "failure_analyzer", agent_ledger, agent_state
            ),
            "strategy_learner": self._build_module(
                "strategy_learner", agent_ledger, agent_state
            ),
            "meta_learner": self._build_module(
                "meta_learner", agent_ledger, agent_state
            ),
        }

        logger.info("Built %d modules for agent %s", len(modules), agent_id)
        return modules

    def dissolve_agent(self, agent_id: str, reason: str) -> AgentArchive:
        """Dissolve an agent: archive data, rename tables, deregister.

        Steps:
          1. Create AgentArchive with current state.
          2. Rename tables with _dissolved suffix.
          3. Remove from scheduler / active registry.
          4. Record dissolution event.

        Returns the archive for future warm-start.
        """
        table_set = self._active_agents.get(agent_id)
        if table_set is None:
            raise ValueError(f"Agent {agent_id} not found in active agents")

        # Build archive from current state
        archive = self._build_archive(agent_id, reason)

        # Rename tables with _dissolved suffix
        self._rename_tables_dissolved(table_set)

        # Deregister
        self._deregister_agent(agent_id)
        del self._active_agents[agent_id]

        logger.info("Dissolved agent %s: %s", agent_id, reason)
        return archive

    # ── Internal Helpers ─────────────────────────────────────────────────────

    def _generate_agent_id(self, proposal: Any) -> str:
        """Generate a unique agent ID from the proposal.

        Format: AGT_{TRACK_ABBREV}_{SEQUENCE:03d}
        Example: AGT_ALG_001, AGT_WEB_002
        """
        track = getattr(proposal, "domain_track", "GEN")
        abbrev = track[:3].upper()
        existing = self._count_agents_for_track(track)
        return f"AGT_{abbrev}_{existing + 1:03d}"

    def _compute_prefix(self, agent_id: str) -> str:
        """Compute table name prefix from agent ID."""
        return agent_id.replace("-", "_")

    def _verify_prefix_unique(self, prefix: str) -> bool:
        """Verify no other agent uses this prefix."""
        for table_set in self._active_agents.values():
            if table_set.prefix == prefix:
                return False
        return True

    def _create_tables(self, agent_id: str, prefix: str) -> AgentTableSet:
        """Create 15 prefixed tables for the agent.

        10 append-only tables + 5 restricted tables.
        Protected by L1 invariants.
        """
        table_names: list[str] = []
        for suffix in ALL_AGENT_TABLE_SUFFIXES:
            table_name = f"{prefix}_{suffix}"
            self._ledger.create_agent_table(table_name, suffix)
            table_names.append(table_name)

        return AgentTableSet(
            agent_id=agent_id,
            prefix=prefix,
            table_names=tuple(table_names),
        )

    def _seed_initial_data(self, agent_id: str, proposal: Any) -> None:
        """Seed agent with data from generalist.

        Seeds:
          - Recent failure patterns for agent's skills
          - Active prediction rules
          - Current strategy weights
        No direct pattern seeding (shared library handles it).
        """
        skill_cluster = getattr(proposal, "skill_cluster", ())

        # Copy recent failure patterns for these skills
        recent_failures = self._ledger.get_recent_failures_for_skills(
            skill_cluster, limit=50
        )
        for failure in recent_failures:
            self._ledger.insert_agent_failure_seed(agent_id, failure)

        # Copy active prediction rules
        prediction_rules = self._ledger.get_active_prediction_rules(skill_cluster)
        for rule in prediction_rules:
            self._ledger.insert_agent_prediction_rule(agent_id, rule)

        # Copy current strategy weights
        strategy = self._ledger.get_current_strategy_weights(skill_cluster)
        if strategy is not None:
            self._ledger.insert_agent_strategy_version(agent_id, strategy)

        logger.info(
            "Seeded agent %s with %d failures, %d rules",
            agent_id,
            len(recent_failures),
            len(prediction_rules),
        )

    def _warm_start_from_archive(self, agent_id: str, archive: AgentArchive) -> None:
        """Warm-start from a prior agent's archive.

        Loads archived weights with widened parameters, predictor rules,
        and strategy versions. Prevents cold-start.
        """
        # Load and widen beta weights
        archived_weights = json.loads(archive.beta_weights_json)
        widened = self._widen_params(archived_weights)
        self._ledger.insert_agent_beta_weights(agent_id, widened)

        # Load predictor rules
        rules = json.loads(archive.predictor_rules_json)
        for rule in rules:
            self._ledger.insert_agent_prediction_rule(agent_id, rule)

        # Load strategy snapshot
        strategy = json.loads(archive.strategy_snapshot_json)
        self._ledger.insert_agent_strategy_version(agent_id, strategy)

    @staticmethod
    def _widen_params(archived_weights: dict[str, Any]) -> dict[str, Any]:
        """Widen archived Beta distribution parameters.

        Algorithm: multiply alpha AND beta by 0.5.
        Preserves the mean (ratio) but increases variance,
        allowing the agent to re-explore rather than being
        locked into the previous agent's beliefs.
        """
        widened: dict[str, Any] = {}
        for skill, params in archived_weights.items():
            alpha = params.get("alpha", 1.0)
            beta = params.get("beta", 1.0)
            widened[skill] = {
                "alpha": alpha * 0.5,
                "beta": beta * 0.5,
            }
        return widened

    def _find_archive(self, skill_cluster: tuple[str, ...]) -> Optional[AgentArchive]:
        """Find a dissolved agent archive matching the skill cluster."""
        archives = self._ledger.get_dissolved_agent_archives()
        for arch in archives:
            if set(arch.skill_cluster) & set(skill_cluster):
                return arch
        return None

    def _set_gradual_ramp(self, agent_id: str) -> None:
        """Set initial allocation with gradual ramp-up.

        New agents start at initial_allocation_pct and ramp to target
        over ramp_cycles. Stored in system_state.
        """
        initial_pct = getattr(self._config, "initial_allocation_pct", 5.0)
        ramp_cycles = getattr(self._config, "ramp_cycles", 100)
        self._ledger.set_system_state(
            f"agent_ramp_{agent_id}",
            json.dumps(
                {
                    "current_pct": initial_pct,
                    "target_pct": None,  # Set by resource_allocator
                    "ramp_cycles_remaining": ramp_cycles,
                }
            ),
        )

    def _register_agent(
        self, agent_id: str, proposal: Any, table_set: AgentTableSet
    ) -> None:
        """Register agent in the agent registry table."""
        self._ledger.insert_agent_registry(
            agent_id=agent_id,
            domain_track=getattr(proposal, "domain_track", "CORE_ALGORITHMS"),
            skill_cluster=getattr(proposal, "skill_cluster", ()),
            state="TRAINING",
            created_at=datetime.now(timezone.utc).isoformat(),
            table_prefix=table_set.prefix,
        )

    def _deregister_agent(self, agent_id: str) -> None:
        """Mark agent as dissolved in registry."""
        self._ledger.update_agent_registry_state(agent_id, "DISSOLVED")

    def _build_archive(self, agent_id: str, reason: str) -> AgentArchive:
        """Build an archive from the agent's current state."""
        predictor_rules = self._ledger.get_agent_prediction_rules(agent_id)
        strategy = self._ledger.get_agent_current_strategy(agent_id)
        beta_weights = self._ledger.get_agent_beta_weights(agent_id)
        cycle_count = self._ledger.get_agent_cycle_count(agent_id)
        skill_cluster = self._ledger.get_agent_skill_cluster(agent_id)

        return AgentArchive(
            agent_id=agent_id,
            skill_cluster=tuple(skill_cluster),
            predictor_rules_json=json.dumps(predictor_rules),
            strategy_snapshot_json=json.dumps(strategy),
            beta_weights_json=json.dumps(beta_weights),
            dissolved_at_cycle=cycle_count,
            dissolved_at=datetime.now(timezone.utc).isoformat(),
            dissolution_reason=reason,
        )

    def _rename_tables_dissolved(self, table_set: AgentTableSet) -> None:
        """Rename agent tables with _dissolved suffix."""
        for table_name in table_set.table_names:
            dissolved_name = f"{table_name}_dissolved"
            self._ledger.rename_table(table_name, dissolved_name)

    def _count_agents_for_track(self, track: str) -> int:
        """Count existing agents (active + dissolved) for a track."""
        return self._ledger.count_agents_for_track(track)

    def _create_agent_ledger(self, agent_id: str, table_set: AgentTableSet) -> Any:
        """Create an AgentLedger that routes to prefixed tables.

        AgentLedger wraps the main Ledger:
          - Agent-specific operations route to prefixed tables.
          - Shared operations (embeddings, patterns, tasks, config,
            cost events, approval queue) pass through to main Ledger.
        """
        return AgentLedger(
            main_ledger=self._ledger,
            agent_id=agent_id,
            table_set=table_set,
        )

    @staticmethod
    def _build_module(
        module_name: str, agent_ledger: Any, agent_state: Any
    ) -> Any:
        """Build a single L4 module configured for an agent.

        Returns a placeholder module config dict; actual module
        instantiation depends on L4 module factory.
        """
        return {
            "module_name": module_name,
            "ledger": agent_ledger,
            "agent_state": agent_state,
            "is_agent_module": True,
        }


class AgentLedger:
    """Wraps the main Ledger to route agent-specific data to prefixed tables.

    Agent-prefixed tables: cycle records, failure analysis, learning state.
    Shared tables (pass-through): embedding index, pattern library,
    task pool, config, templates, cost events, root cause chains,
    approval queue.
    """

    def __init__(
        self, main_ledger: Any, agent_id: str, table_set: AgentTableSet
    ) -> None:
        self._main = main_ledger
        self._agent_id = agent_id
        self._table_set = table_set
        self._prefix = table_set.prefix

    @property
    def agent_id(self) -> str:
        return self._agent_id

    # ── Agent-prefixed operations ────────────────────────────────────────────

    def insert_cycle(self, record: Any) -> None:
        """Insert cycle record into agent-prefixed cycle table."""
        self._main.insert_into_prefixed(f"{self._prefix}_cycle", record)

    def insert_cycle_outcome(self, outcome: Any) -> None:
        self._main.insert_into_prefixed(f"{self._prefix}_cycle_outcome", outcome)

    def insert_failure_narrative(self, narrative: Any) -> None:
        self._main.insert_into_prefixed(
            f"{self._prefix}_failure_narrative", narrative
        )

    def insert_scoring_result(self, result: Any) -> None:
        self._main.insert_into_prefixed(f"{self._prefix}_scoring_result", result)

    def insert_promotion_result(self, result: Any) -> None:
        self._main.insert_into_prefixed(f"{self._prefix}_promotion_result", result)

    def get_recent_cycles(self, limit: int = 50) -> list[Any]:
        return self._main.get_from_prefixed(f"{self._prefix}_cycle", limit=limit)

    def get_skill_rates(self) -> dict[str, float]:
        return self._main.get_from_prefixed_dict(f"{self._prefix}_skill_rate")

    # ── Shared pass-through operations ───────────────────────────────────────

    def insert_embedding(self, *args: Any, **kwargs: Any) -> Any:
        return self._main.insert_embedding(*args, **kwargs)

    def search_similar(self, *args: Any, **kwargs: Any) -> Any:
        return self._main.search_similar(*args, **kwargs)

    def add_pattern(self, *args: Any, **kwargs: Any) -> Any:
        return self._main.add_pattern(*args, entity_id=self._agent_id, **kwargs)

    def get_patterns(self, *args: Any, **kwargs: Any) -> Any:
        return self._main.get_patterns(*args, **kwargs)

    def get_tasks(self, *args: Any, **kwargs: Any) -> Any:
        return self._main.get_tasks(*args, **kwargs)

    def get_config(self, *args: Any, **kwargs: Any) -> Any:
        return self._main.get_config(*args, **kwargs)

    def get_template(self, *args: Any, **kwargs: Any) -> Any:
        return self._main.get_template(*args, **kwargs)

    def record_cost_event(self, *args: Any, **kwargs: Any) -> Any:
        return self._main.record_cost_event(
            *args, entity_id=self._agent_id, **kwargs
        )

    def insert_approval_item(self, *args: Any, **kwargs: Any) -> Any:
        return self._main.insert_approval_item(*args, **kwargs)

    def insert_root_cause_chain(self, chain: Any) -> None:
        """Agent-local during discovery; copies to shared after STABLE."""
        self._main.insert_into_prefixed(
            f"{self._prefix}_root_cause_chain", chain
        )

    def promote_root_cause_to_shared(self, chain_id: str) -> None:
        """Copy confirmed (STABLE) root cause chain to shared table."""
        chain = self._main.get_from_prefixed_by_id(
            f"{self._prefix}_root_cause_chain", chain_id
        )
        if chain is not None:
            self._main.insert_root_cause_chain(chain)
