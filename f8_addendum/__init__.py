"""F8 Addendum — Quality-of-Life Upgrades.

10 cross-cutting improvements derived from Claude Code source review.
All changes are ADDITIVE — no modifications to existing types or methods.
Separate compatible module that works alongside Layers 0-8.

Items:
  A-1: Explicit recovery transitions (6 named paths)
  A-2: Static/dynamic prompt boundary for cache optimization
  A-3: FAIL/PASS/PARTIAL verdict taxonomy
  A-4: Circuit breaker on repeated failures
  A-5: Error cascade isolation
  A-6: Session-stable config latching
  A-7: Concurrent evaluation with deferred state commits
  A-8: Speculative sandbox provisioning
  A-9: Self-correcting error messages
  A-10: Conservative-then-escalate token budgets

~980 lines across types, services, and engine enhancements.
"""
from __future__ import annotations
