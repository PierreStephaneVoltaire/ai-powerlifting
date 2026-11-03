
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from services.lib.aws import dynamodb_resource, client as aws_client
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class TemplateNotFoundError(Exception):
    """Raised when a template is not found or not visible to the actor."""

class TemplatePermissionError(Exception):
    """Raised when an actor cannot mutate a template."""


class TemplateRevisionConflictError(Exception):
    def __init__(self, expected_revision: int, current_revision: int, current_record: dict | None = None):
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        self.current_record = current_record
        super().__init__(f"revision conflict: expected {expected_revision}, current {current_revision}")


def require_mutation_envelope(expected_revision: Any = None, idempotency_key: Any = None) -> tuple[int, str]:
    return 0, idempotency_key if isinstance(idempotency_key, str) else ""

class TemplateStore:
    """DynamoDB-backed store for global training templates."""

    INDEX_SK = "template#index"
    LEGACY_INDEX_SK = "template#current_list"
    TEMPLATE_SK_PREFIX = "template#"
    IMPORT_JOB_SK_PREFIX = "template_import#"

    def __init__(self, table_name: str, pk: str = "template_library", region: str = "ca-central-1"):
        self._table_name = table_name
        self._pk = pk
        self._region = region
        self._table = None

    @property
    def pk(self) -> str:
        return self._pk

    @pk.setter
    def pk(self, value: str) -> None:
        self._pk = value

    @property
    def table(self):
        if self._table is None:
            self._table = dynamodb_resource(
                "dynamodb", region_name=self._region
            ).Table(self._table_name)
        return self._table

    def _floats_to_decimals(self, obj: Any) -> Any:
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: self._floats_to_decimals(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._floats_to_decimals(v) for v in obj]
        return obj

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _new_template_sk(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return f"{self.TEMPLATE_SK_PREFIX}{stamp}#{uuid.uuid4().hex[:8]}"

    def _is_published_meta(self, meta: dict[str, Any]) -> bool:
        if "published" not in meta:
            return True
        return bool(meta.get("published"))

    @staticmethod
    def _owner_ids(actor_pk: str | None) -> frozenset[str]:
        if not actor_pk:
            return frozenset()
        from services.lib.storage_scope import current_owner_aliases
        aliases = current_owner_aliases.get()
        return aliases if str(actor_pk) in aliases else frozenset({str(actor_pk)})

    def _owns(self, template_or_summary: dict[str, Any], actor_pk: str | None) -> bool:
        meta = template_or_summary.get("meta") if isinstance(template_or_summary.get("meta"), dict) else template_or_summary
        author_pk = str(meta.get("author_pk") or "")
        return bool(author_pk) and author_pk in self._owner_ids(actor_pk)

    def _visible(self, template_or_summary: dict[str, Any], actor_pk: str | None) -> bool:
        meta = template_or_summary.get("meta") if isinstance(template_or_summary.get("meta"), dict) else template_or_summary
        return self._is_published_meta(meta) or self._owns(template_or_summary, actor_pk)

    def _assert_owner(self, template: dict[str, Any], actor_pk: str | None) -> None:
        if not self._owns(template, actor_pk):
            raise TemplatePermissionError("Template mutation requires the original author")

    def _summary(self, template_item: dict[str, Any]) -> dict[str, Any]:
        meta = template_item.get("meta") if isinstance(template_item.get("meta"), dict) else {}
        return {
            "sk": template_item.get("sk"),
            "name": meta.get("name"),
            "source_filename": meta.get("source_filename"),
            "source_file_hash": meta.get("source_file_hash"),
            "estimated_weeks": meta.get("estimated_weeks"),
            "days_per_week": meta.get("days_per_week"),
            "archived": bool(meta.get("archived", False)),
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
            "author": meta.get("author"),
            "author_pk": meta.get("author_pk"),
            "published": self._is_published_meta(meta),
            "published_at": meta.get("published_at"),
            "import_job_id": meta.get("import_job_id"),
        }

    def _read_index_sync(self) -> list[dict[str, Any]]:
        resp = self.table.get_item(Key={"pk": self._pk, "sk": self.INDEX_SK})
        if "Item" not in resp:
            resp = self.table.get_item(Key={"pk": self._pk, "sk": self.LEGACY_INDEX_SK})
        if "Item" not in resp:
            return []
        return list(resp["Item"].get("templates", []))

    def _write_index_sync(self, templates: list[dict[str, Any]], updated_at: str | None = None) -> None:
        self.table.put_item(Item=self._floats_to_decimals({
            "pk": self._pk,
            "sk": self.INDEX_SK,
            "templates": templates,
            "updated_at": updated_at or self._now(),
        }))

    def _transaction_canceled(self, exc: Exception) -> bool:
        return isinstance(exc, ClientError) and exc.response.get("Error", {}).get("Code") == "TransactionCanceledException"

    def _read_index_item_sync(self) -> dict[str, Any]:
        current = self.table.get_item(Key={"pk": self._pk, "sk": self.INDEX_SK}, ConsistentRead=True).get("Item") or {}
        if not current:
            current = self.table.get_item(Key={"pk": self._pk, "sk": self.LEGACY_INDEX_SK}, ConsistentRead=True).get("Item") or {}
        return current

    def _write_template_index_sync(self, template: dict, *, expected_revision: int | None = None, marker: dict | None = None) -> None:
        self.table.put_item(Item=self._floats_to_decimals(template))
        self._upsert_index_summary_sync(self._summary(template))

    def _upsert_index_summary_sync(self, summary: dict[str, Any]) -> None:
        current = self._read_index_item_sync()
        templates = [t for t in (current.get("templates") or []) if t.get("sk") != summary.get("sk")]
        templates.append(summary)
        templates.sort(key=lambda t: str(t.get("created_at") or ""))
        self._write_index_sync(templates, str(summary.get("updated_at") or self._now()))

    def _conditional_put_sync(self, template: dict, expected_revision: int, current: dict) -> None:
        self.table.put_item(Item=self._floats_to_decimals({**template, "pk": self._pk, "sk": template["sk"]}))

    def list_templates_sync(self, include_archived: bool = False, actor_pk: str | None = None) -> list[dict[str, Any]]:
        templates = self._read_index_sync()
        visible = [{**t, "is_owner": self._owns(t, actor_pk)} for t in templates if self._visible(t, actor_pk)]
        if not include_archived:
            visible = [t for t in visible if not t.get("archived", False)]
        visible.sort(key=lambda t: str(t.get("updated_at") or ""), reverse=True)
        return visible

    async def list_templates(self, include_archived: bool = False, actor_pk: str | None = None) -> list[dict]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.list_templates_sync(include_archived, actor_pk)
        )

    def get_template_sync(self, sk: str, actor_pk: str | None = None, include_hidden: bool = False) -> dict | None:
        resp = self.table.get_item(Key={"pk": self._pk, "sk": sk})
        if "Item" not in resp:
            return None
        item = dict(resp["Item"])
        item["pk"] = item.get("pk", self._pk)
        item["sk"] = item.get("sk", sk)
        if not include_hidden and not self._visible(item, actor_pk):
            return None
        return item

    async def get_template(self, sk: str, actor_pk: str | None = None, include_hidden: bool = False) -> dict | None:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.get_template_sync(sk, actor_pk, include_hidden)
        )

    def put_template_sync(
        self,
        template: dict,
        *,
        actor_pk: str | None = None,
        author: str | None = None,
        published: bool = False,
        import_job_id: str | None = None,
        sk: str | None = None,
        expected_revision: int | None = None,
        idempotency_key: str | None = None,
        _idempotency_payload_hash: str | None = None,
    ) -> str:
        now = self._now()
        new_sk = sk or self._new_template_sk()
        template_item = copy.deepcopy(template)
        template_item.pop("is_owner", None)
        meta = template_item.setdefault("meta", {})

        meta.setdefault("created_at", now)
        meta["updated_at"] = now
        meta["archived"] = bool(meta.get("archived", False))
        meta["published"] = bool(meta.get("published", published))
        if meta["published"] and not meta.get("published_at"):
            meta["published_at"] = now
        if not meta["published"]:
            meta.pop("published_at", None)
        if actor_pk:
            meta["author_pk"] = str(actor_pk)
        meta.setdefault("author_pk", "operator" if meta["published"] else actor_pk)
        if author:
            meta["author"] = author
        meta.setdefault("author", meta.get("author_pk") or "operator")
        if import_job_id:
            meta["import_job_id"] = import_job_id
        meta.setdefault("revision", 0)

        template_item["pk"] = self._pk
        template_item["sk"] = new_sk
        self._write_template_index_sync(template_item)
        return new_sk

    async def put_template(
        self,
        template: dict,
        *,
        actor_pk: str | None = None,
        author: str | None = None,
        published: bool = False,
        import_job_id: str | None = None,
        sk: str | None = None,
        expected_revision: int | None = None,
        idempotency_key: str | None = None,
        _idempotency_payload_hash: str | None = None,
    ) -> str:
        return await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self.put_template_sync(
                template,
                actor_pk=actor_pk,
                author=author,
                published=published,
                import_job_id=import_job_id,
                sk=sk,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
                _idempotency_payload_hash=_idempotency_payload_hash,
            ),
        )

    def update_template_sync(self, sk: str, template: dict, *, actor_pk: str | None = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict:
        require_mutation_envelope(expected_revision, idempotency_key)
        existing = self.get_template_sync(sk, actor_pk=actor_pk)
        if not existing:
            raise TemplateNotFoundError(f"Template not found: {sk}")
        self._assert_owner(existing, actor_pk)

        now = self._now()
        template_item = copy.deepcopy(template)
        template_item.pop("is_owner", None)
        incoming_meta = template_item.setdefault("meta", {})
        existing_meta = existing.get("meta") if isinstance(existing.get("meta"), dict) else {}

        incoming_meta["created_at"] = existing_meta.get("created_at", now)
        incoming_meta["updated_at"] = now
        incoming_meta["author_pk"] = existing_meta.get("author_pk")
        incoming_meta["author"] = existing_meta.get("author")
        incoming_meta["published"] = bool(existing_meta.get("published", True))
        incoming_meta.pop("idempotency", None)
        if existing_meta.get("published_at"):
            incoming_meta["published_at"] = existing_meta.get("published_at")
        else:
            incoming_meta.pop("published_at", None)
        if existing_meta.get("import_job_id"):
            incoming_meta["import_job_id"] = existing_meta.get("import_job_id")

        template_item["pk"] = self._pk
        template_item["sk"] = sk
        self._write_template_index_sync(template_item, expected_revision=expected_revision)
        return {"status": "updated", "sk": sk}

    async def update_template(self, sk: str, template: dict, *, actor_pk: str | None = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.update_template_sync(sk, template, actor_pk=actor_pk, expected_revision=expected_revision, idempotency_key=idempotency_key)
        )

    def _set_archived_sync(self, sk: str, archived: bool, actor_pk: str | None, expected_revision: int | None, idempotency_key: str | None) -> dict:
        require_mutation_envelope(expected_revision, idempotency_key)
        template = self.get_template_sync(sk, actor_pk=actor_pk)
        if not template:
            raise TemplateNotFoundError(f"Template not found: {sk}")
        self._assert_owner(template, actor_pk)
        meta = template.setdefault("meta", {})
        result = {"status": "archived" if archived else "unarchived", "sk": sk}
        meta["archived"] = archived
        meta.pop("idempotency", None)
        meta["updated_at"] = self._now()
        self._write_template_index_sync({**template, "pk": self._pk, "sk": sk}, expected_revision=expected_revision)
        return result

    def archive_template_sync(self, sk: str, actor_pk: str | None = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict:
        return self._set_archived_sync(sk, True, actor_pk, expected_revision, idempotency_key)

    async def archive_template(self, sk: str, actor_pk: str | None = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.archive_template_sync(sk, actor_pk, expected_revision, idempotency_key)
        )

    def unarchive_template_sync(self, sk: str, actor_pk: str | None = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict:
        return self._set_archived_sync(sk, False, actor_pk, expected_revision, idempotency_key)

    async def unarchive_template(self, sk: str, actor_pk: str | None = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.unarchive_template_sync(sk, actor_pk, expected_revision, idempotency_key)
        )

    def set_published_sync(self, sk: str, published: bool, actor_pk: str | None = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict:
        require_mutation_envelope(expected_revision, idempotency_key)
        template = self.get_template_sync(sk, actor_pk=actor_pk)
        if not template:
            raise TemplateNotFoundError(f"Template not found: {sk}")
        self._assert_owner(template, actor_pk)
        now = self._now()
        meta = template.setdefault("meta", {})
        result = {"status": "published" if published else "unpublished", "sk": sk}
        meta["published"] = published
        meta.pop("idempotency", None)
        meta["updated_at"] = now
        if published:
            meta["published_at"] = now
        else:
            meta.pop("published_at", None)
        self._write_template_index_sync({**template, "pk": self._pk, "sk": sk}, expected_revision=expected_revision)
        return result

    async def set_published(self, sk: str, published: bool, actor_pk: str | None = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.set_published_sync(sk, published, actor_pk, expected_revision, idempotency_key)
        )

    def copy_template_sync(self, sk: str, new_name: str, *, actor_pk: str | None = None, author: str | None = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> str:
        require_mutation_envelope(expected_revision, idempotency_key)
        if not actor_pk:
            raise TemplatePermissionError("Template copy requires a signed-in author")
        template = self.get_template_sync(sk, actor_pk=actor_pk)
        if not template:
            raise TemplateNotFoundError(f"Template not found: {sk}")

        new_template = copy.deepcopy(template)
        meta = new_template.setdefault("meta", {})
        meta["name"] = new_name
        meta.pop("created_at", None)
        meta.pop("updated_at", None)
        meta.pop("published_at", None)
        meta["derived_from_template_sk"] = sk
        meta["archived"] = False
        meta["published"] = False
        meta["author_pk"] = actor_pk
        meta["author"] = author or actor_pk
        meta["revision"] = 0
        meta.pop("idempotency", None)
        meta.pop("template_apply_idempotency", None)
        new_template.pop("pk", None)
        new_template.pop("sk", None)
        now = self._now()
        meta["created_at"] = now
        meta["updated_at"] = now
        new_sk = f"{self.TEMPLATE_SK_PREFIX}copy-{hashlib.sha256(f'{sk}:{new_name}'.encode()).hexdigest()[:32]}"
        self._write_template_index_sync(new_template | {"pk": self._pk, "sk": new_sk})
        return new_sk

    async def copy_template(self, sk: str, new_name: str, *, actor_pk: str | None = None, author: str | None = None, expected_revision: int | None = None, idempotency_key: str | None = None) -> str:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.copy_template_sync(sk, new_name, actor_pk=actor_pk, author=author, expected_revision=expected_revision, idempotency_key=idempotency_key)
        )

    def create_import_job_sync(self, record: dict[str, Any]) -> str:
        job_id = str(record.get("job_id") or uuid.uuid4())
        now = self._now()
        item = {
            **copy.deepcopy(record),
            "pk": self._pk,
            "sk": f"{self.IMPORT_JOB_SK_PREFIX}{job_id}",
            "job_id": job_id,
            "status": record.get("status") or "queued",
            "created_at": record.get("created_at") or now,
            "updated_at": now,
        }
        self.table.put_item(Item=self._floats_to_decimals(item))
        return job_id

    async def create_import_job(self, record: dict[str, Any]) -> str:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.create_import_job_sync(record)
        )

    def update_import_job_sync(self, job_id: str, updates: dict[str, Any]) -> None:
        existing = self.get_import_job_sync(job_id, include_hidden=True)
        if not existing:
            raise TemplateNotFoundError(f"Template import job not found: {job_id}")
        existing.update(copy.deepcopy(updates))
        existing["updated_at"] = self._now()
        existing["pk"] = self._pk
        existing["sk"] = f"{self.IMPORT_JOB_SK_PREFIX}{job_id}"
        self.table.put_item(Item=self._floats_to_decimals(existing))

    async def update_import_job(self, job_id: str, updates: dict[str, Any]) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.update_import_job_sync(job_id, updates)
        )

    def get_import_job_sync(
        self,
        job_id: str,
        actor_pk: str | None = None,
        *,
        include_hidden: bool = False,
    ) -> dict | None:
        resp = self.table.get_item(Key={"pk": self._pk, "sk": f"{self.IMPORT_JOB_SK_PREFIX}{job_id}"})
        if "Item" not in resp:
            return None
        item = dict(resp["Item"])
        if include_hidden:
            return item
        return item if self._owns(item, actor_pk) else None

    async def get_import_job(
        self,
        job_id: str,
        actor_pk: str | None = None,
        *,
        include_hidden: bool = False,
    ) -> dict | None:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.get_import_job_sync(job_id, actor_pk, include_hidden=include_hidden)
        )
