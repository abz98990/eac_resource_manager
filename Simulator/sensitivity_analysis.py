"""
Sensitivity analysis: does the Green Heuristic's advantage over Round-Robin
(lower SLA breach rate, marginal energy edge) hold across cluster sizes and
workload intensities, or was the single scenario in run_simulation.py a
lucky/unlucky point? IPR S5's evaluation as originally scoped is a single
snapshot; this sweeps two axes to check how broadly the Task 3 result holds.
"""

from __future__ import annotations

import pandas as pd
import simpy

from src import metrics, workload
from src.datacenter import DataCenter
from src.schedulers.green_consolidating import ConsolidatingGreenScheduler
from src.schedulers.green_heuristic import GreenHeuristicScheduler
from src.schedulers.round_robin import RoundRobinScheduler

DURATION_MIN = 1440.0
SAMPLE_INTERVAL_MIN = 15.0
BASE_SPIKE_WINDOWS = [(600, 660, 6.0), (900, 930, 8.0)]
SCHEDULER_CLASSES = (RoundRobinScheduler, GreenHeuristicScheduler, ConsolidatingGreenScheduler)


def run_once(num_nodes: int, tasks, scheduler_cls) -> dict:
    env = simpy.Environment()
    scheduler = scheduler_cls(num_nodes)
    dc = DataCenter(env, num_nodes=num_nodes, scheduler=scheduler)
    dc.run(tasks, duration_min=DURATION_MIN, sample_interval_min=SAMPLE_INTERVAL_MIN)
    task_df = metrics.task_records_to_df(dc.task_records)
    util_df = metrics.utilization_samples_to_df(dc.utilization_samples)
    return metrics.summarize(task_df, util_df, SAMPLE_INTERVAL_MIN, scheduler.name)


def node_count_sweep(node_counts: list[int]) -> pd.DataFrame:
    """Fixed workload, varying cluster size: from oversubscribed to generously provisioned."""
    tasks = workload.generate_tasks(duration_min=DURATION_MIN, spike_windows=BASE_SPIKE_WINDOWS)
    rows = []
    for n in node_counts:
        for cls in SCHEDULER_CLASSES:
            summary = run_once(n, tasks, cls)
            summary["num_nodes"] = n
            rows.append(summary)
            print(f"nodes={n:2d}  {summary['scheduler']:45s}  "
                  f"energy={summary['total_energy_kwh']:6.2f} kWh  "
                  f"sla_breach={summary['sla_breach_rate']*100:5.1f}%  "
                  f"latency={summary['mean_completion_latency_min']:5.1f} min")
    return pd.DataFrame(rows)


def intensity_sweep(multipliers: list[float], num_nodes: int = 20) -> pd.DataFrame:
    """Fixed 20-node cluster, scaling arrival rates (base/peak/spike) together."""
    rows = []
    for m in multipliers:
        spike_windows = [(s, e, r * m) for s, e, r in BASE_SPIKE_WINDOWS]
        tasks = workload.generate_tasks(
            duration_min=DURATION_MIN,
            base_rate_per_min=0.6 * m,
            peak_rate_per_min=3.0 * m,
            spike_windows=spike_windows,
        )
        for cls in SCHEDULER_CLASSES:
            summary = run_once(num_nodes, tasks, cls)
            summary["intensity_multiplier"] = m
            summary["num_tasks"] = len(tasks)
            rows.append(summary)
            print(f"intensity={m:.2f}x ({len(tasks):4d} tasks)  {summary['scheduler']:45s}  "
                  f"energy={summary['total_energy_kwh']:6.2f} kWh  "
                  f"sla_breach={summary['sla_breach_rate']*100:5.1f}%  "
                  f"latency={summary['mean_completion_latency_min']:5.1f} min")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print("=== Node-count sweep (fixed workload, 3198 tasks) ===")
    node_df = node_count_sweep([14, 17, 20, 25, 30])
    metrics.export_csv(node_df, "sensitivity_node_count.csv")

    print("\n=== Workload-intensity sweep (fixed 20 nodes) ===")
    intensity_df = intensity_sweep([0.5, 0.75, 1.0, 1.25, 1.5])
    metrics.export_csv(intensity_df, "sensitivity_intensity.csv")
