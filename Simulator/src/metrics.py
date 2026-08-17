"""
Pandas-based data extraction (IPR S4.1 Task 4 / S3.2): turns raw DataCenter
run output into structured DataFrames, CSV exports, and summary statistics
comparable across schedulers.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from . import power_model

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def task_records_to_df(task_records) -> pd.DataFrame:
    rows = [
        {
            "task_id": r.task.task_id,
            "arrival_time_min": r.task.arrival_time,
            "cpu_demand_pct": r.task.cpu_demand_pct,
            "duration_min": r.task.duration_min,
            "latency_sla_min": r.task.latency_sla_min,
            "node_id": r.node_id,
            "queue_wait_min": r.queue_wait_min,
            "start_time_min": r.start_time,
            "end_time_min": r.end_time,
            "completion_latency_min": (r.end_time - r.task.arrival_time) if r.end_time else None,
            "migrated": r.migrated,
            "sla_breached": r.sla_breached,
        }
        for r in task_records
    ]
    return pd.DataFrame(rows)


def utilization_samples_to_df(samples) -> pd.DataFrame:
    return pd.DataFrame(samples, columns=["time_min", "node_id", "used_pct", "powered_on"])


def utilization_heatmap_matrix(util_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot to node x time-bucket matrix of % utilization, for heatmap plotting."""
    return util_df.pivot_table(index="node_id", columns="time_min", values="used_pct")


def active_nodes_over_time(util_df: pd.DataFrame) -> pd.DataFrame:
    """Count of powered-on nodes at each sampled timestep."""
    return util_df.groupby("time_min")["powered_on"].sum().reset_index(name="active_nodes")


def sample_power_watts(util_df: pd.DataFrame) -> "pd.Series":
    """Per-sample power draw: the ON-state model where powered on, 0 where off."""
    on_power = power_model.power_draw_watts(util_df["used_pct"].to_numpy())
    return pd.Series(
        np.where(util_df["powered_on"].to_numpy(), on_power, power_model.POWERED_OFF_W),
        index=util_df.index,
    )


def total_energy_kwh(util_df: pd.DataFrame, sample_interval_min: float) -> float:
    """Riemann-sum the power model over every (node, timestep) utilization sample."""
    power_w = sample_power_watts(util_df)
    energy = power_model.energy_kwh(power_w.to_numpy(), timestep_hours=sample_interval_min / 60.0)
    return float(energy.sum())


def summarize(task_df: pd.DataFrame, util_df: pd.DataFrame, sample_interval_min: float,
              scheduler_name: str) -> dict:
    completed = task_df[task_df["end_time_min"] > 0]
    return {
        "scheduler": scheduler_name,
        "tasks_generated": len(task_df),
        "tasks_completed": len(completed),
        "total_energy_kwh": total_energy_kwh(util_df, sample_interval_min),
        "mean_completion_latency_min": completed["completion_latency_min"].mean(),
        "mean_queue_wait_min": completed["queue_wait_min"].mean(),
        "sla_breach_count": int(completed["sla_breached"].sum()),
        "sla_breach_rate": float(completed["sla_breached"].mean()),
        "migrated_count": int(completed["migrated"].sum()),
        "mean_active_nodes": float(util_df.groupby("time_min")["powered_on"].sum().mean()),
    }


def export_csv(df: pd.DataFrame, filename: str) -> str:
    path = os.path.join(DATA_DIR, filename)
    df.to_csv(path, index=False)
    return path
