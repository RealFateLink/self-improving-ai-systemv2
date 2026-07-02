"""Layer 7 — Benchmark Runner.

Main orchestration for benchmark execution. Tiered schedule based on
graduation level, problem iteration, score recording, session management,
leak audit integration. Runs as a SEPARATE PROCESS from the orchestrator.
~420 lines | Category: BENCHMARK
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BenchmarkSessionStatus(StrEnum):
    """Session completion states."""

    IN_PROGRESS = "IN_PROGRESS"
    PENDING_LEAK_CHECK = "PENDING_LEAK_CHECK"
    COMPLETED_CLEAN = "COMPLETED_CLEAN"
    COMPLETED_SCRUBBED = "COMPLETED_SCRUBBED"
    QUARANTINED = "QUARANTINED"
    INVALIDATED = "INVALIDATED"


class BenchmarkName(StrEnum):
    """Supported benchmark names."""

    HUMANEVAL = "humaneval"
    MBPP = "mbpp"
    LIVECODEBENCH = "livecodebench"
    SWEBENCH = "swebench"


@dataclass(frozen=True)
class BenchmarkSession:
    """Active benchmark session."""

    session_id: str
    benchmark_names: tuple[str, ...]
    status: BenchmarkSessionStatus
    started_at: str
    completed_at: Optional[str] = None
    total_problems: int = 0
    problems_completed: int = 0
    problems_passed: int = 0
    aggregate_scores: dict[str, float] = field(default_factory=dict)
    leak_audit_result: Optional[str] = None


@dataclass(frozen=True)
class BenchmarkProblemResult:
    """Result for a single benchmark problem."""

    problem_id: str
    benchmark_name: str
    session_id: str
    passed: bool
    generated_code: str
    reasoning_chain: str
    test_results: list[dict[str, Any]]
    execution_traces: list[str]
    error_messages: list[str]
    performance_metrics: dict[str, Any]
    cost_usd: float
    duration_seconds: float


# ── Tiered schedule configuration ────────────────────────────────────────────

TIERED_SCHEDULE: dict[str, dict[str, Any]] = {
    "G0_G1": {
        "frequency": "monthly",
        "benchmarks": [BenchmarkName.HUMANEVAL],
        "max_cycle_count": 3000,
    },
    "G1_G2": {
        "frequency": "monthly",
        "benchmarks": [BenchmarkName.HUMANEVAL, BenchmarkName.LIVECODEBENCH],
        "max_cycle_count": 5000,
    },
    "G2_G3": {
        "frequency": "biweekly",
        "benchmarks": [
            BenchmarkName.HUMANEVAL,
            BenchmarkName.MBPP,
            BenchmarkName.LIVECODEBENCH,
        ],
        "max_cycle_count": None,
    },
    "G4_PLUS": {
        "frequency": "weekly",
        "benchmarks": [
            BenchmarkName.HUMANEVAL,
            BenchmarkName.MBPP,
            BenchmarkName.LIVECODEBENCH,
            BenchmarkName.SWEBENCH,
        ],
        "swebench_frequency": "bimonthly",
        "max_cycle_count": None,
    },
}


class BenchmarkRunner:
    """Orchestrates benchmark execution with contamination prevention.

    Runs as a separate process. Feeds failures through L4 failure
    analysis anonymously. Never exposes benchmark problems, scores,
    or identifiers to the learning system.

    The system improves FROM benchmark failures (general patterns)
    but never learns TO benchmark problems (no specific answers).
    """

    def __init__(
        self,
        ledger: Any,
        config: Any,
        llm_client: Any,
        sandbox: Any,
    ) -> None:
        self._ledger = ledger
        self._config = config
        self._llm = llm_client
        self._sandbox = sandbox
        self._isolation_verifier: Optional[Any] = None
        self._problem_adapter: Optional[Any] = None
        self._anonymous_feeder: Optional[Any] = None
        self._swebench_adapter: Optional[Any] = None

    def set_components(
        self,
        isolation_verifier: Any,
        problem_adapter: Any,
        anonymous_feeder: Any,
        swebench_adapter: Any,
    ) -> None:
        """Set dependent components after construction."""
        self._isolation_verifier = isolation_verifier
        self._problem_adapter = problem_adapter
        self._anonymous_feeder = anonymous_feeder
        self._swebench_adapter = swebench_adapter

    # ── Public API ───────────────────────────────────────────────────────────

    def run(
        self,
        benchmark_name: Optional[str] = None,
        force: bool = False,
    ) -> BenchmarkSession:
        """Main entry point for benchmark execution.

        Steps:
          1. Verify isolation (5 contamination checks).
          2. Determine scheduled benchmarks (or use forced name).
          3. Check budget.
          4. Create session.
          5. Run each benchmark.
          6. Score and record results.
          7. Leak audit.
          8. Finalize session.

        Args:
            benchmark_name: Specific benchmark to run (overrides schedule).
            force: Bypass isolation check failures.

        Returns BenchmarkSession with final status.
        """
        # Step 1: Isolation verification
        isolation_result = self._isolation_verifier.verify()
        if not isolation_result.overall_passed and not force:
            logger.error("Isolation verification failed: %s", isolation_result.issues)
            session = self._create_session(())
            return self._invalidate_session(
                session, f"Isolation failure: {isolation_result.issues}"
            )

        # Step 2: Determine benchmarks to run
        if benchmark_name:
            benchmarks = [BenchmarkName(benchmark_name)]
        else:
            benchmarks = self._get_scheduled_benchmarks()
            if not benchmarks:
                logger.info("No benchmarks scheduled for this period")
                return self._create_session(())

        # Step 3: Budget check
        for bm in benchmarks:
            if not self._check_budget(bm):
                logger.warning("Insufficient budget for %s", bm)
                benchmarks = [b for b in benchmarks if b != bm]

        if not benchmarks:
            return self._create_session(())

        # Step 4: Create session
        session = self._create_session(tuple(b.value for b in benchmarks))
        logger.info(
            "Starting benchmark session %s: %s",
            session.session_id,
            [b.value for b in benchmarks],
        )

        # Step 5: Run each benchmark
        all_results: list[BenchmarkProblemResult] = []
        for bm in benchmarks:
            if bm == BenchmarkName.SWEBENCH:
                results = self._run_swebench(session.session_id)
            else:
                results = self._run_standard_benchmark(bm, session.session_id)
            all_results.extend(results)

        # Step 6: Record results and feed failures
        for result in all_results:
            self._record_problem_result(result)

        # Step 7: Leak audit
        session = self._update_session_status(
            session, BenchmarkSessionStatus.PENDING_LEAK_CHECK
        )

        # Step 8: Finalize
        return self._finalize_session(session, all_results)

    # ── Benchmark Execution ──────────────────────────────────────────────────

    def _run_standard_benchmark(
        self, benchmark_name: BenchmarkName, session_id: str
    ) -> list[BenchmarkProblemResult]:
        """Run a standard benchmark (HumanEval, MBPP, LiveCodeBench).

        Iterates problems: adapt → generate → execute → score.
        Feeds failures anonymously.
        """
        problems = self._load_benchmark_problems(benchmark_name)
        results: list[BenchmarkProblemResult] = []

        for problem in problems:
            # Adapt to TaskSpec format
            task_spec = self._problem_adapter.adapt(problem, benchmark_name.value)

            # Generate solution
            generation_result = self._generate_solution(task_spec)

            # Execute in sandbox
            execution_result = self._execute_solution(
                generation_result, task_spec
            )

            # Score
            passed = self._score_result(execution_result, task_spec)

            result = BenchmarkProblemResult(
                problem_id=getattr(task_spec, "task_id", ""),
                benchmark_name=benchmark_name.value,
                session_id=session_id,
                passed=passed,
                generated_code=getattr(generation_result, "code", ""),
                reasoning_chain=getattr(generation_result, "reasoning", ""),
                test_results=getattr(execution_result, "test_results", []),
                execution_traces=getattr(execution_result, "traces", []),
                error_messages=getattr(execution_result, "errors", []),
                performance_metrics=getattr(execution_result, "metrics", {}),
                cost_usd=getattr(generation_result, "cost_usd", 0.0),
                duration_seconds=getattr(execution_result, "duration", 0.0),
            )

            results.append(result)

            # Feed failures anonymously
            if not passed:
                self._anonymous_feeder.feed(result, session_id)

        logger.info(
            "Completed %s: %d/%d passed",
            benchmark_name.value,
            sum(1 for r in results if r.passed),
            len(results),
        )

        return results

    def _run_swebench(self, session_id: str) -> list[BenchmarkProblemResult]:
        """Run SWE-bench: clone repo → investigate → generate patch → test.

        Most expensive benchmark: $0.50–2.00 per problem.
        """
        swebench_budget_cap = getattr(
            self._config, "swebench_per_run_usd", 20.0
        )
        problems = self._load_benchmark_problems(BenchmarkName.SWEBENCH)
        results: list[BenchmarkProblemResult] = []
        total_cost = 0.0

        for problem in problems:
            if total_cost >= swebench_budget_cap:
                logger.warning("SWE-bench budget cap reached: $%.2f", total_cost)
                break

            swe_result = self._swebench_adapter.run_problem(
                issue=problem,
                repo_url=getattr(problem, "repo_url", ""),
            )

            passed = getattr(swe_result, "resolved", False)
            cost = getattr(swe_result, "cost_usd", 0.0)
            total_cost += cost

            result = BenchmarkProblemResult(
                problem_id=getattr(problem, "problem_id", ""),
                benchmark_name=BenchmarkName.SWEBENCH.value,
                session_id=session_id,
                passed=passed,
                generated_code=getattr(swe_result, "patch", ""),
                reasoning_chain=getattr(swe_result, "investigation_summary", ""),
                test_results=getattr(swe_result, "test_results", []),
                execution_traces=getattr(swe_result, "traces", []),
                error_messages=getattr(swe_result, "errors", []),
                performance_metrics={"cost_usd": cost},
                cost_usd=cost,
                duration_seconds=getattr(swe_result, "duration", 0.0),
            )

            results.append(result)

            if not passed:
                self._anonymous_feeder.feed(result, session_id)

        return results

    # ── Session Management ───────────────────────────────────────────────────

    def _create_session(
        self, benchmark_names: tuple[str, ...]
    ) -> BenchmarkSession:
        """Create a new benchmark session."""
        session_id = self._generate_session_id()
        session = BenchmarkSession(
            session_id=session_id,
            benchmark_names=benchmark_names,
            status=BenchmarkSessionStatus.IN_PROGRESS,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._ledger.insert_benchmark_session(session)
        return session

    def _finalize_session(
        self,
        session: BenchmarkSession,
        results: list[BenchmarkProblemResult],
    ) -> BenchmarkSession:
        """Finalize session: compute scores, run leak audit, set status.

        Session completion states:
          COMPLETED_CLEAN: Leak audit PASS. Metrics eligible.
          COMPLETED_SCRUBBED: Leak issues found and cleaned. Metrics eligible.
          QUARANTINED: Leak issues found, can't clean. Metrics ineligible.
          INVALIDATED: Severe contamination. Metrics void.
        """
        # Compute aggregate scores
        aggregate = self._compute_aggregate_scores(results)

        # Run leak audit
        leak_result = self._run_leak_audit(session.session_id, results)

        # Determine final status
        if leak_result.get("severe_contamination", False):
            final_status = BenchmarkSessionStatus.INVALIDATED
        elif leak_result.get("issues_found", False):
            if leak_result.get("cleaned", False):
                final_status = BenchmarkSessionStatus.COMPLETED_SCRUBBED
            else:
                final_status = BenchmarkSessionStatus.QUARANTINED
        else:
            final_status = BenchmarkSessionStatus.COMPLETED_CLEAN

        # Build finalized session
        finalized = BenchmarkSession(
            session_id=session.session_id,
            benchmark_names=session.benchmark_names,
            status=final_status,
            started_at=session.started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            total_problems=len(results),
            problems_completed=len(results),
            problems_passed=sum(1 for r in results if r.passed),
            aggregate_scores=aggregate,
            leak_audit_result=json.dumps(leak_result),
        )

        self._ledger.update_benchmark_session(finalized)

        logger.info(
            "Finalized session %s: status=%s, %d/%d passed",
            session.session_id,
            final_status.value,
            finalized.problems_passed,
            finalized.total_problems,
        )

        return finalized

    def _update_session_status(
        self, session: BenchmarkSession, status: BenchmarkSessionStatus
    ) -> BenchmarkSession:
        """Update session status in the ledger."""
        updated = BenchmarkSession(
            session_id=session.session_id,
            benchmark_names=session.benchmark_names,
            status=status,
            started_at=session.started_at,
            total_problems=session.total_problems,
            problems_completed=session.problems_completed,
            problems_passed=session.problems_passed,
        )
        self._ledger.update_benchmark_session(updated)
        return updated

    def _invalidate_session(
        self, session: BenchmarkSession, reason: str
    ) -> BenchmarkSession:
        """Mark a session as INVALIDATED."""
        invalidated = BenchmarkSession(
            session_id=session.session_id,
            benchmark_names=session.benchmark_names,
            status=BenchmarkSessionStatus.INVALIDATED,
            started_at=session.started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            leak_audit_result=json.dumps({"reason": reason}),
        )
        self._ledger.update_benchmark_session(invalidated)
        return invalidated

    def _record_problem_result(self, result: BenchmarkProblemResult) -> None:
        """Insert a problem result into the benchmark results table."""
        self._ledger.insert_benchmark_problem_result(result)

    # ── Schedule and Budget ──────────────────────────────────────────────────

    def _get_scheduled_benchmarks(self) -> list[BenchmarkName]:
        """Determine which benchmarks are due based on graduation tier + schedule."""
        graduation_tier = self._ledger.get_system_state("graduation_tier")
        cycle_count_str = self._ledger.get_system_state("cycle_count")
        cycle_count = int(cycle_count_str) if cycle_count_str else 0

        last_run_str = self._ledger.get_benchmark_state("last_benchmark_run_date")

        tier = graduation_tier or "G0"

        if tier in ("G0", "G1") and cycle_count < 3000:
            schedule = TIERED_SCHEDULE["G0_G1"]
        elif tier in ("G1", "G2") and cycle_count < 5000:
            schedule = TIERED_SCHEDULE["G1_G2"]
        elif tier in ("G2", "G3"):
            schedule = TIERED_SCHEDULE["G2_G3"]
        else:
            schedule = TIERED_SCHEDULE["G4_PLUS"]

        # Check if enough time has passed since last run
        if last_run_str and not self._schedule_due(
            last_run_str, schedule["frequency"]
        ):
            return []

        return list(schedule["benchmarks"])

    def _check_budget(self, benchmark_name: BenchmarkName) -> bool:
        """Verify benchmark budget remaining before starting."""
        budget_pct = getattr(self._config, "benchmark_budget_percent", 5.0)
        monthly_budget = getattr(self._config, "monthly_budget_usd", 200.0)
        benchmark_budget = monthly_budget * (budget_pct / 100.0)

        spent = self._ledger.get_benchmark_spend_this_month()
        remaining = benchmark_budget - spent

        # Estimate cost for this benchmark
        estimated_costs = {
            BenchmarkName.HUMANEVAL: 1.0,
            BenchmarkName.MBPP: 2.0,
            BenchmarkName.LIVECODEBENCH: 3.0,
            BenchmarkName.SWEBENCH: 20.0,
        }
        estimated = estimated_costs.get(benchmark_name, 5.0)

        return remaining >= estimated

    # ── Internal Helpers ─────────────────────────────────────────────────────

    def _load_benchmark_problems(self, benchmark_name: BenchmarkName) -> list[Any]:
        """Load benchmark problems from data files."""
        data_dir = getattr(self._config, "benchmark_data_dir", "benchmark_data")
        path_map = {
            BenchmarkName.HUMANEVAL: f"{data_dir}/humaneval.json",
            BenchmarkName.MBPP: f"{data_dir}/mbpp.json",
            BenchmarkName.LIVECODEBENCH: f"{data_dir}/livecodebench.json",
            BenchmarkName.SWEBENCH: f"{data_dir}/swebench.json",
        }
        path = path_map.get(benchmark_name)
        if path is None:
            return []

        return self._ledger.load_benchmark_data(path)

    def _generate_solution(self, task_spec: Any) -> Any:
        """Generate a solution using the LLM client."""
        prompt = self._build_generation_prompt(task_spec)
        return self._llm.generate(
            prompt=prompt,
            max_tokens=getattr(self._config, "benchmark_max_tokens", 4096),
            is_benchmark=True,
        )

    def _execute_solution(self, generation: Any, task_spec: Any) -> Any:
        """Execute the generated solution in the sandbox."""
        code = getattr(generation, "code", "")
        tests = getattr(task_spec, "hidden_tests", [])
        return self._sandbox.execute(
            code=code,
            tests=tests,
            timeout=getattr(self._config, "benchmark_timeout_seconds", 30),
            is_benchmark=True,
        )

    def _score_result(self, execution: Any, task_spec: Any) -> bool:
        """Score a benchmark problem result. Binary pass/fail."""
        return getattr(execution, "all_tests_passed", False)

    def _compute_aggregate_scores(
        self, results: list[BenchmarkProblemResult]
    ) -> dict[str, float]:
        """Compute aggregate scores by benchmark."""
        scores: dict[str, dict[str, int]] = {}
        for r in results:
            if r.benchmark_name not in scores:
                scores[r.benchmark_name] = {"passed": 0, "total": 0}
            scores[r.benchmark_name]["total"] += 1
            if r.passed:
                scores[r.benchmark_name]["passed"] += 1

        return {
            name: data["passed"] / data["total"] if data["total"] > 0 else 0.0
            for name, data in scores.items()
        }

    def _run_leak_audit(
        self, session_id: str, results: list[BenchmarkProblemResult]
    ) -> dict[str, Any]:
        """Run post-session leak audit.

        Checks that no benchmark data leaked into training system
        during the session.
        """
        audit = {
            "session_id": session_id,
            "issues_found": False,
            "cleaned": False,
            "severe_contamination": False,
            "checks": [],
        }

        # Re-run isolation checks
        verification = self._isolation_verifier.verify()
        if not verification.overall_passed:
            audit["issues_found"] = True
            for issue in verification.issues:
                audit["checks"].append(
                    {"check": issue.check_name, "passed": False, "detail": issue.detail}
                )

            # Attempt cleanup
            cleaned = self._attempt_leak_cleanup(verification.issues)
            audit["cleaned"] = cleaned
            if not cleaned:
                audit["severe_contamination"] = any(
                    i.severity == "CRITICAL" for i in verification.issues
                )

        return audit

    def _attempt_leak_cleanup(self, issues: list[Any]) -> bool:
        """Attempt to clean up leaked benchmark data."""
        all_cleaned = True
        for issue in issues:
            cleaned = self._ledger.cleanup_benchmark_leak(issue)
            if not cleaned:
                all_cleaned = False
        return all_cleaned

    @staticmethod
    def _schedule_due(last_run_str: str, frequency: str) -> bool:
        """Check if enough time has passed for the next run."""
        from datetime import timedelta

        try:
            last_run = datetime.fromisoformat(last_run_str)
        except (ValueError, TypeError):
            return True

        now = datetime.now(timezone.utc)
        intervals = {
            "weekly": timedelta(days=7),
            "biweekly": timedelta(days=14),
            "monthly": timedelta(days=30),
            "bimonthly": timedelta(days=60),
        }
        interval = intervals.get(frequency, timedelta(days=30))
        return (now - last_run) >= interval

    @staticmethod
    def _generate_session_id() -> str:
        """Generate a unique session ID."""
        import uuid
        return f"BMS_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _build_generation_prompt(task_spec: Any) -> str:
        """Build generation prompt for a benchmark problem."""
        description = getattr(task_spec, "description", "")
        visible_tests = getattr(task_spec, "visible_tests", [])
        tests_str = "\n".join(str(t) for t in visible_tests)
        return (
            f"Solve the following programming problem.\n\n"
            f"{description}\n\n"
            f"Visible tests:\n{tests_str}\n\n"
            f"Provide a complete, correct solution."
        )
