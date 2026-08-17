import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

def generate_gantt_chart():
    print("Generating Project Gantt Chart...")

    # Define the tasks, their start weeks, duration in weeks, and status colors
    # Status: Completed (Green), In Progress (Blue), Pending (Gray)
    tasks = [
        {"name": "Task 1: Lit Review & Power Modeling", "start": 0, "duration": 3, "color": "#2ca02c"}, 
        {"name": "Task 2: Baseline SimPy & Data Gen", "start": 3, "duration": 2, "color": "#2ca02c"},
        {"name": "Task 3: Code Constraint Engine", "start": 5, "duration": 3, "color": "#1f77b4"},
        {"name": "Task 4: Simulation & Data Extraction", "start": 8, "duration": 2, "color": "#7f7f7f"},
        {"name": "Task 5: Data Visualization & Analysis", "start": 10, "duration": 1, "color": "#7f7f7f"},
        {"name": "Task 6: Final Report Formatting", "start": 11, "duration": 1, "color": "#7f7f7f"}
    ]

    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot each task as a horizontal bar
    for i, task in enumerate(tasks):
        # We use len(tasks) - i to plot the first task at the top
        y_pos = len(tasks) - i 
        ax.barh(y_pos, task["duration"], left=task["start"], height=0.5, align='center', color=task["color"], edgecolor='black')
        # Add a text label inside/next to the bar for duration
        ax.text(task["start"] + task["duration"]/2, y_pos, f"{task['duration']} wks", 
                ha='center', va='center', color='white', fontweight='bold', fontsize=10)

    # Format the Y-axis
    ax.set_yticks(range(1, len(tasks) + 1))
    ax.set_yticklabels([task["name"] for task in reversed(tasks)], fontsize=11)

    # Format the X-axis (Weeks 1 to 12)
    ax.set_xticks(range(0, 13))
    ax.set_xticklabels([f"Wk {i}" if i > 0 else "" for i in range(0, 13)])
    ax.set_xlabel("Project Timeline (Weeks)", fontsize=12, fontweight='bold', labelpad=10)
    
    # Add a vertical line to indicate the "Current" point in time (End of Week 5 / Start of Week 6)
    ax.axvline(x=5, color='red', linestyle='--', linewidth=2, label="Current Progress (Mid-July)")

    # Create a custom legend
    comp_patch = mpatches.Patch(color='#2ca02c', label='Completed')
    prog_patch = mpatches.Patch(color='#1f77b4', label='In Progress')
    pend_patch = mpatches.Patch(color='#7f7f7f', label='Pending')
    curr_line = plt.Line2D([0], [0], color='red', linestyle='--', linewidth=2, label='Current Date')
    ax.legend(handles=[comp_patch, prog_patch, pend_patch, curr_line], loc='upper right', fontsize=10)

    # Title and grid
    plt.title("Project Plan: 12-Week Gantt Chart", fontsize=16, fontweight='bold', pad=15)
    ax.xaxis.grid(True, linestyle='--', alpha=0.6)
    
    # Layout adjustment and save
    plt.tight_layout()
    filename = "fig_3_gantt_chart.png"
    plt.savefig(filename, dpi=300)
    plt.close()
    
    print(f"Success! Saved as {filename}")

if __name__ == "__main__":
    generate_gantt_chart()