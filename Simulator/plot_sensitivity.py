import pandas as pd

from src import visualize

node_df = pd.read_csv("data/sensitivity_node_count.csv")
intensity_df = pd.read_csv("data/sensitivity_intensity.csv")

print("Saved:", visualize.plot_sensitivity(
    node_df, "num_nodes", "Number of Nodes",
    "Sensitivity to Cluster Size (fixed workload)", "sensitivity_node_count.png",
))
print("Saved:", visualize.plot_sensitivity(
    intensity_df, "intensity_multiplier", "Workload Intensity Multiplier",
    "Sensitivity to Workload Intensity (fixed 20 nodes)", "sensitivity_intensity.png",
))
