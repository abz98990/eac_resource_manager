"""Task arrival generator: diurnal traffic with optional load spikes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Task:
    task_id: int
    arrival_time: float
    cpu_demand_pct: float
    duration_min: float
    latency_sla_min: float  # delay budget on top of execution, not total runtime


def diurnal_rate(t_minutes, *, base_rate: float, peak_rate: float, period_min: float = 1440.0):
    """Arrival rate on a day/night cycle: trough at midnight, peak at midday."""
    phase = 2 * np.pi * (np.asarray(t_minutes) % period_min) / period_min
    cycle = (1 - np.cos(phase)) / 2.0
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
    """Arrivals over `duration_min` as a non-homogeneous Poisson process.

    `spike_windows` are `(start_min, end_min, extra_rate_per_min)` bursts
    layered on top of the diurnal cycle.
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
        # Thinning: sample at the peak rate, then keep each candidate with
        # probability rate(t)/max_rate to get the time-varying rate.
        if rng.random() < rate_fn(t) / max_rate:
            cpu_demand = float(rng.uniform(*demand_range_pct))
            dur = float(rng.uniform(*task_duration_range_min))
            sla = float(rng.uniform(*sla_slack_range_min))
            tasks.append(Task(task_id, t, cpu_demand, dur, sla))
            task_id += 1
    return tasks
