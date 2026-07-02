"""curriculum_sampler.py — Selects next task for the learning cycle.

Stage 2.  Uses: shadow injection, exploration, weakness targeting, cooldowns,
anti-thrashing, depletion pressure handling.

Issues pool depletion warnings (routed by Layer 5 to generation service).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["CurriculumSampler", "TaskSelection"]


@dataclass(frozen=True)
class TaskSelection:
    """Result of task selection."""
    task: Any
    selection_reason: str    # shadow | exploration | weakness | cooldown_skip | normal
    is_shadow: bool
    pool_health: dict[str, Any]


@dataclass
class CurriculumSampler:
    """Selects the next task using multi-factor heuristics.

    Dependencies (Layer 3):
      - task_loader: for task pool
      - skill_tracker: for weakness targeting
      - shadow_injector: for shadow injection decisions
      - curriculum_logger: for learning value prediction
      - embedding_index: for novelty/diversity
    """

    task_loader: Any = None
    skill_tracker: Any = None
    shadow_injector: Any = None
    curriculum_logger: Any = None
    embedding_index: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    exploration_rate: float = 0.15
    cooldown_cycles: int = 10
    anti_thrash_window: int = 5

    _recent_tasks: list[str] = field(default_factory=list)
    _cooldown_map: dict[str, int] = field(default_factory=dict)

    def sample_next(
        self,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Select next task.

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        track_id = cycle_context.get("domain_track", "")
        readiness_mode = cycle_context.get("readiness_mode", "FULL")
        cycle_number = cycle_context.get("cycle_number", 0)

        warnings: list[dict[str, Any]] = []

        # Step 1: Shadow injection check.
        if self.shadow_injector:
            should_shadow = self.shadow_injector.should_inject(
                track_id, readiness_mode, cycle_context,
            )
            if should_shadow:
                shadow_task = self._select_shadow(track_id, readiness_mode)
                if shadow_task:
                    return True, self._make_result(
                        TaskSelection(
                            task=shadow_task,
                            selection_reason="shadow",
                            is_shadow=True,
                            pool_health=self._check_pool(track_id),
                        ),
                        warnings,
                    )

        # Step 2: Check pool health → depletion warning.
        pool = self._check_pool(track_id)
        if pool.get("generation_needed", False):
            warnings.append({
                "type": "POOL_DEPLETION",
                "severity": "CAUTION",
                "message": f"Track {track_id}: pool below threshold ({pool.get('remaining', 0)} remaining).",
                "track_id": track_id,
            })

        # Step 3: Exploration vs exploitation.
        if random.random() < self.exploration_rate:
            task = self._explore(track_id, cycle_number)
            if task:
                return True, self._make_result(
                    TaskSelection(task=task, selection_reason="exploration",
                                  is_shadow=False, pool_health=pool),
                    warnings,
                )

        # Step 4: Weakness targeting.
        task = self._target_weakness(track_id, cycle_number)
        if task:
            return True, self._make_result(
                TaskSelection(task=task, selection_reason="weakness",
                              is_shadow=False, pool_health=pool),
                warnings,
            )

        # Step 5: Normal selection with learning value prediction.
        task = self._normal_select(track_id, cycle_number)
        if task:
            return True, self._make_result(
                TaskSelection(task=task, selection_reason="normal",
                              is_shadow=False, pool_health=pool),
                warnings,
            )

        # No task available.
        from .intent_interpreter import ModuleError
        return False, ModuleError(
            error_type="RECOVERABLE",
            message=f"No tasks available for track {track_id}.",
            is_retryable=False,
        )

    def _select_shadow(self, track_id: str, mode: str) -> Any:
        """Select a shadow task via shadow_injector."""
        max_cost = None if mode == "FULL" else 50.0
        if self.shadow_injector and self.task_loader:
            return self.shadow_injector.select_shadow_task(
                self.task_loader, track_id, level="F2", max_cost=max_cost,
            )
        return None

    def _explore(self, track_id: str, cycle: int) -> Any:
        """Random exploration — pick a diverse/novel task."""
        if self.task_loader is None:
            return None
        tasks = self.task_loader.get_tasks_for_track(track_id, level=None)
        if not tasks:
            return None
        # Filter out recently used and on cooldown.
        candidates = [t for t in tasks if self._not_on_cooldown(t, cycle)]
        if not candidates:
            return random.choice(tasks) if tasks else None
        return random.choice(candidates)

    def _target_weakness(self, track_id: str, cycle: int) -> Any:
        """Target weakest skills."""
        if self.skill_tracker is None or self.task_loader is None:
            return None
        weakest = self.skill_tracker.get_weakest(3, track_id)
        if not weakest:
            return None
        for skill_rate in weakest:
            skill_name = getattr(skill_rate, "skill", "") if hasattr(skill_rate, "skill") else str(skill_rate)
            tasks = self.task_loader.get_tasks(
                skill=skill_name, domain="", level="", track_id=track_id,
                language="", exclude=[],
            )
            candidates = [t for t in (tasks or []) if self._not_on_cooldown(t, cycle)]
            if candidates:
                return candidates[0]
        return None

    def _normal_select(self, track_id: str, cycle: int) -> Any:
        """Normal selection with learning value ranking."""
        if self.task_loader is None:
            return None
        tasks = self.task_loader.get_tasks_for_track(track_id, level=None)
        if not tasks:
            return None
        candidates = [t for t in tasks if self._not_on_cooldown(t, cycle)]
        if not candidates:
            candidates = tasks

        # Rank by predicted learning value.
        if self.curriculum_logger:
            ranked = sorted(
                candidates,
                key=lambda t: self.curriculum_logger.predict_learning_value(t, {}),
                reverse=True,
            )
            return ranked[0] if ranked else None

        return candidates[0] if candidates else None

    def _not_on_cooldown(self, task: Any, cycle: int) -> bool:
        """Check cooldown and anti-thrashing."""
        tid = getattr(task, "task_id", "")
        if not tid:
            return True
        last_used = self._cooldown_map.get(tid, -999)
        return (cycle - last_used) >= self.cooldown_cycles

    def _check_pool(self, track_id: str) -> dict[str, Any]:
        """Get pool health status."""
        if self.task_loader is None:
            return {"remaining": 999, "generation_needed": False}
        try:
            tasks = self.task_loader.get_tasks_for_track(track_id, level=None)
            remaining = len(tasks) if tasks else 0
        except Exception:
            remaining = 0
        return {
            "remaining": remaining,
            "generation_needed": remaining < 20,
        }

    def record_selection(self, task: Any, cycle: int) -> None:
        """Record task selection for cooldown tracking."""
        tid = getattr(task, "task_id", "")
        if tid:
            self._cooldown_map[tid] = cycle
            self._recent_tasks.append(tid)
            if len(self._recent_tasks) > 100:
                self._recent_tasks = self._recent_tasks[-100:]

    @staticmethod
    def _make_result(selection: TaskSelection, warnings: list[dict[str, Any]]) -> Any:
        from .intent_interpreter import ModuleResult
        return ModuleResult(primary=selection, warnings=warnings)
