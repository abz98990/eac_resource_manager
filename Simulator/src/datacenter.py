"""SimPy data centre: server nodes executing a task stream under a scheduler."""

from __future__ import annotations

from dataclasses import dataclass

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
    """A server node holding 100 capacity units, one per CPU percentage point."""

    # SimPy refuses a put() that would overshoot capacity by even a float
    # rounding error, and the task then blocks forever. A hair of slack
    # absorbs the drift that builds up over thousands of get/put cycles.
    _CAPACITY_EPSILON = 1e-6

    def __init__(self, env: simpy.Environment, node_id: int, capacity_pct: float = 100.0):
        self.env = env
        self.node_id = node_id
        self.capacity_pct = capacity_pct
        self.container = simpy.Container(
            env, capacity=capacity_pct + self._CAPACITY_EPSILON, init=capacity_pct
        )
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
        self.utilization_samples: list[tuple[float, int, float, bool]] = []
        self.migration_cost_per_pct_min = migration_cost_per_pct_min or getattr(
            scheduler, "migration_cost_per_pct_min", 0.0
        )
        self.wake_up_min = wake_up_min or getattr(scheduler, "wake_up_min", 0.0)

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
                # The rebalancer interrupts with a target node id. The task
                # holds capacity nowhere while it moves.
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

    def run(self, tasks: list[Task], duration_min: float,
            sample_interval_min: float = 30.0, rebalance_interval_min: float = 5.0):
        self.env.process(self._arrivals(tasks))
        self.env.process(self._sample_utilization(sample_interval_min))
        if hasattr(self.scheduler, "rebalance"):
            self.env.process(self._rebalance_loop(rebalance_interval_min))
        self.env.run(until=duration_min)
