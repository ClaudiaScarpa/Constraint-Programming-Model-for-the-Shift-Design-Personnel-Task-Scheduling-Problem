import math
import time
from collections import defaultdict
from fractions import Fraction
from ortools.sat.python import cp_model

from src.constants import (
    MAX_BREAKS_IN_A_DAY,
    MAX_TIME_BEFORE_BREAK,
    MIN_BREAK_DUR,
    MIN_TIME_AFTER_BREAK,
    SLOTS_IN_A_DAY,
)
from src.data_classes import EmployeeRosteringInstance


class ProgressRecorder(cp_model.CpSolverSolutionCallback):
    """Callback to record solver progress metrics over time."""

    def __init__(self):
        super().__init__()
        self._data = []
        self._start_time = time.time()
        self.current_step_name = "Unmet Demand"  # Initial default step

    def on_solution_callback(self):
        self._data.append({
            'Step': self.current_step_name,
            'Time': self.WallTime(),
            'BestSolution': self.ObjectiveValue(),
            'BestBound': self.BestObjectiveBound()
        })

    def get_data(self) -> list[dict]:
        return self._data


class EmployeeSolver:
    """CP-SAT Constraint Programming Solver for Employee Rostering Problems."""

    def __init__(self, instance: EmployeeRosteringInstance):
        # CP model and solver initialization
        self.model = cp_model.CpModel() 
        self.solver = cp_model.CpSolver()

        # Problem Instance Data
        self.instance = instance
        self.employees = instance.employees
        self.activities = instance.activities
        self.days = range(instance.horizon_days)
        self.all_vars = []

        # Internal Data Structures / Dictionaries for Variables
        self.employee_start_shift = {}
        self.employee_end_shift = {}
        self.employee_activities_dict = {}
        self.employee_isworking_dict = {}
        self.daily_activities = {}
        self.activity_info_dict = {}
        self.break_info_dict = {}
        self.constr_one_employee_per_activity = {}
        self.is_unmet = {}
        self.constr_max_daily_span = {}

    def create_model(self) -> None:
        """Builds all variables, constraints, and objective function into the CP Model."""
        # Variables Construction
        self._build_employee_activity_assignment()
        self._build_info_activities()
        self._build_employee_isworking()
        self._build_employee_start_end_time()
        self._build_info_break()

        # Constraints Construction
        self._build_shift_limits()
        self._build_activity_by_one_employee()
        self._build_temporal_consistency()
        self._build_no_overlap()
        self._build_constraints_on_breaks()
        self._build_max_daily_and_weekly_time()
        self._build_max_consecutive_days()
        self._build_rest_between_consecutive_shifts()
        self._build_max_total_days()
        self._build_max_daily_span()
        self._build_demand_satisfaction_constraints()
        self._build_redundant_constraints()

        # Objective Function
        self._build_objective()

# -----------------------------------------------------------------------------
# VARIABLES
# -----------------------------------------------------------------------------

    def _build_employee_start_end_time(self) -> None:
        """Creates shift start and end time variables based on employee daily availability windows."""
        for r in self.employees:
            avail_limits = {day: (s, e) for day, s, e in r.availabilities}
                
            for d in self.days:
                # If unavailable on day d, bounds fall back to (0, 0)
                first_avail, last_avail = avail_limits.get(d, (0, 0))              
                
                s_var = self.model.new_int_var(first_avail, last_avail, f'start_shift_{r.uid}_{d}')
                e_var = self.model.new_int_var(first_avail, last_avail, f'end_shift_{r.uid}_{d}')
                
                self.employee_start_shift[r.uid, d] = s_var
                self.employee_end_shift[r.uid, d] = e_var
                self.all_vars.extend([s_var, e_var])

    def _build_employee_activity_assignment(self) -> None:
        """Creates boolean variables indicating whether employee r is assigned to activity a."""
        for r in self.employees:
            for a in r.possible_activities:
                act_var = self.model.new_bool_var(f"act_r{r.uid}_a{a.uid}")
                self.employee_activities_dict[r.uid, a] = act_var
                self.all_vars.append(act_var)

    def _build_employee_isworking(self) -> None:
        """Creates boolean variables indicating whether employee r works on day d."""
        for r in self.employees:
            for d in self.days:
                work_var = self.model.new_bool_var(f"isworking_r{r.uid}_d{d}")
                self.employee_isworking_dict[r.uid, d] = work_var
                self.all_vars.append(work_var)
        
                self.daily_activities[r.uid, d] = [
                    self.employee_activities_dict[r.uid, a] 
                    for a in r.possible_activities if a.activity_day == d
                ]

                if not self.daily_activities[r.uid, d]:
                    self.model.add(self.employee_isworking_dict[r.uid, d] == 0)
                else:
                    self.model.add_max_equality(
                        self.employee_isworking_dict[r.uid, d], 
                        self.daily_activities[r.uid, d]
                    )

    def _build_info_activities(self) -> None:
        """Defines optional intervals, start, end, and presence variables for assigned activities."""
        for r in self.employees:
            for a in r.possible_activities:
                presence_var = self.employee_activities_dict[r.uid, a]
                duration = a.activity_demand

                real_latest_start = a.activity_t2 - duration
                if real_latest_start < a.activity_t1:
                    # Activity does not fit the timeframe: force presence to 0
                    self.model.add(presence_var == 0)
                    latest_start_for_var = a.activity_t1
                else:
                    latest_start_for_var = real_latest_start

                start_var = self.model.new_int_var(a.activity_t1, latest_start_for_var, f"start_r{r.uid}_act{a.uid}")

                interval_var = self.model.new_optional_interval_var(
                    start_var, 
                    duration, 
                    start_var + duration, 
                    presence_var, 
                    f"interval_r{r.uid}_act{a.uid}"
                )

                self.activity_info_dict[r.uid, a] = {
                    "interval": interval_var,
                    "start": start_var,
                    "end": start_var + duration,
                    "duration": duration,
                    "presence": presence_var,
                }
                self.all_vars.append(start_var)

    def _build_info_break(self) -> None:
        """Creates variables and optional interval structures for break periods within shifts."""
        for r in self.employees:
            avail_limits = {day: (s, e) for day, s, e in r.availabilities}
            max_possible_breaks = (r.max_daily_span // MAX_TIME_BEFORE_BREAK) + 1
            max_breaks_per_day = min(max_possible_breaks, MAX_BREAKS_IN_A_DAY)

            for d in self.days:
                first_avail, last_avail = avail_limits.get(d, (0, 0))
                self.break_info_dict[r.uid, d] = []

                for i in range(max_breaks_per_day):
                    p_var = self.model.new_bool_var(f"break_pres_r{r.uid}_d{d}_i{i}")
                    b_start = self.model.new_int_var(first_avail, last_avail, f"brk_start_{r.uid}_{d}_{i}")
                    b_end = self.model.new_int_var(first_avail, last_avail, f"brk_end_{r.uid}_{d}_{i}")
                                        
                    # If break is absent, end time matches start time
                    self.model.add(b_end == b_start).only_enforce_if(p_var.Not())

                    b_interval = self.model.new_optional_interval_var(
                        b_start,  
                        MIN_BREAK_DUR, 
                        b_end,
                        p_var, 
                        f"brk_interval_{r.uid}_{d}_{i}"
                    )

                    self.break_info_dict[r.uid, d].append({
                        "interval": b_interval,
                        "start": b_start,
                        "end": b_end,
                        "presence": p_var,
                        "duration": MIN_BREAK_DUR
                    })

                    self.all_vars.extend([p_var, b_start, b_end])

    def _build_shift_limits(self) -> None:
        """Constrains shift bounds using tighter domain cuts and effective working duration."""
        for r in self.employees:
            avail_limits = {day: (s, e) for day, s, e in r.availabilities}
            for d in self.days:
                is_working = self.employee_isworking_dict[r.uid, d]
                s_shift = self.employee_start_shift[r.uid, d]
                e_shift = self.employee_end_shift[r.uid, d]
                
                day_acts = [a for a in r.possible_activities if a.activity_day == d]
                if not day_acts: 
                    self.model.add(is_working == 0)
                    continue

                first_avail, _ = avail_limits.get(d, (0, 0))

                # --- DOMAIN PRUNING ---
                # Shift cannot start before earliest activity or end after latest possible activity
                min_t1 = min(a.activity_t1 for a in day_acts)
                max_t2 = max(a.activity_t2 for a in day_acts)
                
                self.model.add(s_shift >= min_t1).only_enforce_if(is_working)
                self.model.add(e_shift <= max_t2).only_enforce_if(is_working)

                # --- GEOMETRIC LINKING (Prunes search space) ---
                # Shift span (end - start) must at least cover total assigned workload duration
                effective_work = sum(
                    self.activity_info_dict[r.uid, a]["duration"] * self.employee_activities_dict[r.uid, a] 
                    for a in day_acts
                )
                self.model.add(e_shift - s_shift >= effective_work).only_enforce_if(is_working)

                # Reset shifts when not working
                self.model.add(s_shift == first_avail).only_enforce_if(is_working.Not())
                self.model.add(e_shift == first_avail).only_enforce_if(is_working.Not())              

# -----------------------------------------------------------------------------
# CONSTRAINTS
# -----------------------------------------------------------------------------

    def _build_consistency_activity_isworking(self) -> None:
        """Ensures working status matches active assigned activities per day."""
        for r in self.employees:
            for d in self.days:
                if not self.daily_activities[r.uid, d]:
                    self.model.add(self.employee_isworking_dict[r.uid, d] == 0)
                else:
                    self.model.add_max_equality(
                        self.employee_isworking_dict[r.uid, d], 
                        self.daily_activities[r.uid, d]
                    )

    def _build_activity_by_one_employee(self) -> None:
        """Ensures each activity is assigned to exactly one employee or marked as unmet."""
        for a in self.activities:
            vars_for_act = [
                self.employee_activities_dict[r.uid, a]
                for r in self.employees 
                if (r.uid, a) in self.employee_activities_dict
            ]
            
            self.is_unmet[a] = self.model.new_bool_var(f"unmet_bool_a{a.uid}")
            self.constr_one_employee_per_activity[a] = self.model.add_exactly_one(
                vars_for_act + [self.is_unmet[a]]
            )

    def _build_temporal_consistency(self) -> None:
        """Enforces that assigned activities fit strictly within the employee's shift boundaries."""
        for r in self.employees:
            for d in self.days:
                daily_acts = [a for a in r.possible_activities if a.activity_day == d]
                for a in daily_acts:
                    info_act = self.activity_info_dict[r.uid, a]
                    self.model.add(
                        info_act["start"] >= self.employee_start_shift[r.uid, d]
                    ).only_enforce_if(info_act["presence"])
                    
                    self.model.add(
                        info_act["end"] <= self.employee_end_shift[r.uid, d]
                    ).only_enforce_if(info_act["presence"])

    def _build_constraints_on_breaks(self) -> None:
        """Enforces mandatory meal/rest break constraints depending on shift duration."""
        for r in self.employees:
            for d in self.days:
                day_breaks = self.break_info_dict.get((r.uid, d), [])
                if not day_breaks:
                    continue

                is_working = self.employee_isworking_dict[r.uid, d]
                shift_start = self.employee_start_shift[r.uid, d]
                shift_end = self.employee_end_shift[r.uid, d]

                duration = self.model.new_int_var(0, SLOTS_IN_A_DAY, f"duration_{r.uid}_{d}")
                self.model.add(duration >= shift_end - shift_start).only_enforce_if(is_working)

                presence1 = day_breaks[0]["presence"]
                presence2 = day_breaks[1]["presence"] if len(day_breaks) > 1 else None
                b1_start, b1_end = day_breaks[0]["start"], day_breaks[0]["end"]

                # Constraints for FIRST break presence based on continuous shift length
                self.model.add(duration >= MAX_TIME_BEFORE_BREAK + 1).only_enforce_if(presence1)
                self.model.add(duration <= MAX_TIME_BEFORE_BREAK).only_enforce_if(presence1.Not())
                
                # Constraints for SECOND break presence
                if presence2 is not None:
                    self.model.add(duration >= 2 * MAX_TIME_BEFORE_BREAK + 1).only_enforce_if(presence2)
                    self.model.add(duration <= 2 * MAX_TIME_BEFORE_BREAK).only_enforce_if(presence2.Not())
                    self.model.add(presence2 <= presence1)
                    self.model.add(day_breaks[0]["start"] <= day_breaks[1]["start"]).only_enforce_if(presence2)

                # Distance from shift start
                self.model.add(b1_start >= shift_start + MIN_TIME_AFTER_BREAK).only_enforce_if(presence1)
                self.model.add(b1_start - shift_start <= MAX_TIME_BEFORE_BREAK).only_enforce_if(presence1)

                # Timing gaps between breaks and shift end
                if presence2 is not None:
                    b2_start, b2_end = day_breaks[1]["start"], day_breaks[1]["end"]

                    # CASE A: Only one break present
                    self.model.add(shift_end - b1_end <= MAX_TIME_BEFORE_BREAK).only_enforce_if([presence1, presence2.Not()])
                    self.model.add(shift_end >= b1_end + MIN_TIME_AFTER_BREAK).only_enforce_if([presence1, presence2.Not()])

                    # CASE B: Both breaks present
                    self.model.add(b2_start >= b1_end + MIN_TIME_AFTER_BREAK).only_enforce_if(presence2)
                    self.model.add(b2_start - b1_end <= MAX_TIME_BEFORE_BREAK).only_enforce_if(presence2)
                    self.model.add(shift_end - b2_end <= MAX_TIME_BEFORE_BREAK).only_enforce_if(presence2)
                    self.model.add(shift_end >= b2_end + MIN_TIME_AFTER_BREAK).only_enforce_if(presence2)
                else:
                    self.model.add(shift_end - b1_end <= MAX_TIME_BEFORE_BREAK).only_enforce_if(presence1)

                # No breaks allowed on non-working days
                self.model.add(presence1 == 0).only_enforce_if(is_working.Not())

    def _build_max_daily_and_weekly_time(self) -> None:
        """Limits employee total daily and weekly working hours."""
        for r in self.employees:
            weekly_work_vars = []

            for d in self.days:
                daily_activity_dur = [
                    self.activity_info_dict[r.uid, a]["duration"] * self.employee_activities_dict[r.uid, a]
                    for a in r.possible_activities if a.activity_day == d
                ]

                if daily_activity_dur:
                    daily_sum = self.model.new_int_var(0, r.max_daily_time, f"daily_sum_{r.uid}_{d}")
                    self.model.add(daily_sum == sum(daily_activity_dur))
                    
                    self.model.add(daily_sum <= r.max_daily_time).only_enforce_if(
                        self.employee_isworking_dict[r.uid, d]
                    )
                    self.model.add(daily_sum == 0).only_enforce_if(
                        self.employee_isworking_dict[r.uid, d].Not()
                    )
                    weekly_work_vars.append(daily_sum)

            if weekly_work_vars:
                weekly_sum = self.model.new_int_var(0, r.max_weekly_time, f"weekly_sum_{r.uid}")
                self.model.add(weekly_sum == sum(weekly_work_vars))
                self.model.add(weekly_sum <= r.max_weekly_time)

    def _build_max_daily_span(self) -> None:
        """Limits maximum span (end_time - start_time) per day for an employee."""
        for r in self.employees:            
            for d in self.days:
                if (r.uid, d) in self.employee_start_shift:                    
                    daily_span = self.employee_end_shift[r.uid, d] - self.employee_start_shift[r.uid, d]                    
                    self.model.add(daily_span <= r.max_daily_span).only_enforce_if(
                        self.employee_isworking_dict[r.uid, d]
                    )
    def _build_max_consecutive_days(self) -> None:
        """Limits consecutive working days per employee, accounting for historical work days."""
        for r in self.employees:
            max_cons_days = r.max_consecutive_work_days
            days_since_last_off = r.days_since_last_off
            
            # Initial window: adjust limit based on days worked prior to current horizon
            if days_since_last_off > 0:
                remaining_days = max_cons_days - days_since_last_off
                
                if remaining_days >= 0:
                    actual_end = min(remaining_days + 1, len(self.days))
                    self.model.add(
                        sum(
                            self.employee_isworking_dict[r.uid, d]
                            for d in range(actual_end)
                        ) <= remaining_days
                    )
                else:
                    self.model.add(self.employee_isworking_dict[r.uid, 0] == 0)
            
            # Rolling windows across the remaining planning horizon
            for d in range(len(self.days) - max_cons_days):
                self.model.add_bool_or([
                    self.employee_isworking_dict[r.uid, t].Not() 
                    for t in range(d, d + max_cons_days + 1)
                ])

    def _build_max_total_days(self) -> None:
        """Constrains total working days per employee over the whole planning horizon."""
        self.constr_max_total_days = {}

        for r in self.employees:
            max_days_horizon = r.max_work_days_horizon
            days_worked_total = sum(
                self.employee_isworking_dict[r.uid, d] for d in self.days
            )
            self.constr_max_total_days[r.uid] = self.model.add(
                days_worked_total <= max_days_horizon
            )

    def _build_rest_between_consecutive_shifts(self) -> None:
        """Enforces minimum required rest slots between consecutive shifts for an employee."""
        self.constr_rest_btw_shifts = {}
        self.employee_rest_vars = {}

        for r in self.employees:
            min_rest = r.min_time_between_shifts

            # Historical rest check for Day 0 based on last worked hour
            if r.last_working_hour >= 0:
                rest_day_0 = (SLOTS_IN_A_DAY - r.last_working_hour) + self.employee_start_shift[r.uid, 0]
                self.model.add(rest_day_0 >= min_rest).only_enforce_if(
                    self.employee_isworking_dict[r.uid, 0]
                )

            # Rest constraints between consecutive days in current horizon
            for d in range(len(self.days) - 1):
                if d in r.availabilities and (d + 1) in r.availabilities:
                    rest_btw_shifts = self.model.new_int_var(
                        min_rest, SLOTS_IN_A_DAY, f"rest_{r.uid}_{d}"
                    )
                    self.model.add(
                        rest_btw_shifts == self.employee_start_shift[r.uid, d + 1] - self.employee_end_shift[r.uid, d]
                    )
                    self.employee_rest_vars[r.uid, d] = rest_btw_shifts

                    self.constr_rest_btw_shifts[r.uid, d] = self.model.add(
                        rest_btw_shifts >= min_rest
                    ).only_enforce_if(
                        self.employee_isworking_dict[r.uid, d],
                        self.employee_isworking_dict[r.uid, d + 1],
                    )

    def _build_no_overlap(self) -> None:
        """Prevents overlapping activities or overlaps between activities and breaks."""
        self.constr_no_overlap = {}

        for r in self.employees:
            for d in self.days:
                daily_intervals = []
                
                for a in r.possible_activities:
                    if a.activity_day == d and (r.uid, a) in self.activity_info_dict:
                        daily_intervals.append(self.activity_info_dict[r.uid, a]["interval"])
                
                day_breaks = self.break_info_dict.get((r.uid, d), [])
                for b in day_breaks:
                    daily_intervals.append(b["interval"])

                self.constr_no_overlap[r.uid] = self.model.add_no_overlap(
                    daily_intervals
                ).only_enforce_if(self.employee_isworking_dict[r.uid, d])

    def _build_demand_satisfaction_constraints(self) -> None:
        """Computes penalty weight for each unmet activity demand."""
        self.unmet_demand_vars = []

        for a in self.activities:
            penalty_weight = a.activity_demand * a.penalty
            self.unmet_demand_vars.append(self.is_unmet[a] * penalty_weight)

    def _build_redundant_constraints(self) -> None:
        """Adds redundant cuts (Global Capacity & Assignment) to accelerate propagation."""
        activities_by_day = defaultdict(list)
        for a in self.activities:
            activities_by_day[a.activity_day].append(a)

        for d, day_activities in activities_by_day.items():
            day_unmet_durations = [self.is_unmet[a] * a.activity_demand for a in day_activities]
            
            # 1. Daily Assignment Conservation Constraint
            day_assigned_durations = []
            for a in day_activities:
                for r in self.employees:
                    if (r.uid, a) in self.employee_activities_dict:
                        day_assigned_durations.append(
                            self.employee_activities_dict[r.uid, a] * a.activity_demand
                        )
            
            total_demand_today = sum(a.activity_demand for a in day_activities)
            self.model.add(sum(day_assigned_durations) + sum(day_unmet_durations) == total_demand_today)

            # 2. Global Capacity Constraint Cut
            # Total open shift span must be >= Total Demand - Unmet Demand
            total_capacity_span = sum(
                (self.employee_end_shift[r.uid, d] - self.employee_start_shift[r.uid, d])
                for r in self.employees
            )
            unmet_sum = sum(day_unmet_durations)
            self.model.add(total_capacity_span >= total_demand_today - unmet_sum)

    def _build_objective(self) -> None:
        """Defines sub-objectives: Unmet Demand, Preference Penalties, and Idle Time."""
        self.obj_unmet = sum(self.unmet_demand_vars)
        
        # Fixed scale to support up to 3 decimal places safely without integer overflow
        self.preference_scale = 1000

        weighted_prefs = []
        for r in self.employees:
            for a in r.possible_activities:
                if (r.uid, a) in self.activity_info_dict:
                    presence_var = self.employee_activities_dict[r.uid, a]
                    actual_duration_var = self.activity_info_dict[r.uid, a]["duration"]

                    raw_pref = r.activity_preferences.get(a.original_id, 0)
                    pref_score = int(round(raw_pref * self.preference_scale))
                    
                    weighted_prefs.append(actual_duration_var * pref_score * presence_var)

        self.obj_prefs = sum(weighted_prefs)

        idle_time_vars = []
        for r in self.employees:
            for d in self.days:
                span = self.model.new_int_var(0, SLOTS_IN_A_DAY, f"span_r{r.uid}_d{d}")
                self.model.add(span == self.employee_end_shift[r.uid, d] - self.employee_start_shift[r.uid, d])

                active_act_durations = [
                    self.activity_info_dict[r.uid, a]["duration"] * self.employee_activities_dict[r.uid, a]
                    for a in r.possible_activities if a.activity_day == d
                ]
                
                active_break_durations = [
                    b["duration"] * b["presence"]
                    for b in self.break_info_dict.get((r.uid, d), [])
                ]

                # Idle = Shift Span - (Total Activities Duration + Total Breaks Duration)
                day_idle = self.model.new_int_var(0, SLOTS_IN_A_DAY, f"idle_r{r.uid}_d{d}")
                self.model.add(day_idle == span - sum(active_act_durations) - sum(active_break_durations))
                
                idle_time_vars.append(day_idle)

        self.obj_idle = sum(idle_time_vars)

# -----------------------------------------------------------------------------
# HELPER & SOLVING METHODS
# -----------------------------------------------------------------------------

    def _infer_scale_for_floats(self, values: list[float], max_denominator: int = 1000) -> int:
        """Finds a common integer multiplier scale to safely convert float parameters to CP-SAT integers."""
        scale = 1
        for v in values:
            if v == 0: 
                continue
            frac = Fraction(str(v)).limit_denominator(max_denominator)
            scale = math.lcm(scale, frac.denominator)
        return scale

    @staticmethod
    def slots_to_time(slots: int) -> str:
        """Converts integer time slot index to formatted HH:MM string."""
        slots_in_day = int(slots) % SLOTS_IN_A_DAY
        hours = slots_in_day // 4
        minutes = (slots_in_day % 4) * 15
        return f"{hours:02d}:{minutes:02d}"
    
    def solve_lexicographic(self, timeout: list[float] = [1800.0, 900.0], toll: float = 1.0) -> int:
        """
        Solves the model lexicographically across 3 hierarchical priorities:
          1. Unmet Demand (Primary)
          2. Preferences (Secondary)
          3. Idle time (Tertiary)
        """
        self.recorder = ProgressRecorder()
        start_all_objectives = time.time()

        self.bound_unmet = 0
        self.bound_prefs = 0
        self.bound_idle = 0
        self.time_unmet = 0
        self.history_kpis = []

        objectives = [
            (self.obj_unmet, None, "Unmet Demand"),
            (self.obj_prefs, timeout[0], "Preferences"),
            (self.obj_idle, timeout[1], "Idle Time")
        ]
        
        last_solution_values = None
        final_status = cp_model.UNKNOWN

        for i, (obj_var, t_limit, name) in enumerate(objectives):
            self.recorder.current_step_name = name

            if t_limit is not None:
                self.solver.parameters.max_time_in_seconds = t_limit
                self.solver.parameters.add_lp_constraints_lazily = False
            else:
                self.solver.parameters.max_time_in_seconds = 1800.0
            
            self.solver.parameters.num_workers = 8

            # Warm-start / Hinting from previous hierarchical step
            if i > 0 and last_solution_values:
                self.model.clear_hints()
                for var, val in last_solution_values.items():
                    self.model.add_hint(var, val)

            self.model.minimize(obj_var)
            step_start_time = time.time()
            
            status = self.solver.solve(self.model, self.recorder)
            final_status = status

            step_duration = time.time() - step_start_time
            if name == "Unmet Demand":
                self.time_unmet = step_duration

            if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
                print(f"Warning: Objective '{name}' produced no feasible solution.")
                break

            current_step_results = {
                'Step': name,
                'Duration': step_duration,
                'Unmet_Cost': self.solver.value(self.obj_unmet),
                'Prefs_Raw': self.solver.value(self.obj_prefs) / getattr(self, 'preference_scale', 1),
                'Idle_Slots': self.solver.value(self.obj_idle)
            }
            self.history_kpis.append(current_step_results)

            best_bound = self.solver.best_objective_bound
            if name == "Unmet Demand":
                self.bound_unmet = best_bound
            elif name == "Preferences":
                self.bound_prefs = best_bound
            elif name == "Idle Time":
                self.bound_idle = best_bound
                        
            current_val = self.solver.objective_value
            last_solution_values = {
                var: self.solver.value(var) for var in self.all_vars if hasattr(var, 'Index')
            }
            
            # Lock upper bound for the next optimization stage
            limit = math.ceil(current_val * toll)
            self.model.add(obj_var <= limit)

        self.total_time = time.time() - start_all_objectives
        return final_status

    def solve(self) -> bool:
        """Weighted single-objective fallback solver run."""
        self.recorder = ProgressRecorder() 

        self.model.minimize(self.obj_unmet * 15 + self.obj_prefs)
        self.solver.parameters.add_lp_constraints_lazily = False
        self.solver.parameters.log_search_progress = True
        self.solver.parameters.max_time_in_seconds = 3600.0
        self.solver.parameters.relative_gap_limit = 0.05

        status = self.solver.solve(self.model, self.recorder)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            print("\n" + "=" * 30)
            print(" SOLUTION FOUND!")
            print(f" Objective value: {self.solver.objective_value}")
            print(f" Best Bound: {self.solver.best_objective_bound}")
            print("=" * 30 + "\n")
            return True
        return False