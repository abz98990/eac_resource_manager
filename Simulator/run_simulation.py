"""
Entry point: runs an identical generated workload through three schedulers
(Round-Robin baseline, Green Heuristic Rule-Based Constraint Engine, and the
Consolidating Green Heuristic that adds power-down/wake-up), extracts
metrics to CSV, and saves comparison figures.

IPR S4.1 "Comparative Analysis" step: "Using identical workload arrays for
both 'dumb' workloads and intelligent workloads, we will be able to see
exactly what differences in the total energy consumed (kWh) and the amount
of time to complete a task are presented."
"""

from __future__ import annotations

import pandas as pd
import simpy

from src import metrics, visualize, workload
from src.datacenter import DataCenter
from src.schedulers.green_consolidating import ConsolidatingGreenScheduler
from src.schedulers.green_heuristic import GreenHeuristicScheduler
from src.schedulers.round_robin import RoundRobinScheduler

NUM_NODES = 20
DURATION_MIN = 1440.0  # 1 simulated day
SAMPLE_INTERVAL_MIN = 15.0
SPIKE_WINDOWS = [(600, 660, 6.0), (900, 930, 8.0)]  # (start_min, end_min, extra tasks/min)

SCHEDULERS = (
    (RoundRobinScheduler, "baseline", "Baseline\n(Round-Robin)"),
    (GreenHeuristicScheduler, "green_heuristic", "Green\nHeuristic"),
    (ConsolidatingGreenScheduler, "consolidating", "Consolidating\nGreen"),
)


def run_scenario(scheduler_factory, name_slug: str, tasks):
    env = simpy.Environment()
    scheduler = scheduler_factory(NUM_NODES)
    dc = DataCenter(env, num_nodes=NUM_NODES, scheduler=scheduler)
    dc.run(tasks, duration_min=DURATION_MIN, sample_interval_min=SAMPLE_INTERVAL_MIN)

    task_df = metrics.task_records_to_df(dc.task_records)
    util_df = metrics.utilization_samples_to_df(dc.utilization_samples)

    metrics.export_csv(task_df, f"{name_slug}_tasks.csv")
    metrics.export_csv(util_df, f"{name_slug}_utilization.csv")

    heat_matrix = metrics.utilization_heatmap_matrix(util_df)
    visualize.plot_utilization_heatmap(
        heat_matrix, f"{scheduler.name}: Node Utilization Over Time", f"{name_slug}_heatmap.png"
    )

    active_df = metrics.active_nodes_over_time(util_df)
    summary = metrics.summarize(task_df, util_df, SAMPLE_INTERVAL_MIN, scheduler.name)
    stats = dict(scheduler.stats) if hasattr(scheduler, "stats") else None
    return summary, active_df, stats


def main():
    tasks = workload.generate_tasks(duration_min=DURATION_MIN, spike_windows=SPIKE_WINDOWS)
    visualize.plot_workload_arrivals(tasks, duration_min=DURATION_MIN)
    print(f"Generated {len(tasks)} tasks over {DURATION_MIN:.0f} simulated minutes across {NUM_NODES} nodes.\n")

    summaries = []
    active_by_scheduler = {}
    for scheduler_factory, slug, _short_label in SCHEDULERS:
        summary, active_df, stats = run_scenario(scheduler_factory, slug, tasks)
        summaries.append(summary)
        active_by_scheduler[summary["scheduler"]] = active_df
        print(f"--- {summary['scheduler']} ---")
        for k, v in summary.items():
            if k == "scheduler":
                continue
            print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")
        if stats:
            print(f"  scheduler stats: {stats}")
        print()

    summary_df = pd.DataFrame(summaries).set_index("scheduler")
    metrics.export_csv(summary_df.reset_index(), "comparison_summary.csv")

    short_labels = [label for _, _, label in SCHEDULERS]
    visualize.plot_scheduler_comparison(summary_df, short_labels=short_labels)
    visualize.plot_active_nodes(active_by_scheduler)

    print("=== Comparison Summary ===")
    print(summary_df[["total_energy_kwh", "mean_completion_latency_min", "sla_breach_rate", "mean_active_nodes"]])

    baseline_kwh = summary_df.loc["Round-Robin (Baseline)", "total_energy_kwh"]
    for scheduler_name in summary_df.index:
        if scheduler_name == "Round-Robin (Baseline)":
            continue
        kwh = summary_df.loc[scheduler_name, "total_energy_kwh"]
        saved_pct = 100 * (baseline_kwh - kwh) / baseline_kwh
        print(f"Energy saved by {scheduler_name} vs. baseline: {saved_pct:.2f}%")


if __name__ == "__main__":
    main()
