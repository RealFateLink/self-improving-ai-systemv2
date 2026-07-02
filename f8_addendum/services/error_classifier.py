"""F8 Addendum — A-5: Error Classifier.

Classifies exceptions into ErrorDomain for cascade routing.
Produces telemetry-safe strings, domain classification, and
human-readable messages.
~60 lines | Integrates with L3 services and L5 orchestrator.
"""
from __future__ import annotations

import logging
import traceback
from typing import Any

from ..types.errors import (
    ClassifiedError,
    DiagnosticError,
    DomainError,
    ErrorDomain,
    GovernanceError,
    ImplementationError,
)
from ..types.recovery import RecoveryPath

logger = logging.getLogger(__name__)

# Map exception types to domains
EXCEPTION_DOMAIN_MAP: dict[str, ErrorDomain] = {
    "CompilationError": ErrorDomain.IMPLEMENTATION,
    "TestFailure": ErrorDomain.IMPLEMENTATION,
    "SandboxTimeout": ErrorDomain.IMPLEMENTATION,
    "RuntimeCrash": ErrorDomain.IMPLEMENTATION,
    "EmbeddingIndexError": ErrorDomain.DIAGNOSTIC,
    "PatternDBTimeout": ErrorDomain.DIAGNOSTIC,
    "LLMRateLimitError": ErrorDomain.DIAGNOSTIC,
    "StaleCacheError": ErrorDomain.DIAGNOSTIC,
    "BudgetExceeded": ErrorDomain.GOVERNANCE,
    "TrackDeactivated": ErrorDomain.GOVERNANCE,
    "GraduationExamInProgress": ErrorDomain.GOVERNANCE,
    "PrivilegeRevoked": ErrorDomain.GOVERNANCE,
}

# Map error patterns to recovery paths
ERROR_RECOVERY_MAP: dict[str, RecoveryPath] = {
    "stream_stall": RecoveryPath.STREAMING_FALLBACK,
    "idle_timeout": RecoveryPath.STREAMING_FALLBACK,
    "model_unavailable": RecoveryPath.MODEL_FALLBACK,
    "529": RecoveryPath.OVERLOAD_RETRY,
    "overloaded": RecoveryPath.OVERLOAD_RETRY,
    "max_tokens": RecoveryPath.TOKEN_ESCALATE,
    "truncated": RecoveryPath.TOKEN_ESCALATE,
    "401": RecoveryPath.AUTH_REFRESH,
    "unauthorized": RecoveryPath.AUTH_REFRESH,
    "credential_expired": RecoveryPath.AUTH_REFRESH,
}


def classify_error(error: Exception, module: str = "") -> ClassifiedError:
    """Classify an exception into an ErrorDomain with recovery guidance.

    Priority chain for domain detection:
      1. DomainError subclass (has .domain attribute)
      2. Exception type name in EXCEPTION_DOMAIN_MAP
      3. Default to DIAGNOSTIC (safe fallback)
    """
    # Check for DomainError with explicit domain
    if isinstance(error, DomainError):
        domain = error.domain
        module = module or error.module
    else:
        # Look up by exception type name
        exc_name = type(error).__name__
        domain = EXCEPTION_DOMAIN_MAP.get(exc_name, ErrorDomain.DIAGNOSTIC)

    # Build telemetry-safe message (no raw stack traces)
    telemetry_msg = _build_telemetry_message(error)

    # Build human-readable message
    human_msg = _build_human_message(error, domain)

    # Determine recovery action
    recovery = _suggest_recovery(error)

    return ClassifiedError(
        domain=domain,
        telemetry_safe_message=telemetry_msg,
        human_readable_message=human_msg,
        error_type=type(error).__name__,
        module=module,
        recovery_action=recovery,
        original_exception_type=f"{type(error).__module__}.{type(error).__qualname__}",
    )


def classify_recovery_path(error: Exception) -> RecoveryPath:
    """Determine the best recovery path for an error.

    Used by the orchestrator to dispatch recovery.
    """
    error_str = str(error).lower()
    for pattern, path in ERROR_RECOVERY_MAP.items():
        if pattern in error_str:
            return path
    return RecoveryPath.ABORT_CLEAN


def _build_telemetry_message(error: Exception) -> str:
    """Build a telemetry-safe error message (no stack traces)."""
    # TelemetrySafeError > errno > stable name > fallback
    if hasattr(error, "telemetry_message"):
        return error.telemetry_message  # type: ignore[attr-defined]
    if hasattr(error, "errno") and error.errno:  # type: ignore[union-attr]
        return f"errno:{error.errno}"  # type: ignore[union-attr]
    return f"{type(error).__name__}: {str(error)[:200]}"


def _build_human_message(error: Exception, domain: ErrorDomain) -> str:
    """Build a human-readable message for the operator dashboard."""
    base = str(error)[:300]
    domain_label = {
        ErrorDomain.IMPLEMENTATION: "Code Error",
        ErrorDomain.DIAGNOSTIC: "System Issue",
        ErrorDomain.GOVERNANCE: "Policy Block",
    }
    return f"[{domain_label.get(domain, 'Error')}] {base}"


def _suggest_recovery(error: Exception) -> str:
    """Suggest a recovery action based on error classification."""
    path = classify_recovery_path(error)
    suggestions = {
        RecoveryPath.STREAMING_FALLBACK: "Switch to non-streaming API",
        RecoveryPath.MODEL_FALLBACK: "Switch to fallback model",
        RecoveryPath.TOKEN_ESCALATE: "Retry with 2x token budget",
        RecoveryPath.OVERLOAD_RETRY: "Retry with exponential backoff",
        RecoveryPath.AUTH_REFRESH: "Refresh API credentials",
        RecoveryPath.ABORT_CLEAN: "Abort and preserve partial state",
    }
    return suggestions.get(path, "Unknown recovery")
