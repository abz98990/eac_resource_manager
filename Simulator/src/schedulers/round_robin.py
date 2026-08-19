"""Static baseline: fixed rotation, no load awareness, no migration."""

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
