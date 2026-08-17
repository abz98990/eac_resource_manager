"""
The Rule-Based Constraint Engine ("Green Heuristic") — IPR S3.2 / S4.1's
novel contribution. Three rules:

1. Power Sweet Spot     - never *choose* to place a task on a node if doing
                           so would push it over the 85% redline threshold;
                           among safe options, prefer landing in the 40-75%
                           efficiency band.
2. Anti-Thrashing Filter - a node must be over the redline threshold for
                           >= 3 consecutive rebalance checks before it is
                           treated as persistently hot and considered for
                           migration (ignores short-lived micro-bursts).
3. SLA Migration Lock    - a migration is only carried out if its overhead
                           fits inside the task's remaining SLA slack;
                           otherwise the migration is skipped, never the SLA.
"""

from __future__ import annotations

from ..power_model import REDLINE_THRESHOLD_PCT

PREFERRED_LOW_PCT = 40.0
PREFERRED_HIGH_PCT = 75.0
PREFERRED_MID_PCT = (PREFERRED_LOW_PCT + PREFERRED_HIGH_PCT) / 2.0
BAND_TIEBREAK_BONUS_PCT = 8.0  # max pct-points an in-band node may trail an idle one and still win

ANTI_THRASH_STREAK = 3  # consecutive hot checks required before a node is "persistently hot"
MIGRATION_COST_PER_PCT_MIN = 0.15  # simulated minutes of migration overhead per % CPU moved


class GreenHeuristicScheduler:
    name = "Green Heuristic (Rule-Based Constraint Engine)"

    def __init__(self, num_nodes: int, migration_cost_per_pct_min: float = MIGRATION_COST_PER_PCT_MIN):
        self.num_nodes = num_nodes
        self.migration_cost_per_pct_min = migration_cost_per_pct_min
        self._hot_streak = [0] * num_nodes
        # evidence counters, inspected by metrics/report generation
        self.stats = {
            "redline_admissions": 0,   # placements forced above the sweet-spot ceiling
            "migrations_attempted": 0,
            "migrations_completed": 0,
            "migrations_blocked_by_sla_lock": 0,
        }

    # --- initial placement -------------------------------------------------
    def choose_node(self, task, nodes, now: float) -> int:
        demand = task.cpu_demand_pct
        eligible = [n for n in nodes if n.used_pct + demand <= REDLINE_THRESHOLD_PCT]

        if not eligible:
            # Every node would breach the sweet spot: best-effort admission
            # onto the least-loaded node rather than dropping the task.
            self.stats["redline_admissions"] += 1
            return min(nodes, key=lambda n: n.used_pct).node_id

        def score(n):
            # Minimize resulting load (spreads risk, avoids queueing) but give
            # a small discount to nodes that land in the 40-75% efficiency
            # band, so it only wins close calls rather than overriding a
            # clearly-better idle node (that inflated queueing latency badly
            # in testing — see DEVLOG 2026-08-17).
            resulting = n.used_pct + demand
            in_band = PREFERRED_LOW_PCT <= resulting <= PREFERRED_HIGH_PCT
            return resulting - (BAND_TIEBREAK_BONUS_PCT if in_band else 0.0)

        return min(eligible, key=score).node_id

    # --- periodic rebalancing / migration -----------------------------------
    def rebalance(self, datacenter, now: float) -> None:
        for node in datacenter.nodes:
            if node.used_pct > REDLINE_THRESHOLD_PCT:
                self._hot_streak[node.node_id] += 1
            else:
                self._hot_streak[node.node_id] = 0

        for node in datacenter.nodes:
            if self._hot_streak[node.node_id] < ANTI_THRASH_STREAK:
                continue  # Anti-Thrashing Filter: not persistently hot yet

            candidates = sorted(
                (r for r in datacenter.running[node.node_id] if not r.migrating),
                key=lambda r: r.task.cpu_demand_pct,
            )
            for record in candidates:
                if self._try_migrate(datacenter, record, node, now):
                    self._hot_streak[node.node_id] = 0
                    break

    def _try_migrate(self, datacenter, record, source_node, now: float) -> bool:
        demand = record.task.cpu_demand_pct
        migration_cost = self.migration_cost_per_pct_min * demand
        remaining_slack = record.task.latency_sla_min - record.queue_wait_min

        self.stats["migrations_attempted"] += 1
        if migration_cost > remaining_slack:
            # Strict SLA Migration Lock: never trade throughput for power savings.
            self.stats["migrations_blocked_by_sla_lock"] += 1
            return False

        targets = [
            n for n in datacenter.nodes
            if n.node_id != source_node.node_id and n.used_pct + demand <= PREFERRED_HIGH_PCT
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
