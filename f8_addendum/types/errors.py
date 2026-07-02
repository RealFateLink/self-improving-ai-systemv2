"""F8 Addendum — A-5: Error Domain Types.

Three error domains for cascade isolation. IMPLEMENTATION errors are the
learning signal; DIAGNOSTIC and GOVERNANCE never cascade to failure analyzer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Optional


class ErrorDomain(StrEnum):
    """Three error domains for cascade isolation.

    Every raised exception must carry a domain field.
    failure_analyzer MUST check domain == IMPLEMENTATION at entry.
    """

    IMPLEMENTATION = "IMPLEMENTATION"
    """Compilation error, test failure, sandbox timeout, runtime crash.
    Cascades to: failure analyzer → pattern extraction → prevention artifacts.
    THESE ARE the learning signal."""

    DIAGNOSTIC = "DIAGNOSTIC"
    """Embedding index down, pattern DB timeout, LLM rate limit, stale cache.
    Action: local retry + graceful degradation.
    Log to diagnostic_errors table. NEVER cascade to failure analyzer."""

    GOVERNANCE = "GOVERNANCE"
    """Budget exceeded, track deactivated, graduation exam in progress,
    privilege revoked.
    Action: stop cycle cleanly, no failure analysis. NEVER cascade."""


@dataclass(frozen=True)
class ClassifiedError:
    """Result of error classification.

    Produces:
      (1) Telemetry-safe string for logging (no raw stack traces)
      (2) ErrorDomain for routing
      (3) Human-readable message for operator dashboard

    Priority chain: TelemetrySafeError > errno code > stable .name > fallback
    """

    domain: ErrorDomain
    telemetry_safe_message: str
    human_readable_message: str
    error_type: str
    module: str
    recovery_action: str = ""
    original_exception_type: str = ""


class DomainError(Exception):
    """Base exception carrying an ErrorDomain field.

    All system exceptions should inherit from this or carry a
    domain attribute.
    """

    def __init__(
        self,
        message: str,
        domain: ErrorDomain = ErrorDomain.DIAGNOSTIC,
        module: str = "",
    ) -> None:
        super().__init__(message)
        self.domain = domain
        self.module = module


class ImplementationError(DomainError):
    """Error in generated code (compilation, test failure, etc.)."""

    def __init__(self, message: str, module: str = "") -> None:
        super().__init__(message, ErrorDomain.IMPLEMENTATION, module)


class DiagnosticError(DomainError):
    """Infrastructure/diagnostic error (DB timeout, rate limit, etc.)."""

    def __init__(self, message: str, module: str = "") -> None:
        super().__init__(message, ErrorDomain.DIAGNOSTIC, module)


class GovernanceError(DomainError):
    """Governance error (budget exceeded, track deactivated, etc.)."""

    def __init__(self, message: str, module: str = "") -> None:
        super().__init__(message, ErrorDomain.GOVERNANCE, module)
