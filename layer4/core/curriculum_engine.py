"""curriculum_engine.py — Capability-adaptive curriculum engine.

Layer 4 — v0.2.0.  Based on TAROT (2602.15449).
Adapts curriculum difficulty based on model capability, not just problem difficulty.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CapabilityProfile:
    """Model's current capability across difficulty tiers."""
    basic_pass_rate: float = 0.0
    intermediate_pass_rate: float = 0.0
    complex_pass_rate: float = 0.0
    edge_pass_rate: float = 0.0
    overall_pass_rate: float = 0.0
    recent_trend: str = "stable"  # improving | stable | declining


@dataclass
class CurriculumEngine:
    """Adaptive curriculum that matches difficulty to model capability.

    From TAROT: "Capability-adaptive curriculum RL. Decouples curriculum
    allocation from reward weights. Less capable models: basic→complex
    progression. More capable models: complex-first."
    """

    config: dict[str, Any] = field(default_factory=dict)
    _history: list[dict[str, Any]] = field(default_factory=list)
    _capability: CapabilityProfile = field(default_factory=CapabilityProfile)
    meta: Any = None  # Optional MetaLearningOrchestrator for skill-based selection

    def update_capability(self, tier_results: dict[str, float]) -> None:
        """Update capability profile from recent results."""
        self._capability.basic_pass_rate = tier_results.get("basic", self._capability.basic_pass_rate)
        self._capability.intermediate_pass_rate = tier_results.get("intermediate", self._capability.intermediate_pass_rate)
        self._capability.complex_pass_rate = tier_results.get("complex", self._capability.complex_pass_rate)
        self._capability.edge_pass_rate = tier_results.get("edge", self._capability.edge_pass_rate)
        self._capability.overall_pass_rate = sum(tier_results.values()) / max(len(tier_results), 1)

        # Compute trend
        if len(self._history) >= 10:
            recent = sum(r["pass_rate"] for r in self._history[-10:]) / 10
            older = sum(r["pass_rate"] for r in self._history[-20:-10]) / 10 if len(self._history) >= 20 else recent
            if recent > older + 0.05:
                self._capability.recent_trend = "improving"
            elif recent < older - 0.05:
                self._capability.recent_trend = "declining"
            else:
                self._capability.recent_trend = "stable"

        self._history.append({"pass_rate": self._capability.overall_pass_rate, "tiers": tier_results})
        if len(self._history) > 1000:
            self._history = self._history[-500:]

    def select_curriculum_strategy(self) -> str:
        """Select curriculum strategy based on capability.

        Returns: 'progressive' | 'hard_first' | 'balanced' | 'remedial'
        """
        cap = self._capability

        # Remedial: struggling on basics
        if cap.basic_pass_rate < 0.5:
            return "remedial"

        # Hard-first: strong on everything
        if cap.basic_pass_rate > 0.9 and cap.intermediate_pass_rate > 0.8 and cap.complex_pass_rate > 0.7:
            return "hard_first"

        # Progressive: moderate capability
        if cap.basic_pass_rate > 0.7 and cap.overall_pass_rate < 0.8:
            return "progressive"

        # Balanced: default
        return "balanced"

    def allocate_tiers(self, strategy: Optional[str] = None) -> dict[str, float]:
        """Allocate training budget across difficulty tiers.

        Returns weights summing to 1.0 for each tier.
        """
        strategy = strategy or self.select_curriculum_strategy()

        allocations = {
            "remedial": {"basic": 0.7, "intermediate": 0.2, "complex": 0.08, "edge": 0.02},
            "progressive": {"basic": 0.3, "intermediate": 0.4, "complex": 0.2, "edge": 0.1},
            "balanced": {"basic": 0.2, "intermediate": 0.3, "complex": 0.3, "edge": 0.2},
            "hard_first": {"basic": 0.05, "intermediate": 0.15, "complex": 0.4, "edge": 0.4},
        }
        return allocations.get(strategy, allocations["balanced"])

    def select_next_task_tier(self) -> str:
        """Select which difficulty tier to train on next."""
        weights = self.allocate_tiers()
        tiers = list(weights.keys())
        probs = list(weights.values())
        return random.choices(tiers, weights=probs, k=1)[0]

    def get_reward_weights(self) -> dict[str, float]:
        """Get reward weights for each tier based on capability.

        From TAROT: weight rewards differently based on model capability.
        """
        cap = self._capability
        strategy = self.select_curriculum_strategy()

        if strategy == "remedial":
            # Focus rewards on basic/intermediate
            return {"basic": 0.5, "intermediate": 0.3, "complex": 0.15, "edge": 0.05}
        elif strategy == "progressive":
            # Balanced but favor current frontier
            if cap.intermediate_pass_rate < 0.7:
                return {"basic": 0.2, "intermediate": 0.5, "complex": 0.2, "edge": 0.1}
            else:
                return {"basic": 0.1, "intermediate": 0.3, "complex": 0.4, "edge": 0.2}
        elif strategy == "hard_first":
            # Reward complex/edge more
            return {"basic": 0.05, "intermediate": 0.15, "complex": 0.35, "edge": 0.45}
        else:
            return {"basic": 0.25, "intermediate": 0.25, "complex": 0.25, "edge": 0.25}

    def should_promote_difficulty(self) -> bool:
        """Check if model is ready for harder problems."""
        cap = self._capability
        return (
            cap.basic_pass_rate >= 0.85
            and cap.intermediate_pass_rate >= 0.75
            and cap.complex_pass_rate >= 0.6
            and cap.recent_trend in ("improving", "stable")
        )

    def should_demote_difficulty(self) -> bool:
        """Check if model needs easier problems."""
        cap = self._capability
        return cap.basic_pass_rate < 0.5 or cap.recent_trend == "declining"

    def get_skill_recommendation(self, language: str = "python") -> Optional[dict[str, Any]]:
        """Return skill-gap recommendation from MetaLearningOrchestrator, if wired in."""
        if not self.meta:
            return None
        try:
            return self.meta.get_curriculum_recommendation(language)
        except Exception:
            return None

    def select_next_problem(self, language: str = "python") -> dict[str, Any]:
        """
        Combines tier-based selection (TAROT) with skill-gap analysis (meta-learning).
        Returns a spec the caller uses to look up or generate a task.
        """
        tier = self.select_next_task_tier()
        result: dict[str, Any] = {"tier": tier, "language": language}

        rec = self.get_skill_recommendation(language)
        if rec:
            result["meta_recommendation"] = rec["recommendation"]
            result["focus_skills"] = rec["focus_skills"]
            result["meta_stats"] = rec["stats"]
            # Prefer prerequisite drilling when there are blocking skills
            if rec["recommendation"] == "drill_prerequisites" and rec["focus_skills"]:
                result["target_skill_id"] = rec["focus_skills"][0]["id"]
                result["target_skill_name"] = rec["focus_skills"][0]["name"]
            elif rec["focus_skills"]:
                result["target_skill_ids"] = [s["id"] for s in rec["focus_skills"]]

        return result

    def get_stats(self) -> dict[str, Any]:
        return {
            "capability": {
                "basic": self._capability.basic_pass_rate,
                "intermediate": self._capability.intermediate_pass_rate,
                "complex": self._capability.complex_pass_rate,
                "edge": self._capability.edge_pass_rate,
                "overall": self._capability.overall_pass_rate,
                "trend": self._capability.recent_trend,
            },
            "strategy": self.select_curriculum_strategy(),
            "history_length": len(self._history),
        }
