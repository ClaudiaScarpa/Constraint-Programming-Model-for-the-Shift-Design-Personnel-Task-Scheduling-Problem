"""
Global constants and configuration settings for the Employee Rostering CP-SAT Model.
All time durations are expressed in 15-minute time slots (4 slots = 1 hour).
"""

# Time Granularity Constants
SLOTS_IN_A_DAY: int = 96  # 24 hours * 4 slots per hour
NUM_DAYS: int = 7         # Horizon days

# Objective Function Weights
WEIGHT_OBJ_PREF: float = 0
WEIGHT_OBJ_UNMET: float = 1

# Shift and Break Regulations (in time slots)
MAX_TIME_BEFORE_BREAK: int = 20  # Max continuous working slots before mandatory break (5 hours)
MIN_TIME_AFTER_BREAK: int = 8    # Min continuous working slots before/after break (2 hours)
MIN_BREAK_DUR: int = 2           # Duration of a meal/rest break (30 minutes)
MAX_BREAKS_IN_A_DAY: int = 2     # Max allowed breaks per shift
