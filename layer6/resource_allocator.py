"""Layer 6 — Resource Allocator.

Cycle allocation rebalancing across entities. Performance-weighted
allocation with cap enforcement, oscillation dampening, and gradual
ramp for new agents.
~170 lines | Category: AGENT_SYSTEM
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

GENERALIST_ENTITY_ID = "MAIN"


@dataclass
class ResourceAllocation:
    """Allocation state for a single entity."""

    entity_id: str
    allocation_pct: float
    actual_cycles: int = 0
    target_cycles: int = 0
    is_ramping: bool = False
    ramp_cycles_remaining: int = 0


@dataclass
class AllocationSnapshot:
    """Complete allocation state across all entities."""

    allocations: dict[str, ResourceAllocation]
    total_cycles: int
    generalist_floor_pct: float
    rebalanced_at_cycle: int


class ResourceAllocator:
    """Manages cycle allocation across generalist and specialist agents.

    Rebalances periodically based on performance. Higher-performing
    entities get more cycles. Enforces caps, generalist floor, and
    oscillation dampening. New agents ramp up gradually.
    """

    def __init__(self, ledger: Any, config: Any) -> None:
        self._ledger = ledger
        self._config = config
        self._prev_allocations: dict[str, float] = {}

    # ── Public API ───────────────────────────────────────────────────────────

    def reallocate(
        self,
        agents: list[Any],
        cycle_number: int,
    ) -> AllocationSnapshot:
        """Compute new allocation percentages for all entities.

        Called every reallocation_interval_cycles. Steps:
          1. Compute performance-weighted allocations.
          2. Apply caps (min, max, generalist floor).
          3. Apply oscillation dampening.
          4. Apply gradual ramp for new agents.
          5. Normalize to 100%.

        Returns AllocationSnapshot.
        """
        generalist_floor = getattr(
            self._config, "generalist_floor_pct", 40.0
        )

        # Step 1: Performance-weighted allocation
        raw_allocations = self._compute_allocations(agents)

        # Step 2: Apply caps
        capped = self._apply_caps(raw_allocations, agents, generalist_floor)

        # Step 3: Oscillation dampening
        dampened = self._dampen_oscillation(capped)

        # Step 4: Gradual ramp for new agents
        ramped = self._apply_gradual_ramps(dampened, agents)

        # Step 5: Normalize to 100%
        normalized = self._normalize(ramped, generalist_floor)

        # Build allocation objects
        allocations: dict[str, ResourceAllocation] = {}
        for entity_id, pct in normalized.items():
            ramp_info = self._get_ramp_info(entity_id)
            allocations[entity_id] = ResourceAllocation(
                entity_id=entity_id,
                allocation_pct=pct,
                is_ramping=ramp_info.get("ramping", False),
                ramp_cycles_remaining=ramp_info.get("remaining", 0),
            )

        # Store for next dampening comparison
        self._prev_allocations = {eid: a.allocation_pct for eid, a in allocations.items()}

        # Persist to system state
        self._persist_allocations(allocations, cycle_number)

        snapshot = AllocationSnapshot(
            allocations=allocations,
            total_cycles=cycle_number,
            generalist_floor_pct=generalist_floor,
            rebalanced_at_cycle=cycle_number,
        )

        logger.info(
            "Rebalanced allocations at cycle %d: %s",
            cycle_number,
            {eid: f"{a.allocation_pct:.1f}%" for eid, a in allocations.items()},
        )

        return snapshot

    def get_current_allocations(self) -> dict[str, float]:
        """Return current allocation percentages."""
        state_json = self._ledger.get_system_state("resource_allocations")
        if state_json is None:
            return {GENERALIST_ENTITY_ID: 100.0}
        return json.loads(state_json)

    def check_drift(
        self,
        agents: list[Any],
        cycle_number: int,
    ) -> bool:
        """Check if actual cycles deviate significantly from target.

        Returns True if drift exceeds tolerance and rebalancing is needed.
        """
        tolerance = getattr(self._config, "allocation_drift_tolerance_pct", 3.0)
        current = self.get_current_allocations()

        for entity_id, target_pct in current.items():
            actual_pct = self._compute_actual_pct(entity_id, cycle_number)
            if abs(actual_pct - target_pct) > tolerance:
                return True

        return False

    # ── Internal Methods ─────────────────────────────────────────────────────

    def _compute_allocations(
        self, agents: list[Any]
    ) -> dict[str, float]:
        """Performance-weighted allocation.

        Higher-performing entities get more cycles. Generalist
        always included.
        """
        scores: dict[str, float] = {}

        # Generalist score
        gen_rate = self._ledger.get_entity_pass_rate(GENERALIST_ENTITY_ID)
        scores[GENERALIST_ENTITY_ID] = max(gen_rate, 0.01)

        # Agent scores (only ACTIVE agents)
        for agent in agents:
            agent_id = getattr(agent, "agent_id", "")
            state = getattr(agent, "lifecycle_state", "")
            if state != "ACTIVE":
                continue
            rate = self._ledger.get_agent_pass_rate(agent_id)
            scores[agent_id] = max(rate, 0.01)

        # Normalize to percentages
        total = sum(scores.values())
        return {eid: (score / total) * 100.0 for eid, score in scores.items()}

    def _apply_caps(
        self,
        allocations: dict[str, float],
        agents: list[Any],
        generalist_floor: float,
    ) -> dict[str, float]:
        """Enforce min/max caps and generalist floor."""
        max_pct = getattr(self._config, "max_allocation_pct", 60.0)
        min_pct = getattr(self._config, "min_allocation_pct", 5.0)

        capped: dict[str, float] = {}
        for eid, pct in allocations.items():
            if eid == GENERALIST_ENTITY_ID:
                capped[eid] = max(pct, generalist_floor)
            else:
                capped[eid] = max(min(pct, max_pct), min_pct)

        return capped

    def _dampen_oscillation(
        self, new_alloc: dict[str, float]
    ) -> dict[str, float]:
        """Limit change per reallocation to prevent wild swings.

        Max change: max_reallocation_delta_pct per cycle (default 5%).
        """
        max_delta = getattr(self._config, "max_reallocation_delta_pct", 5.0)

        dampened: dict[str, float] = {}
        for eid, new_pct in new_alloc.items():
            prev_pct = self._prev_allocations.get(eid, new_pct)
            delta = new_pct - prev_pct

            if abs(delta) > max_delta:
                clamped_delta = max_delta if delta > 0 else -max_delta
                dampened[eid] = prev_pct + clamped_delta
            else:
                dampened[eid] = new_pct

        return dampened

    def _apply_gradual_ramps(
        self,
        allocations: dict[str, float],
        agents: list[Any],
    ) -> dict[str, float]:
        """Apply gradual ramp for new agents.

        New agents start at initial_allocation_pct and ramp to target
        over ramp_cycles. Excess given to generalist.
        """
        ramped = dict(allocations)

        for agent in agents:
            agent_id = getattr(agent, "agent_id", "")
            if agent_id not in ramped:
                continue

            ramp_state = self._ledger.get_system_state(f"agent_ramp_{agent_id}")
            if ramp_state is None:
                continue

            ramp = json.loads(ramp_state)
            remaining = ramp.get("ramp_cycles_remaining", 0)
            if remaining <= 0:
                continue

            initial_pct = getattr(self._config, "initial_allocation_pct", 5.0)
            target_pct = ramped[agent_id]

            # Linear interpolation
            total_ramp = getattr(self._config, "ramp_cycles", 100)
            progress = (total_ramp - remaining) / total_ramp
            ramped_pct = initial_pct + (target_pct - initial_pct) * progress
            ramped[agent_id] = ramped_pct

            # Decrement ramp counter
            ramp["ramp_cycles_remaining"] = remaining - 1
            ramp["current_pct"] = ramped_pct
            ramp["target_pct"] = target_pct
            self._ledger.set_system_state(
                f"agent_ramp_{agent_id}", json.dumps(ramp)
            )

        return ramped

    def _normalize(
        self, allocations: dict[str, float], generalist_floor: float
    ) -> dict[str, float]:
        """Normalize allocations to sum to 100%.

        If rounding causes overflow/underflow, adjust generalist.
        """
        total = sum(allocations.values())
        if total == 0:
            return {GENERALIST_ENTITY_ID: 100.0}

        normalized = {eid: (pct / total) * 100.0 for eid, pct in allocations.items()}

        # Ensure generalist floor after normalization
        if normalized.get(GENERALIST_ENTITY_ID, 0) < generalist_floor:
            deficit = generalist_floor - normalized[GENERALIST_ENTITY_ID]
            normalized[GENERALIST_ENTITY_ID] = generalist_floor

            # Distribute deficit proportionally among agents
            agent_ids = [eid for eid in normalized if eid != GENERALIST_ENTITY_ID]
            agent_total = sum(normalized[eid] for eid in agent_ids)
            if agent_total > 0:
                for eid in agent_ids:
                    reduction = deficit * (normalized[eid] / agent_total)
                    normalized[eid] = max(normalized[eid] - reduction, 0.0)

        return normalized

    def _get_ramp_info(self, entity_id: str) -> dict[str, Any]:
        """Get ramp info for an entity."""
        ramp_state = self._ledger.get_system_state(f"agent_ramp_{entity_id}")
        if ramp_state is None:
            return {"ramping": False, "remaining": 0}

        ramp = json.loads(ramp_state)
        remaining = ramp.get("ramp_cycles_remaining", 0)
        return {"ramping": remaining > 0, "remaining": remaining}

    def _compute_actual_pct(self, entity_id: str, cycle_number: int) -> float:
        """Compute actual allocation percentage from cycle counts."""
        entity_cycles = self._ledger.count_entity_cycles(
            entity_id, window=100
        )
        total_cycles = self._ledger.count_all_cycles(window=100)
        if total_cycles == 0:
            return 0.0
        return (entity_cycles / total_cycles) * 100.0

    def _persist_allocations(
        self,
        allocations: dict[str, ResourceAllocation],
        cycle_number: int,
    ) -> None:
        """Save allocation state to system_state."""
        state = {
            eid: alloc.allocation_pct for eid, alloc in allocations.items()
        }
        self._ledger.set_system_state(
            "resource_allocations", json.dumps(state)
        )
        self._ledger.set_system_state(
            "last_reallocation_cycle", str(cycle_number)
        )
