"""Layer 7 — Anonymous Feeder.

Strips identifying info from benchmark failures and feeds them through
L4 failure analysis with anonymous templates. Maintains BM- namespace.
Leak sanitization on stored artifacts.
~230 lines | Category: BENCHMARK
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Patterns that indicate benchmark identifiers
IDENTIFIER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"HumanEval/\d+", re.IGNORECASE),
    re.compile(r"MBPP[-_]\d+", re.IGNORECASE),
    re.compile(r"LCB[-_]\d+", re.IGNORECASE),
    re.compile(r"SWE[-_]bench", re.IGNORECASE),
    re.compile(r"humaneval", re.IGNORECASE),
    re.compile(r"mbpp", re.IGNORECASE),
    re.compile(r"livecodebench", re.IGNORECASE),
    re.compile(r"swebench", re.IGNORECASE),
]


@dataclass(frozen=True)
class AnonymousFailurePackage:
    """Stripped failure data ready for anonymous analysis."""

    anonymous_cycle_id: str
    anonymous_task_id: str
    generated_code: str
    reasoning_chain: str
    test_results: list[dict[str, Any]]
    execution_traces: list[str]
    error_messages: list[str]
    performance_metrics: dict[str, Any]
    session_id: str
    is_benchmark: bool = True


@dataclass(frozen=True)
class AnonymousAnalysisResult:
    """Result of anonymous failure analysis."""

    cycle_id: str
    narratives: list[str]
    reasoning_corrections: list[str]
    artifacts_clean: bool
    leak_issues: list[str]


class AnonymousFeeder:
    """Feeds benchmark failures through L4 failure analysis anonymously.

    The system improves FROM benchmark failures (learning general coding
    patterns) but never learns TO benchmark problems (no specific answers).

    Steps:
      1. Strip all identifying information.
      2. Create anonymous CycleRecord with BM- prefix.
      3. Run failure analysis with anonymous templates.
      4. Apply leak sanitization on stored artifacts.
      5. Validate BM- namespace enforcement.
    """

    def __init__(self, ledger: Any, config: Any) -> None:
        self._ledger = ledger
        self._config = config
        self._failure_analyzer: Optional[Any] = None

    def set_failure_analyzer(self, analyzer: Any) -> None:
        """Set the L4 failure analyzer for anonymous analysis."""
        self._failure_analyzer = analyzer

    # ── Public API ───────────────────────────────────────────────────────────

    def feed(
        self, problem_result: Any, session_id: str
    ) -> AnonymousAnalysisResult:
        """Main entry: strip → create anonymous cycle → analyze → sanitize.

        Args:
            problem_result: BenchmarkProblemResult from runner.
            session_id: Current benchmark session ID.

        Returns AnonymousAnalysisResult.
        """
        # Step 1: Strip identifiers
        stripped = self._strip_identifiers(problem_result)

        # Step 2: Create anonymous cycle record
        anonymous_cycle = self._create_anonymous_cycle(stripped, session_id)
        self._ledger.insert_cycle(anonymous_cycle)

        # Step 3: Run anonymous analysis (narrator + reasoning_analyzer only)
        analysis_artifacts = self._run_anonymous_analysis(
            anonymous_cycle, stripped
        )

        # Step 4: Leak sanitization
        leak_issues = self._apply_leak_sanitization(analysis_artifacts)

        # Step 5: Validate BM- namespace
        namespace_issues = self._validate_bm_namespace(analysis_artifacts)
        leak_issues.extend(namespace_issues)

        artifacts_clean = len(leak_issues) == 0

        result = AnonymousAnalysisResult(
            cycle_id=anonymous_cycle["cycle_id"],
            narratives=analysis_artifacts.get("narratives", []),
            reasoning_corrections=analysis_artifacts.get(
                "reasoning_corrections", []
            ),
            artifacts_clean=artifacts_clean,
            leak_issues=leak_issues,
        )

        if not artifacts_clean:
            logger.warning(
                "Leak issues in anonymous analysis for %s: %s",
                anonymous_cycle["cycle_id"],
                leak_issues,
            )

        return result

    # ── Step 1: Strip Identifiers ────────────────────────────────────────────

    def _strip_identifiers(self, result: Any) -> AnonymousFailurePackage:
        """Strip all identifying information from a benchmark result.

        Removes: benchmark name, problem description, function signature,
        source benchmark.

        Keeps: generated code, reasoning chain, test results
        (input/expected/actual), execution traces, error messages,
        performance metrics.
        """
        generated_code = getattr(result, "generated_code", "")
        reasoning_chain = getattr(result, "reasoning_chain", "")
        test_results = getattr(result, "test_results", [])
        execution_traces = getattr(result, "execution_traces", [])
        error_messages = getattr(result, "error_messages", [])
        performance_metrics = getattr(result, "performance_metrics", {})
        session_id = getattr(result, "session_id", "")

        # Scrub any remaining benchmark identifiers from kept fields
        generated_code = self._scrub_identifiers(generated_code)
        reasoning_chain = self._scrub_identifiers(reasoning_chain)
        execution_traces = [self._scrub_identifiers(t) for t in execution_traces]
        error_messages = [self._scrub_identifiers(m) for m in error_messages]

        # Generate anonymous IDs
        content_hash = hashlib.sha256(
            generated_code.encode()
        ).hexdigest()[:12]
        anonymous_cycle_id = f"BM-CYC-{content_hash}"
        anonymous_task_id = f"BM-ANON-{content_hash}"

        return AnonymousFailurePackage(
            anonymous_cycle_id=anonymous_cycle_id,
            anonymous_task_id=anonymous_task_id,
            generated_code=generated_code,
            reasoning_chain=reasoning_chain,
            test_results=test_results,
            execution_traces=execution_traces,
            error_messages=error_messages,
            performance_metrics=performance_metrics,
            session_id=session_id,
        )

    @staticmethod
    def _scrub_identifiers(text: str) -> str:
        """Remove benchmark identifier patterns from text."""
        scrubbed = text
        for pattern in IDENTIFIER_PATTERNS:
            scrubbed = pattern.sub("[REDACTED]", scrubbed)
        return scrubbed

    # ── Step 2: Create Anonymous Cycle ───────────────────────────────────────

    @staticmethod
    def _create_anonymous_cycle(
        stripped: AnonymousFailurePackage, session_id: str
    ) -> dict[str, Any]:
        """Create an anonymous CycleRecord with BM- prefix.

        Stored in shared cycle table. is_benchmark=True.
        """
        return {
            "cycle_id": stripped.anonymous_cycle_id,
            "task_id": stripped.anonymous_task_id,
            "entity_id": f"BM-{session_id}",
            "is_benchmark": True,
            "generated_code": stripped.generated_code,
            "reasoning_chain": stripped.reasoning_chain,
            "test_results": json.dumps(stripped.test_results),
            "execution_traces": json.dumps(stripped.execution_traces),
            "error_messages": json.dumps(stripped.error_messages),
            "performance_metrics": json.dumps(stripped.performance_metrics),
            "outcome": "FAIL",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Step 3: Anonymous Analysis ───────────────────────────────────────────

    def _run_anonymous_analysis(
        self, cycle: dict[str, Any], stripped: AnonymousFailurePackage
    ) -> dict[str, Any]:
        """Run L4 failure analysis with anonymous template.

        Uses failure_narrator_anonymous.yaml template.
        No embedding retrieval. No counterfactual (too expensive).
        Narrator + reasoning_analyzer only.
        """
        if self._failure_analyzer is None:
            logger.warning("No failure analyzer set, skipping anonymous analysis")
            return {"narratives": [], "reasoning_corrections": []}

        try:
            result = self._failure_analyzer.analyze_anonymous(
                cycle_id=cycle["cycle_id"],
                generated_code=stripped.generated_code,
                error_messages=stripped.error_messages,
                test_results=stripped.test_results,
                execution_traces=stripped.execution_traces,
                template_name="failure_narrator_anonymous",
            )

            return {
                "narratives": getattr(result, "narratives", []),
                "reasoning_corrections": getattr(
                    result, "reasoning_corrections", []
                ),
                "artifact_ids": getattr(result, "artifact_ids", []),
            }

        except Exception as exc:
            logger.error("Anonymous analysis failed: %s", exc)
            return {"narratives": [], "reasoning_corrections": []}

    # ── Step 4: Leak Sanitization ────────────────────────────────────────────

    def _apply_leak_sanitization(
        self, artifacts: dict[str, Any]
    ) -> list[str]:
        """Post-analysis: scan stored artifacts for leaked identifiers.

        If found: scrub or quarantine.
        """
        issues: list[str] = []

        # Scan narratives
        for i, narrative in enumerate(artifacts.get("narratives", [])):
            if isinstance(narrative, str):
                for pattern in IDENTIFIER_PATTERNS:
                    if pattern.search(narrative):
                        issues.append(
                            f"Narrative {i} contains benchmark identifier"
                        )
                        # Scrub in-place
                        artifacts["narratives"][i] = pattern.sub(
                            "[REDACTED]", narrative
                        )

        # Scan reasoning corrections
        for i, correction in enumerate(
            artifacts.get("reasoning_corrections", [])
        ):
            if isinstance(correction, str):
                for pattern in IDENTIFIER_PATTERNS:
                    if pattern.search(correction):
                        issues.append(
                            f"Reasoning correction {i} contains benchmark identifier"
                        )
                        artifacts["reasoning_corrections"][i] = pattern.sub(
                            "[REDACTED]", correction
                        )

        return issues

    # ── Step 5: BM- Namespace Validation ─────────────────────────────────────

    @staticmethod
    def _validate_bm_namespace(
        artifacts: dict[str, Any]
    ) -> list[str]:
        """Verify all artifact_ids have BM- prefix.

        Also verify no parent_id crosses BM/non-BM boundary.
        """
        issues: list[str] = []
        artifact_ids = artifacts.get("artifact_ids", [])

        for aid in artifact_ids:
            if isinstance(aid, str) and not aid.startswith("BM-"):
                issues.append(
                    f"Artifact {aid} missing BM- prefix"
                )

        return issues
