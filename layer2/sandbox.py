"""Layer 2 — Sandbox execution environment.

Manages code execution in isolated environments with timeout and
memory limits. Supports subprocess, Docker, and QEMU modes.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..result import Result, SandboxError, SandboxErrorType
from ..types.common import SandboxExecution
from ..types.enums import SandboxType, TaskLevel


# Blocked import patterns for security
_BLOCKED_IMPORT_PATTERN = re.compile(
    r"^\s*(?:import|from)\s+("
    r"os|sys|subprocess|shutil|socket|requests|urllib|http|ftplib|"
    r"ctypes|multiprocessing|signal|resource|pathlib"
    r")(?:\s|\.|$)",
    re.MULTILINE,
)

# F-level to numeric mapping
_LEVEL_MAP: dict[str, int] = {
    "f1": 1, "f2": 2, "f3": 3, "f4": 4,
    "f5": 5, "f6": 6, "f7": 7, "f8": 8,
}


def compute_timeout(level: TaskLevel | str, base_timeout: int = 30) -> int:
    """Compute timeout using formula: base * 2^((level-1)/2).

    F1=30s, F2=42s, F3=60s, F4=85s, F5=120s, F6=170s, F7=240s, F8=339s
    """
    level_str = level.value if isinstance(level, TaskLevel) else str(level).lower()
    n = _LEVEL_MAP.get(level_str, 1)
    return int(base_timeout * math.pow(2, (n - 1) / 2))


class SandboxManager:
    """Manages code execution in sandboxed environments."""

    def __init__(
        self,
        default_type: SandboxType = SandboxType.SUBPROCESS,
        base_timeout: int = 30,
        memory_limit_mb: int = 256,
        blocked_imports: Optional[list[str]] = None,
        docker_image: str = "python:3.11-slim",
    ) -> None:
        self._default_type = default_type
        self._base_timeout = base_timeout
        self._memory_limit_mb = memory_limit_mb
        self._blocked_imports = blocked_imports or []
        self._docker_image = docker_image
        self._execution_count = 0
        self._total_runtime_ms = 0.0

    def execute(
        self,
        code: str,
        language: str = "python",
        level: TaskLevel | str = TaskLevel.F1,
        test_code: str = "",
        sandbox_type: Optional[SandboxType] = None,
        timeout_override: Optional[int] = None,
    ) -> Result[SandboxExecution, SandboxError]:
        """Execute code in a sandboxed environment."""
        sb_type = sandbox_type or self._default_type
        timeout = timeout_override or compute_timeout(level, self._base_timeout)

        # Security check
        security_result = self.check_security(code)
        if security_result.error is not None:
            return Result(error=security_result.error)

        if sb_type == SandboxType.SUBPROCESS:
            return self._execute_subprocess(code, language, timeout, test_code)
        elif sb_type == SandboxType.DOCKER:
            return self._execute_docker(code, language, timeout, test_code)
        elif sb_type == SandboxType.QEMU:
            return Result(error=SandboxError(
                error_type=SandboxErrorType.RUNTIME_ERROR,
                message="QEMU sandbox not yet implemented",
            ))
        else:
            return Result(error=SandboxError(
                error_type=SandboxErrorType.RUNTIME_ERROR,
                message=f"Unknown sandbox type: {sb_type}",
            ))

    def check_security(self, code: str) -> Result[None, SandboxError]:
        """Check code for blocked imports and security violations."""
        violations = []

        matches = _BLOCKED_IMPORT_PATTERN.findall(code)
        if matches:
            violations.extend(f"blocked import: {m}" for m in matches)

        for blocked in self._blocked_imports:
            if re.search(rf"\b{re.escape(blocked)}\b", code):
                violations.append(f"blocked module: {blocked}")

        if violations:
            return Result(error=SandboxError(
                error_type=SandboxErrorType.IMPORT_BLOCKED,
                message=f"Security violations: {'; '.join(violations)}",
            ))
        return Result(value=None)

    def validate_code(self, code: str, language: str = "python") -> Result[bool, SandboxError]:
        """Validate code syntax without executing."""
        if language != "python":
            return Result(value=True)  # Only Python syntax check for now
        try:
            compile(code, "<sandbox>", "exec")
            return Result(value=True)
        except SyntaxError as exc:
            return Result(error=SandboxError(
                error_type=SandboxErrorType.RUNTIME_ERROR,
                message=f"Syntax error: {exc}",
            ))

    def get_execution_stats(self) -> dict[str, Any]:
        return {
            "total_executions": self._execution_count,
            "total_runtime_ms": self._total_runtime_ms,
            "avg_runtime_ms": (
                self._total_runtime_ms / self._execution_count
                if self._execution_count > 0 else 0.0
            ),
        }

    def _execute_subprocess(
        self, code: str, language: str, timeout: int, test_code: str,
    ) -> Result[SandboxExecution, SandboxError]:
        """Execute code in a subprocess."""
        exec_id = str(uuid.uuid4())
        start_time = time.monotonic()

        # Combine code and test code
        full_code = code
        if test_code:
            full_code = f"{code}\n\n{test_code}"

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False,
            ) as tmp:
                tmp.write(full_code)
                tmp_path = tmp.name

            result = subprocess.run(
                ["python3", tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

            elapsed_ms = (time.monotonic() - start_time) * 1000
            self._execution_count += 1
            self._total_runtime_ms += elapsed_ms

            execution = SandboxExecution(
                execution_id=exec_id,
                cycle_number=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                sandbox_type=SandboxType.SUBPROCESS,
                language=language,
                timeout_seconds=timeout,
                actual_runtime_ms=elapsed_ms,
                exit_code=result.returncode,
                success=result.returncode == 0,
                stdout_excerpt=result.stdout[:2000] if result.stdout else "",
                stderr_excerpt=result.stderr[:2000] if result.stderr else "",
            )
            return Result(value=execution)

        except subprocess.TimeoutExpired:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            self._execution_count += 1
            self._total_runtime_ms += elapsed_ms
            return Result(error=SandboxError(
                error_type=SandboxErrorType.TIMEOUT,
                message=f"Execution timed out after {timeout}s",
            ))
        except Exception as exc:
            return Result(error=SandboxError(
                error_type=SandboxErrorType.RUNTIME_ERROR,
                message=f"Subprocess execution failed: {exc}",
            ))
        finally:
            try:
                os.unlink(tmp_path)
            except (OSError, UnboundLocalError):
                pass

    def _execute_docker(
        self, code: str, language: str, timeout: int, test_code: str,
    ) -> Result[SandboxExecution, SandboxError]:
        """Execute code in a Docker container."""
        exec_id = str(uuid.uuid4())
        full_code = f"{code}\n\n{test_code}" if test_code else code

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False,
            ) as tmp:
                tmp.write(full_code)
                tmp_path = tmp.name

            start_time = time.monotonic()
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "--memory", f"{self._memory_limit_mb}m",
                    "--network", "none",
                    "--read-only",
                    "-v", f"{tmp_path}:/code/main.py:ro",
                    self._docker_image,
                    "python3", "/code/main.py",
                ],
                capture_output=True, text=True, timeout=timeout + 10,
            )
            elapsed_ms = (time.monotonic() - start_time) * 1000
            self._execution_count += 1
            self._total_runtime_ms += elapsed_ms

            execution = SandboxExecution(
                execution_id=exec_id,
                cycle_number=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                sandbox_type=SandboxType.DOCKER,
                language=language,
                timeout_seconds=timeout,
                actual_runtime_ms=elapsed_ms,
                exit_code=result.returncode,
                success=result.returncode == 0,
                stdout_excerpt=result.stdout[:2000] if result.stdout else "",
                stderr_excerpt=result.stderr[:2000] if result.stderr else "",
            )
            return Result(value=execution)

        except subprocess.TimeoutExpired:
            return Result(error=SandboxError(
                error_type=SandboxErrorType.TIMEOUT,
                message=f"Docker execution timed out after {timeout}s",
            ))
        except FileNotFoundError:
            return Result(error=SandboxError(
                error_type=SandboxErrorType.RUNTIME_ERROR,
                message="Docker not available",
            ))
        except Exception as exc:
            return Result(error=SandboxError(
                error_type=SandboxErrorType.RUNTIME_ERROR,
                message=f"Docker execution failed: {exc}",
            ))
        finally:
            try:
                os.unlink(tmp_path)
            except (OSError, UnboundLocalError):
                pass
