# Analytics Calculations Migration Guide

This document identifies analytics logic currently residing in the frontend (TypeScript) or the Node.js middleware that should be migrated to the Agent API (Python) and exposed as health tools.

## 1. Frontend Logic (React / TypeScript)

Location: `utils/powerlifting-app/frontend/src/`

### Exercise Volume & Sets (`utils/volume.ts`)
- **`executedSets`**: Logic to filter `set_statuses` for 'completed' or 'failed'.
- **`exerciseVolume`**: Calculation of `sets * reps * kg`.
- **`sessionVolume`**: Summation of all exercise volumes in a session.
- **`normalizeExerciseName`**: Heuristic to strip parentheticals (e.g., "(heavy)") and singularize names for better matching.
- **`categorizeExercise`**: Heuristic mapping of exercise names to categories (Squat, Bench, Deadlift, Back, Chest, etc.).

### Muscle Group Workload (`AnalysisPage.tsx`, `utils/volume.ts`)
- **`volumeByMuscleGroup` / `weeklySetsByMuscleGroup`**: Aggregates workload by muscle group with weighting:
    - Primary muscles: 100% (1.0)
    - Secondary muscles: 50% (0.5)
    - Tertiary muscles: 25% (0.25)
- **`muscleGroupAvgWeekly`**: Calculates the average weekly volume and sets for muscle groups across the analysis window.

### e1RM & Relative Scoring (`AnalysisPage.tsx`)
- **`estimateAnalysisE1rm`**: Frontend implementation of e1RM using RPE and Conservative tables. (Backend has a similar but more robust implementation).
- **`dotsTrend`**: Calculates weekly best e1RMs for Squat, Bench, and Deadlift, then computes:
    - **Total**: Sum of best e1RMs.
    - **DOTS Score**: Sex-specific polynomial coefficient.
    - **IPF GL Score**: Discipline-specific (Classic/Bench-only) exponential coefficient.
- **`highestMaxes`**: Identifies peak e1RMs and total within a specific date window.

### Trend Calculations (`AnalysisPage.tsx`)
- **`nutritionTrend`**: Aggregates diet notes into weekly buckets and calculates deltas (e.g., "Calories change per week").
- **`ipfGlTrend`**: Calculates the rate of change for relative scoring over time.

---

## 2. Node.js Backend Logic (Node.js / TypeScript)

Location: `utils/powerlifting-app/backend/src/services/blockAnalytics.ts`

### Block Comparison Engine
- **`BlockComparisonResult`**: The primary logic for comparing multiple training blocks.
- **`exerciseRoi`**: Aggregates exercise stats across multiple blocks to find correlations with lift progress.
    - Counts positive/negative/unclear signals.
    - Tracks total sets and volume per exercise across lifetime history.
- **`liftDoseResponse`**: Calculates efficiency metrics:
    - **kg / 1000kg volume**: Strength gain normalized by volume load.
    - **response per set**: Strength gain per working set.
- **`trainingDayResponse`**: Correlates training frequency (days/week) with strength deltas.

### Pattern Detection & Data Quality
- **`patternSignals`**: Heuristic detection of behavioral patterns:
    - ROI patterns (which exercises consistently work).
    - Fatigue patterns (high monotony or overload streaks).
    - Compliance patterns.
- **`DataQualityFlag`**: Identifies missing or inconsistent data that might invalidate analysis (e.g., missing bodyweight, missing sex, no main lifts).

### Historical Mapping
- **`BlockCompetitionOutcome`**: Logic to map competition results to the correct training block and calculate projection accuracy (Actual vs. Projected).
- **`BlockHistoricalSummary`**: Calculates Block-Start vs. Block-End strength deltas and identifies the source of start maxes (Manual vs. Estimated).

---

## 3. Duplicated Logic & Constants

These should be consolidated into a single source of truth in the Python backend:

- **RPE Tables**: `RPE_TABLE_PRIMARY` exists in three places (Frontend, Node.js, Python).
- **Conservative Percentages**: `CONSERVATIVE_REP_PCT` exists in three places.
- **Scoring Coefficients**: DOTS and IPF GL coefficients are duplicated in Node.js and Python.
- **Unit Conversions**: LB to KG conversions and display logic are scattered.
- **Date/Week Windowing**: `resolveTrainingWeekForDate` and similar logic for training weeks (starting on specific days) exists in both JS and Python.

## 4. Proposed Health Tools (Python)

- `health.calculate_dots(total_kg, bodyweight_kg, sex)`
- `health.calculate_ipf_gl(result_kg, bodyweight_kg, sex, mode)`
- `health.get_muscle_workload(sessions, glossary)`
- `health.get_exercise_roi_lifetime(blocks_history)`
- `health.detect_training_patterns(sessions_history)`
- `health.get_data_quality_report(program)`
- `health.get_block_comparison(block_keys)`
