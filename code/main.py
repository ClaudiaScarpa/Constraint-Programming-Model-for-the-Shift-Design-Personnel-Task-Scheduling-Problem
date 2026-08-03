import os
from datetime import datetime
import matplotlib.pyplot as plt
import pandas as pd

from src.input import CSVImporter
from src.output import save_to_csv, save_to_excel
from src.solver import EmployeeSolver


def plot_convergence(df: pd.DataFrame, filename: str = "convergence_plot.png") -> None:
    """Generates and saves a convergence plot comparing Best Solution and Best Bound over time."""
    plt.figure(figsize=(11, 5))
    df_plot = df.copy()

    # Convergence Curves
    plt.step(
        df_plot['Time'],
        df_plot['BestSolution'],
        where='post',
        label='Best Solution',
        linewidth=2.5
    )

    plt.plot(
        df_plot['Time'],
        df_plot['BestBound'],
        '--',
        label='Best Bound',
        linewidth=2.5
    )

    # Linear scale configuration
    plt.yscale('linear')

    # Dynamic y-axis scaling with balanced padding
    ymin = min(df_plot['BestBound'].min(), df_plot['BestSolution'].min())
    ymax = max(df_plot['BestSolution'].max(), df_plot['BestBound'].max())
    padding = (ymax - ymin) * 0.1 if ymax > ymin else 1.0
    
    plt.ylim(ymin - padding, ymax + padding)

    # Labels and Formatting
    plt.xlabel('Execution time (seconds)', fontsize=18)
    plt.ylabel('Objective value', fontsize=18)
    plt.tick_params(axis='both', which='major', labelsize=14)
    plt.ticklabel_format(style='sci', axis='y', scilimits=(0, 0))
    plt.legend(fontsize=15)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    # Save Plot
    os.makedirs('plots', exist_ok=True)
    save_path = os.path.join('plots', filename)
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()  # Free memory instead of blocking with plt.show() in batch runs


def main() -> None:
    # Set input path (using relative paths for portability)
    input_folder = os.path.join("data_io", "input_csv", "PV_Grande")
    horizon_days = 7

    # Data Import
    importer = CSVImporter()
    instance = importer.csv_read(input_folder, horizon_days=horizon_days)

    # Solver Setup
    solver = EmployeeSolver(instance)
    solver.create_model()

    solver.solver.parameters.log_search_progress = True
    solver.model.export_to_file('model.txt')

    # Execute Lexicographic Optimization
    if solver.solve_lexicographic():
        print("\nSUCCESS: Optimal or feasible solution found.")
        save_to_excel(solver, folder="outputs/rostering")
        save_to_csv(solver, folder="outputs/rostering")
        
        raw_data = solver.recorder.get_data() 
        df = pd.DataFrame(raw_data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 1. UNMET DEMAND PLOT
        df_unmet = df[df['Step'] == "Unmet Demand"].copy()
        if not df_unmet.empty:
            plot_convergence(df_unmet, filename=f"convergence_unmet_{timestamp}.png")

        # 2. PREFERENCES PLOT
        df_prefs = df[df['Step'] == "Preferences"].copy()
        if not df_prefs.empty:
            scale = getattr(solver, 'preference_scale', 1)
            df_prefs['BestSolution'] /= scale
            df_prefs['BestBound'] /= scale
            plot_convergence(df_prefs, filename=f"convergence_preferences_{timestamp}.png")

        # 3. IDLE TIME PLOT
        df_idle = df[df['Step'] == "Idle Time"].copy()
        if not df_idle.empty:
            plot_convergence(df_idle, filename=f"convergence_idle_{timestamp}.png")
            
    else:
        print("\nFAIL: No feasible solution found.")


if __name__ == "__main__":
    main()