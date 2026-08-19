"""Rule-Based Constraint Engine: sweet-spot placement, anti-thrashing, SLA lock."""

from __future__ import annotations

from ..power_model import REDLINE_THRESHOLD_PCT

PREFERRED_LOW_PCT = 40.0
PREFERRED_HIGH_PCT = 75.0
BAND_TIEBREAK_BONUS_PCT = 8.0

ANTI_THRASH_STREAK = 3
MIGRATION_COST_PER_PCT_MIN = 0.15


class GreenHeuristicScheduler:
    name = "Green Heuristic (Rule-Based Constraint Engine)"

    def __init__(self, num_nodes: int, migration_cost_per_pct_min: float = MIGRATION_COST_PER_PCT_MIN):
        self.num_nodes = num_nodes
        self.migration_cost_per_pct_min = migration_cost_per_pct_min
        self._hot_streak = [0] * num_nodes
        self.stats = {
            "redline_admissions": 0,
            "migrations_attempted": 0,
            "migrations_completed": 0,
            "migrations_blocked_by_sla_lock": 0,
        }

    def choose_node(self, task, nodes, now: float) -> int:
        demand = task.cpu_demand_pct
        eligible = [n for n in nodes if n.used_pct + demand <= REDLINE_THRESHOLD_PCT]

        if not eligible:
            # Nothing has headroom, so take the least-loaded node rather than
            # drop the task.
            self.stats["redline_admissions"] += 1
            return min(nodes, key=lambda n: n.used_pct).node_id

        def score(n):
            # Prefer the least-loaded node, with a small discount for landing
            # in the efficiency band. Making the band strictly win instead
            # piles work onto warm nodes and wrecks queueing latency.
            resulting = n.used_pct + demand
            in_band = PREFERRED_LOW_PCT <= resulting <= PREFERRED_HIGH_PCT
            return resulting - (BAND_TIEBREAK_BONUS_PCT if in_band else 0.0)

        return min(eligible, key=score).node_id

    def rebalance(self, datacenter, now: float) -> None:
        for node in datacenter.nodes:
            if node.used_pct > REDLINE_THRESHOLD_PCT:
                self._hot_streak[node.node_id] += 1
            else:
                self._hot_streak[node.node_id] = 0

        for node in datacenter.nodes:
            if self._hot_streak[node.node_id] < ANTI_THRASH_STREAK:
                continue  # not hot for long enough to be worth acting on

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
            # SLA lock: the saving is never worth breaching the task's budget.
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
