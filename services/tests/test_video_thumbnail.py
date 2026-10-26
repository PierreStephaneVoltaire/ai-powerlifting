import importlib.util
import json
import sys
import threading
from types import SimpleNamespace
from pathlib import Path

from botocore.exceptions import ClientError

from services.lib import media_notifications


MODULE_PATH = Path(__file__).parents[2] / "lambda" / "video-thumbnail" / "index.py"


def load_worker():
    sys.modules["notifications"] = media_notifications
    spec = importlib.util.spec_from_file_location("video_thumbnail_worker", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTable:
    def __init__(self, items=None):
        self.items = items or {}
        self.updates = []
        self.put_calls = []

    def get_item(self, **kwargs):
        return {"Item": self.items.get((kwargs["Key"]["pk"], kwargs["Key"]["sk"]))}

    def put_item(self, **kwargs):
        self.put_calls.append(dict(kwargs))
        item = kwargs["Item"]
        key = (item["pk"], item["sk"])
        current = self.items.get(key)
        values = kwargs.get("ExpressionAttributeValues", {})
        condition = kwargs.get("ConditionExpression", "")
        if "attribute_not_exists(pk)" in condition and current is not None:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        if "allocation_revision = :revision" in condition and (
            current is None or current.get("allocation_revision") != values[":revision"]
        ):
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        if "status = :status" in condition and kwargs.get("ExpressionAttributeNames", {}).get("#status") != "status":
            raise AssertionError("reserved status must use ExpressionAttributeNames")
        if "#status = :status" in condition and (
            current is None or current.get("status") != values[":status"]
        ):
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[key] = dict(item)

    def query(self, **kwargs):
        return {"Items": list(self.items.values())}

    def update_item(self, **kwargs):
        key = (kwargs["Key"]["pk"], kwargs["Key"]["sk"])
        current = self.items[key]
        values = kwargs["ExpressionAttributeValues"]
        if ":profiles" in values:
            current["lift_profiles"] = values[":profiles"]
            self.updates.append(dict(current))
            return
        expected = values.get(":revision")
        if expected is not None and current.get("media_revision", 0) != expected:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
        current["videos"] = values[":videos"]
        current["media_revision"] = values[":next"]
        self.updates.append(dict(current))


class FakeDynamo:
    def __init__(self, health, sessions):
        self.tables = {"if-health": health, "if-sessions": sessions}

    def Table(self, name):
        return self.tables[name]


class FakeS3:
    def __init__(self, source_key, metadata):
        self.source_key = source_key
        self.metadata = metadata
        self.writes = []

    def head_object(self, **kwargs):
        if kwargs["Key"] != self.source_key:
            return {"ContentLength": 10, "Metadata": {}}
        return {"ContentLength": 10, "Metadata": self.metadata}

    def download_file(self, _bucket, _key, path):
        Path(path).write_bytes(b"source")

    def put_object(self, **kwargs):
        self.writes.append(kwargs)


def test_stale_worker_does_not_publish_after_allocation_revision_changes(monkeypatch):
    worker = load_worker()
    source_key = "videos/2026-09-13/video-1.mp4"
    media = {
        "pk": "athlete-1",
        "sk": "Media#video-1",
        "media_id": "video-1",
        "video_id": "video-1",
        "session_id": "session-1",
        "session_date": "2026-09-13",
        "program_sk": "program#v003",
        "source_s3_key": source_key,
        "allocation_revision": 1,
        "status": "allocated",
    }
    health = FakeTable({("athlete-1", "Media#video-1"): media})
    sessions = FakeTable({("athlete-1", "session#program#v003#2026-09-13#session-1"): {
        "pk": "athlete-1",
        "sk": "session#program#v003#2026-09-13#session-1",
        "session_id": "session-1",
        "videos": [{"video_id": "video-1", "allocation_revision": 1, "thumbnail_status": "pending"}],
        "media_revision": 0,
    }})
    metadata = {
        "pk": "athlete-1", "sk": "program#v003", "video_id": "video-1", "media_id": "video-1",
        "session_id": "session-1", "session_date": "2026-09-13", "allocation_revision": "1",
    }
    s3 = FakeS3(source_key, metadata)
    worker.dynamodb = FakeDynamo(health, sessions)
    worker.s3 = s3

    original_put = health.put_item

    def replace_after_processing(**kwargs):
        original_put(**kwargs)
        if kwargs["Item"].get("status") == "processing":
            health.items[("athlete-1", "Media#video-1")] = {
                **kwargs["Item"], "allocation_revision": 2, "status": "allocated",
            }

    health.put_item = replace_after_processing
    monkeypatch.setattr(worker.subprocess, "run", lambda args, **kwargs: Path(args[args.index("-y") + 1]).write_bytes(b"output"))

    completed = worker._process_record("videos", source_key)

    assert completed["allocation_revision"] == 2
    assert not sessions.updates


def test_stale_worker_cannot_replace_newer_processed_objects(monkeypatch):
    worker = load_worker()
    source_key = "videos/2026-09-13/video-race.mp4"
    media_key = ("athlete-1", "Media#video-race")
    media = {
        "pk": "athlete-1", "sk": "Media#video-race", "media_id": "video-race", "video_id": "video-race",
        "session_id": "session-1", "session_date": "2026-09-13", "program_sk": "program#v003",
        "source_s3_key": source_key, "allocation_revision": 1, "status": "allocated",
    }
    health = FakeTable({media_key: media})
    sessions = FakeTable({("athlete-1", "session#program#v003#2026-09-13#session-1"): {
        "pk": "athlete-1", "sk": "session#program#v003#2026-09-13#session-1", "session_id": "session-1",
        "videos": [{"video_id": "video-race", "allocation_revision": 1, "thumbnail_status": "pending"}],
        "media_revision": 0,
    }})
    metadata = {
        "pk": "athlete-1", "sk": "program#v003", "video_id": "video-race", "media_id": "video-race",
        "session_id": "session-1", "session_date": "2026-09-13", "allocation_revision": "1",
    }
    s3 = FakeS3(source_key, metadata)
    worker.dynamodb = FakeDynamo(health, sessions)
    worker.s3 = s3
    transcode_started = threading.Event()
    resume = threading.Event()
    calls = 0

    def run_ffmpeg(args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            transcode_started.set()
            assert resume.wait(2)
        Path(args[args.index("-y") + 1]).write_bytes(f"output-{calls}".encode())

    monkeypatch.setattr(worker.subprocess, "run", run_ffmpeg)
    result = []
    error = []
    thread = threading.Thread(target=lambda: _run_worker(worker, source_key, result, error))
    thread.start()
    assert transcode_started.wait(2)
    newer_video_key = "processed/2026-09-13/video-race/r2.mp4"
    newer_thumbnail_key = "thumbnails/2026-09-13/video-race/r2.jpg"
    health.items[media_key] = {
        **media,
        "allocation_revision": 2,
        "status": "ready",
        "processed_s3_key": newer_video_key,
        "thumbnail_s3_key": newer_thumbnail_key,
    }
    resume.set()
    thread.join(2)

    assert not error
    assert result[0]["processed_s3_key"] == newer_video_key
    assert health.items[media_key]["processed_s3_key"] == newer_video_key
    assert health.items[media_key]["thumbnail_s3_key"] == newer_thumbnail_key
    assert not sessions.updates
    assert {write["Key"] for write in s3.writes} == {
        "processed/2026-09-13/video-race/r1.mp4",
        "thumbnails/2026-09-13/video-race/r1.jpg",
    }


def _run_worker(worker, source_key, result, error):
    try:
        result.append(worker._process_record("videos", source_key))
    except Exception as exc:
        error.append(exc)


def test_worker_metadata_requires_exact_allocation_revision():
    worker = load_worker()
    source_key = "videos/2026-09-13/video-2.mp4"
    health = FakeTable({("athlete-1", "Media#video-2"): {
        "pk": "athlete-1", "sk": "Media#video-2", "video_id": "video-2", "media_id": "video-2",
        "session_id": "session-1", "session_date": "2026-09-13", "program_sk": "program#v003",
        "source_s3_key": source_key, "allocation_revision": 2, "expected_size": 10, "status": "allocated",
    }})
    worker.dynamodb = FakeDynamo(health, FakeTable())
    worker.s3 = FakeS3(source_key, {
        "pk": "athlete-1", "sk": "program#v003", "video_id": "video-2", "media_id": "video-2",
        "session_id": "session-1", "session_date": "2026-09-13", "allocation_revision": "1", "expected_size": "10",
    })

    try:
        worker._process_record("videos", source_key)
    except ValueError as error:
        assert str(error) == "Stale media allocation"
    else:
        raise AssertionError("stale allocation was accepted")


def test_form_duration_uses_ffmpeg_when_layer_has_no_ffprobe(monkeypatch):
    worker = load_worker()
    monkeypatch.setattr(worker.os.path, "exists", lambda path: False)
    monkeypatch.setattr(worker.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stderr="Duration: 00:01:02.50"))

    assert worker._form_duration_seconds("ffmpeg", "/tmp/form.webm") == 62.5


def test_worker_rejects_expected_size_metadata_mismatch():
    worker = load_worker()
    source_key = "videos/2026-09-13/video-3.mp4"
    health = FakeTable({("athlete-1", "Media#video-3"): {
        "pk": "athlete-1", "sk": "Media#video-3", "video_id": "video-3", "media_id": "video-3",
        "session_id": "session-1", "session_date": "2026-09-13", "program_sk": "program#v003",
        "source_s3_key": source_key, "allocation_revision": 1, "expected_size": 10, "status": "allocated",
    }})
    worker.dynamodb = FakeDynamo(health, FakeTable())
    worker.s3 = FakeS3(source_key, {
        "pk": "athlete-1", "sk": "program#v003", "video_id": "video-3", "media_id": "video-3",
        "session_id": "session-1", "session_date": "2026-09-13", "allocation_revision": "1", "expected_size": "11",
    })

    try:
        worker._process_record("videos", source_key)
    except ValueError as error:
        assert str(error) == "Uploaded video metadata does not match allocation"
    else:
        raise AssertionError("mismatched expected size was accepted")


def test_form_video_completion_replaces_only_matching_pending_slot():
    worker = load_worker()
    source_key = "videos/2026-09-13/form-1.mp4"
    media_key = ("athlete-1", "Media#form-1")
    health = FakeTable({
        ("athlete-1", "program#current"): {"pk": "athlete-1", "sk": "program#current", "ref_sk": "program#v003"},
        ("athlete-1", "program#v003"): {
            "pk": "athlete-1", "sk": "program#v003", "meta": {"revision": 4},
            "lift_profiles": [{"lift": "squat", "form_videos": {"front": {
                "video_id": "old", "s3_key": "processed/old.mp4", "thumbnail_status": "ready",
                "pending_media_id": "form-1", "target_revision": 4,
            }}}],
        },
        media_key: {
            "pk": "athlete-1", "sk": "Media#form-1", "media_id": "form-1", "video_id": "form-1",
            "session_id": "lift-profile:squat:front", "session_date": "2026-09-13", "program_sk": "program#v003",
            "source_s3_key": source_key, "allocation_revision": 1, "status": "allocated",
            "lift": "squat", "angle": "front", "target_revision": 4,
        },
    })
    sessions = FakeTable()
    worker.dynamodb = FakeDynamo(health, sessions)
    worker.s3 = FakeS3(source_key, {
        "pk": "athlete-1", "sk": "program#v003", "video_id": "form-1", "media_id": "form-1",
        "session_id": "lift-profile:squat:front", "session_date": "2026-09-13", "allocation_revision": "1",
        "lift": "squat", "angle": "front", "target_revision": "4",
    })

    def run_process(args, **kwargs):
        if "-y" in args:
            Path(args[args.index("-y") + 1]).write_bytes(b"output")
        return SimpleNamespace(stdout="10", stderr="Duration: 00:00:10.00")

    worker.subprocess.run = run_process
    worker._process_record("videos", source_key)

    profile = health.items[("athlete-1", "program#v003")]["lift_profiles"][0]
    slot = profile["form_videos"]["front"]
    assert slot["video_id"] == "form-1"
    assert "pending_media_id" not in slot
    assert slot["processing_status"] == "ready"


def test_processing_failure_marks_confirmed_pending_media_failed_and_preserves_ready_media():
    worker = load_worker()
    source_key = "videos/2026-09-13/video-4.mp4"
    media = {
        "pk": "athlete-1", "sk": "Media#video-4", "video_id": "video-4", "media_id": "video-4",
        "session_id": "session-1", "session_date": "2026-09-13", "program_sk": "program#v003",
        "source_s3_key": source_key, "allocation_revision": 1, "status": "confirmed",
    }
    health = FakeTable({("athlete-1", "Media#video-4"): media})
    sessions = FakeTable({("athlete-1", "session#program#v003#2026-09-13#session-1"): {
        "pk": "athlete-1", "sk": "session#program#v003#2026-09-13#session-1", "session_id": "session-1",
        "videos": [{"video_id": "video-4", "allocation_revision": 1, "thumbnail_status": "pending"}],
        "media_revision": 0,
    }})
    worker.dynamodb = FakeDynamo(health, sessions)
    worker.s3 = FakeS3(source_key, {
        "pk": "athlete-1", "sk": "program#v003", "video_id": "video-4", "media_id": "video-4",
        "session_id": "session-1", "session_date": "2026-09-13", "allocation_revision": "1",
    })

    def fail(*_args, **_kwargs):
        raise RuntimeError("ffmpeg failed")

    worker.subprocess.run = fail
    try:
        worker.handler({"Records": [{"s3": {"bucket": {"name": "videos"}, "object": {"key": source_key}}}]}, None)
    except RuntimeError as error:
        assert str(error) == "ffmpeg failed"
    else:
        raise AssertionError("processing failure was swallowed")

    assert health.items[("athlete-1", "Media#video-4")]["status"] == "failed"
    assert sessions.items[("athlete-1", "session#program#v003#2026-09-13#session-1")]["videos"][0]["thumbnail_status"] == "failed"
    status_writes = [call for call in health.put_calls if "#status = :status" in call.get("ConditionExpression", "")]
    assert status_writes
    assert status_writes[-1]["ExpressionAttributeNames"] == {"#status": "status"}


def test_ready_notification_requires_confirmation_and_uses_the_existing_marker_wire():
    worker = load_worker()
    helper = worker._notifications_module()
    media = {
        "pk": "athlete-1",
        "video_id": "video-5",
        "allocation_revision": 2,
        "status": "confirmed",
        "session_date": "2026-09-13",
        "uploader_person_pk": "person-1",
        "processed_s3_key": "processed/video-5/r2.mp4",
        "thumbnail_s3_key": "thumbnails/video-5/r2.jpg",
    }
    notification = helper.media_ready_notification(media)
    assert notification is not None
    person, event_id, kind, payload = notification
    assert person == "person-1"
    assert event_id == "video:athlete-1:video-5:ready:2"
    assert kind == "video_ready"
    writes = helper.notification_transaction_items(person, event_id, kind, payload, "2026-09-14T00:00:00+00:00")
    assert writes[0]["Put"]["Item"]["pk"] == "Event#video:athlete-1:video-5:ready:2"
    assert writes[1]["Put"]["Item"]["pk"] == "Person#person-1"
    assert writes[1]["Put"]["Item"]["read_at"] is None
    assert helper.media_ready_notification({**media, "status": "ready"}) is None
    assert helper.media_ready_notification({**media, "thumbnail_s3_key": ""}) is None
