import copy, json, os, sys, types
from datetime import datetime, timezone
from decimal import Decimal

SRC = "/home/sirsimpalot/Downloads/discord-ai-bot/utils/ai-powerlifting/src"
OUT = sys.argv[1]
sys.path.insert(0, SRC)
os.environ.update({"IF_SESSIONS_TABLE_NAME": "if-sessions", "IF_HEALTH_TABLE_NAME": "if-health", "AWS_REGION": "ca-central-1", "HEALTH_PROGRAM_PK": "operator"})

increments = []
stub = types.ModuleType("services.runtime.valkey")
stub.increment = lambda key: increments.append(key)
stub.get_text = lambda key: None
sys.modules["services.runtime.valkey"] = stub

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from boto3.dynamodb.conditions import ConditionBase
import services.runtime.aws as aws
import services.runtime.session_store as ss
import services.runtime.program_store as ps
from services.runtime.contract import load_operations
from services.runtime import dispatch as disp

SER, DES = TypeSerializer(), TypeDeserializer()


def roundtrip(item):
    return {k: DES.deserialize(SER.serialize(v)) for k, v in item.items()}


def decimals(value):
    return json.loads(json.dumps(value), parse_float=Decimal, parse_int=Decimal)


def conditions(expr):
    exp = expr.get_expression()
    if exp["operator"] == "AND":
        out = {}
        for c in exp["values"]:
            out.update(conditions(c))
        return out
    name = exp["values"][0].name
    return {name: (exp["operator"], [v for v in exp["values"][1:]])}


class FakeTable:
    def __init__(self, name, items):
        self.name = name
        self.items = {(i["pk"], i["sk"]): roundtrip(i) for i in items}

    def get_item(self, Key, **kw):
        item = self.items.get((Key["pk"], Key["sk"]))
        if not item:
            return {}
        item = copy.deepcopy(item)
        proj = kw.get("ProjectionExpression")
        if proj:
            item = {k: v for k, v in item.items() if k in [p.strip() for p in proj.split(",")]}
        return {"Item": item}

    def query(self, **kw):
        c = conditions(kw["KeyConditionExpression"])
        pk = c["pk"][1][0]
        rows = [v for (p, s), v in self.items.items() if p == pk]
        if "sk" in c:
            op, vals = c["sk"]
            if op == "begins_with":
                rows = [r for r in rows if r["sk"].startswith(vals[0])]
            elif op == "BETWEEN":
                rows = [r for r in rows if vals[0] <= r["sk"] <= vals[1]]
        rows.sort(key=lambda r: r["sk"], reverse=kw.get("ScanIndexForward") is False)
        return {"Items": copy.deepcopy(rows)}

    def put_item(self, Item, **kw):
        assert not kw
        self.items[(Item["pk"], Item["sk"])] = roundtrip(Item)

    def delete_item(self, Key, **kw):
        assert not kw
        self.items.pop((Key["pk"], Key["sk"]), None)

    def batch_writer(self):
        table = self

        class Batch:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def delete_item(self, Key):
                table.delete_item(Key=Key)

            def put_item(self, Item):
                table.put_item(Item=Item)

        return Batch()


class FakeResource:
    def __init__(self, tables):
        self.tables = tables

    def Table(self, name):
        return self.tables[name]


class Counter:
    n = 0

    @classmethod
    def uuid4(cls):
        cls.n += 1
        return f"uuid-{cls.n:04d}"


class FixedDatetime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 11, 14, 12, 0, 0, 123456, tzinfo=timezone.utc)


ss.uuid = Counter
ss.datetime = FixedDatetime

import services.sessions.session_list.core as list_core
OPS = load_operations("sessions")
PK = "athlete"

PHASES = [
    {"name": "Hypertrophy", "intent": "volume", "start_week": 1, "end_week": 4, "block": "current", "target_rpe": 7.5},
    {"name": "Peak #2", "intent": "", "start_week": 5, "end_week": 8, "block": "current"},
    {"name": "Old", "intent": "legacy", "start_week": 1, "end_week": 3, "block": "b1"},
]


def health(published=None, phases=True, pointer="program#v002"):
    items = []
    if pointer:
        items.append({"pk": PK, "sk": "program#current", "ref_sk": pointer, "version": 2})
    v2 = {"pk": PK, "sk": "program#v002", "meta": {"current_block_id": "current"}}
    if phases:
        v2["phases"] = PHASES
    if published is not None:
        v2["published"] = published
    items += [v2, {"pk": PK, "sk": "program#v001", "meta": {}, "phases": [{"name": "V1", "start_week": 1, "end_week": 12, "block": "current"}]}]
    return items


def sess(program, date, ordinal, sid, **extra):
    base = {
        "pk": PK, "sk": f"session#{program}#{date}#{ordinal:03d}#{sid}", "entity_type": "session", "source_pk": PK,
        "source_table": "if-health", "program_sk": program, "program_version": program.removeprefix("program#"),
        "program_version_number": int(program[-3:]), "source_index": 0, "same_day_ordinal": ordinal,
        "session_id": sid, "id": sid, "date": date, "week_number": 1, "block": "current", "block_id": "current",
        "status": "planned", "completed": False, "exercises": [], "planned_exercises": [],
        "phase": {"name": "Hypertrophy", "intent": "volume", "start_week": 1, "end_week": 4, "block": "current"},
        "phase_name": "Hypertrophy", "phase_ref": "phase#current#W1-W4#Hypertrophy", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(extra)
    return base


def seed_sessions():
    v2 = "program#v002"
    return [
        sess(v2, "2026-09-14", 1, "s-a", week_number=1, label="Squat day", name="A", status="completed", completed=True, source_index=0,
             exercises=[{"name": "Squat", "sets": 3, "reps": 5, "kg": 100.5, "rpe": 8, "set_ids": ["x1", "x2", "x3"], "id": "ex-1"}, {"name": "Bench", "sets": 2, "kg": 80, "notes": "n"}],
             videos=[{"video_id": "vid-1", "thumbnail_status": "ready"}], media_revision=3, body_weight_kg=82.5, body_weight_lb=181.9, session_rpe=7.5),
        sess(v2, "2026-09-14", 2, "s-b", week_number=1, status="planned", source_index=1, exercises=[{"name": "Row", "sets": 4, "kg": 60}]),
        sess(v2, "2026-09-16", 1, "s-c", week_number=2, source_index=2, label="Bench", exercises=[]),
        sess(v2, "2026-10-05", 1, "s-d", week_number=5, source_index=3, phase={"name": "Peak #2", "intent": "", "start_week": 5, "end_week": 8, "block": "current"}, phase_name="Peak #2", phase_ref="phase#current#W5-W8#Peak -2"),
        sess(v2, "2026-06-01", 1, "s-old", week_number=2, block="b1", block_id="b1", source_index=4, phase={"name": "Old", "intent": "legacy", "start_week": 1, "end_week": 3, "block": "b1"}, phase_name="Old"),
        sess(v2, "2026-11-01", 1, "s-e", week_number=9, source_index=5, exercises=[{"name": "DL", "sets": 1, "kg": 200}]),
        {"pk": PK, "sk": "session#program#v002#2026-11-02#001#legacy", "session_id": "legacy", "date": "2026-11-02", "week": "W6", "exercises": [], "program_sk": "program#v002"},
        sess("program#v001", "2026-02-01", 1, "v1-a", week_number=3, phase={"name": "V1", "start_week": 1, "end_week": 12, "block": "current"}, phase_name="V1"),
        {"pk": "other", "sk": "session#program#v002#2026-09-14#001#o1", "session_id": "o1", "date": "2026-09-14", "program_sk": "program#v002"},
    ]


ALL_ACCESS = {"is_self": True, "permissions": []}
VIEWER = {"is_self": False, "permissions": ["sessions:read"], "granted_permissions": ["sessions:read"]}
VIEWER_CURRENT_ONLY = {"is_self": False, "permissions": ["sessions:read", "videos:read"], "granted_permissions": []}
VIEWER_FULL = {"is_self": False, "permissions": ["sessions:read", "videos:read", "weight-log:read"], "granted_permissions": ["sessions:read"]}

SCENARIOS = []


def scenario(name, op, args, seed=None, health_items=None, access=None, athlete=PK):
    SCENARIOS.append({"name": name, "op": op, "args": args, "athlete": athlete, "access": access or ALL_ACCESS, "seed": {"sessions": seed if seed is not None else seed_sessions(), "health": health_items if health_items is not None else health()}})


scenario("list_default", "session_list", {})
scenario("list_limit_2", "session_list", {"limit": 2})
scenario("list_limit_clamped_low", "session_list", {"limit": 0})
scenario("list_limit_clamped_high", "session_list", {"limit": 9999})
scenario("list_alias_current", "session_list", {"program_sk": "current"})
scenario("list_alias_pointer", "session_list", {"program_sk": "program#current", "limit": 3})
scenario("list_v001", "session_list", {"program_sk": "program#v001"})
scenario("list_unknown_program", "session_list", {"program_sk": "program#v009"})
scenario("list_unpublished", "session_list", {}, health_items=health(published=False))
scenario("list_no_pointer", "session_list", {}, health_items=health(pointer=None))
scenario("list_empty_table", "session_list", {}, seed=[])
scenario("list_viewer_current_block_only", "session_list", {}, access=VIEWER_CURRENT_ONLY)
scenario("list_viewer_full", "session_list", {}, access=VIEWER)

scenario("list_full_default", "session_list_full", {})
scenario("list_full_v001", "session_list_full", {"program_sk": "program#v001"})
scenario("list_full_no_phases", "session_list_full", {}, health_items=health(phases=False))
scenario("list_full_unpublished", "session_list_full", {}, health_items=health(published=False))
scenario("list_full_viewer_strips", "session_list_full", {}, access=VIEWER)
scenario("list_full_viewer_current_only", "session_list_full", {}, access=VIEWER_CURRENT_ONLY)
scenario("list_full_viewer_full", "session_list_full", {}, access=VIEWER_FULL)

scenario("get_by_index", "session_get", {"date": "2026-09-14", "index": 0})
scenario("get_by_index_second", "session_get", {"date": "2026-09-14", "index": 1})
scenario("get_index_out_of_range", "session_get", {"date": "2026-09-14", "index": 5})
scenario("get_negative_index", "session_get", {"date": "2026-09-14", "index": -1})
scenario("get_by_id", "session_get", {"date": "x", "index": 0, "session_id": "s-d"})
scenario("get_by_id_missing", "session_get", {"date": "2026-09-14", "index": 0, "session_id": "gone"})
scenario("get_legacy_week_string", "session_get", {"date": "2026-11-02", "index": 0})
scenario("get_viewer_strips", "session_get", {"date": "2026-09-14", "index": 0}, access=VIEWER)
scenario("get_viewer_full", "session_get", {"date": "2026-09-14", "index": 0}, access=VIEWER_FULL)
scenario("get_unknown_date", "session_get", {"date": "2030-01-01", "index": 0})
scenario("get_unpublished", "session_get", {"date": "2026-09-14", "index": 0}, health_items=health(published=False))

dup_seed = seed_sessions() + [sess("program#v002", "2026-12-01", 1, "dup", source_index=7), sess("program#v002", "2026-12-02", 1, "dup", source_index=8)]
scenario("get_ambiguous_identity", "session_get", {"date": "2026-12-01", "index": 0, "session_id": "dup"}, seed=dup_seed)

scenario("create_basic", "session_create", {"session": {"date": "2026-09-20", "week_number": 3, "day": "Sunday", "session_notes": "hi", "exercises": [{"name": "Squat", "sets": 3, "reps": 5, "kg": 102.5, "rpe": 8.0}, {"name": "Pause", "sets": 2, "kg": 90, "set_ids": ["keep", ""]}]}})
scenario("create_second_same_day", "session_create", {"session": {"date": "2026-09-14", "week_number": 1, "exercises": []}})
scenario("create_with_id", "session_create", {"session": {"id": "my-id", "date": "2026-09-21", "week": "W4", "completed": True, "exercises": []}})
scenario("create_status_logged", "session_create", {"session": {"date": "2026-09-22", "status": "logged", "week_number": 2, "planned_exercises": [{"name": "Squat"}]}})
scenario("create_planned_exercises_not_list", "session_create", {"session": {"date": "2026-09-22", "planned_exercises": "nope", "week_number": 6}})
scenario("create_other_block", "session_create", {"session": {"date": "2026-06-10", "block": "b1", "week_number": 2, "exercises": []}})
scenario("create_unscheduled_week", "session_create", {"session": {"date": "2026-09-23", "week_number": 40, "exercises": []}})
scenario("create_float_variants", "session_create", {"session": {"date": "2026-09-24", "week_number": 1, "body_weight_kg": 100.0, "exercises": [{"name": "A", "sets": 1, "kg": 1e-07, "reps": 1.0, "notes": 1e22}]}})
scenario("create_conflicting_id", "session_create", {"session": {"id": "s-a", "date": "2026-09-30"}})
scenario("create_missing_date", "session_create", {"session": {"week_number": 1}})
scenario("create_empty_date", "session_create", {"session": {"date": ""}})
scenario("create_v001", "session_create", {"program_sk": "program#v001", "session": {"date": "2026-02-02", "week_number": 2}})
scenario("create_no_phases", "session_create", {"session": {"date": "2026-09-25", "week_number": 2}}, health_items=health(phases=False))
scenario("create_unpublished", "session_create", {"session": {"date": "2026-09-25"}}, health_items=health(published=False))
scenario("create_viewer_not_filtered", "session_create", {"session": {"date": "2026-09-26", "body_weight_kg": 90.5, "videos": [{"video_id": "v"}], "week_number": 2}}, access=VIEWER)
scenario("create_no_pointer", "session_create", {"session": {"date": "2026-09-27", "week_number": 1}}, health_items=health(pointer=None))

scenario("patch_by_index", "session_patch", {"date": "2026-09-14", "index": 0, "patch": {"session_notes": "logged", "completed": True, "session_rpe": 8.5}})
scenario("patch_by_index_second", "session_patch", {"date": "2026-09-14", "index": 1, "patch": {"status": "logged"}})
scenario("patch_preserves_media", "session_patch", {"date": "2026-09-14", "index": 0, "patch": {"videos": [], "media_revision": 99, "session_notes": "x"}})
scenario("patch_exercises_set_ids", "session_patch", {"date": "2026-09-14", "index": 0, "patch": {"exercises": [{"name": "Squat", "sets": 4, "kg": 105}, {"name": "Bench", "sets": 1, "set_ids": ["bb"]}]}})
scenario("patch_move_date", "session_patch", {"date": "2026-09-14", "index": 0, "session_id": "s-a", "patch": {"date": "2026-09-18"}})
scenario("patch_move_date_to_busy_day", "session_patch", {"date": "2026-09-16", "index": 0, "patch": {"date": "2026-09-14"}})
scenario("patch_week_change_rephases", "session_patch", {"date": "2026-09-16", "index": 0, "patch": {"week_number": 6}})
scenario("patch_by_id_ordering_changed", "session_patch", {"date": "2026-09-14", "index": 0, "session_id": "s-b", "patch": {"session_notes": "intended"}})
scenario("patch_identity_rejected", "session_patch", {"date": "2026-09-14", "index": 0, "patch": {"id": "new"}})
scenario("patch_session_id_rejected", "session_patch", {"date": "2026-09-14", "index": 0, "patch": {"session_id": "s-a"}})
scenario("patch_deleted_session", "session_patch", {"date": "2026-09-14", "index": 0, "session_id": "deleted", "patch": {"session_notes": "k"}})
scenario("patch_index_not_found", "session_patch", {"date": "2026-09-14", "index": 9, "patch": {}})
scenario("patch_legacy_session", "session_patch", {"date": "2026-11-02", "index": 0, "patch": {"session_notes": "legacy"}})
scenario("patch_viewer_not_filtered", "session_patch", {"date": "2026-09-14", "index": 0, "patch": {"session_notes": "q"}}, access=VIEWER)
scenario("patch_unpublished", "session_patch", {"date": "2026-09-14", "index": 0, "patch": {}}, health_items=health(published=False))

scenario("patch_by_date_unique", "session_patch_by_date", {"date": "2026-09-16", "patch": {"session_notes": "by date", "body_weight_kg": 83.25}})
scenario("patch_by_date_ambiguous", "session_patch_by_date", {"date": "2026-09-14", "patch": {"session_notes": "x"}})
scenario("patch_by_date_missing", "session_patch_by_date", {"date": "2031-09-14", "patch": {"session_notes": "x"}})
scenario("patch_by_date_with_id", "session_patch_by_date", {"date": "2026-09-14", "session_id": "s-b", "patch": {"session_notes": "id route"}})
scenario("patch_by_date_identity_rejected", "session_patch_by_date", {"date": "2026-09-16", "patch": {"id": "zzz"}})

scenario("replace_same_id", "session_replace", {"date": "2026-09-16", "index": 0, "session": {"id": "s-c", "date": "2026-09-16", "week_number": 2, "session_notes": "replaced"}})
scenario("replace_without_id_by_index", "session_replace", {"date": "2026-09-16", "index": 0, "session": {"date": "2026-09-16", "week_number": 2, "label": "L"}})
scenario("replace_different_id", "session_replace", {"date": "2026-09-16", "index": 0, "session": {"id": "other", "date": "2026-09-16"}})
scenario("replace_explicit_session_id_arg", "session_replace", {"date": "2026-09-14", "index": 0, "session_id": "s-b", "session": {"date": "2026-09-14", "week_number": 1, "exercises": [{"name": "X", "sets": 2}]}})
scenario("replace_move_date", "session_replace", {"date": "2026-09-16", "index": 0, "session": {"id": "s-c", "date": "2026-09-17", "week_number": 2}})

scenario("delete_by_index", "session_delete", {"date": "2026-09-14", "index": 1})
scenario("delete_by_id", "session_delete", {"date": "ignored", "index": 0, "session_id": "s-e"})
scenario("delete_missing", "session_delete", {"date": "2030-01-01", "index": 0})
scenario("delete_missing_id", "session_delete", {"date": "2030-01-01", "index": 0, "session_id": "nope"})

scenario("replace_all_reorder_and_new", "session_replace_all", {"sessions": [
    {"id": "s-b", "date": "2026-09-14", "week_number": 1, "exercises": [{"name": "Row", "sets": 1}]},
    {"id": "s-a", "date": "2026-09-14", "week_number": 1, "session_notes": "swapped", "exercises": [{"name": "Squat", "sets": 2, "kg": 100.5}], "videos": [], "media_revision": 1},
    {"date": "2026-09-30", "week_number": 3, "exercises": []},
    {"id": "s-d", "date": "2026-10-05", "week_number": 5},
]})
scenario("replace_all_position_overrides_id", "session_replace_all", {"sessions": [{"id": "brand-new", "date": "2026-09-16", "week_number": 2}]})
scenario("replace_all_new_day_same_id", "session_replace_all", {"sessions": [{"id": "s-c", "date": "2026-09-19", "week_number": 2}]})
scenario("replace_all_empty", "session_replace_all", {"sessions": []})
scenario("replace_all_missing_date", "session_replace_all", {"sessions": [{"id": "x"}]})
scenario("replace_all_duplicate_ids", "session_replace_all", {"sessions": [{"id": "new", "date": "2026-09-15"}, {"id": "new", "date": "2026-09-16"}]})
scenario("replace_all_existing_duplicates", "session_replace_all", {"sessions": [{"id": "q", "date": "2026-12-09"}]}, seed=dup_seed)
scenario("replace_all_v001", "session_replace_all", {"program_sk": "program#v001", "sessions": [{"date": "2026-02-01", "week_number": 3}, {"date": "2026-02-08", "week_number": 4}]})
scenario("replace_all_non_object", "session_replace_all", {"sessions": [1]})

scenario("range_basic", "health_get_sessions_range", {"start_date": "2026-09-14", "end_date": "2026-10-05"})
scenario("range_all", "health_get_sessions_range", {"start_date": "2000-01-01", "end_date": "2100-01-01"})
scenario("range_none", "health_get_sessions_range", {"start_date": "2030-01-01", "end_date": "2031-01-01"})
scenario("range_no_phases", "health_get_sessions_range", {"start_date": "2026-09-01", "end_date": "2026-12-01"}, health_items=health(phases=False))
scenario("range_viewer_strips", "health_get_sessions_range", {"start_date": "2026-09-01", "end_date": "2026-12-01"}, access=VIEWER)
scenario("range_viewer_current_only", "health_get_sessions_range", {"start_date": "2026-01-01", "end_date": "2026-12-01"}, access=VIEWER_CURRENT_ONLY)


def render(value):
    if isinstance(value, Decimal):
        return float(value) if value % 1 > 0 else int(value)
    if isinstance(value, dict):
        return {k: render(v) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v) for v in value]
    return value


def run(sc):
    Counter.n = 0
    increments.clear()
    tables = {"if-sessions": FakeTable("if-sessions", decimals(sc["seed"]["sessions"])), "if-health": FakeTable("if-health", decimals(sc["seed"]["health"]))}
    resource = FakeResource(tables)
    aws.dynamodb_resource = lambda *a, **k: resource
    for mod in (ss, ps, list_core):
        mod.dynamodb_resource = aws.dynamodb_resource
    list_core._table = None
    op = OPS[sc["op"]]
    arguments = json.loads(json.dumps(sc["args"]))
    arguments["pk"] = sc["athlete"]
    arguments["_person_pk"] = "person"
    arguments["_access"] = sc["access"]
    expect = {}
    try:
        op.validate_input({k: v for k, v in arguments.items() if not k.startswith("_")})
        result = disp.dispatch(op, arguments)
        expect["ok"] = True
        expect["result"] = result
    except ss.SessionIdentityConflictError as exc:
        expect.update(ok=False, status=409, code=exc.code, message=str(exc))
    except ValueError as exc:
        expect.update(ok=False, status=422, code="validation", message=str(exc))
    except Exception as exc:
        expect.update(ok=False, status=500, code=type(exc).__name__, message=str(exc))
    expect["sessions_after"] = [render(v) for _, v in sorted(tables["if-sessions"].items.items())]
    expect["health_after"] = [render(v) for _, v in sorted(tables["if-health"].items.items())]
    expect["increments"] = list(increments)
    return expect


def main():
    os.makedirs(OUT, exist_ok=True)
    out = []
    for sc in SCENARIOS:
        sc = copy.deepcopy(sc)
        expect = run(sc)
        sc["expect"] = json.loads(json.dumps(expect, default=lambda o: float(o) if isinstance(o, Decimal) and o % 1 > 0 else int(o) if isinstance(o, Decimal) else str(o)))
        out.append(sc)
    with open(os.path.join(OUT, "scenarios.json"), "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    bad = [s["name"] for s in out if not s["expect"]["ok"] and s["expect"]["status"] == 500]
    print(len(out), "scenarios; 500s:", bad)


main()
