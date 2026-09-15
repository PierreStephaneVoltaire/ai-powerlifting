import asyncio
import copy
import importlib
import json
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError

from services.contract import load_operations


class FakeHealthTable:
    def __init__(self):
        self.items = {}
        self.program = None
        self.put_calls = []
        self.conflict_updates = 0

    def get_item(self, **kwargs):
        key = kwargs["Key"]
        if key["sk"] == "program#current":
            item = {"ref_sk": "program#v003"}
        elif key["sk"] == "program#v003":
            item = self.program or {"phases": [{"name": "Strength"}]}
        else:
            item = self.items.get((key["pk"], key["sk"]))
        if item is None:
            return {}
        if kwargs.get("ProjectionExpression"):
            fields = {field.strip() for field in kwargs["ProjectionExpression"].split(",")}
            item = {key: value for key, value in item.items() if key in fields}
        return {"Item": copy.deepcopy(item)}

    def put_item(self, **kwargs):
        self.put_calls.append(copy.deepcopy(kwargs))
        item = copy.deepcopy(kwargs["Item"])
        key = (item["pk"], item["sk"])
        current = self.items.get(key)
        condition = kwargs.get("ConditionExpression", "")
        values = kwargs.get("ExpressionAttributeValues", {})
        valid = True
        if "attribute_not_exists(pk)" in condition:
            valid = current is None
        if "allocation_revision = :revision" in condition:
            valid = valid and current is not None and current.get("allocation_revision") == values[":revision"]
        if "status = :status" in condition and kwargs.get("ExpressionAttributeNames", {}).get("#status") != "status":
            raise AssertionError("reserved status must use ExpressionAttributeNames")
        if "#status = :status" in condition:
            valid = valid and current is not None and current.get("status") == values[":status"]
        if not valid:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[key] = item

    def update_item(self, **kwargs):
        if self.conflict_updates:
            self.conflict_updates -= 1
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
        key = (kwargs["Key"]["pk"], kwargs["Key"]["sk"])
        item = copy.deepcopy(self.get_item(Key=kwargs["Key"])["Item"])
        values = kwargs.get("ExpressionAttributeValues", {})
        current = values.get(":current")
        if current is not None and item.get("lift_profiles") != current:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
        item["lift_profiles"] = copy.deepcopy(values[":next"])
        self.items[key] = item
        self.program = item


class FakeStore:
    def __init__(self):
        self.sessions = [{
            "id": "session-1",
            "session_id": "session-1",
            "date": "2026-09-13",
            "day": "Sunday",
            "week_number": 3,
            "phase": {"name": "Strength"},
            "exercises": [{"name": "Squat", "sets": 3, "reps": 5, "kg": 140}],
            "videos": [{
                "video_id": "vid-1",
                "s3_key": "videos/2026-09-13/vid-1.mp4",
                "uploaded_at": "2026-09-13T10:00:00+00:00",
                "thumbnail_s3_key": "thumbnails/2026-09-13/vid-1.jpg",
                "thumbnail_status": "ready",
                "exercise_name": "Squat",
                "set_number": 2,
            }],
        }]
        self.patches = []

    def list_sessions_sync(self, program_sk, phases):
        return self.sessions

    def patch_session_sync(self, program_sk, date, patch, phases):
        self.patches.append((program_sk, date, patch))
        self.sessions[0].update(patch)
        return self.sessions[0]


class FakeS3:
    def __init__(self):
        self.deleted = []
        self.uploads = []
        self.objects = {}

    def add_object(self, key, metadata, size=11):
        self.objects[key] = {"ContentLength": size, "Metadata": metadata}

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs)

    def put_object(self, **kwargs):
        self.uploads.append(kwargs)

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://upload.test/{Params['Key']}"

    def head_object(self, **kwargs):
        if kwargs["Key"] not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
        return copy.deepcopy(self.objects[kwargs["Key"]])


def register_media(table, video_id="vid-1", status="ready", revision=1, program_sk="program#v003"):
    table.items[("athlete-1", f"Media#{video_id}")] = {
        "pk": "athlete-1", "sk": f"Media#{video_id}", "media_id": video_id, "video_id": video_id,
        "session_id": "session-1", "session_date": "2026-09-13", "program_sk": program_sk,
        "s3_key": f"videos/2026-09-13/{video_id}.mp4",
        "thumbnail_s3_key": f"thumbnails/2026-09-13/{video_id}.jpg",
        "processed_s3_key": f"processed/2026-09-13/{video_id}.mp4" if status == "ready" else None,
        "allocation_revision": revision, "status": status,
    }


def register_form_media(table, video_id, status="ready", revision=1):
    table.items[("athlete-1", f"Media#{video_id}")] = {
        "pk": "athlete-1", "sk": f"Media#{video_id}", "media_id": video_id, "video_id": video_id,
        "session_id": "lift-profile:squat:front", "session_date": "2026-09-13", "program_sk": "program#v003",
        "lift": "squat", "angle": "front", "allocation_revision": revision, "status": status,
    }


def _core(name):
    return importlib.import_module(f"lambda.pod_videos.handlers.{name}.core")


def _patch_core(core, store, s3=None):
    core.get_health_table = lambda: store.health_table
    core.get_session_store = lambda args: store
    if s3 is not None:
        core.get_s3 = lambda: s3


def test_video_contracts_have_handlers_and_result_shapes():
    operations = load_operations("videos")
    assert set(operations) == {
        "video_library_get",
        "video_remove",
        "video_update_metadata",
        "video_upload_presign",
        "video_upload_confirm",
        "video_media_resolve",
    }
    for operation in operations.values():
        importlib.import_module(operation.handler)
        assert operation.result_schema
    operations["video_library_get"].validate_result({"videos": [], "exercises": []})
    operations["video_remove"].validate_result({"removed": "vid-1"})


def test_library_resolves_exercise_set_and_sort_filter():
    core = _core("video_library_get")
    store = FakeStore()
    store.health_table = FakeHealthTable()
    _patch_core(core, store)

    result = asyncio.run(core.video_library_get({"pk": "athlete-1", "version": "current", "sort": "weight"}))

    assert result["exercises"] == ["Squat"]
    assert result["videos"][0]["exercise_kg"] == 140
    assert result["videos"][0]["exercise_sets"] == 3
    assert result["videos"][0]["exercise_reps"] == 5


def test_library_converts_dynamodb_decimals_before_contract_validation():
    core = _core("video_library_get")
    store = FakeStore()
    store.health_table = FakeHealthTable()
    store.sessions[0]["week_number"] = Decimal("3")
    store.sessions[0]["exercises"][0].update({"sets": Decimal("3"), "reps": Decimal("5"), "kg": Decimal("140.5")})
    store.sessions[0]["videos"][0]["set_number"] = Decimal("2")
    _patch_core(core, store)

    result = asyncio.run(core.video_library_get({"pk": "athlete-1", "version": "current", "sort": "weight"}))

    load_operations("videos")["video_library_get"].validate_result(result)
    assert result["videos"][0]["week_number"] == 3
    assert result["videos"][0]["exercise_kg"] == 140.5
    assert result["videos"][0]["video"]["set_number"] == 2


def test_metadata_and_remove_preserve_session_storage():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    register_media(store.health_table)
    s3 = FakeS3()

    metadata = _core("video_update_metadata")
    _patch_core(metadata, store)
    changed = asyncio.run(metadata.video_update_metadata({"pk": "athlete-1", "session_date": "2026-09-13", "video_id": "vid-1", "notes": "top set"}))
    assert changed["notes"] == "top set"
    assert changed["s3_key"].endswith("vid-1.mp4")

    remove = _core("video_remove")
    _patch_core(remove, store, s3)
    assert asyncio.run(remove.video_remove({"pk": "athlete-1", "session_date": "2026-09-13", "video_id": "vid-1"})) == {"removed": "vid-1"}
    assert store.patches[-1][2]["videos"] is None


def test_form_remove_clears_ready_slot():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    store.health_table.program = {
        "pk": "athlete-1", "sk": "program#v003", "phases": [],
        "lift_profiles": [{"lift": "squat", "form_videos": {"front": {
            "video_id": "form-ready", "s3_key": "processed/form-ready.mp4", "thumbnail_status": "ready",
            "processing_status": "ready", "allocation_revision": 1,
        }}}],
    }
    register_form_media(store.health_table, "form-ready")
    remove = _core("video_remove")
    _patch_core(remove, store)
    args = {"pk": "athlete-1", "session_date": "2026-09-13", "video_id": "form-ready"}
    assert asyncio.run(remove.video_remove(args)) == {"removed": "form-ready"}
    assert "front" not in store.health_table.program["lift_profiles"][0]["form_videos"]
    assert asyncio.run(remove.video_remove(args)) == {"removed": "form-ready"}


def test_form_remove_clears_first_pending_slot_when_ids_match():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    store.health_table.program = {
        "pk": "athlete-1", "sk": "program#v003", "phases": [],
        "lift_profiles": [{"lift": "squat", "form_videos": {"front": {
            "video_id": "form-pending", "pending_media_id": "form-pending", "processing_status": "pending",
        }}}],
    }
    register_form_media(store.health_table, "form-pending", status="allocated")
    remove = _core("video_remove")
    _patch_core(remove, store)
    assert asyncio.run(remove.video_remove({"pk": "athlete-1", "session_date": "2026-09-13", "video_id": "form-pending"})) == {"removed": "form-pending"}
    assert "front" not in store.health_table.program["lift_profiles"][0]["form_videos"]


def test_form_remove_old_ready_preserves_pending():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    store.health_table.program = {
        "pk": "athlete-1", "sk": "program#v003", "phases": [],
        "lift_profiles": [{"lift": "squat", "form_videos": {"front": {
            "video_id": "form-old", "s3_key": "processed/form-old.mp4", "thumbnail_status": "pending",
            "processing_status": "pending", "pending_media_id": "form-new", "pending_s3_key": "uploads/form-new.mp4",
            "target_revision": 2,
        }}}],
    }
    register_form_media(store.health_table, "form-old")
    remove = _core("video_remove")
    _patch_core(remove, store)
    result = asyncio.run(remove.video_remove({"pk": "athlete-1", "session_date": "2026-09-13", "video_id": "form-old"}))
    slot = store.health_table.program["lift_profiles"][0]["form_videos"]["front"]
    assert result == {"removed": "form-old"}
    assert slot["pending_media_id"] == "form-new"
    assert "video_id" not in slot
    assert "pending_s3_key" in slot


def test_form_remove_pending_preserves_ready():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    store.health_table.program = {
        "pk": "athlete-1", "sk": "program#v003", "phases": [],
        "lift_profiles": [{"lift": "squat", "form_videos": {"front": {
            "video_id": "form-old", "s3_key": "processed/form-old.mp4", "thumbnail_status": "pending",
            "processing_status": "failed", "pending_media_id": "form-new", "pending_s3_key": "uploads/form-new.mp4",
            "target_revision": 2, "failure": "decode failed",
        }}}],
    }
    register_form_media(store.health_table, "form-new")
    remove = _core("video_remove")
    _patch_core(remove, store)
    result = asyncio.run(remove.video_remove({"pk": "athlete-1", "session_date": "2026-09-13", "video_id": "form-new"}))
    slot = store.health_table.program["lift_profiles"][0]["form_videos"]["front"]
    assert result == {"removed": "form-new"}
    assert slot["video_id"] == "form-old"
    assert slot["s3_key"] == "processed/form-old.mp4"
    assert slot["processing_status"] == "ready"
    assert slot["thumbnail_status"] == "ready"
    assert "pending_media_id" not in slot


def test_form_remove_retries_profile_cas_without_losing_slot_state():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    store.health_table.program = {
        "pk": "athlete-1", "sk": "program#v003", "phases": [],
        "lift_profiles": [{"lift": "squat", "form_videos": {"front": {
            "video_id": "form-old", "s3_key": "processed/form-old.mp4", "pending_media_id": "form-new",
            "pending_s3_key": "uploads/form-new.mp4", "target_revision": 2,
        }}}],
    }
    store.health_table.conflict_updates = 1
    register_form_media(store.health_table, "form-old")
    remove = _core("video_remove")
    _patch_core(remove, store)
    assert asyncio.run(remove.video_remove({"pk": "athlete-1", "session_date": "2026-09-13", "video_id": "form-old"})) == {"removed": "form-old"}
    slot = store.health_table.program["lift_profiles"][0]["form_videos"]["front"]
    assert slot == {"pending_media_id": "form-new", "pending_s3_key": "uploads/form-new.mp4", "target_revision": 2}


def test_presign_and_confirm_keep_file_bytes_out_of_domain_json():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    s3 = FakeS3()
    presign = _core("video_upload_presign")
    _patch_core(presign, store, s3)
    ticket = asyncio.run(presign.video_upload_presign({
        "pk": "athlete-1",
        "session_date": "2026-09-13",
        "filename": "attempt.mp4",
        "mimetype": "video/mp4",
    }))
    s3.add_object(ticket["s3_key"], ticket["metadata"])
    assert ticket["metadata"]["pk"] == "athlete-1"

    confirm = _core("video_upload_confirm")
    _patch_core(confirm, store, s3)
    video = asyncio.run(confirm.video_upload_confirm({
        "pk": "athlete-1",
        "session_date": "2026-09-13",
        "video_id": ticket["video_id"],
        "s3_key": ticket["s3_key"],
        "exercise_name": "Squat",
    }))
    assert video["s3_key"] == ticket["s3_key"]
    assert store.patches[-1][2]["videos"][-1]["video_id"] == ticket["video_id"]


def test_form_reservation_is_installed_before_confirm():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    store.health_table.program = {
        "pk": "athlete-1", "sk": "program#v003", "phases": [{"name": "Strength"}],
        "lift_profiles": [{"lift": "squat", "style_notes": "", "sticking_points": "", "primary_muscle": "", "volume_tolerance": "moderate", "form_videos": {
            "front": {"video_id": "old", "s3_key": "processed/old.mp4", "thumbnail_status": "ready", "target_revision": 2},
        }}],
    }
    s3 = FakeS3()
    args = {
        "pk": "athlete-1", "session_date": "2026-09-13", "filename": "form.mp4",
        "mimetype": "video/mp4", "lift": "squat", "angle": "front", "idempotency_key": "form-1", "expected_size": 11,
    }
    presign = _core("video_upload_presign")
    _patch_core(presign, store, s3)
    ticket = asyncio.run(presign.video_upload_presign(args))
    slot = store.health_table.program["lift_profiles"][0]["form_videos"]["front"]
    assert slot["pending_media_id"] == ticket["video_id"]
    assert slot["video_id"] == "old"
    assert slot["target_revision"] == 3
    assert slot["source_filename"] == "form.mp4"
    assert slot["source_size"] == 11
    s3.add_object(ticket["s3_key"], ticket["metadata"])
    confirm = _core("video_upload_confirm")
    _patch_core(confirm, store, s3)
    result = asyncio.run(confirm.video_upload_confirm({**args, "video_id": ticket["video_id"], "s3_key": ticket["s3_key"]}))
    assert result["video_id"] == ticket["video_id"]


def test_failed_processing_retry_reuses_id_and_advances_registry_revision():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    s3 = FakeS3()
    presign = _core("video_upload_presign")
    _patch_core(presign, store, s3)
    args = {
        "pk": "athlete-1", "session_date": "2026-09-13", "filename": "attempt.mp4",
        "mimetype": "video/mp4", "idempotency_key": "retry-1", "expected_size": 11,
    }
    ticket = asyncio.run(presign.video_upload_presign(args))
    s3.add_object(ticket["s3_key"], ticket["metadata"])
    confirm = _core("video_upload_confirm")
    _patch_core(confirm, store, s3)
    asyncio.run(confirm.video_upload_confirm({**args, "video_id": ticket["video_id"], "s3_key": ticket["s3_key"]}))
    current = store.health_table.items[("athlete-1", f"Media#{ticket['video_id']}")]
    store.health_table.items[("athlete-1", f"Media#{ticket['video_id']}")] = {**current, "status": "failed"}
    retry = asyncio.run(presign.video_upload_presign(args))
    assert retry["video_id"] == ticket["video_id"]
    assert retry["metadata"]["allocation_revision"] == "2"
    s3.add_object(retry["s3_key"], retry["metadata"])
    video = asyncio.run(confirm.video_upload_confirm({**args, "video_id": retry["video_id"], "s3_key": retry["s3_key"]}))
    assert video["allocation_revision"] == 2
    assert video["thumbnail_status"] == "pending"
    assert video["idempotency_key"] == args["idempotency_key"]


def test_duplicate_confirmation_uses_completed_registry_after_source_disappears():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    s3 = FakeS3()
    presign = _core("video_upload_presign")
    _patch_core(presign, store, s3)
    args = {
        "pk": "athlete-1", "session_date": "2026-09-13", "filename": "attempt.mp4",
        "mimetype": "video/mp4", "idempotency_key": "complete-1", "expected_size": 11,
    }
    ticket = asyncio.run(presign.video_upload_presign(args))
    s3.add_object(ticket["s3_key"], ticket["metadata"])
    confirm = _core("video_upload_confirm")
    _patch_core(confirm, store, s3)
    first = asyncio.run(confirm.video_upload_confirm({**args, "video_id": ticket["video_id"], "s3_key": ticket["s3_key"]}))
    confirmed_put = next(call for call in store.health_table.put_calls if call["Item"].get("status") == "confirmed")
    assert confirmed_put["ConditionExpression"] == "allocation_revision = :revision AND #status = :status"
    assert confirmed_put["ExpressionAttributeNames"] == {"#status": "status"}
    media_key = ("athlete-1", f"Media#{ticket['video_id']}")
    media = store.health_table.items[media_key]
    processed_key = f"processed/2026-09-13/{ticket['video_id']}/r1.mp4"
    store.health_table.items[media_key] = {**media, "status": "ready", "processed_s3_key": processed_key}
    s3.objects.pop(ticket["s3_key"])
    second = asyncio.run(confirm.video_upload_confirm({**args, "video_id": ticket["video_id"], "s3_key": ticket["s3_key"]}))
    assert second == first


def test_same_day_upload_requires_the_stable_session_id():
    store = FakeStore()
    store.sessions.append({"id": "session-2", "session_id": "session-2", "date": "2026-09-13", "videos": []})
    store.health_table = FakeHealthTable()
    presign = _core("video_upload_presign")
    _patch_core(presign, store)
    args = {"pk": "athlete-1", "session_date": "2026-09-13", "filename": "attempt.mp4", "mimetype": "video/mp4"}
    with pytest.raises(ValueError, match="session_id is required"):
        asyncio.run(presign.video_upload_presign(args))
    ticket = asyncio.run(presign.video_upload_presign({**args, "session_id": "session-2"}))
    assert ticket["metadata"]["session_id"] == "session-2"


def test_confirm_rejects_an_object_owned_by_another_athlete():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    s3 = FakeS3()
    confirm = _core("video_upload_confirm")
    _patch_core(confirm, store, s3)
    with pytest.raises(ValueError, match="allocation not found"):
        asyncio.run(confirm.video_upload_confirm({
            "pk": "athlete-2",
            "session_date": "2026-09-13",
            "video_id": "vid-1",
            "s3_key": "videos/2026-09-13/vid-1.mp4",
        }))


def test_confirm_rejects_empty_object():
    store = FakeStore()
    store.health_table = FakeHealthTable()
    s3 = FakeS3()
    register_media((store.health_table), "vid-2", status="allocated", revision=1)
    s3.add_object("videos/2026-09-13/vid-2.mp4", {
        "video_id": "vid-2", "media_id": "vid-2", "session_date": "2026-09-13", "session_id": "session-1",
        "pk": "athlete-1", "sk": "program#v003", "allocation_revision": "1",
    }, size=0)
    confirm = _core("video_upload_confirm")
    _patch_core(confirm, store, s3)
    with pytest.raises(ValueError, match="empty"):
        asyncio.run(confirm.video_upload_confirm({
            "pk": "athlete-1", "session_date": "2026-09-13", "video_id": "vid-2",
            "s3_key": "videos/2026-09-13/vid-2.mp4",
        }))


def test_media_resolve_rejects_a_forged_thumbnail_key():
    core = _core("video_media_resolve")
    store = FakeStore()
    store.health_table = FakeHealthTable()
    register_media(store.health_table)
    _patch_core(core, store)
    assert asyncio.run(core.video_media_resolve({
        "pk": "athlete-1", "s3_key": "thumbnails/2026-09-13/vid-1.jpg",
    })) == "thumbnails/2026-09-13/vid-1.jpg"
    with pytest.raises(ValueError, match="not attached"):
        asyncio.run(core.video_media_resolve({
            "pk": "athlete-1", "session_date": "2026-09-13",
            "s3_key": "thumbnails/2026-09-13/other-video.jpg",
        }))


def test_media_resolve_supports_revisioned_processed_keys():
    core = _core("video_media_resolve")
    store = FakeStore()
    store.health_table = FakeHealthTable()
    register_media(store.health_table)
    media_key = ("athlete-1", "Media#vid-1")
    media = store.health_table.items[media_key]
    store.health_table.items[media_key] = {
        **media,
        "processed_s3_key": "processed/2026-09-13/vid-1/r2.mp4",
        "thumbnail_s3_key": "thumbnails/2026-09-13/vid-1/r2.jpg",
    }
    store.sessions[0]["videos"][0]["processed_s3_key"] = "processed/2026-09-13/vid-1/r2.mp4"
    _patch_core(core, store)
    assert asyncio.run(core.video_media_resolve({
        "pk": "athlete-1", "s3_key": "processed/2026-09-13/vid-1/r2.mp4",
    })) == "processed/2026-09-13/vid-1/r2.mp4"


def test_pod_handler_returns_json_and_rejects_unknown_function():
    handler = importlib.import_module("lambda.pod_videos.handler")
    unknown = handler.handler({"function": "missing"}, None)
    assert unknown["statusCode"] == 404
    assert json.loads(unknown["body"])["error"] == "unknown function: missing"
    assert handler.handler({"function": "video_update_thumbnail"}, None)["statusCode"] == 404
    assert handler.handler({"function": "video_upload"}, None)["statusCode"] == 404
