# Energy-Aware Cloud Resource Infrastructure Simulator

A discrete-event simulator (SimPy) comparing three VM scheduling strategies for a cloud
data center on energy consumption, task completion latency, and SLA compliance:

- **Round-Robin** — blind static baseline, ignores load entirely.
- **Green Heuristic** — Rule-Based Constraint Engine: avoids the >85% thermal "redline"
  zone, migrates off overloaded nodes with an anti-thrashing filter and a strict SLA lock.
- **Consolidating Green Heuristic** — adds opportunistic node power-down/wake-up on top of
  the Green Heuristic, without ever migrating a task purely to consolidate.

Full methodology, decisions, bugs found/fixed, and results are in [DEVLOG.md](DEVLOG.md) —
that file is written as source material for the thesis's Final Progress Report.

## Setup (one-time)

From the `Simulator/` folder, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

That's it — no other configuration. Do this *before* a live demo, not during one (installs
take a minute or two; nobody wants to watch a progress bar).

## Running it

Everything goes through `main.py`:

```powershell
.\.venv\Scripts\python main.py demo          # narrated walkthrough — use this to present
.\.venv\Scripts\python main.py run           # just the 3-scheduler comparison
.\.venv\Scripts\python main.py sensitivity   # node-count / intensity sweeps (~1-2 min)
.\.venv\Scripts\python main.py components    # just the power model + workload generator
```

Add `--fast` before the subcommand (e.g. `python main.py --fast demo`) to skip the demo's
narration pauses if you just want the output quickly.

Every run regenerates its outputs in `data/` (CSVs) and `figures/` (PNGs) — nothing is
hand-edited or one-off; re-running always reproduces the same evidence from scratch (the
workload generator is seeded, so numbers are deterministic between runs).

## Project structure

```
main.py                  CLI entry point — start here
run_simulation.py        3-scheduler comparison (single scenario)
sensitivity_analysis.py  node-count / intensity sweeps
src/
  power_model.py         CPU% -> power draw (the non-linear "redline" curve)
  workload.py             synthetic task arrival generator (diurnal + spikes)
  datacenter.py            SimPy environment: nodes, capacity, task lifecycle
  schedulers/
    round_robin.py          baseline
    green_heuristic.py       Rule-Based Constraint Engine
    green_consolidating.py   + power-down/wake-up
  metrics.py                Pandas extraction, CSV export, summary stats
  visualize.py               all chart generation
data/                     CSV outputs (raw simulation logs)
figures/                  PNG outputs (evidence — see below for which ones matter)
```

## Demoing this live to someone else

**Before they arrive:** run the setup above, and run `python main.py run` once so the
`.venv` is warm and you've confirmed nothing is broken. Have `figures/` open in a file
browser or ready to screen-share.

**During the demo**, run:

```powershell
.\.venv\Scripts\python main.py demo
```

This runs in well under a minute and narrates itself in three stages — talk over each one:

1. **Power model.** It prints the CPU%→Watts table and saves `power_curve.png`. Say: *"Power
   draw is linear up to 85% load, then grows exponentially — that exponential zone is what
   the scheduler is designed to avoid."* Open `power_curve.png` if you want a visual.

2. **The comparison.** All three schedulers run on the identical generated workload. While
   it prints, say: *"Same tasks, same arrival times, same cluster — only the placement
   decision changes."* When it finishes, pull up two figures:
   - `scheduler_comparison.png` — the headline numbers: baseline breaches SLA on ~32% of
     tasks, the Green Heuristic cuts that in half, Consolidating Green adds real energy
     savings (~10%) on top for a modest latency cost.
   - `active_nodes.png` — **the best figure in the project.** It visibly tracks the diurnal
     load curve: nodes power down overnight, wake back up ahead of the daytime peak and the
     two injected traffic spikes. This is the one to leave on screen the longest.

3. **Wrap-up.** It points at the output files. If there's time, follow with
   `python main.py sensitivity` (~1-2 min) and show `sensitivity_node_count.png` /
   `sensitivity_intensity.png` — these demonstrate the result isn't a cherry-picked lucky
   run, *and* honestly show where it breaks down (Consolidating Green underperforms even
   the baseline at very light load — a real, characterised limitation, not hand-waved away).
   That honesty is worth stating out loud; it's more convincing than a clean win would be.

**If asked "is this the real result or a mock-up":** everything shown is computed live from
the SimPy simulation each time you run it — there are no pre-baked numbers or placeholder
charts anywhere in this project. Re-running produces the same evidence again from scratch.

**If short on time:** skip straight to showing `figures/active_nodes.png` and
`figures/scheduler_comparison.png` from a previous run (they're already committed in the
repo) and narrate stages 1-2 above without re-running anything live.
