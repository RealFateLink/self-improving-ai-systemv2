"""Layer 6 — Merger.

Compatibility analysis, pattern merging, Beta distribution combining,
and competition-based merge triggers. Handles agent-to-agent merging
where the absorber receives the donor's knowledge.
~260 lines | Category: AGENT_SYSTEM
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MergeCompatibilityReport:
    """Analysis of two agents' compatibility for merging."""

    agent_a_id: str
    agent_b_id: str
    skill_overlap: float         # 0.0–1.0, fraction of shared skills
    beta_alignment: float        # 0.0–1.0, how similar their distributions are
    pattern_intersection: int    # Number of shared patterns
    communication_score: float   # Historical communication value between them
    recommended_absorber: str    # Which agent should be the absorber
    compatible: bool
    rationale: str


@dataclass(frozen=True)
class MergeResult:
    """Result of a merge operation."""

    success: bool
    absorber_id: str
    donor_id: str
    patterns_merged: int
    rules_imported: int
    betas_combined: int
    error: Optional[str] = None


@dataclass(frozen=True)
class MergeAction:
    """Proposed merge action for approval queue."""

    absorber_id: str
    donor_id: str
    compatibility_report: MergeCompatibilityReport
    proposed_at: str
    competition_evidence: dict[str, Any] = field(default_factory=dict)


class Merger:
    """Handles agent merging: compatibility analysis and knowledge transfer.

    When two agents consistently outperform each other on complementary
    skills, they can be merged. The absorber receives the donor's
    knowledge (patterns, Beta distributions, predictor rules). The
    donor is dissolved after merge.
    """

    def __init__(self, ledger: Any, config: Any) -> None:
        self._ledger = ledger
        self._config = config

    # ── Public API ───────────────────────────────────────────────────────────

    def check_merge_trigger(
        self,
        competitions: list[Any],
        agents: list[Any],
    ) -> list[MergeAction]:
        """Analyze competition results and propose merges.

        Every 500 cycles: if two agents consistently outperform each other
        on complementary skills, propose a merge.

        Returns list of MergeAction proposals for the approval queue.
        """
        proposals: list[MergeAction] = []
        checked_pairs: set[tuple[str, str]] = set()

        for agent_a in agents:
            for agent_b in agents:
                a_id = getattr(agent_a, "agent_id", "")
                b_id = getattr(agent_b, "agent_id", "")

                if a_id >= b_id:
                    continue  # Avoid duplicate pairs and self-compare

                pair = (a_id, b_id)
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)

                # Check complementary performance
                evidence = self._analyze_competition_pair(a_id, b_id, competitions)
                if evidence is None:
                    continue

                # Only propose if both are ACTIVE
                a_state = getattr(agent_a, "lifecycle_state", "")
                b_state = getattr(agent_b, "lifecycle_state", "")
                if a_state != "ACTIVE" or b_state != "ACTIVE":
                    continue

                report = self.analyze_compatibility(agent_a, agent_b)
                if not report.compatible:
                    continue

                proposals.append(
                    MergeAction(
                        absorber_id=report.recommended_absorber,
                        donor_id=(
                            b_id if report.recommended_absorber == a_id else a_id
                        ),
                        compatibility_report=report,
                        proposed_at=datetime.now(timezone.utc).isoformat(),
                        competition_evidence=evidence,
                    )
                )

        if proposals:
            logger.info("Proposed %d agent merges", len(proposals))

        return proposals

    def analyze_compatibility(
        self, agent_a: Any, agent_b: Any
    ) -> MergeCompatibilityReport:
        """Produce compatibility report for two agents.

        Evaluates: skill overlap, Beta distribution alignment,
        pattern library intersection, communication history.
        """
        a_id = getattr(agent_a, "agent_id", "")
        b_id = getattr(agent_b, "agent_id", "")

        # Skill overlap
        a_skills = set(getattr(agent_a, "skill_cluster", ()))
        b_skills = set(getattr(agent_b, "skill_cluster", ()))
        union = a_skills | b_skills
        intersection = a_skills & b_skills
        skill_overlap = len(intersection) / len(union) if union else 0.0

        # Beta distribution alignment
        beta_alignment = self._compute_beta_alignment(a_id, b_id)

        # Pattern intersection
        pattern_intersection = self._count_shared_patterns(a_id, b_id)

        # Communication history
        comm_score = self._get_communication_score(a_id, b_id)

        # Determine recommended absorber (higher-performing agent absorbs)
        a_rate = self._ledger.get_agent_pass_rate(a_id)
        b_rate = self._ledger.get_agent_pass_rate(b_id)
        recommended_absorber = a_id if a_rate >= b_rate else b_id

        # Compatibility decision
        min_overlap = getattr(self._config, "merge_min_skill_overlap", 0.1)
        max_overlap = getattr(self._config, "merge_max_skill_overlap", 0.7)
        compatible = min_overlap <= skill_overlap <= max_overlap

        rationale = self._build_compatibility_rationale(
            skill_overlap, beta_alignment, pattern_intersection,
            comm_score, compatible,
        )

        return MergeCompatibilityReport(
            agent_a_id=a_id,
            agent_b_id=b_id,
            skill_overlap=skill_overlap,
            beta_alignment=beta_alignment,
            pattern_intersection=pattern_intersection,
            communication_score=comm_score,
            recommended_absorber=recommended_absorber,
            compatible=compatible,
            rationale=rationale,
        )

    def execute_merge(
        self, report: MergeCompatibilityReport, absorber_id: str, donor_id: str
    ) -> MergeResult:
        """Execute the merge: absorber receives donor's knowledge.

        CRITICAL: Re-checks both agents are ACTIVE before proceeding.
        Race condition guard: first merge transitions donor to MERGING;
        a second concurrent merge attempt finds donor in MERGING and aborts.

        Steps:
          1. Re-verify both ACTIVE.
          2. Transition donor to MERGING.
          3. Combine Beta distributions.
          4. Merge patterns via embedding dedup.
          5. Import predictor rules at 50% confidence.
          6. Transition donor to DISSOLVING.

        Returns MergeResult.
        """
        try:
            # Race condition guard: re-check both ACTIVE
            absorber_state = self._ledger.get_agent_state(absorber_id)
            donor_state = self._ledger.get_agent_state(donor_id)

            if absorber_state != "ACTIVE":
                return MergeResult(
                    success=False,
                    absorber_id=absorber_id,
                    donor_id=donor_id,
                    patterns_merged=0,
                    rules_imported=0,
                    betas_combined=0,
                    error=f"Absorber {absorber_id} not ACTIVE (state: {absorber_state})",
                )

            if donor_state != "ACTIVE":
                return MergeResult(
                    success=False,
                    absorber_id=absorber_id,
                    donor_id=donor_id,
                    patterns_merged=0,
                    rules_imported=0,
                    betas_combined=0,
                    error=f"Donor {donor_id} not ACTIVE (state: {donor_state})",
                )

            # Transition donor to MERGING (prevents double-merge race)
            self._ledger.update_agent_registry_state(donor_id, "MERGING")

            # Combine Beta distributions
            betas_combined = self._combine_all_betas(absorber_id, donor_id)

            # Merge patterns
            donor_patterns = self._ledger.get_agent_patterns(donor_id)
            patterns_merged = self._merge_patterns(absorber_id, donor_patterns)

            # Import predictor rules at 50% confidence
            donor_rules = self._ledger.get_agent_prediction_rules(donor_id)
            rules_imported = self._merge_predictor_rules(absorber_id, donor_rules)

            # Transition donor to DISSOLVING
            self._ledger.update_agent_registry_state(donor_id, "DISSOLVING")

            logger.info(
                "Merged %s into %s: %d betas, %d patterns, %d rules",
                donor_id,
                absorber_id,
                betas_combined,
                patterns_merged,
                rules_imported,
            )

            return MergeResult(
                success=True,
                absorber_id=absorber_id,
                donor_id=donor_id,
                patterns_merged=patterns_merged,
                rules_imported=rules_imported,
                betas_combined=betas_combined,
            )

        except Exception as exc:
            logger.error("Merge failed %s → %s: %s", donor_id, absorber_id, exc)
            # Attempt to revert donor state if merge failed mid-way
            try:
                self._ledger.update_agent_registry_state(donor_id, "ACTIVE")
            except Exception:
                logger.error("Failed to revert donor %s state", donor_id)

            return MergeResult(
                success=False,
                absorber_id=absorber_id,
                donor_id=donor_id,
                patterns_merged=0,
                rules_imported=0,
                betas_combined=0,
                error=str(exc),
            )

    # ── Internal Helpers ─────────────────────────────────────────────────────

    def _analyze_competition_pair(
        self,
        a_id: str,
        b_id: str,
        competitions: list[Any],
    ) -> Optional[dict[str, Any]]:
        """Analyze competition results between two agents.

        Returns evidence dict if they show complementary strengths,
        None if no merge signal.
        """
        a_wins_skills: set[str] = set()
        b_wins_skills: set[str] = set()

        for comp in competitions:
            entities = getattr(comp, "entities", ())
            if a_id not in entities or b_id not in entities:
                continue

            winner = getattr(comp, "winner_id", "")
            skill = getattr(comp, "skill_tag", "")

            if winner == a_id:
                a_wins_skills.add(skill)
            elif winner == b_id:
                b_wins_skills.add(skill)

        # Complementary: each wins on different skills
        min_complementary = getattr(self._config, "merge_min_complementary_skills", 2)
        if len(a_wins_skills) >= min_complementary and len(b_wins_skills) >= min_complementary:
            return {
                "a_wins": list(a_wins_skills),
                "b_wins": list(b_wins_skills),
                "complementary_count": len(a_wins_skills) + len(b_wins_skills),
            }

        return None

    def _combine_all_betas(self, absorber_id: str, donor_id: str) -> int:
        """Combine Beta distributions from donor into absorber.

        Algorithm: new_alpha = alpha1 + alpha2, new_beta = beta1 + beta2.
        Preserves evidence from both agents.
        """
        absorber_betas = self._ledger.get_agent_beta_weights(absorber_id)
        donor_betas = self._ledger.get_agent_beta_weights(donor_id)

        combined = self._combine_betas(absorber_betas, donor_betas)

        count = 0
        for skill, params in combined.items():
            self._ledger.update_agent_beta_weight(absorber_id, skill, params)
            count += 1

        return count

    @staticmethod
    def _combine_betas(
        absorber_betas: dict[str, Any],
        donor_betas: dict[str, Any],
    ) -> dict[str, Any]:
        """Combine Beta distributions: new_a = a1+a2, new_b = b1+b2."""
        combined: dict[str, Any] = {}

        all_skills = set(absorber_betas.keys()) | set(donor_betas.keys())
        for skill in all_skills:
            a_params = absorber_betas.get(skill, {"alpha": 1.0, "beta": 1.0})
            d_params = donor_betas.get(skill, {"alpha": 1.0, "beta": 1.0})

            combined[skill] = {
                "alpha": a_params.get("alpha", 1.0) + d_params.get("alpha", 1.0),
                "beta": a_params.get("beta", 1.0) + d_params.get("beta", 1.0),
            }

        return combined

    def _merge_patterns(
        self, absorber_id: str, donor_patterns: list[Any]
    ) -> int:
        """Add donor patterns to shared library with embedding-based dedup."""
        merged = 0
        for pattern in donor_patterns:
            pattern_text = getattr(pattern, "description", "")
            # Embedding dedup: check for >0.95 similarity
            similar = self._ledger.search_similar(pattern_text, threshold=0.95, limit=1)
            if similar:
                continue  # Duplicate, skip

            self._ledger.add_pattern(
                entity_id=absorber_id,
                pattern=pattern,
            )
            merged += 1

        return merged

    def _merge_predictor_rules(
        self, absorber_id: str, donor_rules: list[Any]
    ) -> int:
        """Import donor's prediction rules at 50% confidence.

        Recalibrated confidence: new context may differ from donor's.
        """
        imported = 0
        for rule in donor_rules:
            original_confidence = getattr(rule, "confidence", 1.0)
            recalibrated_confidence = original_confidence * 0.5

            self._ledger.insert_agent_prediction_rule(
                absorber_id,
                rule,
                confidence_override=recalibrated_confidence,
            )
            imported += 1

        return imported

    def _compute_beta_alignment(self, a_id: str, b_id: str) -> float:
        """Compute how aligned two agents' Beta distributions are.

        Uses KL divergence approximation; returns 0.0–1.0 where
        1.0 means identical distributions.
        """
        a_betas = self._ledger.get_agent_beta_weights(a_id)
        b_betas = self._ledger.get_agent_beta_weights(b_id)

        if not a_betas or not b_betas:
            return 0.0

        shared_skills = set(a_betas.keys()) & set(b_betas.keys())
        if not shared_skills:
            return 0.0

        total_alignment = 0.0
        for skill in shared_skills:
            a_alpha = a_betas[skill].get("alpha", 1.0)
            a_beta = a_betas[skill].get("beta", 1.0)
            b_alpha = b_betas[skill].get("alpha", 1.0)
            b_beta = b_betas[skill].get("beta", 1.0)

            # Simple mean comparison as alignment proxy
            a_mean = a_alpha / (a_alpha + a_beta) if (a_alpha + a_beta) > 0 else 0.5
            b_mean = b_alpha / (b_alpha + b_beta) if (b_alpha + b_beta) > 0 else 0.5

            # Alignment: 1 - |difference|
            total_alignment += 1.0 - abs(a_mean - b_mean)

        return total_alignment / len(shared_skills)

    def _count_shared_patterns(self, a_id: str, b_id: str) -> int:
        """Count patterns shared between two agents in the pattern library."""
        a_patterns = set(
            getattr(p, "pattern_id", "")
            for p in self._ledger.get_agent_patterns(a_id)
        )
        b_patterns = set(
            getattr(p, "pattern_id", "")
            for p in self._ledger.get_agent_patterns(b_id)
        )
        return len(a_patterns & b_patterns)

    def _get_communication_score(self, a_id: str, b_id: str) -> float:
        """Get communication value score between two agents."""
        score = self._ledger.get_communication_value_score(a_id, b_id)
        if score is None:
            return 0.0
        return getattr(score, "help_rate", 0.0)

    @staticmethod
    def _build_compatibility_rationale(
        skill_overlap: float,
        beta_alignment: float,
        pattern_intersection: int,
        comm_score: float,
        compatible: bool,
    ) -> str:
        """Build human-readable compatibility rationale."""
        status = "COMPATIBLE" if compatible else "INCOMPATIBLE"
        return (
            f"{status}: skill_overlap={skill_overlap:.2f}, "
            f"beta_alignment={beta_alignment:.2f}, "
            f"shared_patterns={pattern_intersection}, "
            f"comm_value={comm_score:.2f}"
        )
