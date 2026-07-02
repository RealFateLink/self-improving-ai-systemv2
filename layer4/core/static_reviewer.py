"""static_reviewer.py — Runs lint, type checks, checklist rules.

Stage 5.  Emits review confidence.
batch mode MUST be a semantic wrapper over the single-call path
(batch/single parity required).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["StaticReviewer", "ReviewResult"]


@dataclass(frozen=True)
class ReviewFinding:
    """A single review finding."""
    category: str     # lint | type_check | checklist | style
    severity: str     # error | warning | info
    message: str
    line: int | None = None
    rule: str = ""


@dataclass(frozen=True)
class ReviewResult:
    """Aggregate review for a candidate."""
    candidate_id: str
    findings: tuple[ReviewFinding, ...]
    passed: bool
    confidence: float  # 0.0–1.0
    confidence_basis: str = ""

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")


@dataclass
class StaticReviewer:
    """Performs static analysis on code candidates.

    Reviews include: lint checks, type checking, checklist rules, style.
    """

    config: dict[str, Any] = field(default_factory=dict)
    checklist_rules: list[dict[str, Any]] = field(default_factory=list)

    def review(
        self,
        candidate: Any,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Review a single candidate.

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        from .intent_interpreter import ModuleResult, ModuleError

        try:
            code = getattr(candidate, "code", "")
            cid = getattr(candidate, "candidate_id", "unknown")
            language = candidate.metadata.get("language", "python") if hasattr(candidate, "metadata") else "python"

            findings: list[ReviewFinding] = []

            # Lint checks.
            findings.extend(self._lint_check(code, language))
            # Type checks.
            findings.extend(self._type_check(code, language))
            # Checklist rules.
            findings.extend(self._checklist_check(code))
            # Style checks.
            findings.extend(self._style_check(code, language))

            errors = sum(1 for f in findings if f.severity == "error")
            passed = errors == 0

            # Confidence: higher when more checks ran successfully.
            check_count = 4  # lint, type, checklist, style
            confidence = min(1.0, 0.5 + len(findings) * 0.05) if passed else max(0.1, 0.5 - errors * 0.1)

            result = ReviewResult(
                candidate_id=cid,
                findings=tuple(findings),
                passed=passed,
                confidence=confidence,
                confidence_basis=f"{len(findings)} findings from {check_count} check categories",
            )

            return True, ModuleResult(primary=result)

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Static review failed: {exc}",
                is_retryable=True,
            )

    def review_batch(
        self,
        candidates: list[Any],
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Batch review — semantic wrapper over single-call path.

        Batch/single parity: identical results regardless of call path.
        """
        from .intent_interpreter import ModuleResult, ModuleError

        results: list[ReviewResult] = []
        all_warnings: list[dict[str, Any]] = []

        for candidate in candidates:
            ok, result = self.review(candidate, cycle_context)
            if ok:
                results.append(result.primary)
                all_warnings.extend(result.warnings)
            else:
                # Partial failure — record but continue.
                all_warnings.append({
                    "type": "REVIEW_PARTIAL_FAILURE",
                    "severity": "CAUTION",
                    "message": f"Review failed for candidate {getattr(candidate, 'candidate_id', '?')}",
                })

        return True, ModuleResult(
            primary=results,
            warnings=all_warnings,
        )

    # ── Check implementations ────────────────────────────────────────────────

    def _lint_check(self, code: str, language: str) -> list[ReviewFinding]:
        """Basic lint checks."""
        findings = []
        if language == "python":
            # Check for common issues.
            import ast
            try:
                ast.parse(code)
            except SyntaxError as e:
                findings.append(ReviewFinding(
                    category="lint", severity="error",
                    message=f"Syntax error: {e.msg}",
                    line=e.lineno, rule="syntax",
                ))

            lines = code.split("\n")
            for i, line in enumerate(lines, 1):
                if len(line) > 120:
                    findings.append(ReviewFinding(
                        category="lint", severity="warning",
                        message=f"Line too long ({len(line)} > 120 chars)",
                        line=i, rule="line_length",
                    ))
                if "\t" in line and "    " in line:
                    findings.append(ReviewFinding(
                        category="lint", severity="warning",
                        message="Mixed tabs and spaces",
                        line=i, rule="mixed_indent",
                    ))

        return findings

    def _type_check(self, code: str, language: str) -> list[ReviewFinding]:
        """Basic type annotation checks."""
        findings = []
        if language == "python":
            if "def " in code:
                # Check for type hints on function definitions.
                import re
                func_defs = re.findall(r"def\s+\w+\([^)]*\)\s*:", code)
                no_return = re.findall(r"def\s+\w+\([^)]*\)\s*:", code)
                hint_defs = re.findall(r"def\s+\w+\([^)]*\)\s*->", code)
                missing = len(no_return) - len(hint_defs)
                if missing > 0:
                    findings.append(ReviewFinding(
                        category="type_check", severity="info",
                        message=f"{missing} function(s) missing return type hints.",
                        rule="missing_return_type",
                    ))
        return findings

    def _checklist_check(self, code: str) -> list[ReviewFinding]:
        """User-defined checklist rules."""
        findings = []
        for rule in self.checklist_rules:
            pattern = rule.get("pattern", "")
            if pattern and pattern in code:
                findings.append(ReviewFinding(
                    category="checklist",
                    severity=rule.get("severity", "warning"),
                    message=rule.get("message", f"Checklist: found '{pattern}'"),
                    rule=rule.get("name", "custom"),
                ))
        return findings

    def _style_check(self, code: str, language: str) -> list[ReviewFinding]:
        """Style checks."""
        findings = []
        if language == "python":
            if "import *" in code:
                findings.append(ReviewFinding(
                    category="style", severity="warning",
                    message="Wildcard import detected.",
                    rule="no_wildcard_import",
                ))
            if code.count("# TODO") > 3:
                findings.append(ReviewFinding(
                    category="style", severity="info",
                    message=f"Multiple TODOs ({code.count('# TODO')}) — may indicate incomplete implementation.",
                    rule="excess_todos",
                ))
        return findings
