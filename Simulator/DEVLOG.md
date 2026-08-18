# Development Log — Energy-Aware Cloud Resource Infrastructure Simulator

This log records development decisions, rationale, and evidence (figures/data) as the
simulator is built, mapped against the 6-task plan in the Interim Progress Report (IPR).
Intended as source material for the Final Progress Report (FPR).

---

## 2026-08-17 — Project scaffolding

**What:** Created `Simulator/` as the codebase root (separate from the `IPR/` and `FPR/`
report folders). Set up an isolated Python virtual environment (`.venv`) and installed the
stack named in IPR §2.3 / §3.2: `simpy` (discrete-event engine), `numpy` (vectorized power
math), `pandas` (log extraction), `matplotlib` + `seaborn` (visualization).

**Structure:**
```
Simulator/
  src/
    power_model.py       - vectorized CPU% -> power draw model
    workload.py           - task arrival generator (diurnal pattern + spikes)
    datacenter.py          - SimPy environment: server nodes, task execution
    schedulers/
      base.py              - scheduler interface
      round_robin.py       - "dumb" static baseline scheduler
      green_heuristic.py   - Rule-Based Constraint Engine
    metrics.py              - Pandas-based per-timestep logger, CSV export
    visualize.py             - heatmaps + baseline-vs-green comparison charts
  data/       - CSV outputs (raw simulation logs)
  figures/    - PNG outputs (evidence for report)
  run_simulation.py - entry point, runs both schedulers on identical workload
  DEVLOG.md   - this file
```

**Why this structure:** IPR §4.1 specifies a decoupled, layered build order — (1) a "dumb"
baseline on a minimal SimPy loop, (2) inject the Rule-Based Constraint Engine, (3) run
comparative analysis on identical workload arrays. The module layout mirrors that order so
each stage can be run and evidenced independently before the next is added.

---

## 2026-08-17 — Power model (`src/power_model.py`)

**What:** Formalized the mathematical power model into a reusable, vectorized module
(`power_draw_watts`, `energy_kwh`), replacing the standalone prototype in
`IPR/dummy data generator/heatmap gen.py`.

Model: `power(load%) = idle_power + linear_coeff * load% + redline_penalty(load%)`, with
`redline_penalty = exp((load% - 85) * 0.28) - 1` for `load% > 85`, else `0`.

**Refinement vs. the IPR prototype script:** the prototype added `exp((load-80)*0.28)`
unconditionally above 80%, which introduces a **discontinuous +1W jump** right at the
threshold (`exp(0) = 1`, not `0`). This version subtracts 1 so the penalty is exactly `0`
at the threshold and grows smoothly above it — a more defensible model for the report, and
threshold now consistently set at **85%** everywhere (matching IPR §3.2's stated
constraint, rather than the prototype's mixed 80/85 values).

**Evidence — smoke test output** (`python src/power_model.py`):

| CPU Load | Power Draw |
|---|---|
| 0%   | 50.00 W |
| 25%  | 87.50 W |
| 50%  | 125.00 W |
| 75%  | 162.50 W |
| 85%  | 177.50 W (sweet-spot boundary, penalty = 0) |
| 90%  | 188.06 W |
| 95%  | 207.94 W |
| 100% | 265.69 W |

Between 85→90% power rises +10.6W (near-linear); between 95→100% it rises +57.75W —
demonstrating the intended non-linear "redline" scaling from IPR §1.1.

**Figure:** [`figures/power_curve.png`](figures/power_curve.png) — visual evidence of the
sweet-spot / redline zones referenced throughout the report.

---

## 2026-08-17 — Workload generator (`src/workload.py`)

**What:** Implemented `generate_tasks()`, producing a synthetic task ("VM") arrival stream
using a **non-homogeneous Poisson process** (thinning method) driven by a diurnal
`base_rate -> peak_rate` day/night cycle (`diurnal_rate()`), with optional injected
**spike windows** — extra arrival-rate bursts over a fixed time range — modeling the
"dynamic load spikes" IPR §1.1 says static schedulers can't adapt to.

Each `Task` carries: `cpu_demand_pct` (% of one node's capacity it needs), `duration_min`
(execution time once placed), and `latency_sla_min` (max acceptable queue+migration delay
before an SLA breach — this is what the later SLA Migration Lock checks against).

**Why Poisson-process thinning:** it's the standard technique for sampling arrivals from a
time-varying rate function without discretizing time into bins first, keeping arrivals
continuous-valued (compatible with SimPy's continuous clock) while still respecting the
diurnal shape.

**Evidence — smoke test** (`python -m src.workload`, 1 simulated day, two injected spike
windows at minutes 600-660 and 900-930): generated **3,198 tasks**, with a clear diurnal
rise from ~35 arrivals/hour at midnight to ~130-180/hour at midday, and pronounced spikes
to 538 and 419 arrivals in the injected windows — confirming the generator produces the
"low traffic during the day, high traffic during load spikes" pattern IPR §3.1 specifies
for the Workload Generator component.

**Figure:** [`figures/workload_arrivals.png`](figures/workload_arrivals.png) — histogram
of arrivals per 60-minute bucket, diurnal curve plus the two spike windows clearly visible.

**Correction applied:** initially `latency_sla_min` was generated as `duration + slack`, which
contradicted its own docstring ("delay before SLA breach"). Fixed so it stores the tolerable
*delay budget* directly (queue wait + migration overhead), matching how the scheduler's SLA
Migration Lock consumes it later — see the 2026-08-17 datacenter entry below.

---

## 2026-08-17 — SimPy environment + both schedulers (Task 2 & Task 3 of the project plan)

**What:** Built the two remaining core pieces together, since the Rule-Based Constraint
Engine can't be meaningfully tested without a live environment to rebalance against:

- `src/datacenter.py` — `Node` (a SimPy `Container` capacity pool per server, 100 CPU
  percentage-points) and `DataCenter`, which runs the arrival stream as SimPy processes,
  blocks tasks on `container.get()` until capacity frees (this *is* the queueing delay),
  samples per-node utilization on a timer, and runs a periodic rebalance hook.
- `src/schedulers/round_robin.py` — the "dumb" baseline (IPR S4.1 step 1): cycles nodes in
  fixed order, blind to load, never rebalances.
- `src/schedulers/green_heuristic.py` — the Rule-Based Constraint Engine (IPR S4.1 step 2),
  implementing all three design rules from IPR S3.2 literally:
  - **Power Sweet Spot** — `choose_node` only considers nodes that would stay ≤85% after
    placement, and among those prefers landing in the 40-75% band (falls back to the
    least-loaded node, logged as a `redline_admission`, only if every node would breach 85%).
  - **Anti-Thrashing Filter** — a node must read >85% utilization for **3 consecutive**
    rebalance ticks (`ANTI_THRASH_STREAK`) before it's treated as persistently hot and
    considered for migration; a single-tick spike is ignored by design.
  - **Strict SLA Migration Lock** — before migrating a running task off a hot node, the
    engine computes `migration_cost = 0.15 min/% x cpu_demand_pct` and compares it to the
    task's *remaining* SLA slack; if the migration itself would breach the SLA, it is
    **skipped**, never forced through.

**Engineering note — how migration is actually simulated:** a running task is a SimPy
process blocked in `env.timeout(remaining_duration)`. The rebalancer calls
`process.interrupt(target_node_id)`; the task process catches `simpy.Interrupt`, releases
capacity on the old node, pays the migration-cost delay, acquires capacity on the new node,
and resumes its *remaining* execution time. This is a faithful (if simplified) model of
live-migration downtime rather than an instantaneous relabeling.

**Evidence — smoke test** (`python -m src.datacenter`, 12 nodes, 1 simulated day, same
3,198-task workload as above):

| | Round-Robin (Baseline) | Green Heuristic |
|---|---|---|
| Tasks completed | 3,184 / 3,198 | 3,053 / 3,198 |
| Avg queue wait | 65.37 min | 60.47 min |
| SLA breaches | 2,130 (66.9%) | 1,236 (40.5%) |
| Tasks migrated | 0 | 6 |

Scheduler-internal counters for the Green Heuristic run: 1,341 redline admissions, 1,611
migrations attempted, only **6 completed** — because **1,498 were correctly blocked by the
SLA lock**. This is direct evidence the lock is doing its job: the engine repeatedly
*wanted* to migrate for power savings but refused whenever doing so would cost more delay
than the task could tolerate, exactly the "Throughput > Micro-optimization" priority stated
in the pitch doc (`Energy Aware CRI Sim.docx` S3).

**Known limitation to fix before the main comparison run:** 12 nodes is undersized for this
workload — mean concurrent demand alone is close to the fleet's usable capacity, so *both*
schedulers are oversubscribed at peak, which is why breach rates are high for both. This is
useful as a stress-test of the mechanics (queueing, redline, migration, lock all fire and
were verified above) but not representative of a fair capacity-planned comparison. The main
run (`run_simulation.py`) uses a larger, properly-provisioned node count so normal traffic
sits comfortably in the sweet spot and only the diurnal peak / injected spikes create real
redline pressure — which is the scenario the heuristic is actually designed for.

---

## 2026-08-17 — Metrics extraction, comparison runner, and two bug fixes

**What:** Added `src/metrics.py` (Pandas extraction: task/utilization DataFrames, CSV
export, per-scheduler summary stats) and `run_simulation.py` (runs the identical
3,198-task workload through both schedulers on **20 nodes**, exporting
`data/{baseline,green_heuristic}_{tasks,utilization}.csv`, `data/comparison_summary.csv`,
and the heatmap/comparison figures below). This is IPR §4.1's "Comparative Analysis" step.

**First run surfaced a real problem, not just a result.** The initial comparison showed
Green Heuristic *increasing* mean completion latency by ~35% (32.2 vs 23.9 min) — directly
contradicting the design goal of "zero throughput degradation." Rather than report that
number, I traced it to a genuine bug in `choose_node`'s scoring function
(`src/schedulers/green_heuristic.py`): it used a **hard lexicographic priority**
`(0 if in_band else 1, distance)`, meaning *any* node in the 40-75% efficiency band beat
*any* out-of-band node — including a nearly idle one. This funnelled tasks onto a few
"good-looking" nodes while idle capacity sat unused, causing queueing pile-up.

**Fix 1:** replaced the hard override with a soft tie-break — `resulting_pct` minus an
8-point discount for landing in-band — so idle capacity only loses to an in-band node when
they're already close (see `BAND_TIEBREAK_BONUS_PCT` in `green_heuristic.py`). Latency
improved (32.2 → 27.5 min) but energy then went **the wrong direction** (50.4 → 55.2 kWh,
i.e. Green Heuristic became *worse* than baseline) — a second bug, investigated below.

**Bug 2 (the interesting one) — SimPy `Container` float-precision deadlock.** Diagnostics
(`mean util` per scheduler vs. the workload's theoretically-expected mean util) showed
Green Heuristic's sampled utilization running ~7 points hotter than the baseline for no
physical reason — the same tasks, same total demand-minutes, should integrate to the same
aggregate utilization regardless of which nodes execute them. Traced with an instrumented
get/put wrapper (`node.container.get_queue`/`put_queue` inspection) to: **a legitimate
task-completion `put()` was silently stuck in the container's internal queue forever.**

Root cause: `simpy.Container._do_put` only succeeds if `capacity - level >= amount`. After
~150+ get/put cycles per node (more of them for Green Heuristic, which also does migration
get/put pairs), accumulated floating-point drift occasionally makes a *should-be-exact*
release fail that boundary check by an infinitesimal margin. SimPy then leaves the put
queued indefinitely — nothing will ever retry it — silently "leaking" that capacity for
the rest of the run and inflating every subsequent utilization sample on that node. This
hit Green Heuristic harder because migrations roughly double its get/put traffic per node.

**Fix 2:** gave each node's container a hair of slack —
`simpy.Container(env, capacity=capacity_pct + 1e-6, init=capacity_pct)` in
`src/datacenter.py`'s `Node.__init__` — so accumulated drift can never block a legitimate
release. Verified with a capacity-conservation check (held capacity per node vs. sum of
demand for tasks actually still running) across all 20 nodes: zero mismatches after the fix
(all previously-mismatched nodes now read exactly `0.00`/`-0.00`).

**Validated final results** (20 nodes, 1 simulated day, identical 3,198-task workload,
`python run_simulation.py`):

| Metric | Round-Robin (Baseline) | Green Heuristic | Change |
|---|---|---|---|
| Tasks completed | 3,184 / 3,198 | 3,184 / 3,198 | — |
| Total energy | 50.075 kWh | 49.946 kWh | **-0.26%** |
| Mean completion latency | 23.91 min | 28.45 min | +19.0% |
| Mean queue wait | 8.06 min | 12.48 min | +54.8% |
| **SLA breach rate** | **32.1%** | **15.4%** | **-52.1% relative** |
| Tasks migrated | 0 | 13 | — |

A follow-up energy decomposition (redline-penalty-only vs. linear+idle) explains *why* the
aggregate energy delta is small despite the heuristic visibly reducing time spent above the
85% threshold (samples >85%: 10.7% baseline vs. 7.4% Green Heuristic, a ~30% relative cut):

| Component | Baseline | Green Heuristic |
|---|---|---|
| Redline penalty energy | 0.719 kWh | 0.480 kWh (**-33%**) |
| Linear + idle energy | 49.36 kWh | 49.47 kWh (invariant, as expected*) |

\* *This is mathematically expected, not a coincidence:* linear+idle power is proportional
to instantaneous aggregate CPU load, and total (demand × duration) executed is fixed by the
workload regardless of which node runs which task — so this component is scheduler-
invariant. The redline penalty (exponential term above 85%) is the *only* lever a placement
heuristic has over total energy in this model, and it's a small fraction (~1.4%) of total
consumption for this workload. **This is a real, citable finding for the report's
discussion section**, not a limitation to hide: it says any energy-aware *placement-only*
heuristic (no server power-down/consolidation) is fundamentally capped in how much
aggregate energy it can save under this power model — meaningful savings would need either
a much more redline-heavy workload or a consolidation mechanism, which this project
deliberately avoids for SLA-safety reasons (§2.1's critique of Beloglazov et al.).

**Honest interpretation of the latency trade-off:** Green Heuristic's higher *mean*
completion latency alongside a *lower* SLA breach rate is a real, defensible tension, not a
contradiction: SLA breach is defined per-task against that task's own tolerance, while mean
latency is dragged up by the heuristic deliberately making some tasks wait for a safe node
rather than dogpiling an already-hot one. The heuristic is trading a modest amount of
average-case latency for a large reduction in worst-case SLA violations — arguably the more
important metric for the "Strict SLA Migration Lock" story the report tells, but this
trade-off should be stated explicitly in the report rather than glossed over.

**Figures (evidence):**
- [`figures/baseline_heatmap.png`](figures/baseline_heatmap.png) /
  [`figures/green_heuristic_heatmap.png`](figures/green_heuristic_heatmap.png) — per-node
  utilization over the simulated day for each scheduler; both show the diurnal peak and two
  injected spikes (minutes 600-660, 900-930) as dense high-utilization bands.
- [`figures/scheduler_comparison.png`](figures/scheduler_comparison.png) — energy, mean
  latency, and SLA breach rate side-by-side.

**Raw data (evidence):** `data/baseline_tasks.csv`, `data/green_heuristic_tasks.csv`,
`data/baseline_utilization.csv`, `data/green_heuristic_utilization.csv`,
`data/comparison_summary.csv`.

**Status vs. the IPR 6-task plan:** Task 2 (baseline SimPy environment) — done. Task 3
(Green Heuristic constraint engine) — done, with the tuning history above worth including
in the report as evidence of iterative validation. Task 4 (execution & data extraction) —
done. Task 5 (visualization & analysis) — first pass done (heatmaps + comparison chart);
further analysis (e.g. sensitivity to workload intensity, node count) would strengthen the
final report. Task 6 (report writing) — not started; this DEVLOG is intended as raw source
material for it.

---

## 2026-08-17 — Sensitivity analysis: is the Task 3 result a fluke or a trend?

**What:** The single-scenario comparison above (20 nodes, one workload) is a snapshot, not
proof the Green Heuristic's advantage generalizes. Added `sensitivity_analysis.py`, which
sweeps two independent axes and re-runs both schedulers at each point:

1. **Cluster size** (14/17/20/25/30 nodes, same fixed 3,198-task workload) — from
   oversubscribed to generously provisioned.
2. **Workload intensity** (0.5x-1.5x multiplier on base/peak/spike arrival rates, fixed 20
   nodes, 1,596-4,835 tasks) — from lightly loaded to heavily stressed.

Results exported to `data/sensitivity_node_count.csv` / `data/sensitivity_intensity.csv`;
plotted in [`figures/sensitivity_node_count.png`](figures/sensitivity_node_count.png) and
[`figures/sensitivity_intensity.png`](figures/sensitivity_intensity.png) (3 panels each:
energy, mean latency, SLA breach rate vs. the swept variable, both schedulers overlaid).

**Node-count sweep — key numbers:**

| Nodes | RR SLA breach | GH SLA breach | RR latency | GH latency | Energy delta |
|---|---|---|---|---|---|
| 14 | 58.1% | 35.3% | 50.2 min | 57.8 min | -0.6% |
| 17 | 43.2% | 22.2% | 30.5 min | 35.6 min | -0.5% |
| 20 | 32.1% | 15.4% | 23.9 min | 28.4 min | -0.3% |
| 25 | 20.7% | 10.6% | 19.3 min | 25.9 min | -0.5% |
| 30 | 13.2% |  8.2% | 17.5 min | 20.1 min | -0.1% |

**Intensity sweep — key numbers:**

| Intensity | RR SLA breach | GH SLA breach | RR latency | GH latency | Energy delta |
|---|---|---|---|---|---|
| 0.5x | 2.4% | 0.9% | 15.8 min | 15.8 min | -0.03% |
| 0.75x | 18.1% | 10.0% | 18.9 min | 22.2 min | -0.5% |
| 1.0x | 32.1% | 15.4% | 23.9 min | 28.4 min | -0.3% |
| 1.25x | 45.7% | 21.2% | 32.0 min | 44.8 min | -1.3% |
| 1.5x | 61.5% | 36.3% | 54.0 min | 62.5 min | -0.8% |

**Findings — the result is robust, and the trade-off is real, not a one-off:**

- The **SLA-breach reduction is consistent across every single point in both sweeps** —
  Green Heuristic never once loses to the baseline on SLA compliance, across a 5x range of
  cluster sizes and a 3x range of workload intensity. This is the strongest, most defensible
  claim the project can make.
- The **relative SLA improvement is roughly 40-60% throughout**, and the *absolute* gap
  widens as the system gets busier (more nodes = smaller gap as contention eases; more load
  = bigger gap as contention bites) — exactly the shape you'd expect if the mechanism (avoid
  placing onto already-hot nodes) is actually the thing doing the work, not noise.
- The **energy edge is small and consistent** (roughly -0.1% to -1.3%) in the same direction
  throughout — never a energy regression once the container float-precision bug (above) was
  fixed. Confirms the earlier analytical point: with no power-down/consolidation mechanism,
  redline-avoidance is the only lever, so savings are structurally capped low.
- The **latency trade-off is also consistent, not a fluke of one run**: Green Heuristic is
  slower on *mean* completion time at every single point in both sweeps. The absolute gap
  shrinks toward ~0 as the cluster becomes well-provisioned (14 nodes: +7.6 min → 30 nodes:
  +2.5 min) but *grows* as workload intensity rises (0.75x: +3.3 min → 1.5x: +8.5 min,
  peaking at +12.8 min at 1.25x). **This should be reported as a genuine, characterised
  limitation**, not smoothed over: the heuristic buys SLA compliance by making some tasks
  wait longer for a safe node, and that cost is largest exactly when the system is busiest —
  the same condition where the SLA-compliance benefit is also largest. That tension (bigger
  benefit, bigger cost, both driven by the same busy-system mechanism) is worth a paragraph
  of honest discussion in the report rather than picking whichever framing looks best.

**Suggested next steps for Task 5/6:** this sensitivity data is enough to write an honest
"Results & Analysis" section: report the single-scenario headline numbers, then use these
sweeps to show the SLA-improvement generalizes and to characterise (not hide) the latency
trade-off's shape. A natural extension, not yet built, would be to add an optional
consolidation/power-down mechanism as a *third* scheduler variant, to test the earlier
analytical claim that idle+linear power (not redline) dominates total energy — that's the
most direct way to probe whether bigger energy savings are achievable at all under this
power model, and would make a strong "future work" or stretch-goal section.

---

## 2026-08-17 — Third scheduler: Consolidating Green Heuristic (power-down/wake-up)

**Why:** the sensitivity analysis above nailed down *why* the plain Green Heuristic's energy
edge is small: idle+linear power is scheduler-invariant when every node stays powered on
regardless of load, so redline avoidance (the only lever available) can only touch ~1.4% of
total energy. To actually test the "bigger savings are only reachable via consolidation"
hypothesis, rather than just assert it, built a third scheduler and the infrastructure to
support it.

**What was added:**

- **`src/datacenter.py`** — `Node` gained a `powered_on` flag. `DataCenter._run_task` wakes
  a powered-off node (pays `wake_up_min` as delay, added to the task's queue wait) before it
  can accept a task; `_sample_utilization` now records power state alongside utilization.
- **`src/power_model.py`** — `POWERED_OFF_W = 0.0`; a fully powered-down node draws nothing.
- **`src/metrics.py`** — `sample_power_watts()` branches per-sample on `powered_on` before
  applying the power curve; `active_nodes_over_time()` for the new visualization below.
- **`src/schedulers/green_consolidating.py`** — `ConsolidatingGreenScheduler`, built on top
  of (imports constants from) the existing Green Heuristic. Adds exactly two new behaviours,
  deliberately conservative to preserve the SLA-safety story from IPR S2.1's critique of
  Beloglazov et al.'s aggressive consolidation:
  1. **Wake-on-demand:** if no powered-on node has redline-safe headroom for a new task, wake
     a powered-off node (`WAKE_UP_MIN = 3.0` min) rather than forcing a redline admission.
  2. **Power-down-when-empty:** a node that has been *completely empty* (zero running tasks)
     for `EMPTY_STREAK = 6` consecutive rebalance ticks (30 min) is powered off.
  
  Critically, **this scheduler never migrates a task purely to free up a node for
  power-down** — only nodes that emptied out on their own are touched. Redline migration
  (with the same anti-thrashing filter and SLA lock as the plain Green Heuristic) is
  untouched. This means the power-down mechanism is structurally incapable of causing an SLA
  breach by itself — the only new latency cost it can introduce is the wake-up delay, which
  is visible and boundable, not a knock-on migration risk.
- **`run_simulation.py`** now runs all three schedulers on the identical workload; comparison
  chart and heatmaps generalized to N schedulers; added `plot_active_nodes()`.

**Verification:** re-ran the capacity-conservation check from the earlier bug fix
(held capacity per node vs. sum of demand for tasks actually still running) specifically
against this scheduler — **zero mismatches**, and additionally verified no powered-off node
ever shows nonzero held capacity (i.e., the invariant "off implies empty" holds throughout).

**Results** (20 nodes, 1 simulated day, identical 3,198-task workload):

| Metric | Baseline (RR) | Green Heuristic | **Consolidating Green** |
|---|---|---|---|
| Total energy | 50.08 kWh | 49.95 kWh (-0.26%) | **44.74 kWh (-10.65%)** |
| Mean completion latency | 23.9 min | 28.4 min | 35.7 min |
| Mean queue wait | 8.06 min | 12.48 min | 19.77 min |
| SLA breach rate | 32.1% | 15.4% | **15.1%** |
| Mean active nodes | 20.0 | 20.0 | 15.5 |
| Nodes powered down / woken | — | — | 24 / 70 |

**This is the headline result the project set out to find.** Consolidation unlocks
roughly **40x more energy savings** than redline-avoidance alone (10.65% vs 0.26%), while
SLA compliance is *not worse* than the plain Green Heuristic (15.1% vs 15.4% — essentially a
tie, both far better than baseline's 32.1%) — confirming the design succeeds at decoupling
"save idle power" from "risk SLA breaches via forced migration," which is exactly the gap
IPR S2.1 identifies in Beloglazov et al.'s approach.

**Energy decomposition** (`data/{slug}_utilization.csv`, power split by component):

| | Baseline | Green Heuristic | Consolidating Green |
|---|---|---|---|
| Node-time powered off | 0.0% | 0.0% | **22.5%** |
| Redline penalty energy | 0.719 kWh | 0.480 kWh | 0.433 kWh |
| Total energy | 50.075 kWh | 49.946 kWh | 44.743 kWh |

Roughly 5.0 of the 5.3 kWh saved vs. baseline comes from the idle+linear component (nodes
simply not drawing power while off 22.5% of the time), with a further small reduction from
redline avoidance — confirming the analytical prediction from the sensitivity-analysis entry
almost exactly: **idle power, not redline power, is where the real savings live**, and a
scheduler has to touch it directly (via power state) to capture them.

**The cost is real and worth stating plainly, not minimizing:** mean completion latency
rises to 35.7 min (+49% vs. baseline, +25% vs. the plain Green Heuristic) and mean queue
wait nearly triples vs. baseline (19.77 vs. 8.06 min). Two compounding causes: (1) the 70
wake-up events each add a fixed 3-minute delay to whichever task triggered them, and (2)
running with fewer active nodes during ramp-up periods means less spare capacity to absorb
bursts before the scheduler reacts, so some queueing is structural, not just wake-up
overhead. This is the real trade-off the report should discuss: **~10x the energy savings
at roughly 2.5x the mean latency cost**, against a baseline that already breaches SLA on a
third of tasks. Whether that trade is "worth it" depends on which SLA metric matters most to
the stakeholder — worth framing as a discussion point / limitation rather than glossing over
in favour of the strong energy number.

**Figures (evidence):**
- [`figures/active_nodes.png`](figures/active_nodes.png) — the standout figure: powered-on
  node count over the simulated day for all three schedulers. Baseline and Green Heuristic
  are flat at 20 (never power down); Consolidating Green visibly **tracks the diurnal
  curve** — drops to 6 active nodes during the overnight trough (~minutes 40-330), ramps
  back up ahead of the midday peak and both injected spikes (minutes ~380-620), stays fully
  on through the busy period (620-1300), then winds back down toward evening. This single
  chart is probably the strongest visual evidence in the whole project for "the heuristic is
  actually doing something intelligent," and is worth a prominent place in the report.
- [`figures/consolidating_heatmap.png`](figures/consolidating_heatmap.png) — same
  utilization heatmap style as before; the empty (cream) region in the lower-right/upper-left
  triangle visibly corresponds to nodes that are powered off, not merely idle.
- [`figures/scheduler_comparison.png`](figures/scheduler_comparison.png) — regenerated for
  all three schedulers side by side.

**Suggested framing for the FPR:** present the plain Green Heuristic and Consolidating
Green Heuristic as two points on a deliberate design spectrum, not "old version vs. new
version" — the plain heuristic is the more latency-conservative choice, the consolidating
one trades some latency for an order-of-magnitude bigger energy win. Reporting both
(rather than only the best-looking number) demonstrates the kind of critical evaluation a
strong FPR needs.

---

## 2026-08-17 — Sensitivity re-run with the Consolidating scheduler: a more honest picture

**What:** Re-ran both sweeps from the earlier sensitivity analysis (`sensitivity_analysis.py`)
with `ConsolidatingGreenScheduler` added as a third arm, to check whether its headline
10.65%-energy / tied-SLA result at "20 nodes, 1.0x intensity" generalizes, or whether that
scenario happened to be a favourable point. **It does not fully generalize — the energy
trend is clean and monotonic, but the SLA/latency trade-off is genuinely mixed, not
one-directional.** This is a more useful (and more honest) finding than a clean win would
have been.

**Energy savings vs. the plain Green Heuristic (not vs. baseline) — clean, monotonic, and
explained by a single underlying variable (spare capacity relative to load):**

| Node-count sweep (fixed workload) | 14 | 17 | 20 | 25 | 30 |
|---|---|---|---|---|---|
| Consolidating vs. Green Heuristic | -4.6% | -8.2% | -10.4% | -15.3% | **-19.6%** |

| Intensity sweep (fixed 20 nodes) | 0.5x | 0.75x | 1.0x | 1.25x | 1.5x |
|---|---|---|---|---|---|
| Consolidating vs. Green Heuristic | **-27.4%** | -15.0% | -10.4% | -4.6% | -3.8% |

Both trends are two views of the same mechanism: energy savings scale with *how much spare
capacity exists relative to load* — more nodes for a fixed workload, or a lighter workload
for a fixed cluster, both mean more idle time available to reclaim by powering down. This
is a clean, defensible, citable relationship for the report.

**SLA breach rate vs. the plain Green Heuristic — NOT monotonic, mixed sign:**

| Node-count sweep | 14 | 17 | 20 | 25 | 30 |
|---|---|---|---|---|---|
| SLA breach, Consolidating − Green Heuristic (points) | +0.6 | **-2.7** | -0.3 | +1.4 | +2.1 |

| Intensity sweep | 0.5x | 0.75x | 1.0x | 1.25x | 1.5x |
|---|---|---|---|---|---|
| SLA breach, Consolidating − Green Heuristic (points) | **+4.3** | +1.9 | -0.3 | **-1.4** | +4.2 |

The pattern across both sweeps: **consolidation's SLA outcome is comparable-to-better than
the plain heuristic in the middle of the range (17-25 nodes; 0.75x-1.25x intensity), and
measurably worse at both extremes.** The single worst point in the entire sweep is
**0.5x intensity: Consolidating's SLA breach rate (5.2%) is actually worse than the
*baseline Round-Robin's* (2.4%) at that same point** — the one case in the whole project
where the "smart" scheduler is outright worse than doing nothing.

**Why the light-load case breaks it:** at 0.5x intensity, load is sparse enough that nodes
frequently sit empty for the full `EMPTY_STREAK` (30 min) and get powered down, but new
tasks still arrive occasionally — each one has a real chance of landing on a node that then
needs a fresh `WAKE_UP_MIN` (3 min) before it can start. With so few tasks in total (1,596
over the day), that fixed 3-minute tax lands disproportionately often relative to the
(otherwise tiny) queueing delay the baseline would have produced anyway — so the wake-up
overhead, not congestion, becomes the dominant source of SLA breaches. **This is a real
limitation of the current fixed thresholds (`EMPTY_STREAK=6`, `WAKE_UP_MIN=3.0`), not of the
consolidation concept itself** — the same mechanism that saves the most energy in this
regime (aggressive power-down under light load) is exactly what creates the most wake-up
exposure. A scheduler that adapted `EMPTY_STREAK` to observed traffic density (e.g. longer
empty-before-shutdown thresholds when the recent arrival rate is very low) would likely
recover this case, but that's future work, not something built here.

**Figures (evidence):**
- [`figures/sensitivity_node_count.png`](figures/sensitivity_node_count.png) — energy panel
  shows Consolidating Green visibly pulling away from the other two as node count grows
  (they're near-identical; it isn't). Latency/SLA panels show the three lines crossing
  rather than one dominating throughout.
- [`figures/sensitivity_intensity.png`](figures/sensitivity_intensity.png) — mirror-image
  energy trend (gap shrinks as intensity rises); SLA panel shows Consolidating above even
  the baseline at 0.5x — the anomaly described above, clearly visible.

**Recommended framing for the FPR:** don't present the single-scenario 10.65%/tied-SLA
result as if it holds everywhere — present it as the outcome at a representative
mid-range operating point, then use these two sweeps to show (a) the energy benefit's
size is predictable and explained by a clear mechanism (spare capacity), and (b) the SLA
trade-off has a real, characterised failure mode at light load, driven by a specific,
nameable cause (fixed wake-up cost dominating when traffic is sparse) rather than being
mysterious. That's a stronger, more defensible "Limitations" section than simply not
testing the edges would have produced.

---

## 2026-08-17 — Refactor for launchability (no behavior changes)

**What:** the project had grown into several standalone scripts you had to remember to run
in the right order (`run_simulation.py`, then separately `sensitivity_analysis.py`, then
separately `plot_sensitivity.py`), plus a `.venv` set up ad hoc with no pinned dependency
list. Refactored purely for ease of setup/launch — **no simulation logic changed**:

- Added `requirements.txt` (pinned versions) so setup is one command.
- Merged `plot_sensitivity.py` into `sensitivity_analysis.py`'s own `main()` — one command
  now produces both the sweep CSVs and their figures.
- `run_simulation.py` now also generates `power_curve.png`, so a single run produces the
  *complete* evidence set instead of requiring a separate `python -m src.visualize` call.
- Removed the ad hoc 12-node, 2-scheduler comparison in `datacenter.py`'s `__main__` block —
  it was an early smoke test from before `run_simulation.py` existed, had drifted out of
  sync (wrong node count, missing the third scheduler), and risked being mistaken for a
  current result. `power_model.py` and `workload.py` keep their lightweight `__main__`
  self-tests since those stayed accurate and are genuinely useful for quick iteration.
- Added `main.py` as the single command surface: `demo` (narrated, for presenting live),
  `run`, `sensitivity`, `components`.
- Added `README.md` with setup instructions and a live-demo script.

**Verification:** re-ran `demo`, `run`, and `sensitivity` end to end post-refactor — all
numbers reproduce exactly (workload generation is seeded), confirming this was a pure
restructuring with no change to simulation behavior.
