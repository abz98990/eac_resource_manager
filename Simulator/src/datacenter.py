"""
SimPy discrete-event data center environment (IPR S3.1's "SimPy Environment
Engine"): a fixed number of server nodes, each a 100%-capacity CPU pool,
executing an incoming task stream placed by a pluggable scheduler. Tracks
per-node utilization over time and per-task completion/latency/SLA outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import simpy

from .workload import Task


@dataclass
class TaskRecord:
    task: Task
    node_id: int
    queue_wait_min: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0
    migrated: bool = False
    migrating: bool = False
    sla_breached: bool = False
    process: "simpy.Process | None" = None


class Node:
    """A single server node: a capacity pool of 100 CPU percentage-points."""

    # SimPy's Container blocks a put() outright if it fails the capacity
    # check even by a hair; over hundreds of get/put cycles, accumulated
    # float drift can make a legitimate release fail that check and stall
    # forever (see DEVLOG 2026-08-17). A tiny slack absorbs that drift.
    _CAPACITY_EPSILON = 1e-6

    def __init__(self, env: simpy.Environment, node_id: int, capacity_pct: float = 100.0):
        self.env = env
        self.node_id = node_id
        self.capacity_pct = capacity_pct
        self.container = simpy.Container(
            env, capacity=capacity_pct + self._CAPACITY_EPSILON, init=capacity_pct
        )
        # Power-down/wake-up support (only used by consolidation-aware
        # schedulers; a node that never sets this False behaves exactly as
        # before). A powered-off node must never be routed a task directly —
        # DataCenter._run_task wakes it (with delay) before it can get().
        self.powered_on = True

    @property
    def used_pct(self) -> float:
        return self.capacity_pct - self.container.level


class DataCenter:
    def __init__(self, env: simpy.Environment, num_nodes: int, scheduler,
                 migration_cost_per_pct_min: float | None = None, wake_up_min: float | None = None):
        self.env = env
        self.scheduler = scheduler
        self.nodes = [Node(env, i) for i in range(num_nodes)]
        self.running: dict[int, list[TaskRecord]] = {i: [] for i in range(num_nodes)}
        self.task_records: list[TaskRecord] = []
        # (time, node_id, used_pct, powered_on)
        self.utilization_samples: list[tuple[float, int, float, bool]] = []
        # A scheduler-supplied cost takes precedence; falls back to the
        # scheduler's own constant if it doesn't expose one explicitly.
        self.migration_cost_per_pct_min = migration_cost_per_pct_min or getattr(
            scheduler, "migration_cost_per_pct_min", 0.0
        )
        self.wake_up_min = wake_up_min or getattr(scheduler, "wake_up_min", 0.0)

    # --- per-task lifecycle --------------------------------------------------
    def _run_task(self, task: Task):
        arrival = self.env.now
        node_id = self.scheduler.choose_node(task, self.nodes, self.env.now)
        node = self.nodes[node_id]

        if not node.powered_on:
            yield self.env.timeout(self.wake_up_min)
            node.powered_on = True

        yield node.container.get(task.cpu_demand_pct)
        queue_wait = self.env.now - arrival

        record = TaskRecord(
            task=task, node_id=node_id, queue_wait_min=queue_wait, start_time=self.env.now,
            sla_breached=queue_wait > task.latency_sla_min,
        )
        record.process = self.env.active_process
        self.task_records.append(record)
        self.running[node_id].append(record)

        remaining = task.duration_min
        while remaining > 1e-9:
            segment_start = self.env.now
            try:
                yield self.env.timeout(remaining)
                remaining = 0.0
            except simpy.Interrupt as interrupt:
                remaining -= self.env.now - segment_start
                target_id = interrupt.cause

                node.container.put(task.cpu_demand_pct)
                self.running[node_id].remove(record)

                migration_cost = self.migration_cost_per_pct_min * task.cpu_demand_pct
                yield self.env.timeout(migration_cost)

                yield self.nodes[target_id].container.get(task.cpu_demand_pct)
                node_id = target_id
                node = self.nodes[node_id]
                record.node_id = node_id
                record.migrated = True
                record.migrating = False
                self.running[node_id].append(record)

        node.container.put(task.cpu_demand_pct)
        self.running[node_id].remove(record)
        record.end_time = self.env.now

    def _sample_utilization(self, interval_min: float):
        while True:
            for node in self.nodes:
                self.utilization_samples.append(
                    (self.env.now, node.node_id, node.used_pct, node.powered_on)
                )
            yield self.env.timeout(interval_min)

    def _rebalance_loop(self, interval_min: float):
        while True:
            yield self.env.timeout(interval_min)
            self.scheduler.rebalance(self, self.env.now)

    def _arrivals(self, tasks: list[Task]):
        for task in tasks:
            delay = task.arrival_time - self.env.now
            if delay > 0:
                yield self.env.timeout(delay)
            self.env.process(self._run_task(task))

    # --- entry point -----------------------------------------------------------
    def run(self, tasks: list[Task], duration_min: float,
            sample_interval_min: float = 30.0, rebalance_interval_min: float = 5.0):
        self.env.process(self._arrivals(tasks))
        self.env.process(self._sample_utilization(sample_interval_min))
        if hasattr(self.scheduler, "rebalance"):
            self.env.process(self._rebalance_loop(rebalance_interval_min))
        self.env.run(until=duration_min)
