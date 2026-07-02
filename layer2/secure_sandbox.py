"""secure_sandbox.py — AST-based secure sandbox with resource limits.

Layer 2 — v0.2.0.  Replaces regex-based security with AST analysis.
Supports multi-language execution via plugin runners.
"""
from __future__ import annotations

import ast
import math
import os
import resource
import signal
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ── AST Security Analyzer ──────────────────────────────────────────────────

class SecurityAnalyzer(ast.NodeVisitor):
    """AST visitor that detects dangerous operations."""

    BLOCKED_NAMES = frozenset({
        "os", "sys", "subprocess", "shutil", "socket", "requests",
        "urllib", "http", "ftplib", "ctypes", "multiprocessing",
        "signal", "resource", "pathlib", "importlib", "builtins",
        "__builtins__", "eval", "exec", "compile", "open",
    })

    DANGEROUS_CALLS = frozenset({
        "__import__", "eval", "exec", "compile", "open",
        "input", "raw_input", "breakpoint", "exit", "quit",
    })

    def __init__(self) -> None:
        self.violations: list[str] = []
        self._imports: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            base = alias.name.split(".")[0]
            if base in self.BLOCKED_NAMES:
                self.violations.append(f"blocked import: {alias.name}")
            self._imports.add(base)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            base = node.module.split(".")[0]
            if base in self.BLOCKED_NAMES:
                self.violations.append(f"blocked from-import: {node.module}")
            self._imports.add(base)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id in self.DANGEROUS_CALLS:
                self.violations.append(f"dangerous call: {node.func.id}()")
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in self.DANGEROUS_CALLS:
                self.violations.append(f"dangerous method call: {node.func.attr}()")
        self.generic_visit(node)

    def visit_Exec(self, node: ast.AST) -> None:
        self.violations.append("blocked: exec statement")
        self.generic_visit(node)

    def analyze(self, code: str) -> list[str]:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [f"syntax error: {e}"]
        self.violations = []
        self._imports = set()
        self.visit(tree)
        return self.violations


# ── Resource Limit Context ─────────────────────────────────────────────────

class ResourceLimits:
    """Context manager for subprocess resource limits."""

    def __init__(
        self,
        memory_mb: int = 256,
        cpu_seconds: int = 30,
        max_files: int = 64,
    ) -> None:
        self.memory_bytes = memory_mb * 1024 * 1024
        self.cpu_seconds = cpu_seconds
        self.max_files = max_files

    def __enter__(self) -> None:
        # Soft limits — can be raised back in child if needed
        resource.setrlimit(resource.RLIMIT_AS, (self.memory_bytes, self.memory_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (self.cpu_seconds, self.cpu_seconds + 5))
        resource.setrlimit(resource.RLIMIT_NOFILE, (self.max_files, self.max_files))
        # Prevent core dumps
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    def __exit__(self, *args: Any) -> None:
        # Reset to defaults (best effort)
        try:
            resource.setrlimit(resource.RLIMIT_AS, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
        except ValueError:
            pass


def _preexec_fn(memory_mb: int, cpu_seconds: int) -> None:
    """Called in child process before exec."""
    try:
        mem = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    except Exception:
        pass
    # Drop privileges if running as root (not typical)
    try:
        import pwd
        nobody = pwd.getpwnam("nobody")
        os.setgid(nobody.pw_gid)
        os.setuid(nobody.pw_uid)
    except Exception:
        pass


# ── Language Runners ───────────────────────────────────────────────────────

class LanguageRunner:
    """Base class for language-specific execution."""

    def run(self, code: str, test_code: str, timeout: int, memory_mb: int) -> dict[str, Any]:
        raise NotImplementedError


class PythonRunner(LanguageRunner):
    def run(self, code: str, test_code: str, timeout: int, memory_mb: int) -> dict[str, Any]:
        full = f"{code}\n\n{test_code}" if test_code else code
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="/tmp/sandbox",
        ) as tmp:
            tmp.write(full)
            tmp_path = tmp.name
        try:
            # Sanitize environment
            env = {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "PATH": "/usr/bin:/bin",
                "HOME": "/tmp",
            }
            result = subprocess.run(
                ["python3", tmp_path],
                capture_output=True, text=True, timeout=timeout,
                env=env,
                preexec_fn=lambda: _preexec_fn(memory_mb, timeout),
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": "TIMEOUT", "success": False, "timed_out": True}
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class JavaScriptRunner(LanguageRunner):
    def run(self, code: str, test_code: str, timeout: int, memory_mb: int) -> dict[str, Any]:
        full = f"{code}\n\n{test_code}" if test_code else code
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, dir="/tmp/sandbox",
        ) as tmp:
            tmp.write(full)
            tmp_path = tmp.name
        try:
            env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp"}
            result = subprocess.run(
                ["node", tmp_path],
                capture_output=True, text=True, timeout=timeout,
                env=env,
                preexec_fn=lambda: _preexec_fn(memory_mb, timeout),
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": "TIMEOUT", "success": False, "timed_out": True}
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class GoRunner(LanguageRunner):
    def run(self, code: str, test_code: str, timeout: int, memory_mb: int) -> dict[str, Any]:
        full = f"{code}\n\n{test_code}" if test_code else code
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".go", delete=False, dir="/tmp/sandbox",
        ) as tmp:
            tmp.write(full)
            tmp_path = tmp.name
        try:
            env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "GOPATH": "/tmp/go"}
            result = subprocess.run(
                ["go", "run", tmp_path],
                capture_output=True, text=True, timeout=timeout,
                env=env,
                preexec_fn=lambda: _preexec_fn(memory_mb, timeout),
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": "TIMEOUT", "success": False, "timed_out": True}
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class RustRunner(LanguageRunner):
    def run(self, code: str, test_code: str, timeout: int, memory_mb: int) -> dict[str, Any]:
        full = f"{code}\n\n{test_code}" if test_code else code
        work_dir = tempfile.mkdtemp(dir="/tmp/sandbox")
        src_path = os.path.join(work_dir, "main.rs")
        try:
            with open(src_path, "w") as f:
                f.write(full)
            env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp"}
            result = subprocess.run(
                ["rustc", "--edition", "2021", "-o", os.path.join(work_dir, "main"), src_path],
                capture_output=True, text=True, timeout=timeout,
                env=env,
                preexec_fn=lambda: _preexec_fn(memory_mb, timeout),
            )
            if result.returncode != 0:
                return {"exit_code": result.returncode, "stdout": "", "stderr": result.stderr, "success": False}
            result = subprocess.run(
                [os.path.join(work_dir, "main")],
                capture_output=True, text=True, timeout=timeout,
                env=env,
                preexec_fn=lambda: _preexec_fn(memory_mb, timeout),
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": "TIMEOUT", "success": False, "timed_out": True}
        finally:
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)


# ── Secure Sandbox Manager ─────────────────────────────────────────────────

@dataclass
class SecureSandboxManager:
    """AST-based secure sandbox with multi-language support."""

    default_type: str = "subprocess"
    base_timeout: int = 30
    memory_limit_mb: int = 256
    blocked_imports: list[str] = field(default_factory=list)
    docker_image: str = "python:3.11-slim"

    _analyzer: SecurityAnalyzer = field(default_factory=SecurityAnalyzer)
    _runners: dict[str, LanguageRunner] = field(default_factory=dict)
    _execution_count: int = 0
    _total_runtime_ms: float = 0.0

    def __post_init__(self) -> None:
        os.makedirs("/tmp/sandbox", mode=0o700, exist_ok=True)
        self._runners = {
            "python": PythonRunner(),
            "javascript": JavaScriptRunner(),
            "typescript": JavaScriptRunner(),  # ts-node or transpile first
            "go": GoRunner(),
            "rust": RustRunner(),
        }

    def execute(
        self,
        code: str,
        language: str = "python",
        level: str = "F1",
        test_code: str = "",
        timeout_override: Optional[int] = None,
    ) -> dict[str, Any]:
        """Execute code securely. Returns standardized result dict."""
        timeout = timeout_override or self._compute_timeout(level)

        # Security check
        if language == "python":
            violations = self._analyzer.analyze(code)
            if violations:
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"SECURITY_VIOLATION: {'; '.join(violations)}",
                    "security_blocked": True,
                }

        # Validate syntax
        if language == "python":
            try:
                ast.parse(code)
            except SyntaxError as e:
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"SYNTAX_ERROR: {e}",
                    "syntax_error": True,
                }

        # Run
        runner = self._runners.get(language.lower())
        if runner is None:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"UNSUPPORTED_LANGUAGE: {language}",
            }

        start = time.monotonic()
        result = runner.run(code, test_code, timeout, self.memory_limit_mb)
        elapsed_ms = (time.monotonic() - start) * 1000

        self._execution_count += 1
        self._total_runtime_ms += elapsed_ms

        return {
            "execution_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "language": language,
            "timeout_seconds": timeout,
            "actual_runtime_ms": elapsed_ms,
            **result,
        }

    def _compute_timeout(self, level: str) -> int:
        """Compute timeout: base * 2^((level-1)/2)."""
        level_map = {"f1": 1, "f2": 2, "f3": 3, "f4": 4, "f5": 5, "f6": 6, "f7": 7, "f8": 8}
        n = level_map.get(str(level).lower(), 1)
        return int(self.base_timeout * math.pow(2, (n - 1) / 2))

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_executions": self._execution_count,
            "total_runtime_ms": self._total_runtime_ms,
            "avg_runtime_ms": self._total_runtime_ms / max(self._execution_count, 1),
        }
