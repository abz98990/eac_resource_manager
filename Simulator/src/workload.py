"""
Workload generator: produces a stream of task ("VM") arrivals over simulated
time, following a diurnal (day/night) traffic pattern with optional injected
load-spike windows — the "dynamic bursts in load" motivating IPR S1.1.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Task:
    task_id: int
    arrival_time: float  # simulated minutes
    cpu_demand_pct: float  # % of one node's capacity required
    duration_min: float  # how long the task runs once started
    latency_sla_min: float  # max tolerable delay ON TOP of pure execution (queue wait +
    # migration overhead) before this task's SLA is breached


def diurnal_rate(t_minutes, *, base_rate: float, peak_rate: float, period_min: float = 1440.0):
    """Tasks-per-minute arrival rate on a smooth day/night cycle: trough at
    midnight (`base_rate`), peak at midday (`peak_rate`)."""
    phase = 2 * np.pi * (np.asarray(t_minutes) % period_min) / period_min
    cycle = (1 - np.cos(phase)) / 2.0  # 0 at midnight, 1 at midday
    return base_rate + (peak_rate - base_rate) * cycle


def generate_tasks(
    *,
    duration_min: float,
    base_rate_per_min: float = 0.6,
    peak_rate_per_min: float = 3.0,
    spike_windows: list[tuple[float, float, float]] | None = None,
    demand_range_pct: tuple[float, float] = (5.0, 35.0),
    task_duration_range_min: tuple[float, float] = (2.0, 30.0),
    sla_slack_range_min: tuple[float, float] = (1.0, 8.0),
    seed: int | None = 42,
) -> list[Task]:
    """
    Generate a task arrival stream over `duration_min` simulated minutes using
    a non-homogeneous Poisson process (thinning method) driven by `diurnal_rate`,
    plus optional injected spike windows `(start_min, end_min, extra_rate_per_min)`.
    """
    rng = np.random.default_rng(seed)
    spike_windows = spike_windows or []

    def rate_fn(t: float) -> float:
        r = float(diurnal_rate(t, base_rate=base_rate_per_min, peak_rate=peak_rate_per_min))
        for start, end, spike_rate in spike_windows:
            if start <= t < end:
                r += spike_rate
        return r

    max_rate = peak_rate_per_min + max((s[2] for s in spike_windows), default=0.0)

    tasks: list[Task] = []
    t = 0.0
    task_id = 0
    while True:
        t += rng.exponential(1.0 / max_rate)
        if t >= duration_min:
            break
        if rng.random() < rate_fn(t) / max_rate:  # thinning: keep with prob rate(t)/max_rate
            cpu_demand = float(rng.uniform(*demand_range_pct))
            dur = float(rng.uniform(*task_duration_range_min))
            sla = float(rng.uniform(*sla_slack_range_min))
            tasks.append(Task(task_id, t, cpu_demand, dur, sla))
            task_id += 1
    return tasks


if __name__ == "__main__":
    tasks = generate_tasks(duration_min=1440, spike_windows=[(600, 660, 6.0), (900, 930, 8.0)])
    print(f"Generated {len(tasks)} tasks over 1440 simulated minutes (1 day)")
    hourly_counts = np.histogram([t.arrival_time for t in tasks], bins=24, range=(0, 1440))[0]
    for hour, count in enumerate(hourly_counts):
        print(f"  hour {hour:2d}: {count:3d} arrivals  {'#' * count}")
