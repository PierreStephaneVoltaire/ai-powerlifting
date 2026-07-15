
from __future__ import annotations

import asyncio
import copy
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3

logger = logging.getLogger(__name__)

class TemplateNotFoundError(Exception):
    """Raised when a template is not found or not visible to the actor."""

class TemplatePermissionError(Exception):
    """Raised when an actor cannot mutate a template."""

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
            self._table = boto3.resource(
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

    def _visible(self, template_or_summary: dict[str, Any], actor_pk: str | None) -> bool:
        meta = template_or_summary.get("meta") if isinstance(template_or_summary.get("meta"), dict) else template_or_summary
        if self._is_published_meta(meta):
            return True
        return bool(actor_pk and str(meta.get("author_pk") or "") == str(actor_pk))

    def _assert_owner(self, template: dict[str, Any], actor_pk: str | None) -> None:
        meta = template.get("meta") if isinstance(template.get("meta"), dict) else {}
        author_pk = str(meta.get("author_pk") or "")
        if not actor_pk or not author_pk or author_pk != str(actor_pk):
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

    def _upsert_index_summary_sync(self, summary: dict[str, Any]) -> None:
        templates = self._read_index_sync()
        next_templates = [t for t in templates if t.get("sk") != summary.get("sk")]
        next_templates.append(summary)
        next_templates.sort(key=lambda t: str(t.get("created_at") or ""))
        self._write_index_sync(next_templates, str(summary.get("updated_at") or self._now()))

    def list_templates_sync(self, include_archived: bool = False, actor_pk: str | None = None) -> list[dict[str, Any]]:
        templates = self._read_index_sync()
        visible = [t for t in templates if self._visible(t, actor_pk)]
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
    ) -> str:
        now = self._now()
        new_sk = sk or self._new_template_sk()
        template_item = copy.deepcopy(template)
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

        template_item["pk"] = self._pk
        template_item["sk"] = new_sk
        self.table.put_item(Item=self._floats_to_decimals(template_item))
        self._upsert_index_summary_sync(self._summary(template_item))
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
            ),
        )

    def update_template_sync(self, sk: str, template: dict, *, actor_pk: str | None = None) -> None:
        existing = self.get_template_sync(sk, actor_pk=actor_pk)
        if not existing:
            raise TemplateNotFoundError(f"Template not found: {sk}")
        self._assert_owner(existing, actor_pk)

        now = self._now()
        template_item = copy.deepcopy(template)
        incoming_meta = template_item.setdefault("meta", {})
        existing_meta = existing.get("meta") if isinstance(existing.get("meta"), dict) else {}

        incoming_meta["created_at"] = existing_meta.get("created_at", now)
        incoming_meta["updated_at"] = now
        incoming_meta["author_pk"] = existing_meta.get("author_pk")
        incoming_meta["author"] = existing_meta.get("author")
        incoming_meta["published"] = bool(existing_meta.get("published", True))
        if existing_meta.get("published_at"):
            incoming_meta["published_at"] = existing_meta.get("published_at")
        else:
            incoming_meta.pop("published_at", None)
        if existing_meta.get("import_job_id"):
            incoming_meta["import_job_id"] = existing_meta.get("import_job_id")

        template_item["pk"] = self._pk
        template_item["sk"] = sk
        self.table.put_item(Item=self._floats_to_decimals(template_item))
        self._upsert_index_summary_sync(self._summary(template_item))

    async def update_template(self, sk: str, template: dict, *, actor_pk: str | None = None) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.update_template_sync(sk, template, actor_pk=actor_pk)
        )

    def _set_archived_sync(self, sk: str, archived: bool, actor_pk: str | None) -> None:
        template = self.get_template_sync(sk, actor_pk=actor_pk)
        if not template:
            raise TemplateNotFoundError(f"Template not found: {sk}")
        self._assert_owner(template, actor_pk)
        meta = template.setdefault("meta", {})
        meta["archived"] = archived
        meta["updated_at"] = self._now()
        self.table.put_item(Item=self._floats_to_decimals({**template, "pk": self._pk, "sk": sk}))
        self._upsert_index_summary_sync(self._summary(template))

    def archive_template_sync(self, sk: str, actor_pk: str | None = None) -> None:
        self._set_archived_sync(sk, True, actor_pk)

    async def archive_template(self, sk: str, actor_pk: str | None = None) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.archive_template_sync(sk, actor_pk)
        )

    def unarchive_template_sync(self, sk: str, actor_pk: str | None = None) -> None:
        self._set_archived_sync(sk, False, actor_pk)

    async def unarchive_template(self, sk: str, actor_pk: str | None = None) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.unarchive_template_sync(sk, actor_pk)
        )

    def set_published_sync(self, sk: str, published: bool, actor_pk: str | None = None) -> None:
        template = self.get_template_sync(sk, actor_pk=actor_pk)
        if not template:
            raise TemplateNotFoundError(f"Template not found: {sk}")
        self._assert_owner(template, actor_pk)
        now = self._now()
        meta = template.setdefault("meta", {})
        meta["published"] = published
        meta["updated_at"] = now
        if published:
            meta["published_at"] = now
        else:
            meta.pop("published_at", None)
        self.table.put_item(Item=self._floats_to_decimals({**template, "pk": self._pk, "sk": sk}))
        self._upsert_index_summary_sync(self._summary(template))

    async def set_published(self, sk: str, published: bool, actor_pk: str | None = None) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.set_published_sync(sk, published, actor_pk)
        )

    def copy_template_sync(self, sk: str, new_name: str, *, actor_pk: str | None = None, author: str | None = None) -> str:
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
        new_template.pop("pk", None)
        new_template.pop("sk", None)
        return self.put_template_sync(new_template, actor_pk=actor_pk, author=author, published=False)

    async def copy_template(self, sk: str, new_name: str, *, actor_pk: str | None = None, author: str | None = None) -> str:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.copy_template_sync(sk, new_name, actor_pk=actor_pk, author=author)
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
        author_pk = str(item.get("author_pk") or "")
        if actor_pk and author_pk == str(actor_pk):
            return item
        return None

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
