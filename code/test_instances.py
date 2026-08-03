import os
import pytest

from src.constants import MAX_TIME_BEFORE_BREAK, MIN_TIME_AFTER_BREAK
from src.input import CSVImporter
from src.solver import EmployeeSolver


@pytest.fixture(scope="module")
def solver_instance():
    """Sets up and solves the rostering instance once for all integration tests in this module."""
    input_folder = os.path.join("data_io", "input_csv", "PV_Grande")
    importer = CSVImporter()
    instance = importer.csv_read(input_folder, horizon_days=7)
    
    solver = EmployeeSolver(instance)
    solver.create_model()
    solver.solve_lexicographic()
    return solver


def test_activity_window_bounds(solver_instance):
    """Verifies that assigned activities start and end within their allowed [t1, t2] time window."""
    sol = solver_instance.solver
    for (r_uid, a), info in solver_instance.activity_info_dict.items():
        if sol.boolean_value(info["presence"]):
            start_val = sol.value(info["start"])
            end_val = sol.value(info["end"])
            dur_val = sol.value(info["duration"])
            
            t1 = a.activity_t1
            t2 = a.activity_t2

            assert start_val >= t1, (
                f"ERROR: Activity {a.uid} (Emp {r_uid}) starts at {start_val}, earlier than t1={t1}"
            )
            assert end_val <= t2, (
                f"ERROR: Activity {a.uid} (Emp {r_uid}) ends at {end_val}, later than t2={t2}"
            )
            assert start_val + dur_val == end_val, (
                f"ERROR: Temporal inconsistency for activity {a.uid}: {start_val} + {dur_val} != {end_val}"
            )

            if a.min_time_on_activity > 0:
                assert dur_val >= a.min_time_on_activity, (
                    f"ERROR: Activity {a.uid} duration too short: {dur_val} < {a.min_time_on_activity}"
                )


def test_activity_isworking_consistency(solver_instance):
    """Verifies that is_working flag matches whether activities are assigned on a given day."""
    sol = solver_instance.solver
    for r in solver_instance.employees:
        for d in solver_instance.days:
            is_working_val = sol.boolean_value(solver_instance.employee_isworking_dict[r.uid, d])
            activity_vars = solver_instance.daily_activities.get((r.uid, d), [])
            
            any_activity_assigned = any(sol.boolean_value(v) for v in activity_vars)

            if any_activity_assigned:
                assert is_working_val is True, (
                    f"ERROR: Emp {r.uid} has assigned activities on day {d} but is_working is False"
                )
            else:
                assert is_working_val is False, (
                    f"ERROR: Emp {r.uid} has no activities on day {d} but is_working is True"
                )


def test_shift_availability_bounds(solver_instance):
    """Verifies shift start and end times fall within the employee's defined daily availability limits."""
    sol = solver_instance.solver
    for r in solver_instance.employees:
        avail_limits = {day: (s, e) for day, s, e in r.availabilities}
        
        for d in solver_instance.days:
            if sol.boolean_value(solver_instance.employee_isworking_dict[r.uid, d]):
                start_val = sol.value(solver_instance.employee_start_shift[r.uid, d])
                end_val = sol.value(solver_instance.employee_end_shift[r.uid, d])
                first_avail, last_avail = avail_limits.get(d, (0, 0))

                assert start_val >= first_avail, (
                    f"ERROR: Emp {r.uid} Day {d} starts shift at {start_val}, "
                    f"prior to availability start {first_avail}"
                )
                assert end_val <= last_avail, (
                    f"ERROR: Emp {r.uid} Day {d} ends shift at {end_val}, "
                    f"after availability end {last_avail}"
                )


def test_assigned_activities_compatibility(solver_instance):
    """Verifies that assigned activities belong strictly to the employee's skilled activity set."""
    sol = solver_instance.solver
    for r in solver_instance.employees:
        allowed_uids = {a.uid for a in r.possible_activities}

        for (r_uid, activity_obj), var in solver_instance.employee_activities_dict.items():
            if r_uid == r.uid and sol.boolean_value(var):
                assert activity_obj.uid in allowed_uids, (
                    f"ERROR: Employee {r.uid} was assigned activity {activity_obj.uid}, "
                    f"which is not in their skilled activities set!"
                )


def test_max_work(solver_instance):
    """Verifies daily and weekly work duration limits for each employee."""
    sol = solver_instance.solver
    for r in solver_instance.employees:
        total_weekly_time = 0
        
        for d in solver_instance.days:
            daily_time = 0
            for a in r.possible_activities:
                if a.activity_day == d and sol.boolean_value(solver_instance.employee_activities_dict[r.uid, a]):
                    info = solver_instance.activity_info_dict[r.uid, a]
                    daily_time += sol.value(info["duration"])
            
            assert daily_time <= r.max_daily_time, (
                f"ERROR: Emp {r.uid} exceeds max daily work limit on day {d}: {daily_time} > {r.max_daily_time}"
            )
            total_weekly_time += daily_time
        
        assert total_weekly_time <= r.max_weekly_time, (
            f"ERROR: Emp {r.uid} exceeds max weekly work limit: {total_weekly_time} > {r.max_weekly_time}"
        )


def test_max_total_work_days(solver_instance):
    """Verifies total work days do not exceed horizon limits."""
    sol = solver_instance.solver
    for r in solver_instance.employees:
        days_worked = sum(sol.value(solver_instance.employee_isworking_dict[r.uid, d]) for d in solver_instance.days)
        assert days_worked <= r.max_work_days_horizon, (
            f"ERROR: Employee {r.uid} worked {days_worked} days, exceeding limit of {r.max_work_days_horizon}"
        )


def test_rest_between_shifts(solver_instance):
    """Verifies minimum required rest slots between consecutive working days."""
    sol = solver_instance.solver
    for r in solver_instance.employees:
        min_rest = r.min_time_between_shifts

        # 1. Day 0 check against historical work
        if r.last_working_hour >= 0 and sol.boolean_value(solver_instance.employee_isworking_dict[r.uid, 0]):
            start_day_0 = sol.value(solver_instance.employee_start_shift[r.uid, 0])
            rest_from_past = (96 - r.last_working_hour) + start_day_0
            assert rest_from_past >= min_rest, (
                f"ERROR: Insufficient rest on Day 0 for Emp {r.uid}: {rest_from_past} < {min_rest}"
            )

        # 2. Subsequent days check
        for d in range(len(solver_instance.days) - 1):
            work_today = sol.boolean_value(solver_instance.employee_isworking_dict[r.uid, d])
            work_tomorrow = sol.boolean_value(solver_instance.employee_isworking_dict[r.uid, d + 1])
            
            if work_today and work_tomorrow:
                end_today = sol.value(solver_instance.employee_end_shift[r.uid, d])
                start_tomorrow = sol.value(solver_instance.employee_start_shift[r.uid, d + 1])
                actual_rest = (96 - end_today) + start_tomorrow
                
                assert actual_rest >= min_rest, (
                    f"ERROR: Insufficient rest between day {d} and {d+1} for Emp {r.uid}: {actual_rest} < {min_rest}"
                )


def test_no_overlap_logic(solver_instance):
    """Verifies no overlapping activity time slots for any employee on the same day."""
    sol = solver_instance.solver
    for r in solver_instance.employees:
        for d in solver_instance.days:
            assigned_activities = []
            for a in r.possible_activities:
                if a.activity_day == d and sol.value(solver_instance.employee_activities_dict[r.uid, a]):
                    start = sol.value(solver_instance.activity_info_dict[r.uid, a]["start"])
                    end = sol.value(solver_instance.activity_info_dict[r.uid, a]["end"])
                    assigned_activities.append((start, end, f"Act_{a.uid}"))

            for i, (s1, e1, name1) in enumerate(assigned_activities):
                for j, (s2, e2, name2) in enumerate(assigned_activities):
                    if i != j:
                        overlap = (s1 < e2) and (e1 > s2)
                        assert not overlap, (
                            f"ERROR OVERLAP: {name1} [{s1}-{e1}] and {name2} [{s2}-{e2}] "
                            f"overlap on day {d} for Emp {r.uid}"
                        )


def test_consecutive_days_constraints(solver_instance):
    """Verifies max consecutive working days constraint across the planning horizon."""
    sol = solver_instance.solver
    for r in solver_instance.employees:
        work_sequence = [
            sol.value(solver_instance.employee_isworking_dict[r.uid, d]) 
            for d in solver_instance.days
        ]
        
        current_streak = r.days_since_last_off
        for is_working in work_sequence:
            current_streak = current_streak + 1 if is_working == 1 else 0
            assert current_streak <= r.max_consecutive_work_days, (
                f"ERROR: Employee {r.uid} worked {current_streak} consecutive days, "
                f"exceeding limit of {r.max_consecutive_work_days}"
            )


def test_minimum_time_span_after_break(solver_instance):
    """Verifies minimum working duration required after rest breaks."""
    sol = solver_instance.solver
    for r in solver_instance.employees:
        for d in solver_instance.days:
            shift_end = sol.value(solver_instance.employee_end_shift[r.uid, d])
            active_breaks = sorted([
                {"start": sol.value(b["start"]), "end": sol.value(b["end"])}
                for b in solver_instance.break_info_dict.get((r.uid, d), [])
                if sol.boolean_value(b["presence"])
            ], key=lambda x: x["start"])
            
            for i, brk in enumerate(active_breaks):
                brk_end = brk["end"]
                next_boundary = active_breaks[i + 1]["start"] if i < len(active_breaks) - 1 else shift_end
                time_span = next_boundary - brk_end
                
                assert time_span >= MIN_TIME_AFTER_BREAK, (
                    f"ERROR: Emp {r.uid}, Day {d}. Time span after break {i} "
                    f"until next boundary is {time_span} slots (Required >= {MIN_TIME_AFTER_BREAK})"
                )


def test_maximum_time_span_consecutive(solver_instance):
    """Verifies continuous work segments do not exceed maximum continuous work span limits."""
    sol = solver_instance.solver
    for r in solver_instance.employees:
        for d in solver_instance.days:
            if not sol.boolean_value(solver_instance.employee_isworking_dict[r.uid, d]):
                continue

            active_breaks = sorted([
                (sol.value(b["start"]), sol.value(b["end"]))
                for b in solver_instance.break_info_dict.get((r.uid, d), [])
                if sol.boolean_value(b["presence"])
            ])
            
            checkpoints = [sol.value(solver_instance.employee_start_shift[r.uid, d])]
            for b_start, b_end in active_breaks:
                checkpoints.extend([b_start, b_end])
            checkpoints.append(sol.value(solver_instance.employee_end_shift[r.uid, d]))

            for i in range(0, len(checkpoints) - 1, 2):
                w_start = checkpoints[i]
                w_end = checkpoints[i + 1]
                time_span = w_end - w_start
                
                assert time_span <= MAX_TIME_BEFORE_BREAK, (
                    f"ERROR: Emp {r.uid}, Day {d}. Work segment {w_start}-{w_end} "
                    f"spans {time_span} slots, exceeding limit of {MAX_TIME_BEFORE_BREAK}"
                )


def test_activity_uniqueness(solver_instance):
    """Verifies each activity is assigned to at most one employee."""
    sol = solver_instance.solver
    for act in solver_instance.activities:
        assignments_count = 0
        for r in solver_instance.employees:
            if (r.uid, act) in solver_instance.employee_activities_dict:
                var = solver_instance.employee_activities_dict[r.uid, act]
                if sol.boolean_value(var):
                    assignments_count += 1
        
        assert assignments_count <= 1, (
            f"ERROR: Activity {act.uid} was assigned to {assignments_count} employees simultaneously!"
        )