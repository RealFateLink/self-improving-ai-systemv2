"""
result.py — Result Monad + Error Types
Layer 0: Self-Improving Engineering AI Foundation

Provides:
  - StrEnum error-type enumerations for all subsystems
  - Result[T, E]: a frozen, generic monad for typed error propagation
  - InvariantViolation: a BaseException for hard invariant breaches
  - Domain-specific frozen error dataclasses
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Generic, Optional, TypeVar

__all__ = [
    # Enums
    "LLMErrorType",
    "SandboxErrorType",
    "LedgerErrorType",
    "ValidationErrorType",
    # Core monad
    "Result",
    # Hard violation
    "InvariantViolation",
    # Error dataclasses
    "LLMError",
    "SandboxError",
    "LedgerError",
    "ValidationError",
    "ConfigLoadError",
]

# ---------------------------------------------------------------------------
# Type variables
# ---------------------------------------------------------------------------

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")


# ---------------------------------------------------------------------------
# 2.1  Error-type enums
# ---------------------------------------------------------------------------


class LLMErrorType(StrEnum):
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    BUDGET_DENIED = "budget_denied"
    AUTH_FAILED = "auth_failed"
    MODEL_NOT_FOUND = "model_not_found"


class SandboxErrorType(StrEnum):
    TIMEOUT = "timeout"
    MEMORY_EXCEEDED = "memory_exceeded"
    RUNTIME_ERROR = "runtime_error"
    IMPORT_BLOCKED = "import_blocked"
    KILLED = "killed"


class LedgerErrorType(StrEnum):
    INTEGRITY_VIOLATION = "integrity_violation"
    NOT_FOUND = "not_found"
    DUPLICATE = "duplicate"
    WRITE_BLOCKED = "write_blocked"
    DISK_FULL = "disk_full"


class ValidationErrorType(StrEnum):
    INVALID_INPUT = "invalid_input"
    MISSING_FIELD = "missing_field"
    OUT_OF_RANGE = "out_of_range"
    TYPE_MISMATCH = "type_mismatch"


# ---------------------------------------------------------------------------
# 2.2  Result[T, E] — frozen generic monad
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Result(Generic[T, E]):
    """
    Lightweight Result monad.  Exactly one of *value* or *error* is set.

    Construct via convenience class-methods or directly:
        Result(value=x)          — ok
        Result(error=e)          — err
    """

    value: T | None = None
    error: E | None = None

    # ------------------------------------------------------------------
    # Predicates
    # ------------------------------------------------------------------

    def is_ok(self) -> bool:
        """Return True when the result holds a successful value."""
        return self.error is None

    def is_err(self) -> bool:
        """Return True when the result holds an error."""
        return self.error is not None

    # ------------------------------------------------------------------
    # Unwrapping
    # ------------------------------------------------------------------

    def unwrap(self) -> T:
        """
        Return the contained value.

        Raises:
            ValueError: if the result is an error.
        """
        if self.is_err():
            raise ValueError(f"Called unwrap() on an Err result: {self.error!r}")
        return self.value  # type: ignore[return-value]

    def unwrap_or(self, default: T) -> T:
        """Return the contained value, or *default* if this is an error."""
        return self.value if self.is_ok() else default  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Transformations
    # ------------------------------------------------------------------

    def map(self, fn: Callable[[T], U]) -> Result[U, E]:
        """
        Apply *fn* to the contained value and return a new ok Result.
        If this is an error, return it unchanged.
        """
        if self.is_ok():
            return Result(value=fn(self.value))  # type: ignore[arg-type]
        return Result(error=self.error)  # type: ignore[arg-type]

    def and_then(self, fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """
        Monadic bind: apply *fn* to the value if ok, forwarding any error.
        *fn* must itself return a Result.
        """
        if self.is_ok():
            return fn(self.value)  # type: ignore[arg-type]
        return Result(error=self.error)  # type: ignore[arg-type]

    def map_err(self, fn: Callable[[E], F]) -> Result[T, F]:
        """
        Apply *fn* to the error and return a new err Result.
        If this is ok, return it unchanged.
        """
        if self.is_err():
            return Result(error=fn(self.error))  # type: ignore[arg-type]
        return Result(value=self.value)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2.2  InvariantViolation — hard system invariant breach
# ---------------------------------------------------------------------------


class InvariantViolation(BaseException):
    """
    Raised when a hard system invariant (INV-001 … INV-007) is breached.

    Extends BaseException so that broad ``except Exception`` clauses in
    calling code do not accidentally suppress it.
    """

    def __init__(
        self,
        invariant_id: str,
        operation_attempted: str,
        module_source: str,
        detail: str,
        timestamp: str,
        cycle_id: Optional[str] = None,
    ) -> None:
        self.invariant_id = invariant_id
        self.operation_attempted = operation_attempted
        self.module_source = module_source
        self.cycle_id = cycle_id
        self.detail = detail
        self.timestamp = timestamp
        super().__init__(
            f"[{invariant_id}] {detail} "
            f"(op={operation_attempted!r}, src={module_source!r}, ts={timestamp})"
        )


# ---------------------------------------------------------------------------
# 2.2  Domain-specific frozen error dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMError:
    """Error produced by the LLM subsystem."""

    error_type: LLMErrorType
    message: str
    detail: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass(frozen=True)
class SandboxError:
    """Error produced by the code-execution sandbox."""

    error_type: SandboxErrorType
    message: str
    detail: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass(frozen=True)
class LedgerError:
    """Error produced by the append-only ledger / persistence layer."""

    error_type: LedgerErrorType
    message: str
    detail: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass(frozen=True)
class ValidationError:
    """Error produced by input-validation routines."""

    error_type: ValidationErrorType
    message: str
    field: Optional[str] = None
    detail: Optional[str] = None


@dataclass(frozen=True)
class ConfigLoadError:
    """Error raised when a configuration file cannot be loaded or parsed."""

    path: str
    message: str
    detail: Optional[str] = None
