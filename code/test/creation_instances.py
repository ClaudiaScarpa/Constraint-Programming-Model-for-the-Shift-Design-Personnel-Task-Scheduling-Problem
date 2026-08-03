import pytest
from src.data_classes import Activity, Employee, EmployeeRosteringInstance


@pytest.fixture
def get_toy_instance() -> EmployeeRosteringInstance:
    """Standard test instance with two employees and distinct activity demands."""
    activity_1 = Activity(
        uid="501_D0_0",
        original_id=501,
        activity_day=0,
        activity_t1=32,
        activity_t2=36,
        activity_demand=2,
        min_time_on_activity=2,
        penalty=10.0
    )

    activity_2 = Activity(
        uid="502_D0_0",
        original_id=502,
        activity_day=0,
        activity_t1=32,
        activity_t2=36,
        activity_demand=2,
        min_time_on_activity=2,
        penalty=10.0
    )

    activity_3 = Activity(
        uid="503_D0_0",
        original_id=503,
        activity_day=0,
        activity_t1=67,
        activity_t2=90,
        activity_demand=4,
        min_time_on_activity=4,
        penalty=5.0
    )

    employee_1 = Employee(
        uid=1,
        availabilities=[[0, 32, 64]],  # [day, start_slot, end_slot]
        possible_activities={activity_1, activity_3},
        max_daily_time=40,
        max_weekly_time=200,
        max_daily_span=32,
        max_consecutive_work_days=5,
        min_time_between_shifts=44,
        max_work_days_horizon=20,
        days_since_last_off=0,
        last_working_hour=0,
        activity_preferences={501: 1.0, 503: 0.8}
    )

    employee_2 = Employee(
        uid=2,
        availabilities=[[0, 64, 95]],
        possible_activities={activity_1, activity_2, activity_3},
        max_daily_time=40,
        max_weekly_time=200,
        max_daily_span=31,
        max_consecutive_work_days=5,
        min_time_between_shifts=44,
        max_work_days_horizon=20,
        days_since_last_off=0,
        last_working_hour=0,
        activity_preferences={501: 0.5, 502: 1.0, 503: 0.2}
    )

    return EmployeeRosteringInstance(
        employees=[employee_1, employee_2],
        activities=[activity_1, activity_2, activity_3],
        horizon_days=1
    )


@pytest.fixture
def get_rest_test_instance() -> EmployeeRosteringInstance:
    """Test instance for minimum rest duration constraints between consecutive shifts."""
    activity_1 = Activity(
        uid="1_D0_0",
        original_id=1,
        activity_day=0,
        activity_t1=65,
        activity_t2=85,
        activity_demand=1,
        min_time_on_activity=3,
        penalty=10.0
    )
    activity_2 = Activity(
        uid="2_D1_0",
        original_id=2,
        activity_day=1,
        activity_t1=120,
        activity_t2=130,
        activity_demand=4,
        min_time_on_activity=3,
        penalty=10.0
    )

    employee = Employee(
        uid=1,
        availabilities=[[0, 60, 90], [1, 110, 128]],
        possible_activities={activity_1, activity_2},
        max_daily_time=96,
        max_weekly_time=200,
        max_daily_span=30,
        max_consecutive_work_days=5,
        min_time_between_shifts=48,  # Minimum rest required: 48 slots (12 hours)
        max_work_days_horizon=7,
        days_since_last_off=0,
        last_working_hour=0
    )

    return EmployeeRosteringInstance(
        employees=[employee],
        activities=[activity_1, activity_2],
        horizon_days=2
    )


@pytest.fixture
def get_consecutive_days_test_instance() -> EmployeeRosteringInstance:
    """Test instance accounting for days worked prior to the horizon start."""
    activities = [
        Activity(uid="1_D0_0", original_id=1, activity_day=0, activity_t1=35, activity_t2=50, activity_demand=10, min_time_on_activity=1, penalty=5.0),
        Activity(uid="2_D1_0", original_id=2, activity_day=1, activity_t1=131, activity_t2=146, activity_demand=2, min_time_on_activity=1, penalty=5.0),
        Activity(uid="3_D2_0", original_id=3, activity_day=2, activity_t1=227, activity_t2=242, activity_demand=10, min_time_on_activity=1, penalty=5.0),
    ]

    employee = Employee(
        uid=1,
        availabilities=[[0, 32, 56], [1, 128, 152], [2, 224, 248]],
        possible_activities=set(activities),
        max_daily_time=32,
        max_weekly_time=200,
        max_daily_span=24,
        max_consecutive_work_days=3,
        min_time_between_shifts=48,
        max_work_days_horizon=7,
        days_since_last_off=1,  # Already worked 1 day before horizon start
        last_working_hour=0
    )

    return EmployeeRosteringInstance(
        employees=[employee],
        activities=activities,
        horizon_days=3
    )


@pytest.fixture
def get_instance_for_weekly_load_test() -> EmployeeRosteringInstance:
    """Test instance for total weekly working time limits."""
    activities = [
        Activity(uid="10_D0_0", original_id=10, activity_day=0, activity_t1=32, activity_t2=64, activity_demand=1, min_time_on_activity=3, penalty=10.0),
        Activity(uid="11_D1_0", original_id=11, activity_day=1, activity_t1=128, activity_t2=160, activity_demand=1, min_time_on_activity=3, penalty=10.0),
        Activity(uid="12_D2_0", original_id=12, activity_day=2, activity_t1=224, activity_t2=256, activity_demand=1, min_time_on_activity=3, penalty=10.0),
    ]
    employee = Employee(
        uid=1,
        availabilities=[[0, 32, 64], [1, 128, 160], [2, 224, 256]],
        possible_activities=set(activities),
        max_daily_time=32,
        max_weekly_time=65,
        max_daily_span=32,
        max_work_days_horizon=3,
        min_time_between_shifts=0,
        max_consecutive_work_days=7,
        days_since_last_off=0,
        last_working_hour=0
    )
    return EmployeeRosteringInstance(
        employees=[employee],
        activities=activities,
        horizon_days=3
    )


@pytest.fixture
def get_instance_for_max_days_test() -> EmployeeRosteringInstance:
    """Test instance for total horizon working days limit."""
    activities = [
        Activity(uid="10_D0_0", original_id=10, activity_day=0, activity_t1=32, activity_t2=64, activity_demand=1, min_time_on_activity=3, penalty=10.0),
        Activity(uid="11_D1_0", original_id=11, activity_day=1, activity_t1=128, activity_t2=160, activity_demand=1, min_time_on_activity=3, penalty=10.0),
        Activity(uid="12_D2_0", original_id=12, activity_day=2, activity_t1=224, activity_t2=256, activity_demand=3, min_time_on_activity=3, penalty=10.0),
    ]

    employee = Employee(
        uid=1,
        availabilities=[[0, 32, 40], [1, 128, 136], [2, 224, 232]],
        possible_activities=set(activities),
        max_daily_time=32,
        max_weekly_time=100,
        max_daily_span=8,
        max_consecutive_work_days=7,
        min_time_between_shifts=0,
        max_work_days_horizon=2,
        days_since_last_off=0,
        last_working_hour=0
    )

    return EmployeeRosteringInstance(
        employees=[employee],
        activities=activities,
        horizon_days=7
    )


@pytest.fixture
def get_instance_test_no_overlap() -> EmployeeRosteringInstance:
    """Test instance verifying strict non-overlapping constraint between activities and breaks."""
    activity_1 = Activity(
        uid="10_D0_0",
        original_id=10,
        activity_day=0,
        activity_t1=32,
        activity_t2=64,
        activity_demand=28,
        min_time_on_activity=28,
        penalty=10.0
    )

    employee_1 = Employee(
        uid=1,
        availabilities=[[0, 32, 64]],
        possible_activities={activity_1},
        max_daily_time=32,
        max_weekly_time=100,
        max_daily_span=32,
        max_consecutive_work_days=7,
        min_time_between_shifts=0,
        max_work_days_horizon=7,
        days_since_last_off=0,
        last_working_hour=0
    )

    return EmployeeRosteringInstance(
        employees=[employee_1],
        activities=[activity_1],
        horizon_days=1
    )


@pytest.fixture
def get_one_emp_on_activity_test_instance() -> EmployeeRosteringInstance:
    """Test instance verifying that an activity cannot be assigned to more than one employee."""
    activity = Activity(
        uid="1_D0_0",
        original_id=1,
        activity_day=0,
        activity_t1=32,
        activity_t2=64,
        activity_demand=20,
        min_time_on_activity=20,
        penalty=10.0
    )

    employee_1 = Employee(
        uid=1,
        availabilities=[[0, 32, 64]],
        possible_activities={activity},
        max_daily_time=32,
        max_weekly_time=100,
        max_daily_span=32,
        max_consecutive_work_days=7,
        min_time_between_shifts=0,
        max_work_days_horizon=7,
        days_since_last_off=0,
        last_working_hour=0
    )

    employee_2 = Employee(
        uid=2,
        availabilities=[[0, 32, 64]],
        possible_activities={activity},
        max_daily_time=32,
        max_weekly_time=100,
        max_daily_span=32,
        max_consecutive_work_days=7,
        min_time_between_shifts=0,
        max_work_days_horizon=7,
        days_since_last_off=0,
        last_working_hour=0
    )

    return EmployeeRosteringInstance(
        employees=[employee_1, employee_2],
        activities=[activity],
        horizon_days=1
    )
