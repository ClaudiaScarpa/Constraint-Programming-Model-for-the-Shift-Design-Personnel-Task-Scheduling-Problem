from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

from scripts.output_comparison import slots_to_time
from src.constants import SLOTS_IN_A_DAY


def save_to_excel(solver, folder: str = "outputs/rostering", base_filename: str = "pianificazione") -> Path:
    """Exports comprehensive solution metrics, schedules, saturation details, and KPIs to an Excel workbook."""
    sol = solver.solver
    target_path = Path(folder).resolve()
    target_path.mkdir(parents=True, exist_ok=True)
    
    pref_scale = getattr(solver, 'preference_scale', 1)

    # --- 1. EXTRACT SCHEDULE AND SATURATION ROWS ---
    rows_pianificazione = []
    shift_saturation_rows = []

    for r in solver.employees:
        for d in solver.days:
            if not sol.boolean_value(solver.employee_isworking_dict[r.uid, d]):
                continue

            raw_start = sol.value(solver.employee_start_shift[r.uid, d])
            raw_end = sol.value(solver.employee_end_shift[r.uid, d])
            
            start_str = slots_to_time(raw_start % SLOTS_IN_A_DAY)
            end_str = slots_to_time(raw_end % SLOTS_IN_A_DAY)
            total_shift_duration = raw_end - raw_start

            # Add SHIFT entry
            rows_pianificazione.append({
                'Employee_ID': r.uid, 'Day': d, 'Type': 'SHIFT', 'ID': '--',
                'Start': start_str, 'End': end_str,
                'Duration_Slots': total_shift_duration, 'Preference': '--',
                'sort_key': raw_start, 'type_priority': 0
            })
                
            # Add ACTIVITY entries
            working_dur = 0
            for a in r.possible_activities:
                if a.activity_day == d and sol.boolean_value(solver.employee_activities_dict[r.uid, a]):
                    info = solver.activity_info_dict[r.uid, a]
                    v_start = sol.value(info["start"])
                    v_end = sol.value(info["end"])
                    actual_duration = sol.value(info["duration"])
                    pref_val = r.activity_preferences.get(a.original_id, 0)

                    working_dur += actual_duration
                    if actual_duration > 0:
                        rows_pianificazione.append({
                            'Employee_ID': r.uid, 'Day': d, 'Type': '  ACTIVITY', 
                            'ID': f"{a.original_id}", 
                            'Start': slots_to_time(v_start % SLOTS_IN_A_DAY),
                            'End': slots_to_time(v_end % SLOTS_IN_A_DAY), 
                            'Duration_Slots': actual_duration, 'Preference': pref_val,
                            'sort_key': v_start, 'type_priority': 1
                        })

            # Add BREAK entries
            total_break_dur = 0
            for i, b in enumerate(solver.break_info_dict.get((r.uid, d), [])):
                if sol.boolean_value(b["presence"]):
                    total_break_dur += b["duration"]
                    rows_pianificazione.append({
                        'Employee_ID': r.uid, 'Day': d, 'Type': '  BREAK', 'ID': f"{i}",
                        'Start': slots_to_time(sol.value(b["start"]) % SLOTS_IN_A_DAY),
                        'End': slots_to_time(sol.value(b["end"]) % SLOTS_IN_A_DAY),
                        'Duration_Slots': b["duration"], 'Preference': '--',
                        'sort_key': sol.value(b["start"]), 'type_priority': 1
                    })
                    
            # Compute Net Shift (excluding breaks)
            net_dur = total_shift_duration - total_break_dur
            sat_perc = (working_dur / net_dur * 100) if net_dur > 0 else 0
            
            shift_saturation_rows.append({
                'Employee_ID': r.uid, 'Day': d, 
                'Start_Shift': start_str, 'End_Shift': end_str,
                'Total_Shift_Duration': total_shift_duration,
                'Break_Duration': total_break_dur,
                'Net_Shift_Duration': net_dur,
                'Activities_Duration': working_dur,
                'Idle_Slots': net_dur - working_dur,
                'Saturation_Percentage': round(sat_perc, 2)
            })

    # --- 2. EXTRACT UNMET DEMAND STATUS ---
    activities_status_list = []
    for a in solver.activities:
        presence_vars = [
            solver.employee_activities_dict[r.uid, a] 
            for r in solver.employees if (r.uid, a) in solver.employee_activities_dict
        ]
        is_assigned = sum(sol.value(v) for v in presence_vars)
        u_val = a.activity_demand if is_assigned == 0 else 0
        s_val = a.activity_demand if is_assigned == 1 else 0

        activities_status_list.append({
            'uid': a.original_id, 'activity_day': a.activity_day, 
            'activity_demand': a.activity_demand,
            'satisfied': s_val, 'unmet': u_val, 
            'penalty_weight': a.penalty,
            'weighted_unmet_cost': u_val * a.penalty,
            'activity_t1': slots_to_time(a.activity_t1 % SLOTS_IN_A_DAY),
            'activity_t2': slots_to_time(a.activity_t2 % SLOTS_IN_A_DAY) if a.activity_t2 % SLOTS_IN_A_DAY != 0 else "23:59"
        })

    df_act_res = pd.DataFrame(activities_status_list)
    df_sat_details = pd.DataFrame(shift_saturation_rows)

    # --- 3. COMPUTE GLOBAL KPIS AND BOUNDS ---
    tot_demand = df_act_res['activity_demand'].sum()
    tot_unmet = df_act_res['unmet'].sum()
    tot_satisfied = tot_demand - tot_unmet
    tot_penalty_cost = df_act_res['weighted_unmet_cost'].sum()

    tot_preference = 0
    total_worked_slots = 0
    for r in solver.employees:
        for a in r.possible_activities:
            if (r.uid, a) in solver.employee_activities_dict:
                if sol.boolean_value(solver.employee_activities_dict[r.uid, a]):
                    pref = r.activity_preferences.get(a.original_id, 0)
                    dur = solver.activity_info_dict[r.uid, a]["duration"]
                    tot_preference += (pref * dur)
                    total_worked_slots += dur

    avg_preference = (tot_preference / total_worked_slots) if total_worked_slots > 0 else 0
    objective_value = tot_penalty_cost + tot_preference

    unmet_impact = (tot_penalty_cost / objective_value * 100) if abs(objective_value) > 1e-6 else 0
    pref_impact = (tot_preference / objective_value * 100) if abs(objective_value) > 1e-6 else 0

    # Bound and Gap calculations
    raw_bound_unmet = getattr(solver, 'bound_unmet', 0)
    raw_bound_prefs_scaled = getattr(solver, 'bound_prefs', 0)
    real_bound_prefs = abs(raw_bound_prefs_scaled) / pref_scale
    
    best_bound = max(0, raw_bound_unmet + real_bound_prefs)
    
    gap_unmet = (abs(tot_penalty_cost - raw_bound_unmet) / tot_penalty_cost * 100) if tot_penalty_cost > 1e-6 else 0
    gap_prefs = (abs(tot_preference - real_bound_prefs) / tot_preference * 100) if tot_preference > 1e-6 else 0
    gap = (abs(objective_value - best_bound) / objective_value * 100) if abs(objective_value) > 1e-6 else 0

    total_unique_employees = df_sat_details['Employee_ID'].nunique() if not df_sat_details.empty else 0
    avg_shift_saturation = df_sat_details['Saturation_Percentage'].mean() if not df_sat_details.empty else 0
    total_idle_slots = df_sat_details['Idle_Slots'].sum() if not df_sat_details.empty else 0
    execution_time_seconds = getattr(solver, 'total_time', sol.wall_time())
    
    df_global = pd.DataFrame([
        {'Metric': 'Objective Value (Real)', 'Value': round(objective_value, 3)},
        {'Metric': 'Best Bound (Real)', 'Value': round(best_bound, 3)},
        {'Metric': 'Gap (%)', 'Value': f"{round(gap, 4)}%"},
        {'Metric': 'Execution Time (s)', 'Value': round(execution_time_seconds, 3)},
        {'Metric': '---', 'Value': '---'},
        {'Metric': 'Total Demand (slots)', 'Value': tot_demand},
        {'Metric': 'Satisfied slots', 'Value': tot_satisfied},
        {'Metric': 'Coverage % Global', 'Value': f"{round((tot_satisfied / tot_demand) * 100, 2)}%" if tot_demand else "0%"},
        {'Metric': '---', 'Value': '---'},
        {'Metric': 'Cost from Unmet Demand', 'Value': tot_penalty_cost},
        {'Metric': 'Bound: Unmet Demand', 'Value': round(raw_bound_unmet, 2)},
        {'Metric': 'Gap: Unmet Demand (%)', 'Value': f"{round(gap_unmet, 4)}%"},
        {'Metric': 'Impact: Unmet Demand (%)', 'Value': f"{round(unmet_impact, 2)}%"}, 
        {'Metric': 'Cost from Preferences (raw)', 'Value': round(tot_preference, 3)},
        {'Metric': 'Bound: Preferences', 'Value': round(real_bound_prefs, 2)},
        {'Metric': 'Gap: Preferences (%)', 'Value': f"{round(gap_prefs, 4)}%"},
        {'Metric': 'Impact: Preferences (%)', 'Value': f"{round(pref_impact, 2)}%"},  
        {'Metric': '---', 'Value': '---'},
        {'Metric': 'Average Preference Score', 'Value': round(avg_preference, 3)},
        {'Metric': 'Average Shift Saturation', 'Value': f"{round(avg_shift_saturation, 2)}%"},
        {'Metric': 'Total Idle Time (slots)', 'Value': total_idle_slots}, 
        {'Metric': 'Total Employees', 'Value': total_unique_employees}
    ])

    history_rows = []
    if hasattr(solver, 'history_kpis'):
        for entry in solver.history_kpis:
            history_rows.append({
                'Step': entry['Step'],
                'Duration (s)': round(entry.get('Duration', 0), 2), 
                'Unmet Cost': entry['Unmet_Cost'],
                'Preferences (Real)': round(entry['Prefs_Raw'], 2),
                'Idle Time (Slots)': entry['Idle_Slots']
            })
    df_history = pd.DataFrame(history_rows)

    # --- 4. EXPORT TO EXCEL ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_path = target_path / f"{base_filename}_{timestamp}.xlsx"
    
    with pd.ExcelWriter(full_path, engine='openpyxl') as writer:
        df_raw = pd.DataFrame(rows_pianificazione)
        if not df_raw.empty:
            cols_to_show = [
                'Employee_ID', 'Day', 'Type', 'ID', 
                'Start', 'End', 'Duration_Slots', 'Preference'
            ]
            df_sorted = df_raw.sort_values(['Employee_ID', 'Day', 'type_priority', 'sort_key'])
            df_sorted[cols_to_show].to_excel(writer, sheet_name='Rostering', index=False)

        df_act_res[df_act_res['unmet'] > 0].to_excel(writer, sheet_name='Unmet demand', index=False)
        df_sat_details.to_excel(writer, sheet_name='Saturation_Details', index=False)
        df_global.to_excel(writer, sheet_name='Global_KPIs', index=False)
        df_history.to_excel(writer, sheet_name='Lexicographic_Steps', index=False)

    print(f"--- Report Generated: {full_path.name} (Gap: {gap:.4f}%) ---")
    return full_path


def save_to_csv(
    solver, 
    folder: str = "outputs/rostering", 
    filename: str = "solution.csv"
) -> Path:
    """Exports assigned activities to a structured CSV file mapped to actual calendar dates."""
    sol = solver.solver
    target_path = Path(folder).resolve()
    target_path.mkdir(parents=True, exist_ok=True)
    
    # Retrieve the real start date from the instance (fallback to default if not set)
    start_date_str = getattr(solver.instance, 'start_date', "20241021")
    start_dt = datetime.strptime(start_date_str, "%Y%m%d")
    
    rows_activities = []
    
    for r in solver.employees:
        for d in solver.days:
            real_date = (start_dt + timedelta(days=int(d))).strftime("%Y%m%d")
            
            if sol.boolean_value(solver.employee_isworking_dict[r.uid, d]):
                for a in r.possible_activities:
                    if a.activity_day == d and sol.boolean_value(solver.employee_activities_dict[r.uid, a]):
                        info = solver.activity_info_dict[r.uid, a]
                        
                        start_str = slots_to_time(sol.value(info["start"]) % SLOTS_IN_A_DAY)
                        end_str = slots_to_time(sol.value(info["end"]) % SLOTS_IN_A_DAY)
                        
                        rows_activities.append({
                            'employee': r.uid,
                            'activity': a.original_id,
                            'day': real_date,
                            'from': start_str,
                            'to': end_str
                        })

    df_output = pd.DataFrame(rows_activities)
    
    if not df_output.empty:
        df_output = df_output.sort_values(['employee', 'day', 'from'])
    
    full_path = target_path / filename
    df_output.to_csv(full_path, index=False, sep=',')
    
    print(f"--- CSV Output Created: {full_path.name} ---")
    return full_path