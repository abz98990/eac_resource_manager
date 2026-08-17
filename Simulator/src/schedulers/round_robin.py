"""
The "dumb" static baseline scheduler (IPR S4.1, Development Plan step 1).

Cycles through nodes in fixed order with no awareness of current load. This
is deliberate: it is the control group the Green Heuristic Constraint Engine
is measured against. It never rebalances/migrates running tasks.
"""

from __future__ import annotations


class RoundRobinScheduler:
    name = "Round-Robin (Baseline)"

    def __init__(self, num_nodes: int):
        self._num_nodes = num_nodes
        self._next = 0

    def choose_node(self, task, nodes, now: float) -> int:
        node_id = self._next % self._num_nodes
        self._next += 1
        return node_id
