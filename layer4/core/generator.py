"""generator.py — Produces 1–3 candidates with temperature diversity.

Stage 4.  Accumulates assumptions across candidates.
Consumes context: optimization briefs, lessons, patterns, corrections.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["Generator", "Candidate"]


@dataclass(frozen=True)
class Candidate:
    """A generated code candidate."""
    candidate_id: str
    code: str
    temperature: float
    approach_summary: str
    assumptions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Generator:
    """Produces 1–3 solution candidates using temperature diversity.

    Dependencies:
      - llm_client (Layer 2): for code generation
      - context_assembler (Layer 3): provides assembled context
    """

    llm_client: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    default_count: int = 3
    temperatures: tuple[float, ...] = (0.2, 0.5, 0.8)

    def generate_candidates(
        self,
        directive: Any,
        plan: Any,
        assembled_context: Any,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Generate code candidates.

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        from .intent_interpreter import ModuleResult, ModuleError

        try:
            count = self._determine_count(cycle_context)
            candidates: list[Candidate] = []
            all_assumptions: list[str] = []

            for i in range(count):
                temp = self.temperatures[i] if i < len(self.temperatures) else 0.5
                candidate = self._generate_single(
                    directive, plan, assembled_context, temp, cycle_context,
                )
                candidates.append(candidate)
                all_assumptions.extend(candidate.assumptions)

            if not candidates:
                return False, ModuleError(
                    error_type="RECOVERABLE",
                    message="No candidates generated.",
                    is_retryable=True,
                )

            return True, ModuleResult(
                primary=candidates,
                proposals=[],
                warnings=self._check_warnings(candidates),
            )

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Generation failed: {exc}",
                is_retryable=True,
            )

    def _generate_single(
        self,
        directive: Any,
        plan: Any,
        context: Any,
        temperature: float,
        cycle_context: dict[str, Any],
    ) -> Candidate:
        """Generate a single candidate at given temperature."""
        objective = getattr(directive, "objective", "")
        language = getattr(directive, "language", "python")
        plan_steps = getattr(plan, "steps", []) if plan else []
        context_sections = getattr(context, "sections", {}) if context else {}

        # Build prompt.
        prompt_parts = [
            f"Solve the following in {language}:",
            objective,
        ]

        if plan_steps:
            prompt_parts.append("\nPlan:")
            for i, step in enumerate(plan_steps, 1):
                prompt_parts.append(f"  {i}. {step}")

        # Include context sections.
        for section_name, content in context_sections.items():
            if content:
                prompt_parts.append(f"\n## {section_name}\n{content[:500]}")

        prompt = "\n".join(prompt_parts)

        # Generate.
        code = ""
        if self.llm_client:
            try:
                response = self.llm_client.generate(
                    prompt=prompt,
                    max_tokens=2000,
                    temperature=temperature,
                )
                code = getattr(response, "text", str(response))
            except Exception:
                code = f"# Generation failed at temperature {temperature}\npass"
        else:
            code = self._heuristic_generate(objective, language, plan_steps)

        assumptions = list(getattr(directive, "assumptions", []))
        if hasattr(plan, "assumptions"):
            assumptions.extend(plan.assumptions)

        return Candidate(
            candidate_id=str(uuid.uuid4()),
            code=code,
            temperature=temperature,
            approach_summary=f"Generated at temp={temperature:.1f}",
            assumptions=assumptions,
            metadata={
                "language": language,
                "track_id": getattr(directive, "track_id", ""),
                "is_benchmark": cycle_context.get("is_benchmark", False),
            },
        )

    def _determine_count(self, cycle_context: dict[str, Any]) -> int:
        """Determine candidate count based on mode."""
        mode = cycle_context.get("readiness_mode", "FULL")
        economy = cycle_context.get("economy_mode", False)

        if economy:
            return 1
        if mode in ("DEGRADED_LOW_COST", "MAINTENANCE_ONLY"):
            return 1
        return self.default_count

    def _check_warnings(self, candidates: list[Candidate]) -> list[dict[str, Any]]:
        """Check for warning conditions."""
        warnings = []
        for c in candidates:
            if len(c.code) < 20:
                warnings.append({
                    "type": "SHORT_CANDIDATE",
                    "severity": "INFO",
                    "message": f"Candidate {c.candidate_id} is very short ({len(c.code)} chars).",
                })
        return warnings

    @staticmethod
    def _heuristic_generate(objective: str, language: str, steps: list[str]) -> str:
        """Fallback heuristic generation."""
        lines = [f"# {language} solution", f'"""', f"{objective[:200]}", f'"""', ""]
        for i, step in enumerate(steps, 1):
            lines.append(f"# Step {i}: {step}")
        lines.append("")
        lines.append("def solve():")
        lines.append("    # TODO: implement")
        lines.append("    pass")
        return "\n".join(lines)
