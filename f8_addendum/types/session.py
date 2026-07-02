"""F8 Addendum — A-6: Session-Stable Config Latching.

Latched config fields that stabilize the prompt between sessions.
Live state changes normally for internal logic; prompt construction
reads from LATCHED values to avoid cache busting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionConfig:
    """Session-stable latched configuration.

    Behavior: Live state (economy_mode_active, current_track, etc.)
    still changes normally for internal logic. Prompt CONSTRUCTION
    reads from LATCHED values, not live state.

    Tradeoff: ~50K tokens cache savings per cycle at cost of slightly
    stale prompt context until next session.

    Latch reset triggers: session end, operator /reset, compaction
    (new session starts). Matches Claude Code's clearBetaHeaderLatches().
    """

    economy_mode_latched: Optional[bool] = None
    """Set when: economy mode first activates.
    Cleared: session end or operator /reset.
    Why: prompt includes economy skip list; toggling changes prompt → cache bust."""

    active_track_latched: Optional[str] = None
    """Set when: track first selected for session.
    Cleared: session end.
    Why: track context in Zone 1 (static); mid-session switch busts cache."""

    agent_set_latched: Optional[frozenset[str]] = None
    """Set when: agent schemas first sent to API.
    Cleared: session end.
    Why: tool schemas in cached prefix; add/remove agents busts cache."""

    pattern_library_hash: Optional[str] = None
    """Set when: pattern set first sent.
    Cleared: session end.
    Why: sorted pattern list in Zone 1; adding pattern changes sort → cache bust."""

    _latched: bool = False

    def latch_if_first_send(
        self,
        economy_mode: bool,
        active_track: str,
        agent_ids: frozenset[str],
        pattern_hash: str,
    ) -> None:
        """Latch current values on first API send.

        Only latches if not already latched. Subsequent calls are no-ops
        until reset() is called.
        """
        if self._latched:
            return

        self.economy_mode_latched = economy_mode
        self.active_track_latched = active_track
        self.agent_set_latched = agent_ids
        self.pattern_library_hash = pattern_hash
        self._latched = True

    def reset(self) -> None:
        """Reset all latched values (session end, /reset, compaction)."""
        self.economy_mode_latched = None
        self.active_track_latched = None
        self.agent_set_latched = None
        self.pattern_library_hash = None
        self._latched = False

    @property
    def is_latched(self) -> bool:
        return self._latched
