import asyncio
import hashlib
import json
import os
import time
from datetime import date

import boto3
import httpx
from fastapi.encoders import jsonable_encoder
from botocore.exceptions import ClientError

from .dispatch import OperationError

REPORTS = {"correlation_analysis", "program_evaluation", "block_correlation_analysis", "block_program_evaluation", "multi_block_comparison_analysis"}
TERMINAL = {"succeeded", "failed", "cancelled", "uncertain"}


def fingerprint(operation, arguments, source=None):
    inputs = {key: value for key, value in arguments.items() if not key.startswith("_") and key not in {"refresh", "cache_only"}}
    return hashlib.sha256(json.dumps({"operation": operation, "inputs": inputs, "source": source}, sort_keys=True, default=str).encode()).hexdigest()


class GenerationStore:
    def __init__(self, athlete):
        self.athlete = athlete
        self.table = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "ca-central-1")).Table(os.getenv("ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache"))

    def key(self, generation_id):
        return {"pk": "analysis#" + self.athlete, "sk": "native_generation#" + generation_id}

    def get(self, generation_id):
        return self.table.get_item(Key=self.key(generation_id), ConsistentRead=True).get("Item")

    def reserve(self, generation_id, operation, owner, retry=False):
        current = self.get(generation_id)
        if current and not (retry and current["status"] in {"failed", "cancelled", "uncertain"}):
            return current, False
        attempt = int((current or {}).get("attempt", 0)) + 1
        record = {**self.key(generation_id), "generation_id": generation_id, "source_fingerprint": generation_id, "operation": operation,
                  "owner": owner, "status": "starting", "attempt": attempt, "updated_at": int(time.time())}
        try:
            condition = "attribute_not_exists(pk)" if current is None else "#status=:previous AND attempt=:attempt"
            options = {} if current is None else {"ExpressionAttributeNames": {"#status": "status"}, "ExpressionAttributeValues": {":previous": current["status"], ":attempt": current["attempt"]}}
            self.table.put_item(Item=record, ConditionExpression=condition, **options)
            return record, True
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            return self.get(generation_id), False

    def update(self, generation_id, expected_attempt=None, **fields):
        fields["updated_at"] = int(time.time())
        names = {f"#f{i}": key for i, key in enumerate(fields)}
        values = {f":v{i}": value for i, value in enumerate(fields.values())}
        options = {}
        if expected_attempt is not None:
            names["#attempt"] = "attempt"
            values[":attempt"] = expected_attempt
            options["ConditionExpression"] = "#attempt=:attempt"
        try:
            self.table.update_item(Key=self.key(generation_id), UpdateExpression="SET " + ", ".join(f"#f{i}=:v{i}" for i in range(len(fields))),
                ExpressionAttributeNames=names, ExpressionAttributeValues=values, **options)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    def complete(self, generation_id, result, attempt):
        payload = json.dumps(result, default=str)
        for index in range(0, len(payload), 80000):
            self.table.put_item(Item={**self.key(generation_id + f"#result#{attempt}#{index // 80000}"), "payload": payload[index:index + 80000]})
        self.update(generation_id, expected_attempt=attempt, status="succeeded", shards=max(1, (len(payload) + 79999) // 80000))

    def result(self, record):
        parts = [self.get(record["generation_id"] + f"#result#{record['attempt']}#{i}") for i in range(int(record.get("shards", 0)))]
        if not parts or any(not part for part in parts):
            raise OperationError(409, "uncertain", "Report result is incomplete; explicitly retry")
        result = json.loads("".join(part["payload"] for part in parts))
        return {**result, "cached": True} if isinstance(result, dict) else result


async def report_source(arguments, athlete, operation=""):
    source = {}
    if "program_evaluation" in operation:
        from federation_store import FederationStore
        source["federation_library"] = await FederationStore(os.getenv("IF_HEALTH_TABLE_NAME", "if-health"), pk=athlete, region=os.getenv("AWS_REGION", "ca-central-1")).get_library()
    if isinstance(arguments.get("program"), dict):
        return jsonable_encoder(source) or None
    from program_store import ProgramStore
    from storage_scope import current_athlete
    token = current_athlete.set(athlete)
    try:
        store = ProgramStore(table_name=os.getenv("IF_HEALTH_TABLE_NAME", "if-health"), pk=athlete, region=os.getenv("AWS_REGION", "ca-central-1"))
        store.invalidate_cache()
        program = await store.get_program()
        return jsonable_encoder({**source, "program": program, "date": arguments.get("ref_date") or arguments.get("asOfDate") or date.today().isoformat()})
    finally:
        current_athlete.reset(token)


async def status(generation_id, athlete):
    store = GenerationStore(athlete)
    record = await asyncio.to_thread(store.get, generation_id)
    if not record:
        raise OperationError(404, "not_found", "Report generation not found")
    if record["status"] not in TERMINAL and record.get("job_id"):
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(os.environ["IF_API_URL"].rstrip("/") + "/v1/jobs/" + record["job_id"], headers={"X-Internal-Token": os.environ["INTERNAL_API_TOKEN"], "X-Person-Pk": record["owner"]})
            response.raise_for_status()
            job = response.json()
        if job["status"] in TERMINAL:
            record = await asyncio.to_thread(store.get, generation_id)
            if record["status"] == "succeeded":
                return {"generation_id": generation_id, "status": "succeeded", "cached": True, "result": await asyncio.to_thread(store.result, record)}
            record.update(status="uncertain" if job["status"] == "succeeded" else job["status"], error=job.get("error") or {"message": "Report did not persist a validated result; explicitly retry"})
            await asyncio.to_thread(store.update, generation_id, expected_attempt=record["attempt"], status=record["status"], error=record["error"])
    elif record["status"] == "starting" and not record.get("job_id") and time.time() - record["updated_at"] > 60:
        record["status"] = "uncertain"
        await asyncio.to_thread(store.update, generation_id, expected_attempt=record["attempt"], status="uncertain")
    result = {"generation_id": generation_id, "status": record["status"], "source_fingerprint": record["source_fingerprint"], "job_id": record.get("job_id"), "error": record.get("error")}
    if record["status"] == "succeeded":
        result["result"] = await asyncio.to_thread(store.result, record)
        result["cached"] = True
    return result
