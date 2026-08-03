import os
from collections import defaultdict
import pandas as pd

from src.constants import SLOTS_IN_A_DAY
from src.data_classes import Activity, Employee, EmployeeRosteringInstance


class CSVImporter:
    """Imports and processes CSV data files to build an EmployeeRosteringInstance."""

    @staticmethod
    def time_to_slots(time_str: str) -> int:
        """Converts a time string (HH:MM) into 15-minute time slots."""
        hours, minutes = map(int, time_str.split(':'))
        return (hours * 4) + round(minutes / 15)

    def csv_read(self, folder_path: str, horizon_days: int) -> EmployeeRosteringInstance:
        # Load CSV files
        df_activity = pd.read_csv(os.path.join(folder_path, "Activity.csv"))
        df_compatibility = pd.read_csv(os.path.join(folder_path, "Compatibility.csv"))
        df_demand = pd.read_csv(os.path.join(folder_path, "Demand.csv"))
        df_employee = pd.read_csv(os.path.join(folder_path, "Employee.csv"))
        df_employee_shift = pd.read_csv(os.path.join(folder_path, "EmployeeShift.csv"))
        
        output_dir = os.path.join(folder_path, "debug_output")
        os.makedirs(output_dir, exist_ok=True)

        # --- ACTIVITY PROCESSING ---
        df_full_activity = pd.merge(
            df_activity, 
            df_demand.rename(columns={'activity': 'id'}), 
            on="id"
        ).drop(columns=['group'])
        
        # Calculate default penalty for activities with zero penalty
        positive_penalties = df_full_activity.loc[df_full_activity['penalty'] > 0, 'penalty']
        if not positive_penalties.empty:
            min_pos_penalty = positive_penalties.min()
            # 10 points below the minimum, but at least 1
            penalty_for_zeros = max(1, min_pos_penalty - 10)
        else:
            penalty_for_zeros = 1

        # Time conversions (minutes to 15-min slots, days to relative integers 0..N)
        df_full_activity['demand'] = df_full_activity['demand'] / 15
        df_full_activity['minTime'] = df_full_activity['minTime'] / 15


        raw_dates = pd.to_datetime(df_full_activity['day'], format='%Y%m%d')
        start_date_str = raw_dates.min().strftime("%Y%m%d")  # Salva ad es. "20241021"

        df_full_activity['day'] = pd.to_datetime(df_full_activity['day'], format='%Y%m%d')
        df_full_activity['day'] = (df_full_activity['day'] - df_full_activity['day'].min()).dt.days

        df_full_activity['from'] = (
            df_full_activity['from'].apply(CSVImporter.time_to_slots) 
            + df_full_activity['day'] * SLOTS_IN_A_DAY
        )
        df_full_activity['to'] = (
            df_full_activity['to'].apply(CSVImporter.time_to_slots) 
            + df_full_activity['day'] * SLOTS_IN_A_DAY
        )

        # Activity Splitting Logic
        split_activities_rows = []
        global_counters = {}
        
        for _, row in df_full_activity.iterrows():
            block_size = max(1, int(row['minTime']))
            remaining_demand = int(row['demand'])
            day = int(row['day'])
            original_id = str(row['id']).split('.')[0]

            row_penalty = row['penalty'] if row['penalty'] != 0 else penalty_for_zeros
            counter_key = f"{original_id}_D{day}"
            
            if counter_key not in global_counters:
                global_counters[counter_key] = 0

            while remaining_demand > 0:
                current_block_demand = block_size
                unique_id = f"{original_id}_D{day}_{global_counters[counter_key]}"
                
                new_row = {
                    'uid': unique_id,
                    'original_id': original_id,
                    'activity_day': day,
                    'activity_t1': row['from'],
                    'activity_t2': row['to'],
                    'activity_demand': current_block_demand,
                    'min_time_on_activity': block_size,
                    'penalty': row_penalty
                }
                split_activities_rows.append(new_row)
                remaining_demand -= current_block_demand
                global_counters[counter_key] += 1

        # Convert split rows into Activity objects and export debug CSV
        activities = [Activity(**row) for row in split_activities_rows]
        pd.DataFrame(split_activities_rows).to_csv(
            os.path.join(output_dir, "debug_activities.csv"), index=False
        )

        # --- COMPATIBILITY PROCESSING ---
        df_compatibility = df_compatibility.drop(columns=['group'])
        
        # Build employee preferences dictionary: {activity_id: priority}
        def build_pref_dict(group):
            return dict(zip(group['activity'], group['priority']))

        df_compatibility_prefs = (
            df_compatibility.groupby('employee')
            .apply(build_pref_dict)
            .reset_index()
        )
        df_compatibility_prefs.columns = ['id', 'activity_preferences']

        # List of compatible activity IDs per employee
        df_compatibility_ids = (
            df_compatibility.groupby('employee')['activity']
            .apply(list)
            .reset_index()
            .rename(columns={'employee': 'id'})
        )

        # --- EMPLOYEE AVAILABILITY PROCESSING ---
        df_employee_shift['day'] = pd.to_datetime(df_employee_shift['day'], format='%Y%m%d')
        df_employee_shift['day'] = (df_employee_shift['day'] - df_employee_shift['day'].min()).dt.days
        
        df_employee_shift['from'] = (
            df_employee_shift['from'].apply(CSVImporter.time_to_slots) 
            + df_employee_shift['day'] * SLOTS_IN_A_DAY
        )
        df_employee_shift['to'] = (
            df_employee_shift['to'].apply(CSVImporter.time_to_slots) 
            + df_employee_shift['day'] * SLOTS_IN_A_DAY
        )
        
        # Group availabilities as [day, from_slot, to_slot] tuples
        df_employee_shift['avail_tuple'] = df_employee_shift.apply(
            lambda x: [int(x['day']), int(x['from']), int(x['to'])], axis=1
        )
        df_availability_grouped = (
            df_employee_shift.groupby('id')['avail_tuple']
            .apply(list)
            .reset_index()
            .rename(columns={'avail_tuple': 'availabilities'})
        )

        # --- FULL EMPLOYEE PROCESSING ---
        # Convert hours to 15-minute slots
        df_employee['dailyWorkingHours'] *= 4
        df_employee['weeklyWorkingHours'] *= 4
        df_employee['maxShiftSpan'] *= 4
        df_employee['lastWorkingHour'] = (
            df_employee['lastWorkingHour']
            .fillna("00:00")
            .apply(CSVImporter.time_to_slots)
        )

        df_full_employee = (
            df_employee
            .merge(df_availability_grouped, on="id", how="left")
            .merge(df_compatibility_prefs, on="id", how="left")
            .merge(df_compatibility_ids, on="id", how="left")
        )

        df_full_employee = df_full_employee.rename(columns={
            'id': 'uid',
            'available_shifts': 'available_shifts',
            'activity': 'possible_activities',
            'dailyWorkingHours': 'max_daily_time',
            'weeklyWorkingHours': 'max_weekly_time',
            'workingDays': 'max_work_days_horizon',
            'maxConsecutiveWorkingDays': 'max_consecutive_work_days',
            'minRestBetweenDays': 'min_time_between_shifts',
            'daysSinceLastOff': 'days_since_last_off',
            'maxShiftSpan': 'max_daily_span',
            'lastWorkingHour': 'last_working_hour'
        })

        # Map original activity IDs to their corresponding split Activity objects
        activity_lookup = defaultdict(list)
        for act in activities:
            activity_lookup[act.original_id].append(act)

        def explode_activities(original_id_list):
            if not isinstance(original_id_list, list):
                return []
            all_splits = []
            for aid in original_id_list:
                if aid in activity_lookup:
                    all_splits.extend(activity_lookup[aid])
            return all_splits

        df_full_employee['possible_activities'] = (
            df_full_employee['possible_activities'].apply(explode_activities)
        )

        df_full_employee.to_csv(os.path.join(output_dir, "debug_employees.csv"), index=False)
        employees = [Employee(**row) for row in df_full_employee.to_dict('records')]

        return EmployeeRosteringInstance(
            employees=employees, 
            activities=activities, 
            horizon_days=horizon_days,
            start_date=start_date_str  
        )