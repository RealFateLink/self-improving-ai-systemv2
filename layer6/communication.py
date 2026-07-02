"""Layer 6 — Communication.

Inter-agent messaging system: help requests, pattern sharing, status
broadcasts, guidance, and review messages. Rate limiting per pair.
Value tracking for adaptive rate limits.
~260 lines | Category: AGENT_SYSTEM
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MessageType(StrEnum):
    """Types of inter-agent messages."""

    HELP_REQUEST = "HELP_REQUEST"      # Agent → any entity; struggling on task
    PATTERN_SHARE = "PATTERN_SHARE"    # Agent → relevant entities; discovered pattern
    STATUS_UPDATE = "STATUS_UPDATE"    # Broadcast; health, graduation, skills
    GUIDANCE = "GUIDANCE"              # Router-initiated → primary; specialist advice
    REVIEW = "REVIEW"                  # Router-initiated → promoter; specialist review


@dataclass(frozen=True)
class AgentMessage:
    """A message between entities."""

    message_id: str
    message_type: MessageType
    from_entity: str
    to_entity: str
    content: dict[str, Any]
    created_at: str
    cycle_number: int
    processed: bool = False
    outcome_recorded: bool = False


@dataclass
class CommunicationValueScore:
    """Tracks the value of communication between a pair of entities."""

    entity_a: str
    entity_b: str
    messages_sent: int = 0
    messages_helped: int = 0
    help_rate: float = 0.0
    last_evaluated_at: Optional[str] = None


@dataclass
class CommunicationPair:
    """Rate limit and value tracking for an entity pair."""

    entity_a: str
    entity_b: str
    messages_this_window: int = 0
    rate_limit: int = 10  # Messages per window
    value_score: CommunicationValueScore = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.value_score is None:
            self.value_score = CommunicationValueScore(
                entity_a=self.entity_a,
                entity_b=self.entity_b,
            )


class Communication:
    """Inter-agent messaging system.

    Handles help requests, pattern sharing, status broadcasts,
    router-initiated guidance and reviews. Enforces rate limits
    per entity pair and tracks communication value for adaptive
    rate limit adjustment.
    """

    def __init__(self, ledger: Any, config: Any) -> None:
        self._ledger = ledger
        self._config = config
        self._pairs: dict[tuple[str, str], CommunicationPair] = {}
        self._default_rate_limit = getattr(config, "default_message_rate_limit", 10)

    # ── Public API ───────────────────────────────────────────────────────────

    def process_messages(self, entity_id: str) -> list[AgentMessage]:
        """Process incoming messages for an entity.

        Called at the start of each agent cycle. Returns list of
        unprocessed messages for this entity, marks them as processed.
        """
        messages = self._ledger.get_unprocessed_messages(entity_id)
        processed: list[AgentMessage] = []

        for msg in messages:
            self._ledger.mark_message_processed(msg.message_id)
            processed.append(msg)

        if processed:
            logger.debug(
                "Entity %s processed %d messages", entity_id, len(processed)
            )

        return processed

    def send_help_request(
        self,
        from_entity: str,
        to_entity: str,
        task: Any,
        context: dict[str, Any],
        cycle_number: int,
    ) -> Optional[AgentMessage]:
        """Send a help request from one entity to another.

        Reactive: agent struggling on task requests help. Rate-limited.
        """
        pair_key = self._normalize_pair(from_entity, to_entity)
        if not self._check_rate_limit(pair_key):
            logger.debug(
                "Help request from %s to %s rate-limited",
                from_entity,
                to_entity,
            )
            return None

        message = AgentMessage(
            message_id=self._generate_message_id(from_entity, cycle_number),
            message_type=MessageType.HELP_REQUEST,
            from_entity=from_entity,
            to_entity=to_entity,
            content={
                "task_id": getattr(task, "task_id", ""),
                "task_skills": getattr(task, "skill_tags", ()),
                "struggling_context": context,
            },
            created_at=datetime.now(timezone.utc).isoformat(),
            cycle_number=cycle_number,
        )

        self._ledger.insert_agent_message(message)
        self._increment_pair_counter(pair_key)
        return message

    def send_pattern_share(
        self,
        from_entity: str,
        pattern: Any,
        relevant_entities: list[str],
        cycle_number: int,
    ) -> list[AgentMessage]:
        """Share a discovered pattern with relevant entities.

        Proactive: agent shares pattern applicable to others.
        """
        messages: list[AgentMessage] = []

        for to_entity in relevant_entities:
            pair_key = self._normalize_pair(from_entity, to_entity)
            if not self._check_rate_limit(pair_key):
                continue

            message = AgentMessage(
                message_id=self._generate_message_id(from_entity, cycle_number),
                message_type=MessageType.PATTERN_SHARE,
                from_entity=from_entity,
                to_entity=to_entity,
                content={
                    "pattern_id": getattr(pattern, "pattern_id", ""),
                    "pattern_type": getattr(pattern, "pattern_type", ""),
                    "applicability_tags": getattr(pattern, "skill_tags", ()),
                    "description": getattr(pattern, "description", ""),
                },
                created_at=datetime.now(timezone.utc).isoformat(),
                cycle_number=cycle_number,
            )

            self._ledger.insert_agent_message(message)
            self._increment_pair_counter(pair_key)
            messages.append(message)

        return messages

    def send_status_updates(
        self, agents: list[Any], cycle_number: int
    ) -> list[AgentMessage]:
        """Periodic broadcast: agent health, graduation level, active skills.

        Informational only — not measured for value.
        """
        messages: list[AgentMessage] = []

        for agent in agents:
            agent_id = getattr(agent, "agent_id", "")
            message = AgentMessage(
                message_id=self._generate_message_id(agent_id, cycle_number),
                message_type=MessageType.STATUS_UPDATE,
                from_entity=agent_id,
                to_entity="BROADCAST",
                content={
                    "agent_id": agent_id,
                    "lifecycle_state": getattr(agent, "lifecycle_state", ""),
                    "graduation_level": getattr(agent, "graduation_level", None),
                    "active_skills": getattr(agent, "skill_cluster", ()),
                    "pass_rate": getattr(agent, "current_pass_rate", 0.0),
                    "allocation_pct": getattr(agent, "allocation_pct", 0.0),
                },
                created_at=datetime.now(timezone.utc).isoformat(),
                cycle_number=cycle_number,
            )

            self._ledger.insert_agent_message(message)
            messages.append(message)

        return messages

    def send_guidance(
        self,
        supporter_id: str,
        primary_id: str,
        guidance_content: dict[str, Any],
        cycle_number: int,
    ) -> AgentMessage:
        """Router-initiated guidance from supporter to primary entity.

        Used in GUIDED and FULL_COLLAB modes.
        """
        message = AgentMessage(
            message_id=self._generate_message_id(supporter_id, cycle_number),
            message_type=MessageType.GUIDANCE,
            from_entity=supporter_id,
            to_entity=primary_id,
            content=guidance_content,
            created_at=datetime.now(timezone.utc).isoformat(),
            cycle_number=cycle_number,
        )

        self._ledger.insert_agent_message(message)
        return message

    def send_review(
        self,
        reviewer_id: str,
        primary_id: str,
        review_content: dict[str, Any],
        cycle_number: int,
    ) -> AgentMessage:
        """Router-initiated review from supporter to primary entity.

        Used in REVIEWED and FULL_COLLAB modes.
        """
        message = AgentMessage(
            message_id=self._generate_message_id(reviewer_id, cycle_number),
            message_type=MessageType.REVIEW,
            from_entity=reviewer_id,
            to_entity=primary_id,
            content=review_content,
            created_at=datetime.now(timezone.utc).isoformat(),
            cycle_number=cycle_number,
        )

        self._ledger.insert_agent_message(message)
        return message

    def track_value(
        self,
        message: AgentMessage,
        outcome_helped: bool,
    ) -> None:
        """Record whether a message helped (pass rate comparison).

        Updates CommunicationValueScore for the pair.
        """
        pair_key = self._normalize_pair(message.from_entity, message.to_entity)
        self._ensure_pair_exists(pair_key)
        pair = self._pairs[pair_key]

        pair.value_score.messages_sent += 1
        if outcome_helped:
            pair.value_score.messages_helped += 1

        if pair.value_score.messages_sent > 0:
            pair.value_score.help_rate = (
                pair.value_score.messages_helped / pair.value_score.messages_sent
            )

        pair.value_score.last_evaluated_at = datetime.now(
            timezone.utc
        ).isoformat()

        self._ledger.update_communication_value_score(pair.value_score)

        self._ledger.mark_message_outcome_recorded(message.message_id)

    def adapt_rate_limits(self, agents: list[Any]) -> None:
        """Adjust per-pair rate limits based on communication value.

        Every 100 cycles: high-value pairs get more bandwidth,
        low-value pairs get reduced limits.
        """
        high_value_multiplier = getattr(
            self._config, "high_value_rate_multiplier", 2.0
        )
        low_value_threshold = getattr(
            self._config, "low_value_help_rate", 0.2
        )
        high_value_threshold = getattr(
            self._config, "high_value_help_rate", 0.6
        )

        for pair_key, pair in self._pairs.items():
            score = pair.value_score
            if score.messages_sent < 5:
                continue  # Not enough data

            if score.help_rate >= high_value_threshold:
                pair.rate_limit = int(
                    self._default_rate_limit * high_value_multiplier
                )
            elif score.help_rate <= low_value_threshold:
                pair.rate_limit = max(
                    2, self._default_rate_limit // 2
                )
            else:
                pair.rate_limit = self._default_rate_limit

        logger.info("Adapted rate limits for %d pairs", len(self._pairs))

    # ── Internal Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _normalize_pair(entity_a: str, entity_b: str) -> tuple[str, str]:
        """Normalize pair to consistent ordering for lookup."""
        return (min(entity_a, entity_b), max(entity_a, entity_b))

    def _ensure_pair_exists(self, pair_key: tuple[str, str]) -> None:
        """Lazy initialization of communication pair on first interaction."""
        if pair_key not in self._pairs:
            self._pairs[pair_key] = CommunicationPair(
                entity_a=pair_key[0],
                entity_b=pair_key[1],
                rate_limit=self._default_rate_limit,
            )

    def _check_rate_limit(self, pair_key: tuple[str, str]) -> bool:
        """Check if the pair is within rate limit."""
        self._ensure_pair_exists(pair_key)
        pair = self._pairs[pair_key]
        return pair.messages_this_window < pair.rate_limit

    def _increment_pair_counter(self, pair_key: tuple[str, str]) -> None:
        """Increment the message counter for a pair."""
        self._ensure_pair_exists(pair_key)
        self._pairs[pair_key].messages_this_window += 1

    def reset_window_counters(self) -> None:
        """Reset message counters for all pairs (called at window boundary)."""
        for pair in self._pairs.values():
            pair.messages_this_window = 0

    @staticmethod
    def _generate_message_id(entity_id: str, cycle_number: int) -> str:
        """Generate a unique message ID."""
        import uuid
        return f"MSG_{entity_id}_{cycle_number}_{uuid.uuid4().hex[:8]}"
