import asyncio
import base64
import importlib
import json

import pytest

from services.contract import load_operations


class FakeHealthTable:
    def get_item(self, **kwargs):
        if kwargs["Key"]["sk"] == "program#current":
            return {"Item": {"ref_sk": "program#v003"}}
        return {"Item": {"phases": [{"name": "Strength"}]}}


class FakeStore:
    def __init__(self):
        self.sessions = [{
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

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs)

    def put_object(self, **kwargs):
        self.uploads.append(kwargs)

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://upload.test/{Params['Key']}"

    def head_object(self, **kwargs):
        return {
            "ContentLength": 11,
            "Metadata": {
                "video_id": kwargs["Key"].split("/")[-1].split(".")[0],
                "session_date": "2026-09-13",
                "pk": "athlete-1",
                "sk": "program#v003",
            },
        }


def _core(name):
    return importlib.import_module(f"lambda.pod_videos.handlers.{name}.core")


def _patch_core(core, store, s3=None):
    core.get_health_table = lambda: FakeHealthTable()
    core.get_session_store = lambda args: store
    if s3 is not None:
        core.get_s3 = lambda: s3


def test_video_contracts_have_handlers_and_result_shapes():
    operations = load_operations("videos")
    assert set(operations) == {
        "video_library_get",
        "video_remove",
        "video_update_metadata",
        "video_update_thumbnail",
        "video_upload",
        "video_upload_presign",
        "video_upload_confirm",
    }
    for operation in operations.values():
        importlib.import_module(operation.handler)
        assert operation.result_schema
    operations["video_library_get"].validate_result({"videos": [], "exercises": []})
    operations["video_remove"].validate_result({"removed": "vid-1"})


def test_library_resolves_exercise_set_and_sort_filter():
    core = _core("video_library_get")
    store = FakeStore()
    _patch_core(core, store)

    result = asyncio.run(core.video_library_get({"pk": "athlete-1", "version": "current", "sort": "weight"}))

    assert result["exercises"] == ["Squat"]
    assert result["videos"][0]["exercise_kg"] == 140
    assert result["videos"][0]["exercise_sets"] == 3
    assert result["videos"][0]["exercise_reps"] == 5


def test_metadata_thumbnail_and_remove_preserve_session_storage():
    store = FakeStore()
    s3 = FakeS3()

    metadata = _core("video_update_metadata")
    _patch_core(metadata, store)
    changed = asyncio.run(metadata.video_update_metadata({"pk": "athlete-1", "session_date": "2026-09-13", "video_id": "vid-1", "notes": "top set"}))
    assert changed["notes"] == "top set"
    assert changed["s3_key"].endswith("vid-1.mp4")

    thumbnail = _core("video_update_thumbnail")
    _patch_core(thumbnail, store)
    result = asyncio.run(thumbnail.video_update_thumbnail({"pk": "athlete-1", "session_date": "2026-09-13", "video_id": "vid-1", "thumbnail_s3_key": "thumbnails/new.jpg", "status": "ready"}))
    assert result["thumbnail_status"] == "ready"

    remove = _core("video_remove")
    _patch_core(remove, store, s3)
    assert asyncio.run(remove.video_remove({"pk": "athlete-1", "session_date": "2026-09-13", "video_id": "vid-1"})) == {"removed": "vid-1"}
    assert {item["Key"] for item in s3.deleted} == {"videos/2026-09-13/vid-1.mp4", "thumbnails/new.jpg"}
    assert store.patches[-1][2]["videos"] is None


def test_upload_writes_s3_metadata_and_attaches_video():
    core = _core("video_upload")
    store = FakeStore()
    s3 = FakeS3()
    _patch_core(core, store, s3)

    video = asyncio.run(core.video_upload({
        "pk": "athlete-1",
        "session_date": "2026-09-13",
        "file_b64": base64.b64encode(b"video-bytes").decode(),
        "filename": "attempt.MP4",
        "mimetype": "video/mp4",
        "exercise_name": "Squat",
        "set_number": 4,
    }))

    assert video["s3_key"].startswith("videos/2026-09-13/")
    assert video["s3_key"].endswith(".MP4")
    assert video["thumbnail_status"] == "pending"
    assert s3.uploads[0]["Body"] == b"video-bytes"
    assert store.patches[-1][2]["videos"][-1]["video_id"] == video["video_id"]


def test_presign_and_confirm_keep_file_bytes_out_of_domain_json():
    store = FakeStore()
    s3 = FakeS3()
    presign = _core("video_upload_presign")
    _patch_core(presign, store, s3)
    ticket = asyncio.run(presign.video_upload_presign({
        "pk": "athlete-1",
        "session_date": "2026-09-13",
        "filename": "attempt.mp4",
        "mimetype": "video/mp4",
    }))
    assert ticket["upload_url"].startswith("https://upload.test/")
    assert ticket["upload_headers"]["x-amz-meta-pk"] == "athlete-1"

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


def test_confirm_rejects_an_object_owned_by_another_athlete():
    store = FakeStore()
    s3 = FakeS3()
    confirm = _core("video_upload_confirm")
    _patch_core(confirm, store, s3)
    with pytest.raises(ValueError, match="authenticated athlete"):
        asyncio.run(confirm.video_upload_confirm({
            "pk": "athlete-2",
            "session_date": "2026-09-13",
            "video_id": "vid-1",
            "s3_key": "videos/2026-09-13/vid-1.mp4",
        }))


def test_pod_handler_returns_json_and_rejects_unknown_function():
    handler = importlib.import_module("lambda.pod_videos.handler")
    unknown = handler.handler({"function": "missing"}, None)
    assert unknown["statusCode"] == 404
    assert json.loads(unknown["body"])["error"] == "unknown function: missing"
