"""reward_function.py — Composite reward function for code RL.

Layer 4 — v0.2.0.  Combines DRIVE, ReflexiCoder, and Code-A1 reward designs.
Format gating + execution reward + historical robustness + efficiency.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RewardConfig:
    """Configuration for reward computation."""
    format_gate_weight: float = 1.0      # Binary: valid syntax + structure?
    correctness_weight: float = 2.0      # Binary: tests pass?
    historical_weight: float = 0.5       # Passes historically failed tests?
    efficiency_weight: float = 0.3       # Token/runtime efficiency
    adversarial_weight: float = 0.5      # Passes adversarial tests?
    max_completion_length: int = 4096
    reference_runtime_ms: float = 1000.0


@dataclass
class CompositeReward:
    """Computes composite reward for code generation RL.

    Based on:
    - DRIVE: execution reward + efficiency
    - ReflexiCoder: format gating + cycle penalty
    - Code-A1: historical robustness via Mistake Book
    """

    config: RewardConfig = field(default_factory=RewardConfig)
    mistake_book: Any = None

    def compute(
        self,
        completion: str,
        test_results: dict[str, Any],
        execution_time_ms: float = 0.0,
        adversarial_results: Optional[dict[str, Any]] = None,
        num_attempts: int = 1,
    ) -> dict[str, Any]:
        """Compute full composite reward with breakdown.

        Returns dict with 'total', 'breakdown', and 'passed_gate'.
        """
        cfg = self.config
        breakdown = {}

        # === 1. FORMAT GATE (binary) ===
        # From ReflexiCoder: non-compliant trajectories get zero reward
        code = self._extract_code(completion)
        format_ok, format_reason = self._check_format_gate(code)
        breakdown["format_gate"] = 1.0 if format_ok else 0.0
        breakdown["format_reason"] = format_reason

        if not format_ok:
            # Hard gate: everything else is zero
            return {
                "total": 0.0,
                "breakdown": breakdown,
                "passed_gate": False,
            }

        # === 2. CORRECTNESS (primary signal) ===
        # From DRIVE: binary pass/fail from execution
        pass_rate = test_results.get("pass_rate", 0.0)
        breakdown["correctness"] = pass_rate

        # === 3. HISTORICAL ROBUSTNESS ===
        # From Code-A1 Mistake Book: test against historically failed cases
        historical_score = 0.0
        if self.mistake_book and pass_rate > 0:
            challenging = self.mistake_book.get_challenging_tests(limit=5)
            if challenging:
                # In practice, you'd re-run code against these tests
                # For now, use a proxy based on pass rate
                historical_score = pass_rate * 0.8  # Slightly discounted
        breakdown["historical"] = historical_score

        # === 4. ADVERSARIAL ROBUSTNESS ===
        # From Code-A1: pass adversarially generated tests
        adversarial_score = 0.0
        if adversarial_results:
            adversarial_score = adversarial_results.get("pass_rate", 0.0)
        breakdown["adversarial"] = adversarial_score

        # === 5. EFFICIENCY ===
        # From ReflexiCoder: penalize excessive tokens + slow runtime
        token_efficiency = max(0.0, 1.0 - len(completion) / cfg.max_completion_length)
        runtime_efficiency = 0.0
        if execution_time_ms > 0 and cfg.reference_runtime_ms > 0:
            runtime_efficiency = max(0.0, 1.0 - execution_time_ms / cfg.reference_runtime_ms)
        efficiency = (token_efficiency + runtime_efficiency) / 2
        breakdown["efficiency"] = efficiency

        # === 6. CYCLE PENALTY ===
        # From ReflexiCoder: penalize excessive reflection attempts
        cycle_penalty = 0.0
        if num_attempts > 1:
            cycle_penalty = 0.05 * (num_attempts - 1)
        breakdown["cycle_penalty"] = -cycle_penalty

        # === COMPOSITE ===
        total = (
            cfg.format_gate_weight * breakdown["format_gate"]
            + cfg.correctness_weight * breakdown["correctness"]
            + cfg.historical_weight * breakdown["historical"]
            + cfg.adversarial_weight * breakdown["adversarial"]
            + cfg.efficiency_weight * breakdown["efficiency"]
            + breakdown["cycle_penalty"]
        )

        # Normalize by sum of positive weights
        total_weight = (
            cfg.format_gate_weight + cfg.correctness_weight
            + cfg.historical_weight + cfg.adversarial_weight + cfg.efficiency_weight
        )
        normalized_total = max(0.0, total / total_weight)

        return {
            "total": normalized_total,
            "breakdown": breakdown,
            "passed_gate": True,
            "raw_total": total,
        }

    def _extract_code(self, completion: str) -> str:
        """Extract code from markdown blocks or raw text."""
        import re
        # Try markdown code block
        patterns = [
            r"```(?:python)?\n(.*?)```",
            r"```(?:\w+)?\n(.*?)```",
        ]
        for pattern in patterns:
            match = re.search(pattern, completion, re.DOTALL)
            if match:
                return match.group(1).strip()
        return completion.strip()

    def _check_format_gate(self, code: str) -> tuple[bool, str]:
        """Check if code passes format gate.

        Returns (passed, reason).
        """
        if not code or len(code) < 10:
            return False, "code_too_short"

        # Syntax check
        try:
            ast.parse(code)
        except SyntaxError as e:
            return False, f"syntax_error:{e.msg}"

        # Check for basic structure
        lines = code.split("\n")
        has_function = any(l.strip().startswith("def ") for l in lines)
        has_class = any(l.strip().startswith("class ") for l in lines)

        if not has_function and not has_class:
            # Allow scripts that don't define functions
            if "print(" in code or "return" in code:
                return True, "script_ok"
            return False, "no_executable_structure"

        return True, "ok"

    def compute_for_grpo(self, completions: list[str], **kwargs: Any) -> list[float]:
        """Compute rewards for a batch of completions (GRPO-compatible).

        Returns list of floats, one per completion.
        """
        rewards = []
        for completion in completions:
            # Extract kwargs per completion if provided
            test_results = kwargs.get("test_results", {})
            exec_time = kwargs.get("execution_time_ms", 0.0)
            adv_results = kwargs.get("adversarial_results")
            attempts = kwargs.get("num_attempts", 1)

            result = self.compute(completion, test_results, exec_time, adv_results, attempts)
            rewards.append(result["total"])
        return rewards
