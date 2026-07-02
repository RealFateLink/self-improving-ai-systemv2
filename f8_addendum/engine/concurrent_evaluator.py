"""F8 Addendum — A-7: Concurrent Evaluation with Deferred State Commits.

Two-phase evaluation: Phase 1 runs read-only modules concurrently,
Phase 2 runs state-mutating modules serially. Saves 30-50% per-cycle
evaluation time.
~80 lines | Integrates with L4 evaluation modules and L5 orchestrator.
"""
from __future__ import annotations

import asyncio
import copy
import logging
from typing import Any, Optional

from ..types.evaluation import (
    ConcurrentEvaluationResult,
    ConcurrentSafeModule,
    ContextModifier,
    EvaluationPhaseResult,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENCY = 3


class ConcurrentEvaluator:
    """Runs Phase 1 evaluation modules concurrently.

    Phase 1 — Concurrent Read-Only:
      Modules: static_reviewer, dynamic_verifier, semantic_critic.
      Each receives a FROZEN CycleContext snapshot.
      NONE write to the Ledger.

    Phase 2 — Serial State Mutation (handled by caller):
      selector, promotion_manager, failure_analyzer.
      All writes are serial and ordered.
    """

    def __init__(self, config: Any) -> None:
        self._config = config
        self._max_concurrency = getattr(
            config, "max_evaluation_concurrency", DEFAULT_MAX_CONCURRENCY
        )

    async def run_phase1(
        self,
        modules: list[Any],
        cycle_context: Any,
    ) -> ConcurrentEvaluationResult:
        """Run Phase 1: concurrent read-only evaluation.

        Only modules declaring is_concurrent_safe=True participate.
        Each gets a deep copy of cycle_context (frozen snapshot).
        Returns aggregated results + queued context modifiers.
        """
        # Filter to concurrent-safe modules
        concurrent_modules = [
            m for m in modules
            if getattr(m, "is_concurrent_safe", False)
        ]
        serial_modules = [
            m for m in modules
            if not getattr(m, "is_concurrent_safe", False)
        ]

        if serial_modules:
            logger.debug(
                "Skipping %d non-concurrent modules in Phase 1",
                len(serial_modules),
            )

        if not concurrent_modules:
            return ConcurrentEvaluationResult(
                phase1_results=(),
                context_modifiers=(),
                all_succeeded=True,
            )

        # Create frozen snapshots
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def run_module(module: Any) -> EvaluationPhaseResult:
            async with semaphore:
                frozen_ctx = copy.deepcopy(cycle_context)
                module_name = getattr(module, "name", type(module).__name__)
                try:
                    result = await self._evaluate_module(module, frozen_ctx)
                    modifier = getattr(result, "context_modifier", None)
                    return EvaluationPhaseResult(
                        module_name=module_name,
                        result=result,
                        context_modifier=modifier,
                        succeeded=True,
                    )
                except Exception as exc:
                    logger.error(
                        "Phase 1 module %s failed: %s", module_name, exc
                    )
                    return EvaluationPhaseResult(
                        module_name=module_name,
                        result=None,
                        error=str(exc),
                        succeeded=False,
                    )

        # Run concurrently
        tasks = [run_module(m) for m in concurrent_modules]
        results = await asyncio.gather(*tasks)

        # Collect context modifiers (deterministic order by module name)
        sorted_results = sorted(results, key=lambda r: r.module_name)
        modifiers = tuple(
            r.context_modifier
            for r in sorted_results
            if r.context_modifier is not None
        )

        all_succeeded = all(r.succeeded for r in results)

        return ConcurrentEvaluationResult(
            phase1_results=tuple(sorted_results),
            context_modifiers=modifiers,
            all_succeeded=all_succeeded,
            partial_results_available=any(r.succeeded for r in results),
        )

    def apply_deferred_modifiers(
        self,
        context: dict[str, Any],
        modifiers: tuple[ContextModifier, ...],
    ) -> dict[str, Any]:
        """Apply queued context modifiers in deterministic order.

        Called after Phase 1 completes, before Phase 2 begins.
        """
        modified = dict(context)
        for modifier in modifiers:
            modified = modifier(modified)
        return modified

    @staticmethod
    async def _evaluate_module(module: Any, context: Any) -> Any:
        """Run a single evaluation module.

        Wraps sync evaluate() in an executor if not async.
        """
        evaluate_fn = getattr(module, "evaluate", None)
        if evaluate_fn is None:
            raise AttributeError(
                f"Module {type(module).__name__} has no evaluate() method"
            )

        if asyncio.iscoroutinefunction(evaluate_fn):
            return await evaluate_fn(context)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, evaluate_fn, context)
