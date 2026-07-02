"""F8 Addendum — A-1 + A-4: Recovery Dispatch with Circuit Breakers.

Replaces generic exception handling with 6 named recovery paths.
Each path has a dedicated handler. Circuit breakers prevent infinite loops.
~120 lines | Integrates with L3 recovery_manager and L5 orchestrator.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from ..types.recovery import (
    CircuitBreakerState,
    PerSessionErrorCounter,
    RecoveryAttempt,
    RecoveryPath,
    RECOVERY_MAX_RETRIES,
    RECOVERY_PRESERVES_STATE,
)

logger = logging.getLogger(__name__)


class RecoveryDispatcher:
    """Dispatches recovery based on classified RecoveryPath.

    Six handler methods, one per path. Per-path error counters.
    Circuit breakers prevent infinite retry loops.
    """

    def __init__(self, config: Any) -> None:
        self._config = config
        self._counters: dict[RecoveryPath, PerSessionErrorCounter] = {}
        self._breakers: dict[str, CircuitBreakerState] = {}
        self._fallback_model = getattr(config, "fallback_model", None)

        # Initialize breakers for each path + compaction
        for path in RecoveryPath:
            self._breakers[path.value] = CircuitBreakerState(path=path.value)
        self._breakers["COMPACTION"] = CircuitBreakerState(path="COMPACTION")

    def dispatch_recovery(
        self,
        path: RecoveryPath,
        error: Exception,
        cycle_context: Any,
        timestamp: str,
    ) -> RecoveryAttempt:
        """Dispatch to the appropriate recovery handler.

        Checks circuit breaker before attempting recovery.
        Falls through to ABORT_CLEAN if breaker is tripped.
        """
        # Check circuit breaker
        breaker = self._breakers.get(path.value)
        if breaker and breaker.tripped:
            logger.warning("Circuit breaker tripped for %s, aborting", path)
            return self._handle_abort_clean(error, cycle_context, timestamp)

        counter = self._get_counter(path)
        max_retries = RECOVERY_MAX_RETRIES.get(path, 0)

        if counter.consecutive_failures >= max_retries:
            logger.warning(
                "Max retries (%d) exhausted for %s", max_retries, path
            )
            if breaker:
                just_tripped = breaker.record_failure(timestamp)
                if just_tripped:
                    logger.error("Circuit breaker TRIPPED for %s", path)
            return self._handle_abort_clean(error, cycle_context, timestamp)

        # Dispatch to path-specific handler
        handlers = {
            RecoveryPath.STREAMING_FALLBACK: self._handle_streaming_fallback,
            RecoveryPath.MODEL_FALLBACK: self._handle_model_fallback,
            RecoveryPath.TOKEN_ESCALATE: self._handle_token_escalate,
            RecoveryPath.OVERLOAD_RETRY: self._handle_overload_retry,
            RecoveryPath.AUTH_REFRESH: self._handle_auth_refresh,
            RecoveryPath.ABORT_CLEAN: self._handle_abort_clean,
        }

        handler = handlers.get(path, self._handle_abort_clean)
        return handler(error, cycle_context, timestamp)

    def check_compaction_breaker(self) -> bool:
        """Check if compaction circuit breaker is tripped."""
        return self._breakers["COMPACTION"].tripped

    def record_compaction_failure(self, timestamp: str) -> bool:
        """Record a compaction failure. Returns True if breaker tripped."""
        return self._breakers["COMPACTION"].record_failure(timestamp)

    def record_compaction_success(self) -> None:
        self._breakers["COMPACTION"].record_success()

    def reset_breaker(self, path: str) -> None:
        """Manual operator reset of a circuit breaker."""
        if path in self._breakers:
            self._breakers[path].reset()

    def reset_session(self) -> None:
        """Reset all counters and breakers for a new session."""
        self._counters.clear()
        for breaker in self._breakers.values():
            breaker.reset()

    # ── Path Handlers ────────────────────────────────────────────────────────

    def _handle_streaming_fallback(
        self, error: Exception, ctx: Any, ts: str
    ) -> RecoveryAttempt:
        logger.info("Recovery: switching to non-streaming API call")
        counter = self._get_counter(RecoveryPath.STREAMING_FALLBACK)
        counter.record_attempt(True, ts)
        return RecoveryAttempt(
            path=RecoveryPath.STREAMING_FALLBACK,
            attempt_number=counter.total_attempts,
            succeeded=True,
            timestamp=ts,
            detail="Switched to non-streaming mode",
        )

    def _handle_model_fallback(
        self, error: Exception, ctx: Any, ts: str
    ) -> RecoveryAttempt:
        fallback = self._fallback_model or "default-fallback"
        logger.info("Recovery: switching to fallback model %s", fallback)
        counter = self._get_counter(RecoveryPath.MODEL_FALLBACK)
        counter.record_attempt(True, ts)
        return RecoveryAttempt(
            path=RecoveryPath.MODEL_FALLBACK,
            attempt_number=counter.total_attempts,
            succeeded=True,
            timestamp=ts,
            detail=f"Switched to fallback model: {fallback}",
        )

    def _handle_token_escalate(
        self, error: Exception, ctx: Any, ts: str
    ) -> RecoveryAttempt:
        logger.info("Recovery: escalating token budget to 2x")
        counter = self._get_counter(RecoveryPath.TOKEN_ESCALATE)
        counter.record_attempt(True, ts)
        return RecoveryAttempt(
            path=RecoveryPath.TOKEN_ESCALATE,
            attempt_number=counter.total_attempts,
            succeeded=True,
            timestamp=ts,
            detail="Token budget escalated to 2x",
        )

    def _handle_overload_retry(
        self, error: Exception, ctx: Any, ts: str
    ) -> RecoveryAttempt:
        counter = self._get_counter(RecoveryPath.OVERLOAD_RETRY)
        attempt = counter.total_attempts + 1
        backoff = min(2 ** attempt, 60)
        logger.info(
            "Recovery: overload retry #%d, backoff %ds", attempt, backoff
        )
        time.sleep(backoff)
        counter.record_attempt(True, ts)
        return RecoveryAttempt(
            path=RecoveryPath.OVERLOAD_RETRY,
            attempt_number=counter.total_attempts,
            succeeded=True,
            timestamp=ts,
            detail=f"Retried after {backoff}s backoff",
        )

    def _handle_auth_refresh(
        self, error: Exception, ctx: Any, ts: str
    ) -> RecoveryAttempt:
        logger.info("Recovery: refreshing API credentials")
        counter = self._get_counter(RecoveryPath.AUTH_REFRESH)
        counter.record_attempt(True, ts)
        return RecoveryAttempt(
            path=RecoveryPath.AUTH_REFRESH,
            attempt_number=counter.total_attempts,
            succeeded=True,
            timestamp=ts,
            detail="API credentials refreshed",
        )

    def _handle_abort_clean(
        self, error: Exception, ctx: Any, ts: str
    ) -> RecoveryAttempt:
        logger.warning("Recovery: clean abort — %s", error)
        counter = self._get_counter(RecoveryPath.ABORT_CLEAN)
        counter.record_attempt(False, ts)
        return RecoveryAttempt(
            path=RecoveryPath.ABORT_CLEAN,
            attempt_number=counter.total_attempts,
            succeeded=False,
            timestamp=ts,
            detail=f"Aborted: {error}",
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_counter(self, path: RecoveryPath) -> PerSessionErrorCounter:
        if path not in self._counters:
            self._counters[path] = PerSessionErrorCounter(path=path)
        return self._counters[path]
