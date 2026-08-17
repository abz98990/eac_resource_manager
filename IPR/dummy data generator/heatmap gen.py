import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Set a professional visual theme for all plots
sns.set_theme(style="whitegrid", palette="muted")

def generate_power_curve_plot():
    """
    Generates a line graph showing how server power consumption spikes
    exponentially after reaching an 80-85% CPU load.
    """
    print("Generating Non-Linear Power Curve Graph...")

    # Create an array of CPU load percentages from 0% to 100%
    cpu_load = np.linspace(0, 100, 500)

    # Base idle power consumption (e.g., 50 Watts just to stay on)
    idle_power = 50

    # Calculate power: Linear growth up to a point, then exponential spike
    # This represents the cooling fans and thermal inefficiencies kicking in
    power_draw = idle_power + (cpu_load * 1.5) # Linear base

    # Apply the exponential "Redline Penalty" for CPU loads over 80%
    redline_mask = cpu_load > 80
    power_draw[redline_mask] += np.exp((cpu_load[redline_mask] - 80) * 0.28)

    plt.figure(figsize=(10, 6))
    plt.plot(cpu_load, power_draw, color='#d62728', linewidth=3, label='Power Draw (Watts)')

    # Highlight the 85% SLA/Efficiency Sweet Spot boundary
    plt.axvline(x=85, color='#ff7f0e', linestyle='--', linewidth=2, label='85% Constraint Threshold')
    plt.axvspan(0, 75, color='#2ca02c', alpha=0.1, label='Target Efficiency "Sweet Spot"')
    plt.axvspan(85, 100, color='#d62728', alpha=0.1, label='Thermal Redline Penalty Zone')

    plt.title("Mathematical Model: Non-Linear Server Power Scaling", fontsize=16, pad=15)
    plt.xlabel("CPU Load (%)", fontsize=12)
    plt.ylabel("Power Consumption (Watts)", fontsize=12)
    plt.legend(loc='upper left', fontsize=11)

    # Save the figure to the current directory
    filename = "fig_1_power_curve.png"
    plt.tight_layout()
    plt.savefig(filename, dpi=300)
    plt.close()
    print(f"Success! Saved as {filename}")

def generate_heatmap_plot():
    """
    Generates a sample Seaborn heatmap representing what the final simulation
    throughput logs will look like across multiple server nodes.
    """
    print("Generating Expected Resource Utilization Heatmap...")

    # Define our simulated environment dimensions
    num_servers = 12
    time_steps = 24

    # Generate baseline dummy data (servers running comfortably between 30% and 70%)
    utilization_data = np.random.uniform(30, 70, size=(num_servers, time_steps))

    # Inject some "Redline" anomalies (simulating task load spikes)
    utilization_data[2, 14:18] = np.random.uniform(92, 99, size=4) # Server 3 spiked
    utilization_data[8, 5:9] = np.random.uniform(88, 96, size=4)  # Server 9 spiked

    # Inject some "Idle" anomalies (servers that should be powered down)
    utilization_data[5, :] = np.random.uniform(5, 15, size=time_steps)

    plt.figure(figsize=(12, 6))

    # Use a color map that visually warns of high heat (Yellow to Orange to Red)
    ax = sns.heatmap(
        utilization_data,
        cmap="YlOrRd",
        cbar_kws={'label': 'CPU Utilization (%)'},
        linewidths=0.5,
        vmin=0, vmax=100
    )

    plt.title("Expected Output: Datacenter Resource Utilization Heatmap", fontsize=16, pad=15)
    plt.xlabel("Simulation Time-Steps", fontsize=12)
    plt.ylabel("Server Node ID", fontsize=12)

    # Make node IDs 1-indexed for readability
    ax.set_yticklabels([f"Node {i+1}" for i in range(num_servers)], rotation=0)

    # Save the figure
    filename = "fig_2_expected_heatmap.png"
    plt.tight_layout()
    plt.savefig(filename, dpi=300)
    plt.close()
    print(f"Success! Saved as {filename}")

if __name__ == "__main__":
    print("--- Starting Visual Aids Generation ---")
    generate_power_curve_plot()
    generate_heatmap_plot()
    print("--- Process Complete! Check your folder for the PNG files. ---")
