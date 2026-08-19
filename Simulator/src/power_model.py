"""CPU utilisation to server power draw."""

from __future__ import annotations

import numpy as np

IDLE_POWER_W = 50.0
LINEAR_COEFF_W_PER_PCT = 1.5
REDLINE_THRESHOLD_PCT = 85.0
REDLINE_EXP_COEFF = 0.28
POWERED_OFF_W = 0.0


def power_draw_watts(
    cpu_load_pct,
    *,
    idle_power_w: float = IDLE_POWER_W,
    linear_coeff: float = LINEAR_COEFF_W_PER_PCT,
    redline_threshold_pct: float = REDLINE_THRESHOLD_PCT,
    redline_exp_coeff: float = REDLINE_EXP_COEFF,
) -> np.ndarray:
    """Watts drawn at the given CPU load(s). Takes scalars or arrays."""
    load = np.clip(np.asarray(cpu_load_pct, dtype=float), 0.0, 100.0)
    base = idle_power_w + linear_coeff * load

    over_threshold = load - redline_threshold_pct
    # The -1 keeps the penalty continuous at the threshold; without it the
    # curve jumps by a watt the moment load crosses 85%.
    redline_penalty = np.where(
        over_threshold > 0.0,
        np.exp(over_threshold * redline_exp_coeff) - 1.0,
        0.0,
    )
    return base + redline_penalty


def energy_kwh(power_w, timestep_hours: float) -> np.ndarray:
    return np.asarray(power_w, dtype=float) * timestep_hours / 1000.0
