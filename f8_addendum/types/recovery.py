"""F8 Addendum — A-1: Recovery Path Types & A-4: Circuit Breaker Types.

A-1: Six named recovery transitions replacing generic failure→repair.
A-4: Circuit breaker state for repeated compaction/recovery failures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Optional


class RecoveryPath(StrEnum):
    """Six explicit recovery transitions.

    Each path has a well-defined trigger, action, max retries, and
    state preservation behavior. Orchestrator dispatches on enum
    value, not exception type.
    """

    STREAMING_FALLBACK = "STREAMING_FALLBACK"
    """Trigger: stream stall / idle timeout.
    Action: switch to non-streaming API call.
    Max retries: 1. State: full preserve."""

    MODEL_FALLBACK = "MODEL_FALLBACK"
    """Trigger: primary model 529 / unavailable.
    Action: switch to fallback model from config.
    Max retries: 1. State: full preserve."""

    TOKEN_ESCALATE = "TOKEN_ESCALATE"
    """Trigger: max_tokens hit (end_turn with truncation).
    Action: retry with 2x output token budget.
    Max retries: 1. State: full preserve."""

    OVERLOAD_RETRY = "OVERLOAD_RETRY"
    """Trigger: API 529 overloaded.
    Action: exponential backoff, same request.
    Max retries: 3. State: full preserve."""

    AUTH_REFRESH = "AUTH_REFRESH"
    """Trigger: 401 / credential expiry.
    Action: refresh API key, retry same request.
    Max retries: 1. State: full preserve."""

    ABORT_CLEAN = "ABORT_CLEAN"
    """Trigger: user cancel / unrecoverable.
    Action: persist partial results, mark cycle incomplete.
    Max retries: 0. State: partial save."""


# Recovery path configuration
RECOVERY_MAX_RETRIES: dict[RecoveryPath, int] = {
    RecoveryPath.STREAMING_FALLBACK: 1,
    RecoveryPath.MODEL_FALLBACK: 1,
    RecoveryPath.TOKEN_ESCALATE: 1,
    RecoveryPath.OVERLOAD_RETRY: 3,
    RecoveryPath.AUTH_REFRESH: 1,
    RecoveryPath.ABORT_CLEAN: 0,
}

RECOVERY_PRESERVES_STATE: dict[RecoveryPath, bool] = {
    RecoveryPath.STREAMING_FALLBACK: True,
    RecoveryPath.MODEL_FALLBACK: True,
    RecoveryPath.TOKEN_ESCALATE: True,
    RecoveryPath.OVERLOAD_RETRY: True,
    RecoveryPath.AUTH_REFRESH: True,
    RecoveryPath.ABORT_CLEAN: False,
}


@dataclass
class RecoveryAttempt:
    """Record of a single recovery attempt."""

    path: RecoveryPath
    attempt_number: int
    succeeded: bool
    timestamp: str
    detail: str = ""


@dataclass
class PerSessionErrorCounter:
    """Per-session error counter per recovery path.

    Tracks consecutive errors for progressive backoff
    (matching Claude Code's withRetry pattern).
    """

    path: RecoveryPath
    consecutive_failures: int = 0
    total_attempts: int = 0
    last_attempt_at: Optional[str] = None

    def record_attempt(self, succeeded: bool, timestamp: str) -> None:
        self.total_attempts += 1
        self.last_attempt_at = timestamp
        if succeeded:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1


# ── A-4: Circuit Breaker ─────────────────────────────────────────────────────

@dataclass
class CircuitBreakerState:
    """Circuit breaker state for a recovery path or compaction.

    CB-1: Compaction — after 3 consecutive compaction failures.
    CB-2: Recovery — after 3 consecutive same-path recovery failures.

    When tripped: that path is disabled for the remainder of the session.
    """

    path: str  # RecoveryPath value or "COMPACTION"
    consecutive_failures: int = 0
    tripped: bool = False
    tripped_at: Optional[str] = None
    trip_threshold: int = 3

    def record_failure(self, timestamp: str) -> bool:
        """Record a failure. Returns True if breaker just tripped."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.trip_threshold and not self.tripped:
            self.tripped = True
            self.tripped_at = timestamp
            return True
        return False

    def record_success(self) -> None:
        """Record a success. Resets consecutive counter."""
        self.consecutive_failures = 0

    def reset(self) -> None:
        """Manual reset (operator CLI or config change)."""
        self.consecutive_failures = 0
        self.tripped = False
        self.tripped_at = None
