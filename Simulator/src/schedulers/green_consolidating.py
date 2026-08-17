"""
Consolidating Green Heuristic — extends the Rule-Based Constraint Engine
(green_heuristic.py) with a power-down/wake-up mechanism, to test whether
idle-power savings (not just redline avoidance) are reachable without
reintroducing the SLA risk that IPR S2.1 criticises in Beloglazov et al.'s
aggressive VM consolidation.

The key design choice: this scheduler NEVER migrates a running task purely
to consolidate/free up a node. It only powers down a node that has already
gone completely empty on its own (all its tasks finished naturally), and
only wakes a fresh node when no already-on node has headroom. Consolidation
is therefore a strictly zero-disruption, opportunistic side effect of the
existing placement rules — not a competing objective that could touch a
running task's SLA.
"""

from __future__ import annotations

from ..power_model import REDLINE_THRESHOLD_PCT
from .green_heuristic import (
    ANTI_THRASH_STREAK,
    BAND_TIEBREAK_BONUS_PCT,
    MIGRATION_COST_PER_PCT_MIN,
    PREFERRED_HIGH_PCT,
    PREFERRED_LOW_PCT,
)

WAKE_UP_MIN = 3.0  # simulated minutes for a powered-down node to become available
EMPTY_STREAK = 6  # consecutive rebalance ticks a node must sit empty before power-down


class ConsolidatingGreenScheduler:
    name = "Consolidating Green Heuristic"

    def __init__(self, num_nodes: int, migration_cost_per_pct_min: float = MIGRATION_COST_PER_PCT_MIN,
                 wake_up_min: float = WAKE_UP_MIN, empty_streak: int = EMPTY_STREAK):
        self.num_nodes = num_nodes
        self.migration_cost_per_pct_min = migration_cost_per_pct_min
        self.wake_up_min = wake_up_min
        self.empty_streak_threshold = empty_streak
        self._hot_streak = [0] * num_nodes
        self._empty_streak = [0] * num_nodes
        self.stats = {
            "redline_admissions": 0,
            "migrations_attempted": 0,
            "migrations_completed": 0,
            "migrations_blocked_by_sla_lock": 0,
            "nodes_powered_down": 0,
            "nodes_woken": 0,
        }

    # --- initial placement -------------------------------------------------
    def choose_node(self, task, nodes, now: float) -> int:
        demand = task.cpu_demand_pct
        on_nodes = [n for n in nodes if n.powered_on]
        eligible = [n for n in on_nodes if n.used_pct + demand <= REDLINE_THRESHOLD_PCT]

        if eligible:
            return self._score_pick(eligible, demand)

        # No powered-on node has headroom: prefer waking fresh capacity over
        # forcing a redline admission onto an already-hot node.
        off_nodes = [n for n in nodes if not n.powered_on]
        if off_nodes:
            self.stats["nodes_woken"] += 1
            return off_nodes[0].node_id

        self.stats["redline_admissions"] += 1
        return min(on_nodes, key=lambda n: n.used_pct).node_id

    @staticmethod
    def _score_pick(eligible, demand: float) -> int:
        def score(n):
            resulting = n.used_pct + demand
            in_band = PREFERRED_LOW_PCT <= resulting <= PREFERRED_HIGH_PCT
            return resulting - (BAND_TIEBREAK_BONUS_PCT if in_band else 0.0)

        return min(eligible, key=score).node_id

    # --- periodic rebalancing: redline migration + opportunistic power-down --
    def rebalance(self, datacenter, now: float) -> None:
        for node in datacenter.nodes:
            if node.powered_on and node.used_pct > REDLINE_THRESHOLD_PCT:
                self._hot_streak[node.node_id] += 1
            else:
                self._hot_streak[node.node_id] = 0

        for node in datacenter.nodes:
            if not node.powered_on or self._hot_streak[node.node_id] < ANTI_THRASH_STREAK:
                continue
            candidates = sorted(
                (r for r in datacenter.running[node.node_id] if not r.migrating),
                key=lambda r: r.task.cpu_demand_pct,
            )
            for record in candidates:
                if self._try_migrate(datacenter, record, node, now):
                    self._hot_streak[node.node_id] = 0
                    break

        for node in datacenter.nodes:
            if not node.powered_on:
                self._empty_streak[node.node_id] = 0
                continue
            if len(datacenter.running[node.node_id]) == 0:
                self._empty_streak[node.node_id] += 1
            else:
                self._empty_streak[node.node_id] = 0

            if self._empty_streak[node.node_id] >= self.empty_streak_threshold:
                node.powered_on = False
                self._empty_streak[node.node_id] = 0
                self.stats["nodes_powered_down"] += 1

    def _try_migrate(self, datacenter, record, source_node, now: float) -> bool:
        demand = record.task.cpu_demand_pct
        migration_cost = self.migration_cost_per_pct_min * demand
        remaining_slack = record.task.latency_sla_min - record.queue_wait_min

        self.stats["migrations_attempted"] += 1
        if migration_cost > remaining_slack:
            self.stats["migrations_blocked_by_sla_lock"] += 1
            return False

        targets = [
            n for n in datacenter.nodes
            if n.powered_on and n.node_id != source_node.node_id and n.used_pct + demand <= PREFERRED_HIGH_PCT
        ]
        if not targets:
            return False
        target = min(targets, key=lambda n: n.used_pct)

        record.migrating = True
        try:
            record.process.interrupt(target.node_id)
        except RuntimeError:
            record.migrating = False
            return False

        self.stats["migrations_completed"] += 1
        return True
