"""Scheduler interface.

`choose_node` is required. `rebalance` is optional — the engine only starts
the rebalancing loop for schedulers that define it.
"""

from __future__ import annotations

from typing import Protocol


class Scheduler(Protocol):
    name: str

    def choose_node(self, task, nodes, now: float) -> int:
        ...
