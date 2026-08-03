from pydantic import BaseModel, ConfigDict, Field

EmployeeUid = int
ActivityUid = int


class Activity(BaseModel):
    """Represents an activity or a split task required in the schedule."""
    
    model_config = ConfigDict(frozen=True)

    uid: str = Field(
        ...,
        description="Unique identifier for the split activity",
    )
    original_id: ActivityUid = Field(
        ...,
        description="Original activity identifier before splitting",
    )
    activity_day: int = Field(
        ..., 
        description="Day index of the activity (0-indexed)",
    )
    activity_t1: int = Field(
        ..., 
        description="Earliest starting time slot of the activity",
    )
    activity_t2: int = Field(
        ..., 
        description="Latest ending time slot of the activity",
    )
    activity_demand: int = Field(
        ..., 
        description="Demand/duration of the activity (in time slots)",
    )
    min_time_on_activity: int = Field(
        ..., 
        description="Minimum consecutive working time on the activity (in time slots)",
    )
    penalty: float = Field(
        ..., 
        description="Penalty cost associated with unassigned/understaffed activity",
    )


class Employee(BaseModel):
    """Represents an employee and their constraints/skills."""
    
    model_config = ConfigDict(frozen=True)

    uid: EmployeeUid = Field(
        ...,
        description="Unique identifier for the employee",
    )
    availabilities: list[list[int]] = Field(
        ..., 
        description="List of available time windows [day, from_slot, to_slot]",
    )
    possible_activities: set[Activity] | frozenset[Activity] = Field(
        ..., 
        description="Set of activities the employee is skilled to perform",
    )
    max_daily_time: int = Field(
        ..., 
        description="Maximum working time slots allowed per day",
    )
    max_weekly_time: int = Field(
        ..., 
        description="Maximum working time slots allowed per week",
    )
    max_daily_span: int = Field(
        ..., 
        description="Maximum daily time span (in time slots) between shift start and end",
    )
    max_consecutive_work_days: int = Field(
        ..., 
        description="Maximum consecutive working days allowed",
    )
    min_time_between_shifts: int = Field(
        ..., 
        description="Minimum rest duration (in time slots) between consecutive shifts",
    )
    max_work_days_horizon: int = Field(
        ..., 
        description="Maximum working days allowed within the planning horizon",
    )
    days_since_last_off: int = Field(
        ..., 
        description="Number of consecutive working days prior to the start of the horizon",
    )
    last_working_hour: int = Field(
        ..., 
        description="Last worked time slot on the day preceding the planning horizon",
    )
    activity_preferences: dict[int, float] = Field(
        default_factory=dict,
        description="Mapping of activity ID to preference priority score",
    )


class EmployeeRosteringInstance(BaseModel):
    """Container for a complete problem instance."""
    
    model_config = ConfigDict(frozen=True)

    employees: list[Employee] = Field(
        ..., 
        description="List of employees available in the instance",
    )
    activities: list[Activity] = Field(
        ..., 
        description="List of activities to be scheduled",
    )
    horizon_days: int = Field(
        ..., 
        description="Total number of days in the planning horizon",
    )
    start_date: str = Field(
        default="20241021",
        description="Base start date of the horizon in YYYYMMDD format",
    )
