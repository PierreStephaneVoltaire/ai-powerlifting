import json5
import json
import uuid
from datetime import date, datetime, timedelta
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
# ─── Known blocks (workouts INSIDE these are already in DB → drop) ───────────
KNOWN_BLOCKS = [
    {
        "name": "ottawa-prep",
        "start": date(2025, 1, 1),
        "end":   date(2025, 10, 4),
        "hard_cutoff": date(2025, 10, 6),   # nothing after this belongs here
    },
    {
        "name": "off-season#2",
        "start": date(2025, 10, 13),
        "end":   date(2025, 11, 30),
        "hard_cutoff": None,
    },
    {
        "name": "current",
        "start": date(2026, 2, 13),
        "end":   date(2026, 12, 20),
        "hard_cutoff": None,
    },
]

GAP = timedelta(days=28)   # 4-week gap = new block signal
PROGRAM_VERSION        = "v020"
PROGRAM_VERSION_NUMBER = 20

# ─── Helpers ─────────────────────────────────────────────────────────────────

def parse_date(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()

def inside_known_block(d: date) -> str | None:
    """Return block name if date is already covered, else None."""
    for b in KNOWN_BLOCKS:
        if b["start"] <= d <= b["end"]:
            return b["name"]
    return None

def continuation_block(d: date) -> str | None:
    """Return block name if date is within 4 weeks of a block boundary."""
    for b in KNOWN_BLOCKS:
        after_end   = b["end"]   < d <= b["end"]   + GAP
        before_start = b["start"] - GAP <= d < b["start"]

        if after_end:
            if b["hard_cutoff"] and d >= b["hard_cutoff"]:
                continue
            return b["name"]
        if before_start:
            return b["name"]
    return None

def block_start_for(name: str) -> date:
    for b in KNOWN_BLOCKS:
        if b["name"] == name:
            return b["start"]
    return date.today()

def week_number(d: date, block_start: date) -> int:
    return (d - block_start).days // 7 + 1

def convert_exercises(records: list) -> list:
    """
    Each boostcamp set → one DynamoDB exercise entry.
    Strips parenthetical equipment type from name.
    """
    out = []
    for record in records:
        name = record.get("name", "Unknown")
        if "(" in name:
            name = name[:name.index("(")].strip()

        for s in record.get("sets", []):
            weight    = s.get("value", "0")
            reps      = s.get("amount", "0")
            weight_unit = s.get("weight_unit", "kg")

            if not weight or not reps:
                continue

            if weight_unit == "lbs":
                weight = str(round(float(weight) * 0.453592, 2))

            out.append({
                "M": {
                    "failed": {"BOOL": False},
                    "kg":     {"N": str(weight)},
                    "name":   {"S": name},
                    "notes":  {"S": ""},
                    "reps":   {"N": str(reps)},
                    "sets":   {"N": "1"},
                }
            })
    return out

def build_dynamo(
    workout:         dict,
    workout_date:    date,
    block_name:      str,
    block_start:     date,
    is_continuation: bool,
    ordinal:         int,
) -> dict:
    sid      = str(uuid.uuid4())
    date_str = workout_date.strftime("%Y-%m-%d")
    week_num = week_number(workout_date, block_start)

    return {
        "pk":                     {"S": "operator"},
        "sk":                     {"S": f"session#program#{PROGRAM_VERSION}#{date_str}#{ordinal:03d}#{sid}"},
        "block":                  {"S": block_name},
        "body_weight_kg":         {"NULL": True},
        "completed":              {"BOOL": True},
        "date":                   {"S": date_str},
        "day":                    {"S": workout_date.strftime("%A")},
        "entity_type":            {"S": "session"},
        "exercises":              {"L": convert_exercises(workout.get("records", []))},
        "id":                     {"S": sid},
        "is_continuation":        {"BOOL": is_continuation},
        "pain_log":               {"L": []},
        "phase":                  {"M": {}},
        "phase_name":             {"S": ""},
        "phase_ref":              {"S": f"phase#{block_name}"},
        "planned_exercises":      {"L": []},
        "program_sk":             {"S": f"program#{PROGRAM_VERSION}"},
        "program_version":        {"S": PROGRAM_VERSION},
        "program_version_number": {"N": str(PROGRAM_VERSION_NUMBER)},
        "same_day_ordinal":       {"N": str(ordinal)},
        "session_id":             {"S": sid},
        "session_notes":          {"S": ""},
        "status":                 {"S": "completed"},
        "updated_at": {"S": datetime.now(timezone.utc).isoformat()},
        "week":                   {"S": f"W{week_num}"},
        "week_number":            {"N": str(week_num)},
    }

# ─── Load ─────────────────────────────────────────────────────────────────────

with open("workouts.json", encoding="utf-8") as f:
    raw = json5.load(f)

all_workouts: list[tuple[date, dict]] = []
for date_str, sessions in raw["data"].items():
    d = parse_date(date_str)
    for session in sessions:
        all_workouts.append((d, session))

all_workouts.sort(key=lambda x: x[0])

# ─── Classify ─────────────────────────────────────────────────────────────────

dropped      = []   # already in DB
continuations = []  # (date, workout, block_name)
unassigned   = []   # (date, workout) – candidates for new blocks

for d, workout in all_workouts:
    inside = inside_known_block(d)
    if inside:
        dropped.append((d, workout, inside))
        continue

    cont = continuation_block(d)
    if cont:
        continuations.append((d, workout, cont))
    else:
        unassigned.append((d, workout))

# ─── Group unassigned into new blocks by 4-week gap ──────────────────────────

new_block_groups: list[list[tuple[date, dict]]] = []
if unassigned:
    group = [unassigned[0]]
    for i in range(1, len(unassigned)):
        if unassigned[i][0] - unassigned[i - 1][0] > GAP:
            new_block_groups.append(group)
            group = []
        group.append(unassigned[i])
    new_block_groups.append(group)

new_blocks: list[dict] = []
for idx, group in enumerate(new_block_groups, 1):
    start = group[0][0]
    end   = group[-1][0]
    new_blocks.append({
        "name":     f"block-{start.strftime('%Y-%m')}-{idx}",
        "start":    start,
        "end":      end,
        "workouts": group,
    })

# ─── Build DynamoDB objects ───────────────────────────────────────────────────

output          = []
ordinal_counter = defaultdict(int)

for d, workout, block_name in continuations:
    ordinal_counter[d] += 1
    output.append(build_dynamo(
        workout, d, block_name,
        block_start     = block_start_for(block_name),
        is_continuation = True,
        ordinal         = ordinal_counter[d],
    ))

for nb in new_blocks:
    for d, workout in nb["workouts"]:
        ordinal_counter[d] += 1
        output.append(build_dynamo(
            workout, d, nb["name"],
            block_start     = nb["start"],
            is_continuation = False,
            ordinal         = ordinal_counter[d],
        ))

output.sort(key=lambda x: x["date"]["S"])

# ─── Write ────────────────────────────────────────────────────────────────────

with open("dynamo_sessions.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

# ─── Summary ──────────────────────────────────────────────────────────────────

print(f"\n{'─'*50}")
print(f"Dropped  (already in blocks) : {len(dropped)}")
for d, _, b in dropped:
    print(f"   {d}  →  {b}")

print(f"\nContinuations                : {len(continuations)}")
for d, _, b in continuations:
    print(f"   {d}  →  {b}  (continuation)")

print(f"\nNew blocks created           : {len(new_blocks)}")
for nb in new_blocks:
    print(f"   {nb['name']}  {nb['start']} → {nb['end']}  ({len(nb['workouts'])} sessions)")

print(f"\nOutput objects written       : {len(output)}")
print(f"{'─'*50}\n")