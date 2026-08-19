"""Entry point for the Energy-Aware Cloud Resource Infrastructure Simulator.

    python main.py demo         narrated walkthrough, for presenting live
    python main.py run          the three-scheduler comparison
    python main.py sensitivity  cluster-size and workload-intensity sweeps
    python main.py components   power model and workload generator only

CSVs land in data/, figures in figures/. See README.md.
"""

from __future__ import annotations

import argparse
import time


def cmd_components(args) -> None:
    from src import power_model, visualize, workload

    print("--- Power model: CPU load (%) -> power draw (W) ---")
    for load in (0, 25, 50, 75, 85, 90, 95, 100):
        print(f"  {load:3d}%  ->  {power_model.power_draw_watts(load):7.2f} W")
    print("Saved:", visualize.plot_power_curve())

    print("\n--- Workload generator: one simulated day, two injected spikes ---")
    tasks = workload.generate_tasks(
        duration_min=1440, spike_windows=[(600, 660, 6.0), (900, 930, 8.0)]
    )
    print(f"  generated {len(tasks)} tasks")
    print("Saved:", visualize.plot_workload_arrivals(tasks, duration_min=1440))


def cmd_run(args) -> None:
    import run_simulation

    run_simulation.main()


def cmd_sensitivity(args) -> None:
    import sensitivity_analysis

    sensitivity_analysis.main()


def cmd_demo(args) -> None:
    def pause(seconds: float = 1.2) -> None:
        if not args.fast:
            time.sleep(seconds)

    print("=" * 72)
    print("ENERGY-AWARE CLOUD RESOURCE INFRASTRUCTURE SIMULATOR — LIVE DEMO")
    print("=" * 72)

    print("\n[1/3] The power model this whole project is built on:")
    pause()
    cmd_components(args)

    print("\n[2/3] Running all three schedulers on an identical workload...")
    print("      (Round-Robin baseline, Green Heuristic, Consolidating Green)")
    pause()
    cmd_run(args)

    print("\n[3/3] Done. Evidence for what you just watched:")
    print("  figures/active_nodes.png         <- consolidation tracking the diurnal load")
    print("  figures/scheduler_comparison.png <- energy / latency / SLA side by side")
    print("  figures/*_heatmap.png            <- per-node utilization over the day")
    print("  data/comparison_summary.csv      <- the raw numbers")
    print("\nRun `python main.py sensitivity` next to see these results hold (or don't)")
    print("across cluster sizes and workload intensities.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fast", action="store_true", help="skip narration pauses (demo command only)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("demo", help="narrated walkthrough, good for presenting live")
    sub.add_parser("run", help="full 3-scheduler comparison")
    sub.add_parser("sensitivity", help="node-count / intensity sensitivity sweeps")
    sub.add_parser("components", help="quick look at just the power model + workload generator")

    args = parser.parse_args()
    command = args.command or "demo"

    {
        "demo": cmd_demo,
        "run": cmd_run,
        "sensitivity": cmd_sensitivity,
        "components": cmd_components,
    }[command](args)


if __name__ == "__main__":
    main()
