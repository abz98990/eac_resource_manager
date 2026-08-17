"""Scheduler interface. A scheduler must implement `choose_node`; it may
optionally implement `rebalance` to periodically migrate running tasks
(only meaningful schedulers with load-awareness do this — the baseline
Round-Robin scheduler deliberately does not)."""

from __future__ import annotations

from typing import Protocol


class Scheduler(Protocol):
    name: str

    def choose_node(self, task, nodes, now: float) -> int:
        """Return the node_id to place `task` on at simulated time `now`."""
        ...
