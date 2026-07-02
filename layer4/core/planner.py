"""planner.py — Generates or reuses plans.

Stage 3.  Supports cache lookup through embeddings.
Emits: plan confidence + reuse risk.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["Planner", "Plan"]


@dataclass(frozen=True)
class ConfidenceScore:
    """Unified confidence schema."""
    value: float  # 0.0–1.0
    basis: str    # Evidence description


@dataclass(frozen=True)
class Plan:
    """A structured plan for solving a task."""
    plan_id: str
    steps: list[str]
    approach: str
    estimated_complexity: str
    confidence: ConfidenceScore
    reuse_risk: float  # 0.0–1.0: risk that reused plan may not fit
    is_reused: bool
    source_plan_id: str | None = None
    assumptions: list[str] = field(default_factory=list)


@dataclass
class Planner:
    """Generates or reuses execution plans for tasks.

    Uses embedding_index for plan cache lookup.
    Falls back to LLM generation for novel tasks.

    Dependencies:
      - llm_client (Layer 2): for plan generation
      - embedding_index (Layer 3): for plan cache lookup
    """

    llm_client: Any = None
    embedding_index: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    _plan_cache: dict[str, Plan] = field(default_factory=dict)

    def build_plan(
        self,
        directive: Any,
        cycle_context: dict[str, Any],
        assembled_context: Any = None,
    ) -> tuple[bool, Any]:
        """Generate or reuse a plan.

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        from .intent_interpreter import ModuleResult, ModuleError

        try:
            # Step 1: Check plan cache via embeddings.
            reused_plan = self._lookup_cache(directive)
            if reused_plan:
                reuse_risk = self._assess_reuse_risk(reused_plan, directive)
                if reuse_risk < 0.5:
                    plan = Plan(
                        plan_id=str(uuid.uuid4()),
                        steps=reused_plan.steps,
                        approach=reused_plan.approach,
                        estimated_complexity=reused_plan.estimated_complexity,
                        confidence=ConfidenceScore(
                            value=0.7 * (1.0 - reuse_risk),
                            basis="plan_reuse",
                        ),
                        reuse_risk=reuse_risk,
                        is_reused=True,
                        source_plan_id=reused_plan.plan_id,
                        assumptions=reused_plan.assumptions,
                    )
                    return True, ModuleResult(primary=plan)

            # Step 2: Generate new plan via LLM.
            plan = self._generate_plan(directive, cycle_context, assembled_context)
            self._plan_cache[plan.plan_id] = plan

            return True, ModuleResult(primary=plan)

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Planning failed: {exc}",
                is_retryable=True,
            )

    def _lookup_cache(self, directive: Any) -> Plan | None:
        """Search plan cache via embedding similarity."""
        if self.embedding_index is None:
            return None

        objective = getattr(directive, "objective", "")
        if not objective:
            return None

        results = self.embedding_index.query(
            text=objective,
            record_type="plan",
            k=3,
            track_id=getattr(directive, "track_id", None),
        )
        if not results:
            return None

        # Check if top result is similar enough.
        for r in results if isinstance(results, list) else []:
            plan_id = r.get("id") if isinstance(r, dict) else getattr(r, "id", None)
            if plan_id and plan_id in self._plan_cache:
                return self._plan_cache[plan_id]
        return None

    def _assess_reuse_risk(self, plan: Plan, directive: Any) -> float:
        """Assess risk that a cached plan won't fit the new task."""
        risk = 0.1  # Base risk for any reuse.

        # Different difficulty → higher risk.
        plan_difficulty = plan.estimated_complexity
        new_difficulty = getattr(directive, "difficulty", "F1")
        if plan_difficulty != new_difficulty:
            risk += 0.2

        # Different domain → higher risk.
        new_domain = getattr(directive, "domain", "")
        if new_domain and new_domain not in plan.approach:
            risk += 0.15

        return min(risk, 1.0)

    def _generate_plan(
        self,
        directive: Any,
        cycle_context: dict[str, Any],
        assembled_context: Any = None,
    ) -> Plan:
        """Generate a new plan via LLM or heuristic."""
        objective = getattr(directive, "objective", "Solve the task.")
        language = getattr(directive, "language", "python")
        difficulty = getattr(directive, "difficulty", "F1")
        constraints = getattr(directive, "constraints", [])

        # Default plan structure.
        steps = [
            f"Analyze the problem: {objective[:100]}",
            f"Design solution in {language}",
            "Implement core logic",
            "Add error handling and edge cases",
            "Write/verify tests",
        ]

        if difficulty in ("F4", "F5"):
            steps.insert(2, "Research applicable algorithms/patterns")
            steps.append("Performance optimization pass")

        if constraints:
            steps.insert(1, f"Account for constraints: {', '.join(constraints[:3])}")

        # If LLM is available, generate a richer plan.
        if self.llm_client:
            try:
                prompt = (
                    f"Create a step-by-step plan to solve:\n{objective}\n"
                    f"Language: {language}\nDifficulty: {difficulty}\n"
                    f"Constraints: {constraints}\n"
                    f"Return 4-7 concise steps."
                )
                response = self.llm_client.generate(prompt=prompt, max_tokens=300)
                text = getattr(response, "text", str(response))
                if text:
                    steps = [s.strip() for s in text.strip().split("\n") if s.strip()][:7]
            except Exception:
                pass  # Fall back to heuristic steps.

        confidence_val = 0.6 if self.llm_client else 0.4
        assumptions = [f"Language: {language}", f"Difficulty: {difficulty}"]

        return Plan(
            plan_id=str(uuid.uuid4()),
            steps=steps,
            approach=f"{language} solution at {difficulty} level",
            estimated_complexity=difficulty,
            confidence=ConfidenceScore(value=confidence_val, basis="llm_generation" if self.llm_client else "heuristic"),
            reuse_risk=0.0,
            is_reused=False,
            assumptions=assumptions,
        )
