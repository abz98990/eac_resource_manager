"""
Vectorized mathematical power model.

Maps a server's CPU utilization (%) to instantaneous power draw (Watts),
per IPR S1.1 / S4.1: power grows roughly linearly with load, then grows
exponentially once utilization crosses the "Power Sweet Spot" threshold
(85%) as cooling/thermal inefficiencies kick in (the "Redline Penalty").
"""

from __future__ import annotations

import numpy as np

IDLE_POWER_W = 50.0
LINEAR_COEFF_W_PER_PCT = 1.5
REDLINE_THRESHOLD_PCT = 85.0
REDLINE_EXP_COEFF = 0.28
POWERED_OFF_W = 0.0  # a fully powered-down node draws no power


def power_draw_watts(
    cpu_load_pct,
    *,
    idle_power_w: float = IDLE_POWER_W,
    linear_coeff: float = LINEAR_COEFF_W_PER_PCT,
    redline_threshold_pct: float = REDLINE_THRESHOLD_PCT,
    redline_exp_coeff: float = REDLINE_EXP_COEFF,
) -> np.ndarray:
    """Power draw (W) for given CPU load(s) (%). Accepts scalars or arrays."""
    load = np.clip(np.asarray(cpu_load_pct, dtype=float), 0.0, 100.0)

    base = idle_power_w + linear_coeff * load

    # Redline penalty: 0 at the threshold (continuous), exponential above it.
    over_threshold = load - redline_threshold_pct
    redline_penalty = np.where(
        over_threshold > 0.0,
        np.exp(over_threshold * redline_exp_coeff) - 1.0,
        0.0,
    )
    return base + redline_penalty


def energy_kwh(power_w, timestep_hours: float) -> np.ndarray:
    """Energy (kWh) consumed by a given power draw (W) over one timestep."""
    return np.asarray(power_w, dtype=float) * timestep_hours / 1000.0


if __name__ == "__main__":
    for load in (0, 25, 50, 75, 85, 90, 95, 100):
        print(f"CPU {load:3d}% -> {power_draw_watts(load):7.2f} W")
