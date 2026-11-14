# Lift profile detail and coefficient points

## Why

The stimulus coefficient (1.00 to 2.00) scales raw weekly INOL for every
calculation that uses it. The profile options were too coarse, so the model
lost nuance and the numbers trended down:

- "Conventional narrow" has no reference. Slightly inside shoulder width is
  wider than a hip-width conventional stance, so the label can mean the opposite.
- Deadlift hip height cannot tell "slightly high" from "near stiff-leg".
- Deadlift has no toe angle, and the wedge is one option.
- Nothing captures the dominant muscle. A triceps-dominant bencher or a
  quad-dominant squatter loads a smaller muscle harder for the same INOL.
- Squat lost the torso angle (chest position).
- `volume_tolerance` (low / moderate / high) cannot tell "3 to 4 bench days at
  low reps" from "daily high-rep benching".
- There is no body fat input.

Labels are the only thing the model sees (`describe()` sends option labels), so
every label states its reference exactly.

## Scope

1. Option definitions: `src/services/runtime/lift_profile_options.json`.
2. Legacy value mapping so saved profiles keep what still maps.
3. Coefficient prompt points table:
   `src/services/runtime/prompts/lift_profile_estimate_system.j2`.
4. Optional body fat range in program meta, shown in the Dashboard
   measurements editor, passed to every prompt that receives athlete metrics.

Out of scope: `volume_tolerance` storage and its other consumers (Rust
`analytics` compare/flags, exports, badges on Dashboard / Analysis /
BlockWeeklySurface) stay exactly as they are. No new tests; only update the
existing assertions in `services/lift_profiles/tests/test_lift_profiles.py`
that list field keys or option values.

## 1. Option definitions

Keep every existing field key. Labels below are the exact UI and model text.
Fields marked NEW are added. `legacy` maps an old stored value to a new one;
an old value with no mapping is dropped, so the field shows as missing and the
athlete picks it again.

### Squat (field order)

| Key | Options (value: label) | Legacy |
|---|---|---|
| bar_position | high: High bar; low: Low bar | |
| hand_width | narrow: Narrow (hands near shoulders); medium: Medium; wide: Wide | |
| stance | hip_width: Hip width; slightly_inside_shoulder: Slightly inside shoulder width; shoulder_width: Shoulder width; slightly_outside_shoulder: Slightly outside shoulder width; wide: Wide (well outside shoulders) | narrow: none |
| toe_angle | forward: Forward (0 to 10 degrees); slight_out: Slightly out (10 to 30 degrees); wide_out: Wide out (over 30 degrees) | |
| torso_angle NEW | upright: Upright (chest stays up); moderate_lean: Moderate forward lean; pronounced_lean: Pronounced forward lean (hip hinge) | |
| dominant_muscle NEW | quads: Quads; balanced: Balanced; posterior_chain: Posterior chain (glutes, hamstrings, back) | |
| descent | unchanged | |
| knee_gear | unchanged | |
| sticking_point | unchanged | |
| weekly_frequency NEW | see Frequency and rep range | |
| rep_range NEW | see Frequency and rep range | |

### Bench

All existing fields unchanged, plus:

| Key | Options | 
|---|---|
| dominant_muscle NEW | chest: Chest; balanced: Balanced; triceps: Triceps |
| weekly_frequency NEW | see below |
| rep_range NEW | see below |

### Deadlift

| Key | Options (value: label) | Legacy |
|---|---|---|
| stance | feet_together: Feet together; hip_width: Hip width; slightly_inside_shoulder: Slightly inside shoulder width; shoulder_width: Shoulder width; semi_sumo: Semi-sumo; sumo: Sumo | conventional_hip_width: hip_width; conventional_narrow: none |
| toe_angle NEW | forward: Forward (0 to 10 degrees); slight_out: Slightly out (10 to 30 degrees); wide_out: Wide out (over 30 degrees) | |
| grip | unchanged | |
| start | dynamic: Dynamic (drop hips and pull); static_no_wedge: Static, no wedge; static_full_wedge: Static, full wedge (slack pulled, hips set) | static_wedge: static_full_wedge |
| hip_height | low: Low (thighs near parallel, squat-like); mid: Mid; high: High (hips well above knees); near_stiff_leg: Near stiff-leg (knees barely bent) | |
| dominant_muscle NEW | legs: Legs (quads); balanced: Balanced; back: Back (erectors, upper back); hamstrings: Hamstrings | |
| sticking_point | unchanged | |
| weekly_frequency NEW | see below | |
| rep_range NEW | see below | |

Keep the existing `locked` rule (sumo locks hip height to low).

### Frequency and rep range (per lift)

| Key | Options |
|---|---|
| weekly_frequency | 1: 1 day a week; 2: 2 days a week; 3_4: 3 to 4 days a week; 5_plus: 5 or more days a week |
| rep_range | low: 1 to 3 reps only; mid: Up to 6 reps; high: 6 or more reps |

Label wording: "Days a week you recover from" and "Rep range you recover from".

### Legacy mapping

Add an optional `"legacy": {"old": "new" | null}` object to a field
definition. Apply it before validation in both `clean_options`
(`src/services/runtime/lift_profiles.py`) and `cleanOptions`
(`src/frontend/src/utils/liftProfile.ts`). `null` means drop.

## 2. Coefficient prompt

Replace the points table in `lift_profile_estimate_system.j2`. Formula:

    coefficient = 1.00 + technique points + notes adjustment + recovery points + athlete adjustment

Clamp to 1.00 to 2.00, two decimals. Recovery points replace the old tolerance
points, and `volume_tolerance` is ignored by this prompt.

Points (0.00 means the most favourable option):

Squat
- Stance: wide 0.00, slightly outside shoulder 0.03, shoulder width 0.06, slightly inside shoulder 0.09, hip width 0.12
- Bar position: low 0.00, high 0.06
- Toe angle: wide out 0.00, slight out 0.03, forward 0.06
- Torso angle: pronounced lean 0.00, moderate lean 0.03, upright 0.06
- Dominant muscle: posterior chain 0.00, balanced 0.03, quads 0.06
- Descent: dive bomb 0.00, controlled then accelerate 0.03, controlled with bounce 0.05, controlled with no bounce 0.10
- Knee gear: wraps 0.00, stiff sleeves 0.04, soft sleeves 0.07, none 0.08
- Sticking point: near lockout 0.00, mid-range 0.06, out of the hole 0.10
- Hand width: wide 0.00, medium 0.02, narrow 0.04

Bench: keep the current table, plus Dominant muscle: chest 0.00, balanced 0.03, triceps 0.07.

Deadlift
- Stance: sumo 0.00, semi-sumo 0.04, shoulder width 0.08, slightly inside shoulder 0.11, hip width 0.14, feet together 0.16
- Toe angle: wide out 0.00, slight out 0.02, forward 0.03
- Hip height: low 0.03, mid 0.06, high 0.10, near stiff-leg 0.14
- Start: dynamic 0.00, static no wedge 0.05, static full wedge 0.08
- Grip: straps 0.00, hook 0.03, mixed 0.03, double overhand 0.03
- Dominant muscle: legs 0.00, balanced 0.03, back 0.06, hamstrings 0.06
- Sticking point: lockout 0.04, at knee 0.10, below knee 0.12, off floor 0.14

Recovery points (all lifts)
- Days a week: 5 or more 0.00, 3 to 4 0.04, 2 0.08, 1 0.12
- Rep range: 6 or more 0.00, up to 6 0.04, 1 to 3 only 0.08

Notes adjustment, athlete adjustment (leg ratio, ape index, BMI, clamp ±0.30)
stay as they are now. Add: torso is about height minus inseam, so the leg
ratio already says "short torso"; state it in the reasoning, do not add points
for it twice. Body fat range, when present, says whether a high BMI is muscle
or fat; mention it in the reasoning; it adds no points.

## 3. Body fat range

Meta field `body_fat_range`, optional string enum:
`under_10`, `10_15`, `15_20`, `20_25`, `25_30`, `over_30`.
Labels: "Under 10%", "10 to 15%", "15 to 20%", "20 to 25%", "25 to 30%", "Over 30%".

- `ProgramStore.ALLOWED_META_FIELDS` and `access.py` `META_DOMAINS['weight-log']`: add the field.
- If `program_update_meta_field` input schema in `services/operations/program.json` limits value types, make sure a string passes.
- `src/dependencies/types/index.ts` meta: `body_fat_range?: string`.
- Dashboard measurements editor (`src/frontend/src/pages/Dashboard.tsx`): add one row "Body fat" with a Select of the ranges (clearable). Save it with the other measurements. Show it in the read view next to leg length. Change nothing else in the card.
- Pass it as `body_fat_range` (label text) wherever athlete metrics are built:
  `lift_profile_ai._athlete_lines`, both `fatigue_ai.py` files, both
  `muscle_group_ai.py` files, `program/export_program_markdown/prompt_context.py`.

## Rollout

After deploy, every saved profile shows the new fields as missing until filled.
Estimate is blocked until all fields are chosen (existing `missing()` rule).
