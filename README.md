# Constraint Programming Model for the Shift-Design Personnel Task Scheduling Problem

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![OR-Tools](https://img.shields.io/badge/OR--Tools-CP--SAT-orange.svg)](https://developers.google.com/optimization)
[![Pydantic V2](https://img.shields.io/badge/Pydantic-V2-red.svg)](https://docs.pydantic.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

This repository contains the complete implementation and computational artifacts developed for my Master's Thesis in Mathematics at the **University of Bologna**:

> **"Constraint Programming Model for the Shift-Design Personnel Task Scheduling Problem"**

The project develops a **Constraint Programming optimization model** for an integrated workforce scheduling problem that combines:

- **Shift design:** determining employee working intervals, rest periods, and mandatory breaks.
- **Personnel task scheduling:** assigning employees to activities while respecting skills, availability, preferences, and operational requirements.

The proposed model is implemented using **Google OR-Tools CP-SAT** and adopts a **three-stage lexicographic optimization approach** to handle conflicting objectives.

---

# 📌 Problem Description

Personnel scheduling problems are challenging combinatorial optimization problems arising in many real-world environments, such as manufacturing, logistics, healthcare, and service industries.

This project focuses on an integrated version of the problem where both **employee shifts** and **task assignments** must be optimized simultaneously.

Given:

- a set of employees with individual characteristics;
- a set of tasks with time-dependent requirements;
- employee skills and activity preferences;
- working-time regulations and scheduling constraints;

the goal is to construct feasible daily schedules satisfying operational demand while optimizing multiple objectives.

The model simultaneously determines:

1. **When employees work**
2. **Which tasks employees perform**
3. **How breaks and idle periods are distributed**
4. **How employee preferences are respected**

---

# 🎯 Optimization Framework

The model uses a **three-stage lexicographic optimization strategy**.

Instead of combining objectives through weighted sums, objectives are optimized sequentially, guaranteeing that higher-priority goals are never sacrificed for lower-priority ones.

## Stage 1 — Unmet Demand Minimization

The first optimization stage minimizes uncovered task requirements.

\[
\min \sum \text{Unmet Demand}
\]

This ensures that operational requirements are satisfied as much as possible.

---

## Stage 2 — Employee Preference Maximization

After fixing the optimal demand coverage, the model maximizes employee satisfaction by considering activity preferences.

\[
\max \sum \text{Preference Scores}
\]

This stage improves schedule quality without worsening demand coverage.

---

## Stage 3 — Idle Time Minimization

Finally, the model minimizes unnecessary idle periods inside employee shifts.

\[
\min \sum \text{Idle Time}
\]

This produces more compact and efficient schedules.

---

# ⚙️ Technical Features

## Constraint Programming Model

The optimization model is built using:

- **Google OR-Tools CP-SAT Solver**
- Boolean decision variables
- Integer linear constraints
- Reified logical constraints
- Interval-based scheduling constraints

The model exploits CP-SAT propagation capabilities to efficiently explore the solution space.

---

## Shift Design Constraints

The model handles:

- minimum and maximum shift duration;
- continuous working periods;
- mandatory meal breaks;
- rest intervals;
- employee availability windows;
- valid start and end times.

---

## Task Assignment Constraints

The scheduling model includes:

- employee-task compatibility;
- skill requirements;
- activity coverage;
- assignment consistency;
- preference-based decisions.

---

## Advanced Model Improvements

To improve computational performance, the implementation includes:

### Global Capacity Cuts

Redundant but useful constraints limiting the total available workforce capacity over time.

These constraints strengthen propagation and reduce unnecessary search.

---

### Effective Duration Lower Bounds

Additional lower bounds on employee activity durations reduce the feasible domain and accelerate convergence.

---

### Domain Pruning

The model performs preprocessing operations to remove impossible assignments before optimization.

---

# 🏗️ Repository Structure

```
.
├── data_io/
│   └── anonymized benchmark input datasets
│
├── src/
│   ├── constants.py
│   │   └── global scheduling parameters and time discretization
│   │
│   ├── data_classes.py
│   │   └── Pydantic V2 models for employees, activities, and instances
│   │
│   ├── input.py
│   │   └── CSV parsing and preprocessing pipeline
│   │
│   ├── solver.py
│   │   └── CP-SAT model construction and lexicographic optimization
│   │
│   └── output.py
│       └── solution export and KPI computation
│
├── tests/
│   └── automated validation and unit tests
│
├── main.py
│   └── application entry point
│
├── requirements.txt
│
├── .gitignore
│
└── README.md
```

---

# 📊 Input Data

The model receives anonymized CSV datasets describing:

## Employees

Each employee is characterized by:

- identifier;
- availability;
- skills;
- activity preferences;
- working-time constraints.

## Activities

Each activity contains:

- required workforce;
- execution interval;
- required skills;
- duration information.

All input data is validated through strongly typed **Pydantic V2** models before being passed to the optimization engine.

---

# 📈 Output and Reporting

The solution generates detailed reports including:

## Employee Schedule

For each employee:

- assigned shift;
- working periods;
- breaks;
- assigned activities;
- idle intervals.

## Global KPIs

The reporting module computes:

- total unmet demand;
- preference satisfaction score;
- total idle time;
- shift utilization statistics.

## Visualization

The repository includes automatic generation of:

- convergence plots;
- scheduling summaries;
- Excel reports.

# 🔮 Future Developments

Possible extensions include:

- larger benchmark instances;
- comparison with alternative optimization approaches;
- hybrid CP-MIP formulations;
- additional fairness objectives among employees;
