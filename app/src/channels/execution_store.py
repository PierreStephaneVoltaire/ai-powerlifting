













from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from channels.execution_models import (
    ChannelClassificationState,
    ClassificationBatch,
    DiscordOutboundMessage,
    floats_to_decimals,
    get_instance_identity,
    IntentRecord,
    ImplementationTask,
    OpenCodeRunRecord,
)
from config import IF_EXECUTION_REGISTRY_TABLE_NAME, AWS_REGION

logger = logging.getLogger(__name__)

VALID_TRANSITIONS: Dict[str, List[str]] = {
    "idle": ["debouncing"],
    "debouncing": ["classifying"],
    "classifying": ["idle", "debouncing"],
}

TASK_STATUS_TRANSITIONS: Dict[str, List[str]] = {
    "implementing": ["awaiting_instruction", "cancel_requested", "pivot_requested", "completed", "failed"],
    "awaiting_instruction": ["implementing", "cancel_requested", "pivot_requested", "completed", "failed"],
    "cancel_requested": ["completed", "failed", "stale"],
    "pivot_requested": ["implementing", "completed", "failed"],
}

_store: Optional[ExecutionStore] = None

def get_execution_store() -> ExecutionStore:
    global _store
    if _store is None:
        _store = ExecutionStore()
    return _store

class ExecutionStore:
    def __init__(
        self,
        table_name: str = IF_EXECUTION_REGISTRY_TABLE_NAME,
        region: str = AWS_REGION,
    ):
        self.table_name = table_name
        self._region = region
        self._table = None

    @property
    def table(self):
        if self._table is None:
            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self.table_name)
        return self._table

    INTENT_STATUS_TRANSITIONS: Dict[str, List[str]] = {
        "pending": ["applying", "skipped"],
        "applying": ["running", "failed"],
        "running": ["completed", "failed", "skipped"],
    }

    async def get_channel_state(
        self, channel_id: str
    ) -> Optional[ChannelClassificationState]:
        return await asyncio.to_thread(self._get_channel_state_sync, channel_id)

    def _get_channel_state_sync(
        self, channel_id: str
    ) -> Optional[ChannelClassificationState]:
        resp = self.table.get_item(
            Key={"pk": f"CHANNEL#{channel_id}", "sk": "STATE#classification"}
        )
        item = resp.get("Item")
        if item is None:
            return None
        return self._item_to_channel_state(item)

    async def transition_channel_state(
        self,
        channel_id: str,
        from_status: str,
        to_status: str,
        **kwargs: Any,
    ) -> bool:
        return await asyncio.to_thread(
            self._transition_sync, channel_id, from_status, to_status, **kwargs
        )

    def _transition_sync(
        self,
        channel_id: str,
        from_status: str,
        to_status: str,
        **kwargs: Any,
    ) -> bool:
        if to_status not in VALID_TRANSITIONS.get(from_status, []):
            logger.warning(
                "Invalid transition %s -> %s for channel %s",
                from_status,
                to_status,
                channel_id,
            )
            return False
        now = datetime.now(timezone.utc).isoformat()
        update_parts = [
            "#st = :to_status",
            "version = version + :one",
            "updated_at = :now",
        ]
        attr_names = {"#st": "status"}
        attr_values: Dict[str, Any] = {
            ":to_status": to_status,
            ":from_status": from_status,
            ":one": 1,
            ":now": now,
        }
        for k, v in kwargs.items():
            update_parts.append(f"{k} = :kw_{k}")
            attr_values[f":kw_{k}"] = floats_to_decimals(v)
        try:
            self.table.update_item(
                Key={"pk": f"CHANNEL#{channel_id}", "sk": "STATE#classification"},
                UpdateExpression="SET " + ", ".join(update_parts),
                ConditionExpression="#st = :from_status",
                ExpressionAttributeNames=attr_names,
                ExpressionAttributeValues=attr_values,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Transition %s -> %s failed for channel %s (condition)",
                    from_status,
                    to_status,
                    channel_id,
                )
                return False
            raise

    async def update_channel_state_on_event(
        self,
        channel_id: str,
        message_id: str,
        event_at: str,
        is_edit: bool = False,
        debounce_seconds: float = 45.0,
        max_wait_seconds: int = 300,
    ) -> Optional[ChannelClassificationState]:
        return await asyncio.to_thread(
            self._update_state_on_event_sync,
            channel_id,
            message_id,
            event_at,
            is_edit,
            debounce_seconds,
            max_wait_seconds,
        )

    def _update_state_on_event_sync(
        self,
        channel_id: str,
        message_id: str,
        event_at: str,
        is_edit: bool = False,
        debounce_seconds: float = 45.0,
        max_wait_seconds: int = 300,
    ) -> Optional[ChannelClassificationState]:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        debounce_until = (now + timedelta(seconds=debounce_seconds)).isoformat()
        pk = f"CHANNEL#{channel_id}"
        sk = "STATE#classification"
        existing = self.table.get_item(Key={"pk": pk, "sk": sk}).get("Item")
        opening_window = (
            existing is None
            or not existing.get("pending", False)
        )
        if opening_window:
            batch_first_event_at = event_at
            max_wait_until = (
                datetime.fromisoformat(event_at.replace("Z", "+00:00"))
                + timedelta(seconds=max_wait_seconds)
            ).isoformat()
        else:
            batch_first_event_at = existing.get("batch_first_event_at", event_at)
            max_wait_until = existing.get(
                "max_wait_until",
                (now + timedelta(seconds=max_wait_seconds)).isoformat(),
            )
        updates = [
            "channel_id = :channel_id",
            "pending = :true_val",
            "#st = if_not_exists(#st, :debouncing)",
            "pending_event_count = if_not_exists(pending_event_count, :zero) + :one",
            "latest_observed_event_at = :event_at",
            "latest_observed_message_id = :message_id",
            "debounce_until = :debounce_until",
            "batch_first_event_at = :batch_first_event_at",
            "max_wait_until = :max_wait_until",
            "version = if_not_exists(version, :one_init)",
            "updated_at = :now",
        ]
        attr_names = {"#st": "status"}
        values: Dict[str, Any] = {
            ":channel_id": channel_id,
            ":true_val": True,
            ":debouncing": "debouncing",
            ":zero": 0,
            ":one": 1,
            ":one_init": 1,
            ":event_at": event_at,
            ":message_id": message_id,
            ":debounce_until": debounce_until,
            ":batch_first_event_at": batch_first_event_at,
            ":max_wait_until": max_wait_until,
            ":now": now_iso,
        }
        if is_edit:
            updates.append("dirty = :true_val")
            updates.append("latest_observed_edit_at = :event_at")
        classifying_item = existing if existing else {}
        if classifying_item.get("status") == "classifying":
            updates.append("dirty = :true_val")
        try:
            resp = self.table.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression="SET " + ", ".join(updates),
                ExpressionAttributeNames=attr_names,
                ExpressionAttributeValues=values,
                ReturnValues="ALL_NEW",
            )
            item = resp.get("Attributes")
            if item:
                return self._item_to_channel_state(item)
        except ClientError:
            logger.exception(
                "Failed to update channel state on event for %s", channel_id
            )
        return None

    async def acquire_classifier_lock(
        self, channel_id: str, owner: str, expires_at: str
    ) -> bool:
        return await asyncio.to_thread(
            self._acquire_lock_sync, channel_id, owner, expires_at
        )

    def _acquire_lock_sync(
        self, channel_id: str, owner: str, expires_at: str
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            self.table.update_item(
                Key={"pk": f"CHANNEL#{channel_id}", "sk": "STATE#classification"},
                UpdateExpression=(
                    "SET classifier_lock_owner = :owner,"
                    " classifier_lock_expires_at = :expires,"
                    " #st = :classifying,"
                    " last_classifier_started_at = :now,"
                    " updated_at = :now"
                ),
                ConditionExpression=(
                    "attribute_not_exists(classifier_lock_owner)"
                    " OR classifier_lock_expires_at < :now_str"
                ),
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":owner": owner,
                    ":expires": expires_at,
                    ":classifying": "classifying",
                    ":now": now,
                    ":now_str": now,
                },
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info("Lock acquisition failed for channel %s", channel_id)
                return False
            raise

    async def release_classifier_lock(
        self, channel_id: str, owner: str, debounce_seconds: float = 45.0
    ) -> bool:
        return await asyncio.to_thread(
            self._release_lock_sync, channel_id, owner, debounce_seconds
        )

    def _release_lock_sync(
        self, channel_id: str, owner: str, debounce_seconds: float = 45.0
    ) -> bool:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        pk = f"CHANNEL#{channel_id}"
        sk = "STATE#classification"
        try:
            resp = self.table.get_item(Key={"pk": pk, "sk": sk})
            item = resp.get("Item")
            if not item:
                return False
            pending = item.get("pending", False)
            dirty = item.get("dirty", False)
            target_status = "debouncing" if (pending or dirty) else "idle"
            update_parts = [
                "#st = :target",
                "last_classifier_finished_at = :now",
                "updated_at = :now",
            ]
            remove_parts = [
                "classifier_lock_owner",
                "classifier_lock_expires_at",
                "active_classifier_run_id",
            ]
            attr_values: Dict[str, Any] = {
                ":target": target_status,
                ":owner": owner,
                ":now": now_iso,
            }
            if target_status == "idle":
                update_parts.extend([
                    "pending = :false_val",
                    "dirty = :false_val",
                    "pending_event_count = :zero",
                    "batch_first_event_at = :empty",
                    "max_wait_until = :empty",
                    "debounce_until = :empty",
                ])
                attr_values[":false_val"] = False
                attr_values[":zero"] = 0
                attr_values[":empty"] = ""
            else:
                new_debounce_until = (now + timedelta(seconds=debounce_seconds)).isoformat()
                update_parts.append("debounce_until = :debounce_until")
                attr_values[":debounce_until"] = new_debounce_until
            self.table.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression=(
                    "SET " + ", ".join(update_parts)
                    + " REMOVE " + ", ".join(remove_parts)
                ),
                ConditionExpression="classifier_lock_owner = :owner",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues=attr_values,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Lock release failed for channel %s (owner mismatch)", channel_id
                )
                return False
            raise

    async def update_cursors(
        self, channel_id: str, last_classified_message_id: str
    ) -> bool:
        return await asyncio.to_thread(
            self._update_cursors_sync, channel_id, last_classified_message_id
        )

    def _update_cursors_sync(
        self, channel_id: str, last_classified_message_id: str
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            self.table.update_item(
                Key={"pk": f"CHANNEL#{channel_id}", "sk": "STATE#classification"},
                UpdateExpression=(
                    "SET last_classified_message_id = :msg_id,"
                    " last_classified_at = :now,"
                    " updated_at = :now"
                ),
                ExpressionAttributeValues={
                    ":msg_id": last_classified_message_id,
                    ":now": now,
                },
            )
            return True
        except ClientError:
            logger.exception("Failed to update cursors for channel %s", channel_id)
            return False

    @staticmethod
    def _item_to_channel_state(item: Dict[str, Any]) -> ChannelClassificationState:
        return ChannelClassificationState(
            channel_id=item.get("channel_id", ""),
            status=item.get("status", "idle"),
            pending=item.get("pending", False),
            dirty=item.get("dirty", False),
            debounce_until=item.get("debounce_until"),
            batch_first_event_at=item.get("batch_first_event_at"),
            max_wait_until=item.get("max_wait_until"),
            latest_observed_event_at=item.get("latest_observed_event_at"),
            latest_observed_message_id=item.get("latest_observed_message_id"),
            latest_observed_edit_at=item.get("latest_observed_edit_at"),
            last_classifier_started_at=item.get("last_classifier_started_at"),
            last_classifier_finished_at=item.get("last_classifier_finished_at"),
            active_classifier_run_id=item.get("active_classifier_run_id"),
            classifier_lock_owner=item.get("classifier_lock_owner"),
            classifier_lock_expires_at=item.get("classifier_lock_expires_at"),
            last_classified_message_id=item.get("last_classified_message_id"),
            last_classified_at=item.get("last_classified_at"),
            pending_event_count=int(item.get("pending_event_count", 0)),
            version=int(item.get("version", 1)),
            updated_at=item.get("updated_at", ""),
        )

    async def put_classification_batch(self, batch: ClassificationBatch) -> None:
        await asyncio.to_thread(self._put_classification_batch_sync, batch)

    def _put_classification_batch_sync(self, batch: ClassificationBatch) -> None:
        item: Dict[str, Any] = {
            "pk": f"CHANNEL#{batch.channel_id}",
            "sk": f"BATCH#{batch.batch_id}",
            "channel_id": batch.channel_id,
            "batch_id": batch.batch_id,
            "classifier_run_id": batch.classifier_run_id,
            "started_at": batch.started_at,
            "completed_at": batch.completed_at or "",
            "history_fetched_at": batch.history_fetched_at or "",
            "history_oldest_message_id": batch.history_oldest_message_id or "",
            "history_newest_message_id": batch.history_newest_message_id or "",
            "cursor_before_message_id": batch.cursor_before_message_id or "",
            "cursor_after_message_id": batch.cursor_after_message_id or "",
            "edited_since": batch.edited_since or "",
            "candidate_source_message_ids": batch.candidate_source_message_ids,
            "status": batch.status,
            "batch_summary": batch.batch_summary or "",
            "decisions": batch.decisions,
            "error": batch.error or "",
            "version": batch.version,
        }
        if batch.ttl is not None:
            item["ttl"] = batch.ttl
        self.table.put_item(Item=floats_to_decimals(item))

    async def put_intent_record(self, intent: IntentRecord) -> None:
        await asyncio.to_thread(self._put_intent_record_sync, intent)

    def _put_intent_record_sync(self, intent: IntentRecord) -> None:
        item: Dict[str, Any] = {
            "pk": f"BATCH#{intent.batch_id}",
            "sk": f"INTENT#{intent.intent_id}",
            "intent_id": intent.intent_id,
            "batch_id": intent.batch_id,
            "channel_id": intent.channel_id,
            "action": intent.action,
            "kind": intent.kind,
            "source_message_ids": intent.source_message_ids,
            "target_task_id": intent.target_task_id or "",
            "status": intent.status,
            "created_at": intent.created_at,
            "updated_at": intent.updated_at,
            "error": intent.error or "",
        }
        if intent.ttl is not None:
            item["ttl"] = intent.ttl
        self.table.put_item(Item=floats_to_decimals(item))

    async def get_active_tasks_for_channel(
        self, channel_id: str
    ) -> List[ImplementationTask]:
        return await asyncio.to_thread(self._get_active_tasks_sync, channel_id)

    def _get_active_tasks_sync(self, channel_id: str) -> List[ImplementationTask]:
        pk = f"CHANNEL#{channel_id}"
        tasks: List[ImplementationTask] = []
        last_key = None
        while True:
            kwargs: Dict[str, Any] = {
                "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
                "ExpressionAttributeValues": {":pk": pk, ":prefix": "TASK#"},
            }
            if last_key:
                kwargs["ExclusiveStartKey"] = last_key
            resp = self.table.query(**kwargs)
            for item in resp.get("Items", []):
                task = self._item_to_implementation_task(item)
                if task.status in (
                    "implementing",
                    "awaiting_instruction",
                    "cancel_requested",
                    "pivot_requested",
                ):
                    tasks.append(task)
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
        return tasks

    @staticmethod
    def _item_to_implementation_task(item: Dict[str, Any]) -> ImplementationTask:
        return ImplementationTask(
            task_id=item.get("task_id", ""),
            channel_id=item.get("channel_id", ""),
            conversation_id=item.get("conversation_id", ""),
            status=item.get("status", "implementing"),
            root_discord_message_id=item.get("root_discord_message_id", ""),
            related_discord_message_ids=item.get("related_discord_message_ids", []),
            active_implementer_run_id=item.get("active_implementer_run_id") or None,
            latest_planner_run_id=item.get("latest_planner_run_id") or None,
            selected_specialist=item.get("selected_specialist") or None,
            selected_model=item.get("selected_model") or None,
            topic=item.get("topic", {}),
            pending_conflict=item.get("pending_conflict"),
            queued_message_refs=item.get("queued_message_refs", []),
            control=item.get("control", {}),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
            version=int(item.get("version", 1)),
            ttl=item.get("ttl"),
        )

    async def put_implementation_task(self, task: ImplementationTask) -> bool:
        return await asyncio.to_thread(self._put_implementation_task_sync, task)

    def _put_implementation_task_sync(self, task: ImplementationTask) -> bool:
        item: Dict[str, Any] = {
            "pk": f"CHANNEL#{task.channel_id}",
            "sk": f"TASK#{task.task_id}",
            "task_id": task.task_id,
            "channel_id": task.channel_id,
            "conversation_id": task.conversation_id,
            "status": task.status,
            "root_discord_message_id": task.root_discord_message_id,
            "related_discord_message_ids": task.related_discord_message_ids,
            "active_implementer_run_id": task.active_implementer_run_id or "",
            "latest_planner_run_id": task.latest_planner_run_id or "",
            "selected_specialist": task.selected_specialist or "",
            "selected_model": task.selected_model or "",
            "topic": task.topic,
            "queued_message_refs": task.queued_message_refs,
            "control": task.control,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "version": task.version,
        }
        if task.pending_conflict is not None:
            item["pending_conflict"] = task.pending_conflict
        if task.ttl is not None:
            item["ttl"] = task.ttl
        try:
            self.table.put_item(
                Item=floats_to_decimals(item),
                ConditionExpression="attribute_not_exists(pk)",
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Implementation task %s already exists for channel %s",
                    task.task_id,
                    task.channel_id,
                )
                return False
            raise

    async def get_implementation_task(
        self, channel_id: str, task_id: str
    ) -> Optional[ImplementationTask]:
        return await asyncio.to_thread(
            self._get_implementation_task_sync, channel_id, task_id
        )

    def _get_implementation_task_sync(
        self, channel_id: str, task_id: str
    ) -> Optional[ImplementationTask]:
        resp = self.table.get_item(
            Key={"pk": f"CHANNEL#{channel_id}", "sk": f"TASK#{task_id}"}
        )
        item = resp.get("Item")
        if item is None:
            return None
        return self._item_to_implementation_task(item)

    async def update_implementation_task(
        self,
        channel_id: str,
        task_id: str,
        from_status: str,
        to_status: str,
        **extra_updates: Any,
    ) -> bool:
        return await asyncio.to_thread(
            self._update_implementation_task_sync,
            channel_id,
            task_id,
            from_status,
            to_status,
            **extra_updates,
        )

    def _update_implementation_task_sync(
        self,
        channel_id: str,
        task_id: str,
        from_status: str,
        to_status: str,
        **extra_updates: Any,
    ) -> bool:
        if to_status not in TASK_STATUS_TRANSITIONS.get(from_status, []):
            logger.warning(
                "Invalid task transition %s -> %s for task %s/%s",
                from_status,
                to_status,
                channel_id,
                task_id,
            )
            return False
        now = datetime.now(timezone.utc).isoformat()
        pk = f"CHANNEL#{channel_id}"
        sk = f"TASK#{task_id}"
        update_parts = ["#st = :to_status", "updated_at = :now"]
        attr_names = {"#st": "status"}
        attr_values: Dict[str, Any] = {
            ":to_status": to_status,
            ":from_status": from_status,
            ":now": now,
        }
        for k, v in extra_updates.items():
            update_parts.append(f"{k} = :eu_{k}")
            attr_values[f":eu_{k}"] = floats_to_decimals(v)
        try:
            self.table.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression="SET " + ", ".join(update_parts),
                ConditionExpression="#st = :from_status",
                ExpressionAttributeNames=attr_names,
                ExpressionAttributeValues=attr_values,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Task transition %s -> %s failed for %s/%s (condition)",
                    from_status,
                    to_status,
                    channel_id,
                    task_id,
                )
                return False
            raise

    async def append_task_queued_refs(
        self,
        channel_id: str,
        task_id: str,
        refs: List[Dict[str, Any]],
        expected_version: int,
    ) -> bool:
        return await asyncio.to_thread(
            self._append_task_queued_refs_sync,
            channel_id,
            task_id,
            refs,
            expected_version,
        )

    def _append_task_queued_refs_sync(
        self,
        channel_id: str,
        task_id: str,
        refs: List[Dict[str, Any]],
        expected_version: int,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        pk = f"CHANNEL#{channel_id}"
        sk = f"TASK#{task_id}"
        try:
            self.table.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression=(
                    "SET queued_message_refs = list_append(queued_message_refs, :refs),"
                    " version = version + :one,"
                    " updated_at = :now"
                ),
                ConditionExpression="version = :expected_version",
                ExpressionAttributeValues={
                    ":refs": floats_to_decimals(refs),
                    ":one": 1,
                    ":now": now,
                    ":expected_version": expected_version,
                },
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Queued refs append failed for task %s/%s (version mismatch)",
                    channel_id,
                    task_id,
                )
                return False
            raise

    async def put_outbound_message(self, msg: DiscordOutboundMessage) -> bool:
        return await asyncio.to_thread(self._put_outbound_message_sync, msg)

    def _put_outbound_message_sync(self, msg: DiscordOutboundMessage) -> bool:
        pk = f"CHANNEL#{msg.channel_id}"
        priority_padded = f"{msg.priority:02d}"
        send_after = msg.send_after or msg.created_at or datetime.now(timezone.utc).isoformat()
        sk = f"OUTBOX#{priority_padded}#{send_after}#{msg.outbound_id}"
        item: Dict[str, Any] = {
            "pk": pk,
            "sk": sk,
            "outbound_id": msg.outbound_id,
            "channel_id": msg.channel_id,
            "conversation_id": msg.conversation_id,
            "task_id": msg.task_id or "",
            "intent_id": msg.intent_id or "",
            "batch_id": msg.batch_id or "",
            "type": msg.type,
            "priority": msg.priority,
            "content": msg.content,
            "attachments": msg.attachments,
            "reply_to_message_id": msg.reply_to_message_id or "",
            "status": msg.status,
            "send_after": msg.send_after or "",
            "created_at": msg.created_at,
            "updated_at": msg.updated_at,
            "discord_message_id": msg.discord_message_id or "",
            "idempotency_key": msg.idempotency_key,
        }
        if msg.allowed_mentions is not None:
            item["allowed_mentions"] = msg.allowed_mentions
        if msg.ttl is not None:
            item["ttl"] = msg.ttl
        try:
            self.table.put_item(
                Item=floats_to_decimals(item),
                ConditionExpression=(
                    "attribute_not_exists(idempotency_key)"
                    " OR idempotency_key = :idem_key"
                ),
                ExpressionAttributeValues={
                    ":idem_key": msg.idempotency_key,
                },
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Outbound message %s already exists (idempotency)",
                    msg.outbound_id,
                )
                return False
            raise

    async def update_intent_record_status(
        self,
        batch_id: str,
        intent_id: str,
        from_status: str,
        to_status: str,
        **extra_updates: Any,
    ) -> bool:
        return await asyncio.to_thread(
            self._update_intent_status_sync,
            batch_id,
            intent_id,
            from_status,
            to_status,
            **extra_updates,
        )

    def _update_intent_status_sync(
        self,
        batch_id: str,
        intent_id: str,
        from_status: str,
        to_status: str,
        **extra_updates: Any,
    ) -> bool:
        if to_status not in self.INTENT_STATUS_TRANSITIONS.get(from_status, []):
            logger.warning(
                "Invalid intent transition %s -> %s for intent %s/%s",
                from_status,
                to_status,
                batch_id,
                intent_id,
            )
            return False
        now = datetime.now(timezone.utc).isoformat()
        pk = f"BATCH#{batch_id}"
        sk = f"INTENT#{intent_id}"
        update_parts = ["#st = :to_status", "updated_at = :now"]
        attr_names = {"#st": "status"}
        attr_values: Dict[str, Any] = {
            ":to_status": to_status,
            ":from_status": from_status,
            ":now": now,
        }
        for k, v in extra_updates.items():
            update_parts.append(f"{k} = :eu_{k}")
            attr_values[f":eu_{k}"] = floats_to_decimals(v)
        try:
            self.table.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression="SET " + ", ".join(update_parts),
                ConditionExpression="#st = :from_status",
                ExpressionAttributeNames=attr_names,
                ExpressionAttributeValues=attr_values,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Intent transition %s -> %s failed for %s/%s (condition)",
                    from_status,
                    to_status,
                    batch_id,
                    intent_id,
                )
                return False
            raise

    async def get_intent_record(
        self, batch_id: str, intent_id: str
    ) -> Optional[IntentRecord]:
        return await asyncio.to_thread(
            self._get_intent_record_sync, batch_id, intent_id
        )

    def _get_intent_record_sync(
        self, batch_id: str, intent_id: str
    ) -> Optional[IntentRecord]:
        resp = self.table.get_item(
            Key={"pk": f"BATCH#{batch_id}", "sk": f"INTENT#{intent_id}"}
        )
        item = resp.get("Item")
        if item is None:
            return None
        return self._item_to_intent_record(item)

    @staticmethod
    def _item_to_intent_record(item: Dict[str, Any]) -> IntentRecord:
        return IntentRecord(
            intent_id=item.get("intent_id", ""),
            batch_id=item.get("batch_id", ""),
            channel_id=item.get("channel_id", ""),
            action=item.get("action", ""),
            kind=item.get("kind", ""),
            source_message_ids=item.get("source_message_ids", []),
            target_task_id=item.get("target_task_id") or None,
            status=item.get("status", "pending"),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
            error=item.get("error") or None,
            ttl=item.get("ttl"),
        )

    @staticmethod
    def _item_to_outbound_message(item: Dict[str, Any]) -> DiscordOutboundMessage:
        return DiscordOutboundMessage(
            outbound_id=item.get("outbound_id", ""),
            channel_id=item.get("channel_id", ""),
            conversation_id=item.get("conversation_id", ""),
            task_id=item.get("task_id") or None,
            intent_id=item.get("intent_id") or None,
            batch_id=item.get("batch_id") or None,
            type=item.get("type", "social_response"),
            priority=int(item.get("priority", 5)),
            content=item.get("content", ""),
            attachments=item.get("attachments", []),
            reply_to_message_id=item.get("reply_to_message_id") or None,
            allowed_mentions=item.get("allowed_mentions"),
            status=item.get("status", "queued"),
            send_after=item.get("send_after") or None,
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
            discord_message_id=item.get("discord_message_id") or None,
            idempotency_key=item.get("idempotency_key", ""),
            ttl=item.get("ttl"),
        )

    async def acquire_outbound_lock(
        self, channel_id: str, owner: str, expires_at: str
    ) -> bool:
        return await asyncio.to_thread(
            self._acquire_outbound_lock_sync, channel_id, owner, expires_at
        )

    def _acquire_outbound_lock_sync(
        self, channel_id: str, owner: str, expires_at: str
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        pk = f"CHANNEL#{channel_id}"
        sk = "STATE#outbound"
        try:
            self.table.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression=(
                    "SET outbound_lock_owner = :owner,"
                    " outbound_lock_expires_at = :expires,"
                    " updated_at = :now"
                ),
                ConditionExpression=(
                    "attribute_not_exists(outbound_lock_owner)"
                    " OR outbound_lock_expires_at < :now_str"
                ),
                ExpressionAttributeValues={
                    ":owner": owner,
                    ":expires": expires_at,
                    ":now": now,
                    ":now_str": now,
                },
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info("Outbound lock acquisition failed for channel %s", channel_id)
                return False
            raise

    async def release_outbound_lock(
        self, channel_id: str, owner: str
    ) -> bool:
        return await asyncio.to_thread(
            self._release_outbound_lock_sync, channel_id, owner
        )

    def _release_outbound_lock_sync(
        self, channel_id: str, owner: str
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        pk = f"CHANNEL#{channel_id}"
        sk = "STATE#outbound"
        try:
            self.table.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression="REMOVE outbound_lock_owner, outbound_lock_expires_at SET updated_at = :now",
                ConditionExpression="outbound_lock_owner = :owner",
                ExpressionAttributeValues={":owner": owner, ":now": now},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Outbound lock release failed for channel %s (owner mismatch)",
                    channel_id,
                )
                return False
            raise

    async def get_outbound_state(
        self, channel_id: str
    ) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._get_outbound_state_sync, channel_id)

    def _get_outbound_state_sync(
        self, channel_id: str
    ) -> Optional[Dict[str, Any]]:
        resp = self.table.get_item(
            Key={"pk": f"CHANNEL#{channel_id}", "sk": "STATE#outbound"}
        )
        return resp.get("Item")

    async def query_outbox(
        self, channel_id: str, limit: int = 10
    ) -> List[DiscordOutboundMessage]:
        return await asyncio.to_thread(self._query_outbox_sync, channel_id, limit)

    def _query_outbox_sync(
        self, channel_id: str, limit: int
    ) -> List[DiscordOutboundMessage]:
        pk = f"CHANNEL#{channel_id}"
        try:
            resp = self.table.query(
                KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
                ExpressionAttributeValues={":pk": pk, ":prefix": "OUTBOX#"},
                Limit=limit,
                ScanIndexForward=True,
            )
            items = resp.get("Items", [])
            return [self._item_to_outbound_message(item) for item in items]
        except ClientError:
            logger.exception("Failed to query outbox for channel %s", channel_id)
            return []

    async def update_outbound_message_status(
        self,
        channel_id: str,
        outbound_id: str,
        from_status: str,
        to_status: str,
        **extra_updates: Any,
    ) -> bool:
        return await asyncio.to_thread(
            self._update_outbound_status_sync,
            channel_id,
            outbound_id,
            from_status,
            to_status,
            **extra_updates,
        )

    def _update_outbound_status_sync(
        self,
        channel_id: str,
        outbound_id: str,
        from_status: str,
        to_status: str,
        **extra_updates: Any,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        pk = f"CHANNEL#{channel_id}"
        update_parts = ["#st = :to_status", "updated_at = :now"]
        attr_names = {"#st": "status"}
        attr_values: Dict[str, Any] = {
            ":to_status": to_status,
            ":from_status": from_status,
            ":now": now,
        }
        for k, v in extra_updates.items():
            update_parts.append(f"{k} = :eu_{k}")
            attr_values[f":eu_{k}"] = floats_to_decimals(v)
        try:
            resp = self.table.query(
                KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
                FilterExpression="outbound_id = :oid",
                ExpressionAttributeValues={
                    ":pk": pk,
                    ":prefix": "OUTBOX#",
                    ":oid": outbound_id,
                },
                Limit=1,
            )
            items = resp.get("Items", [])
            if not items:
                logger.warning(
                    "Outbound message %s not found for status update", outbound_id
                )
                return False
            sk = items[0]["sk"]
            self.table.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression="SET " + ", ".join(update_parts),
                ConditionExpression="#st = :from_status",
                ExpressionAttributeNames=attr_names,
                ExpressionAttributeValues=attr_values,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Outbound status %s->%s failed for %s (condition)",
                    from_status,
                    to_status,
                    outbound_id,
                )
                return False
            raise

    async def put_run_record(self, record: OpenCodeRunRecord) -> None:
        await asyncio.to_thread(self._put_run_record_sync, record)

    def _put_run_record_sync(self, record: OpenCodeRunRecord) -> None:
        item: Dict[str, Any] = {
            "pk": f"RUN#{record.run_id}",
            "sk": "META",
            "run_id": record.run_id,
            "channel_id": record.channel_id or "",
            "task_id": record.task_id or "",
            "batch_id": record.batch_id or "",
            "kind": record.kind,
            "agent": record.agent,
            "model": record.model,
            "status": record.status,
            "started_at": record.started_at,
        }
        if record.completed_at is not None:
            item["completed_at"] = record.completed_at
        if record.title is not None:
            item["title"] = record.title
        if record.session_dir is not None:
            item["session_dir"] = record.session_dir
        if record.config_path is not None:
            item["config_path"] = record.config_path
        if record.session_marker_path is not None:
            item["session_marker_path"] = record.session_marker_path
        if record.history_path is not None:
            item["history_path"] = record.history_path
        if record.plan_path is not None:
            item["plan_path"] = record.plan_path
        if record.response_path is not None:
            item["response_path"] = record.response_path
        if record.status_path is not None:
            item["status_path"] = record.status_path
        if record.returncode is not None:
            item["returncode"] = record.returncode
        if record.error is not None:
            item["error"] = record.error[:2000]
        if record.ttl is not None:
            item["ttl"] = record.ttl
        if record.task_id:
            task_item = dict(item)
            task_item["pk"] = f"TASK#{record.task_id}"
            task_item["sk"] = f"RUN#{record.run_id}"
            try:
                self.table.put_item(Item=floats_to_decimals(task_item))
            except ClientError:
                logger.debug("Task-indexed run record write failed for %s", record.run_id)
        self.table.put_item(Item=floats_to_decimals(item))

    async def update_run_record_status(
        self,
        run_id: str,
        event: str,
        **kwargs: Any,
    ) -> bool:
        return await asyncio.to_thread(
            self._update_run_record_status_sync, run_id, event, **kwargs
        )

    def _update_run_record_status_sync(
        self,
        run_id: str,
        event: str,
        **kwargs: Any,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        pk = f"RUN#{run_id}"
        sk = "META"
        update_parts = ["#st = :status", "updated_at = :now"]
        attr_names = {"#st": "status"}
        attr_values: Dict[str, Any] = {
            ":status": event,
            ":now": now,
        }
        for k, v in kwargs.items():
            if k == "returncode":
                update_parts.append("returncode = :kw_returncode")
                attr_values[":kw_returncode"] = v
            elif k == "error":
                update_parts.append("error = :kw_error")
                attr_values[":kw_error"] = str(v)[:2000] if v else ""
        if event in ("completed", "failed", "timed_out", "cancelled"):
            update_parts.append("completed_at = :now")
        try:
            self.table.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression="SET " + ", ".join(update_parts),
                ExpressionAttributeNames=attr_names,
                ExpressionAttributeValues=attr_values,
            )
            return True
        except ClientError:
            logger.debug("Run record status update failed for %s", run_id)
            return False
