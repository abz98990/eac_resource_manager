"""
Visualization helpers. Every function saves a PNG into figures/ and returns
the path, so each stage of development leaves behind visual evidence.
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from . import power_model

sns.set_theme(style="whitegrid", palette="muted")

FIGURES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "figures")
os.makedirs(FIGURES_DIR, exist_ok=True)


def _save(filename: str) -> str:
    path = os.path.join(FIGURES_DIR, filename)
    plt.tight_layout()
    plt.savefig(path, dpi=200)
    plt.close()
    return path


def plot_power_curve() -> str:
    """Non-linear power model: idle baseline -> linear growth -> redline penalty."""
    load = np.linspace(0, 100, 500)
    power = power_model.power_draw_watts(load)

    plt.figure(figsize=(9, 5.5))
    plt.plot(load, power, color="#d62728", linewidth=3, label="Power draw (W)")
    plt.axvline(power_model.REDLINE_THRESHOLD_PCT, color="#ff7f0e", linestyle="--",
                linewidth=2, label=f"{power_model.REDLINE_THRESHOLD_PCT:.0f}% sweet-spot threshold")
    plt.axvspan(0, 75, color="#2ca02c", alpha=0.08, label="Target efficiency \"sweet spot\"")
    plt.axvspan(power_model.REDLINE_THRESHOLD_PCT, 100, color="#d62728", alpha=0.08,
                label="Thermal redline penalty zone")
    plt.title("Power Model: Non-Linear Server Power Scaling")
    plt.xlabel("CPU Load (%)")
    plt.ylabel("Power Draw (Watts)")
    plt.legend(loc="upper left", fontsize=9)
    return _save("power_curve.png")


def plot_workload_arrivals(tasks, duration_min: float, bin_minutes: float = 60.0) -> str:
    """Histogram of task arrivals over time, showing the diurnal pattern + spikes."""
    arrivals = [t.arrival_time for t in tasks]
    n_bins = int(duration_min // bin_minutes)

    plt.figure(figsize=(10, 5))
    plt.hist(arrivals, bins=n_bins, range=(0, duration_min), color="#1f77b4", edgecolor="white")
    plt.title(f"Generated Workload: Task Arrivals per {bin_minutes:.0f}-Minute Bucket")
    plt.xlabel("Simulated Time (minutes)")
    plt.ylabel("Task Arrivals")
    return _save("workload_arrivals.png")


def plot_utilization_heatmap(util_df: pd.DataFrame, title: str, filename: str) -> str:
    """util_df: rows = node id, columns = time bucket, values = % utilization."""
    plt.figure(figsize=(12, 6))
    ax = sns.heatmap(util_df, cmap="YlOrRd", vmin=0, vmax=100, linewidths=0.4,
                      cbar_kws={"label": "CPU Utilization (%)"})
    ax.set_title(title)
    ax.set_xlabel("Time Bucket")
    ax.set_ylabel("Server Node")
    return _save(filename)


_PALETTE = ["#7f7f7f", "#2ca02c", "#1f77b4", "#d62728"]


def plot_scheduler_comparison(summary: pd.DataFrame, short_labels: list[str] | None = None) -> str:
    """summary: index = scheduler name, columns include 'total_energy_kwh',
    'mean_completion_latency_min', and 'sla_breach_rate'. Works for any number
    of schedulers (rows)."""
    labels = short_labels or [s.replace(" (", "\n(") for s in summary.index]
    colors = _PALETTE[: len(summary)]
    x = range(len(summary))

    fig, axes = plt.subplots(1, 3, figsize=(5 * len(summary) + 4, 5))

    axes[0].bar(x, summary["total_energy_kwh"], color=colors)
    axes[0].set_title("Total Energy Consumed")
    axes[0].set_ylabel("kWh")

    axes[1].bar(x, summary["mean_completion_latency_min"], color=colors)
    axes[1].set_title("Mean Task Completion Latency")
    axes[1].set_ylabel("Minutes")

    axes[2].bar(x, summary["sla_breach_rate"] * 100, color=colors)
    axes[2].set_title("SLA Breach Rate")
    axes[2].set_ylabel("% of completed tasks")

    for ax in axes:
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, fontsize=8)

    fig.suptitle("Scheduler Comparison")
    plt.tight_layout()
    path = os.path.join(FIGURES_DIR, "scheduler_comparison.png")
    plt.savefig(path, dpi=200)
    plt.close()
    return path


def plot_active_nodes(active_by_scheduler: dict, filename: str = "active_nodes.png") -> str:
    """active_by_scheduler: {scheduler_name: DataFrame(time_min, active_nodes)}."""
    plt.figure(figsize=(10, 5))
    for i, (name, df) in enumerate(active_by_scheduler.items()):
        plt.plot(df["time_min"], df["active_nodes"], label=name,
                 color=_PALETTE[i % len(_PALETTE)], linewidth=2)
    plt.title("Powered-On Nodes Over Time")
    plt.xlabel("Simulated Time (minutes)")
    plt.ylabel("Active (Powered-On) Nodes")
    plt.legend(fontsize=9)
    return _save(filename)


def plot_sensitivity(df: pd.DataFrame, x_col: str, x_label: str, title: str, filename: str) -> str:
    """df: long-format sweep results with columns [x_col, 'scheduler',
    'total_energy_kwh', 'mean_completion_latency_min', 'sla_breach_rate']."""
    schedulers = df["scheduler"].unique()
    palette = {s: _PALETTE[i % len(_PALETTE)] for i, s in enumerate(schedulers)}
    metrics_cols = [
        ("total_energy_kwh", "Total Energy (kWh)", 1.0),
        ("mean_completion_latency_min", "Mean Completion Latency (min)", 1.0),
        ("sla_breach_rate", "SLA Breach Rate (%)", 100.0),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, (col, ylabel, scale) in zip(axes, metrics_cols):
        for scheduler in schedulers:
            sub = df[df["scheduler"] == scheduler].sort_values(x_col)
            ax.plot(sub[x_col], sub[col] * scale, marker="o", label=scheduler,
                    color=palette[scheduler], linewidth=2)
        ax.set_xlabel(x_label)
        ax.set_ylabel(ylabel)
        ax.set_title(ylabel)

    axes[0].legend(fontsize=8, loc="best")
    fig.suptitle(title)
    plt.tight_layout()
    path = os.path.join(FIGURES_DIR, filename)
    plt.savefig(path, dpi=200)
    plt.close()
    return path


if __name__ == "__main__":
    from . import workload

    print("Saved:", plot_power_curve())
    tasks = workload.generate_tasks(duration_min=1440, spike_windows=[(600, 660, 6.0), (900, 930, 8.0)])
    print("Saved:", plot_workload_arrivals(tasks, duration_min=1440))
