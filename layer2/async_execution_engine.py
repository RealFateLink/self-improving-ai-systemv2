"""async_execution_engine.py — Scalable async code execution backend.

Layer 2 — v0.2.0.  Worker-pool based execution for concurrent candidate testing.
Replaces sequential execution with parallel sandbox workers.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ExecutionJob:
    """A single execution job."""
    job_id: str
    code: str
    test_code: str
    language: str
    timeout: int
    memory_mb: int
    callback: Optional[Callable[[dict], None]] = None


@dataclass
class AsyncExecutionEngine:
    """Async execution engine with worker pool.

    Uses ThreadPoolExecutor for I/O-bound sandbox operations.
    For CPU-bound execution, use ProcessPoolExecutor instead.
    """

    sandbox: Any = None
    max_workers: int = 8
    _executor: Optional[concurrent.futures.Executor] = None
    _pending: dict[str, concurrent.futures.Future] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)

    async def execute_single(self, job: ExecutionJob) -> dict[str, Any]:
        """Execute a single job asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._run_in_sandbox,
            job,
        )

    async def execute_batch(self, jobs: list[ExecutionJob]) -> list[dict[str, Any]]:
        """Execute multiple jobs concurrently."""
        tasks = [self.execute_single(job) for job in jobs]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def _run_in_sandbox(self, job: ExecutionJob) -> dict[str, Any]:
        """Run job in sandbox (called in worker thread)."""
        if self.sandbox is None:
            return {"success": False, "stderr": "No sandbox configured", "job_id": job.job_id}
        result = self.sandbox.execute(
            code=job.code,
            test_code=job.test_code,
            language=job.language,
            timeout_override=job.timeout,
        )
        result["job_id"] = job.job_id
        if job.callback:
            job.callback(result)
        return result

    def shutdown(self) -> None:
        if self._executor:
            self._executor.shutdown(wait=True)

    def get_stats(self) -> dict[str, Any]:
        return {
            "max_workers": self.max_workers,
            "pending_jobs": len(self._pending),
        }
