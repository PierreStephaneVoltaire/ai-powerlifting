from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from services.lib.aws import dynamodb_resource, client as aws_client
from boto3.dynamodb.conditions import Key


CONTEXT_DOMAINS = ("program", "sessions", "competition")
NOTE_PREFIX = "Note#"
SHARED_PREFIX = "SharedNote#"


class NoteError(Exception):
    status = 422
    code = "validation"


class NoteForbidden(NoteError):
    status = 403
    code = "forbidden"


class NoteNotFound(NoteError):
    status = 404
    code = "not_found"


class NoteConflict(NoteError):
    status = 409
    code = "conflict"

    def __init__(self, message: str, current_revision: int, current_record: dict | None):
        super().__init__(message)
        self.current_revision = current_revision
        self.current_record = current_record


class NoteIdempotencyConflict(NoteError):
    status = 409
    code = "conflict"


def _floats_to_decimals(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _floats_to_decimals(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_floats_to_decimals(item) for item in value]
    return value


def _decimals_to_numbers(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    if isinstance(value, dict):
        return {key: _decimals_to_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimals_to_numbers(item) for item in value]
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _public_note(item: dict) -> dict:
    return {
        "note_id": item["note_id"],
        "text": item.get("text", ""),
        "revision": int(item.get("revision", 0)),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
    }


def _public_attachment(item: dict, snapshot: dict | None = None) -> dict:
    source = snapshot or item
    return {
        "attachment_id": item["attachment_id"],
        "note_id": item["note_id"],
        "text": source.get("text", ""),
        "revision": int(item.get("attachment_revision", 0)),
        "source_revision": int(source.get("source_revision", item.get("source_revision", 0))),
        "author_person_pk": source.get("author_person_pk", item.get("author_person_pk", "")),
        "context_domain": item.get("context_domain", ""),
        "context_id": item.get("context_id"),
        "attached_at": item.get("attached_at", ""),
    }


class AuthoredNotesStore:
    def __init__(self, table=None, table_name: str | None = None, region: str | None = None):
        self.table = table or dynamodb_resource(
            "dynamodb", region_name=region or os.getenv("AWS_REGION", "ca-central-1")
        ).Table(table_name or os.getenv("IF_HEALTH_TABLE_NAME", "if-health"))

    def _get(self, pk: str, sk: str) -> dict | None:
        return self.table.get_item(Key={"pk": pk, "sk": sk}, ConsistentRead=True).get("Item")

    def _private_note(self, person_pk: str, note_id: str) -> dict:
        item = self._get(person_pk, f"{NOTE_PREFIX}{note_id}")
        if not item:
            raise NoteNotFound("Note not found")
        return item

    def _ledger(self, pk: str, key: str, prefix: str) -> dict | None:
        return self._get(pk, f"{prefix}{key}")

    def _transaction(self, items: list[dict]) -> None:
        self.table.meta.client.transact_write_items(TransactItems=_floats_to_decimals(items))

    def _replay(self, ledger: dict | None, payload_hash: str, actor: str) -> dict | None:
        if not ledger:
            return None
        if ledger.get("payload_hash") != payload_hash or ledger.get("actor") != actor:
            raise NoteIdempotencyConflict("Idempotency key was already used for another mutation")
        return _decimals_to_numbers(ledger.get("result") or {})

    def list_private(self, person_pk: str, args: dict | None = None) -> dict:
        request = {
            "KeyConditionExpression": Key("pk").eq(person_pk) & Key("sk").begins_with(NOTE_PREFIX),
            "ConsistentRead": True,
            "Limit": 100,
        }
        notes = []
        while True:
            response = self.table.query(**request)
            notes.extend(_public_note(_decimals_to_numbers(item)) for item in response.get("Items", []))
            if not response.get("LastEvaluatedKey"):
                break
            request["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return {"notes": sorted(notes, key=lambda note: note["updated_at"], reverse=True)}

    def save_private(self, person_pk: str, args: dict) -> dict:
        text = args.get("text")
        expected = args.get("expected_revision")
        idempotency_key = args.get("idempotency_key")
        if not isinstance(text, str) or not text.strip():
            raise NoteError("text is required")
        if not isinstance(expected, int) or expected < 0:
            raise NoteError("expected_revision must be a nonnegative integer")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise NoteError("idempotency_key is required")
        payload = {"note_id": args.get("note_id"), "text": text, "expected_revision": expected}
        payload_hash = _payload_hash(payload)
        note_id = args.get("note_id") or str(uuid.uuid5(uuid.NAMESPACE_URL, f"authored-note:{person_pk}:{idempotency_key}"))
        if not isinstance(note_id, str) or not note_id.strip():
            raise NoteError("note_id must be a nonempty string")
        ledger = self._ledger(person_pk, idempotency_key, "NoteMutation#")
        replay = self._replay(ledger, payload_hash, person_pk)
        if replay is not None:
            return replay
        key = {"pk": person_pk, "sk": f"{NOTE_PREFIX}{note_id}"}
        current = self._get(person_pk, key["sk"])
        now = _now()
        if current is None:
            if expected != 0:
                raise NoteConflict("Note revision differs", 0, None)
            item = {
                **key,
                "note_id": note_id,
                "author_person_pk": person_pk,
                "text": text,
                "revision": 1,
                "revisions": [{"revision": 1, "text": text, "updated_at": now}],
                "created_at": now,
                "updated_at": now,
            }
            try:
                result = _public_note(item)
                self._transaction([
                    {"Put": {"TableName": self.table.name, "Item": item, "ConditionExpression": "attribute_not_exists(pk)"}},
                    {"Put": {"TableName": self.table.name, "Item": {"pk": person_pk, "sk": f"NoteMutation#{idempotency_key}", "result": result, "payload_hash": payload_hash, "actor": person_pk, "created_at": now}, "ConditionExpression": "attribute_not_exists(pk)"}},
                ])
            except Exception as exc:
                replay = self._replay(self._ledger(person_pk, idempotency_key, "NoteMutation#"), payload_hash, person_pk)
                if replay is not None:
                    return replay
                current = _decimals_to_numbers(self._get(person_pk, key["sk"]) or {})
                if current:
                    raise NoteConflict("Note revision differs", int(current.get("revision", 0)), _public_note(current)) from exc
                raise
        else:
            current = _decimals_to_numbers(current)
            current_revision = int(current.get("revision", 0))
            if expected != current_revision:
                raise NoteConflict("Note revision differs", current_revision, _public_note(current))
            revision = current_revision + 1
            revisions = list(current.get("revisions") or [])
            revisions.append({"revision": revision, "text": text, "updated_at": now})
            result = _public_note({"note_id": note_id, "text": text, "revision": revision, "created_at": current.get("created_at", now), "updated_at": now})
            try:
                self._transaction([
                    {"Update": {"TableName": self.table.name, "Key": key, "UpdateExpression": "SET #text = :text, #revision = :revision, #revisions = :revisions, #updated_at = :updated_at", "ConditionExpression": "#revision = :expected_revision", "ExpressionAttributeNames": {"#text": "text", "#revision": "revision", "#revisions": "revisions", "#updated_at": "updated_at"}, "ExpressionAttributeValues": {":text": text, ":revision": revision, ":revisions": revisions, ":updated_at": now, ":expected_revision": expected}}},
                    {"Put": {"TableName": self.table.name, "Item": {"pk": person_pk, "sk": f"NoteMutation#{idempotency_key}", "result": result, "payload_hash": payload_hash, "actor": person_pk, "created_at": now}, "ConditionExpression": "attribute_not_exists(pk)"}},
                ])
            except Exception as exc:
                replay = self._replay(self._ledger(person_pk, idempotency_key, "NoteMutation#"), payload_hash, person_pk)
                if replay is not None:
                    return replay
                latest = _decimals_to_numbers(self._get(person_pk, key["sk"]) or {})
                raise NoteConflict("Note revision differs", int(latest.get("revision", 0)), _public_note(latest) if latest else None) from exc
        return result

    def _check_context(self, access: dict, domain: str, action: str) -> None:
        if domain not in CONTEXT_DOMAINS:
            raise NoteError("context_domain is invalid")
        if f"{domain}:{action}" not in set(access.get("permissions", [])):
            raise NoteForbidden(f"{domain}:{action} permission required")

    def list_attachments(self, athlete_pk: str, args: dict, access: dict) -> dict:
        domain = args.get("context_domain")
        self._check_context(access, domain, "read")
        request = {"KeyConditionExpression": Key("pk").eq(athlete_pk) & Key("sk").begins_with(SHARED_PREFIX), "ConsistentRead": True, "Limit": 100}
        attachments = []
        while True:
            response = self.table.query(**request)
            for raw in response.get("Items", []):
                item = _decimals_to_numbers(raw)
                if "#r" in item.get("sk", "") or item.get("detached") or item.get("context_domain") != domain:
                    continue
                if args.get("context_id") is not None and item.get("context_id") != args.get("context_id"):
                    continue
                snapshot = self._get(athlete_pk, f"{SHARED_PREFIX}{item['attachment_id']}#r{item['attachment_revision']}")
                if snapshot:
                    attachments.append(_public_attachment(item, _decimals_to_numbers(snapshot)))
            if not response.get("LastEvaluatedKey"):
                break
            request["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return {"attachments": attachments, "next_cursor": None}

    def share(self, athlete_pk: str, person_pk: str, args: dict, access: dict) -> dict:
        note_id = args.get("note_id")
        domain = args.get("context_domain")
        wanted = args.get("wanted_revision")
        expected = args.get("expected_attachment_revision")
        idempotency_key = args.get("idempotency_key")
        if not isinstance(note_id, str) or not note_id.strip():
            raise NoteError("note_id is required")
        if not isinstance(wanted, int) or wanted < 1:
            raise NoteError("wanted_revision must be a positive integer")
        if not isinstance(expected, int) or expected < 0:
            raise NoteError("expected_attachment_revision must be a nonnegative integer")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise NoteError("idempotency_key is required")
        if any(key in args for key in ("text", "author_person_pk", "author")):
            raise NoteError("Share payload cannot include note text or author")
        self._check_context(access, domain, "write")
        note = _decimals_to_numbers(self._private_note(person_pk, note_id))
        if note.get("author_person_pk") != person_pk:
            raise NoteForbidden("Only the author may share a note")
        revision = next((entry for entry in note.get("revisions", []) if int(entry.get("revision", 0)) == wanted), None)
        if revision is None:
            raise NoteConflict("Requested note revision is unavailable", int(note.get("revision", 0)), _public_note(note))
        payload = {"note_id": note_id, "wanted_revision": wanted, "context_domain": domain, "context_id": args.get("context_id"), "expected_attachment_revision": expected}
        payload_hash = _payload_hash(payload)
        ledger = self._ledger(athlete_pk, idempotency_key, "SharedNoteMutation#")
        replay = self._replay(ledger, payload_hash, person_pk)
        if replay is not None:
            return replay
        attachment_id = "shared-" + hashlib.sha256(f"{person_pk}\0{note_id}\0{domain}\0{args.get('context_id') or ''}".encode()).hexdigest()[:32]
        pointer_key = {"pk": athlete_pk, "sk": f"{SHARED_PREFIX}{attachment_id}"}
        pointer = _decimals_to_numbers(self._get(athlete_pk, pointer_key["sk"]) or {})
        current_revision = int(pointer.get("attachment_revision", 0))
        if expected != current_revision:
            raise NoteConflict("Attachment revision differs", current_revision, _public_attachment(pointer) if pointer else None)
        attachment_revision = current_revision + 1
        now = _now()
        snapshot = {
            "pk": athlete_pk,
            "sk": f"{SHARED_PREFIX}{attachment_id}#r{attachment_revision}",
            "attachment_id": attachment_id,
            "note_id": note_id,
            "attachment_revision": attachment_revision,
            "source_revision": wanted,
            "text": revision.get("text", ""),
            "author_person_pk": person_pk,
            "context_domain": domain,
            "context_id": args.get("context_id"),
            "attached_at": now,
        }
        next_pointer = {
            **pointer_key,
            "attachment_id": attachment_id,
            "note_id": note_id,
            "attachment_revision": attachment_revision,
            "source_revision": wanted,
            "author_person_pk": person_pk,
            "context_domain": domain,
            "context_id": args.get("context_id"),
            "attached_at": now,
            "detached": False,
        }
        try:
            transaction = [{"Put": {"TableName": self.table.name, "Item": snapshot, "ConditionExpression": "attribute_not_exists(pk)"}}]
            if pointer:
                transaction.append({"Update": {"TableName": self.table.name, "Key": pointer_key, "UpdateExpression": "SET #revision = :revision, #source = :source, #author = :author, #note = :note, #domain = :domain, #context_id = :context_id, #attached_at = :attached_at, #detached = :detached", "ConditionExpression": "#revision = :expected AND #author = :author AND #note = :note", "ExpressionAttributeNames": {"#revision": "attachment_revision", "#source": "source_revision", "#author": "author_person_pk", "#note": "note_id", "#domain": "context_domain", "#context_id": "context_id", "#attached_at": "attached_at", "#detached": "detached"}, "ExpressionAttributeValues": {":revision": attachment_revision, ":source": wanted, ":author": person_pk, ":note": note_id, ":domain": domain, ":context_id": args.get("context_id"), ":attached_at": now, ":detached": False, ":expected": expected}}})
            else:
                transaction.append({"Put": {"TableName": self.table.name, "Item": next_pointer, "ConditionExpression": "attribute_not_exists(pk)"}})
            transaction.append({"Put": {"TableName": self.table.name, "Item": {"pk": athlete_pk, "sk": f"SharedNoteMutation#{idempotency_key}", "result": _public_attachment(next_pointer, snapshot), "payload_hash": payload_hash, "actor": person_pk, "created_at": now}, "ConditionExpression": "attribute_not_exists(pk)"}})
            self._transaction(transaction)
        except Exception as exc:
            replay = self._replay(self._ledger(athlete_pk, idempotency_key, "SharedNoteMutation#"), payload_hash, person_pk)
            if replay is not None:
                return replay
            latest = _decimals_to_numbers(self._get(athlete_pk, pointer_key["sk"]) or {})
            raise NoteConflict("Attachment revision differs", int(latest.get("attachment_revision", 0)), _public_attachment(latest) if latest else None) from exc
        result = _public_attachment(next_pointer, snapshot)
        return result

    def detach(self, athlete_pk: str, args: dict, access: dict) -> dict:
        if not access.get("is_self") or access.get("own_athlete_pk") != athlete_pk:
            raise NoteForbidden("Only the Athlete may detach an attachment")
        attachment_id = args.get("attachment_id") or args.get("note_id")
        expected = args.get("expected_attachment_revision")
        idempotency_key = args.get("idempotency_key")
        if not isinstance(attachment_id, str) or not attachment_id.strip():
            raise NoteError("attachment_id is required")
        if not isinstance(expected, int) or expected < 1:
            raise NoteError("expected_attachment_revision must be a positive integer")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise NoteError("idempotency_key is required")
        payload = {"attachment_id": attachment_id, "expected_attachment_revision": expected}
        payload_hash = _payload_hash(payload)
        ledger = self._ledger(athlete_pk, idempotency_key, "SharedNoteMutation#")
        replay = self._replay(ledger, payload_hash, str(access.get("person_pk") or athlete_pk))
        if replay is not None:
            return replay
        key = {"pk": athlete_pk, "sk": f"{SHARED_PREFIX}{attachment_id}"}
        pointer = _decimals_to_numbers(self._get(athlete_pk, key["sk"]) or {})
        if not pointer:
            raise NoteNotFound("Attachment not found")
        if int(pointer.get("attachment_revision", 0)) != expected:
            raise NoteConflict("Attachment revision differs", int(pointer.get("attachment_revision", 0)), _public_attachment(pointer))
        revision = expected + 1
        try:
            self._transaction([
                {"Update": {"TableName": self.table.name, "Key": key, "UpdateExpression": "SET #detached = :detached, #revision = :revision", "ConditionExpression": "#revision = :expected AND #detached = :attached", "ExpressionAttributeNames": {"#detached": "detached", "#revision": "attachment_revision"}, "ExpressionAttributeValues": {":detached": True, ":revision": revision, ":expected": expected, ":attached": False}}},
                {"Put": {"TableName": self.table.name, "Item": {"pk": athlete_pk, "sk": f"SharedNoteMutation#{idempotency_key}", "result": {"attachment_id": attachment_id, "detached": True, "revision": revision}, "payload_hash": payload_hash, "actor": str(access.get("person_pk") or athlete_pk), "created_at": _now()}, "ConditionExpression": "attribute_not_exists(pk)"}},
            ])
        except Exception as exc:
            replay = self._replay(self._ledger(athlete_pk, idempotency_key, "SharedNoteMutation#"), payload_hash, str(access.get("person_pk") or athlete_pk))
            if replay is not None:
                return replay
            latest = _decimals_to_numbers(self._get(athlete_pk, key["sk"]) or {})
            raise NoteConflict("Attachment revision differs", int(latest.get("attachment_revision", 0)), _public_attachment(latest) if latest else None) from exc
        result = {"attachment_id": attachment_id, "detached": True, "revision": revision}
        return result
