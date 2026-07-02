"""Layer 1 — Invariant enforcement.

Enforces system invariants including table protection, track state
transitions, budget limits, graduation monotonicity, sandbox isolation,
and deactivation approval requirements.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ..result import Result, InvariantViolation
from ..types.enums import TrackStatus, ProtectionLevel
from ..types.track import TRACK_TRANSITION_RULES


class InvariantEnforcer:
    """Enforces system invariants (INV-001 through INV-007)."""

    def __init__(self, protected_params: dict[str, Any]) -> None:
        self._protected = protected_params
        self._violation_count: int = 0

    # ------------------------------------------------------------------
    # Table write protection
    # ------------------------------------------------------------------

    def check_table_write(
        self,
        table: str,
        operation: str,
        columns: Optional[list[str]] = None,
        human_initiated: bool = False,
    ) -> Result[None, InvariantViolation]:
        """Check if a write operation is allowed on a protected table.

        INV-003: Protected tables cannot be modified outside allowed columns.
        """
        tables_config = self._protected.get("tables", {})
        if table not in tables_config:
            return Result(value=None)  # Unprotected table

        table_config = tables_config[table]
        protection = table_config.get("protection", "")

        # HUMAN_ONLY: reject unless human-initiated
        if protection == "HUMAN_ONLY" and not human_initiated:
            return self._violation(
                "INV-003",
                f"Table '{table}' is HUMAN_ONLY, non-human {operation} rejected",
                "check_table_write",
            )

        # PROTECTED: no modifications at all (after initial seed)
        if protection == "PROTECTED" and operation in ("update", "delete"):
            return self._violation(
                "INV-003",
                f"Table '{table}' is PROTECTED, {operation} not allowed",
                "check_table_write",
            )

        # APPEND_ONLY: inserts only, no updates or deletes
        if protection == "APPEND_ONLY" and operation in ("update", "delete"):
            return self._violation(
                "INV-003",
                f"Table '{table}' is APPEND_ONLY, {operation} not allowed",
                "check_table_write",
            )

        # RESTRICTED_UPDATE: only specific columns
        if protection == "RESTRICTED_UPDATE" and operation == "update":
            allowed = set(table_config.get("allowed_update_columns", []))
            if columns:
                disallowed = set(columns) - allowed
                if disallowed:
                    return self._violation(
                        "INV-003",
                        f"Table '{table}': columns {disallowed} not in allowed "
                        f"update set {allowed}",
                        "check_table_write",
                    )

        return Result(value=None)

    # ------------------------------------------------------------------
    # Track state transitions
    # ------------------------------------------------------------------

    def check_track_transition(
        self,
        from_status: TrackStatus,
        to_status: TrackStatus,
        human_approved: bool = False,
    ) -> Result[None, InvariantViolation]:
        """Validate a track state transition against the state machine.

        INV-006: Track state transitions must follow valid state machine.
        INV-007: Deactivation always requires human approval.
        """
        # Find matching transition rule
        valid_rule = None
        for rule in TRACK_TRANSITION_RULES:
            if rule.from_status == from_status and rule.to_status == to_status:
                valid_rule = rule
                break

        # Special case: Any -> PAUSED is always allowed (safety)
        if to_status == TrackStatus.PAUSED and valid_rule is None:
            return Result(value=None)

        if valid_rule is None:
            return self._violation(
                "INV-006",
                f"Invalid track transition: {from_status.value} -> {to_status.value}",
                "check_track_transition",
            )

        # Check approval requirement
        if valid_rule.requires_approval and not human_approved:
            return self._violation(
                "INV-007" if to_status == TrackStatus.DEACTIVATING else "INV-006",
                f"Transition {from_status.value} -> {to_status.value} "
                f"requires human approval",
                "check_track_transition",
            )

        return Result(value=None)

    def check_deactivation_approval(
        self, human_approved: bool,
    ) -> Result[None, InvariantViolation]:
        """INV-007: Deactivation always requires human approval."""
        if not human_approved:
            return self._violation(
                "INV-007",
                "Track deactivation requires human approval",
                "check_deactivation_approval",
            )
        return Result(value=None)

    # ------------------------------------------------------------------
    # Budget invariant
    # ------------------------------------------------------------------

    def check_budget_invariant(
        self, spent: float, limit: float,
    ) -> Result[None, InvariantViolation]:
        """INV-001: Budget never exceeds monthly limit."""
        if spent > limit:
            return self._violation(
                "INV-001",
                f"Budget exceeded: spent ${spent:.2f} > limit ${limit:.2f}",
                "check_budget_invariant",
            )
        return Result(value=None)

    # ------------------------------------------------------------------
    # Graduation monotonicity
    # ------------------------------------------------------------------

    _GATE_ORDER = {"G1": 1, "G2": 2, "G3": 3, "G4": 4, "G5": 5}

    def check_graduation_monotonic(
        self, old_gate: str, new_gate: str,
    ) -> Result[None, InvariantViolation]:
        """INV-002: Graduation state only advances, never regresses."""
        old_rank = self._GATE_ORDER.get(old_gate, 0)
        new_rank = self._GATE_ORDER.get(new_gate, 0)
        if new_rank < old_rank:
            return self._violation(
                "INV-002",
                f"Graduation regression: {old_gate} -> {new_gate}",
                "check_graduation_monotonic",
            )
        return Result(value=None)

    # ------------------------------------------------------------------
    # Sandbox isolation
    # ------------------------------------------------------------------

    def check_sandbox_isolation(
        self, violations: list[str],
    ) -> Result[None, InvariantViolation]:
        """INV-004: Sandbox cannot access filesystem/network."""
        if violations:
            return self._violation(
                "INV-004",
                f"Sandbox isolation violated: {', '.join(violations)}",
                "check_sandbox_isolation",
            )
        return Result(value=None)

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def check_agent_lifecycle_transition(
        self, from_state: str, to_state: str,
    ) -> Result[None, InvariantViolation]:
        """INV-005: Agent lifecycle transitions follow valid state machine."""
        valid_transitions: dict[str, set[str]] = {
            "proposed": {"constructing"},
            "constructing": {"training"},
            "training": {"probation"},
            "probation": {"active", "dissolving"},
            "active": {"paused", "merging", "dissolving"},
            "paused": {"active", "dissolving"},
            "merging": {"dissolving"},
            "dissolving": set(),
        }

        allowed = valid_transitions.get(from_state, set())
        if to_state not in allowed:
            return self._violation(
                "INV-005",
                f"Invalid agent transition: {from_state} -> {to_state}",
                "check_agent_lifecycle_transition",
            )
        return Result(value=None)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_violation_count(self) -> int:
        return self._violation_count

    def reset_violation_count(self) -> None:
        self._violation_count = 0

    def _violation(
        self,
        invariant_id: str,
        detail: str,
        operation: str,
        cycle_id: Optional[str] = None,
    ) -> Result[None, InvariantViolation]:
        self._violation_count += 1
        return Result(error=InvariantViolation(
            invariant_id=invariant_id,
            operation_attempted=operation,
            module_source="layer1.invariants",
            cycle_id=cycle_id,
            detail=detail,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
