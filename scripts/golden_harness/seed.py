import json
import re
from decimal import Decimal
from pathlib import Path

import boto3
from boto3.dynamodb.types import TypeDeserializer

from .safety import assert_local_endpoint

TABLE_BLOCK = re.compile(r'resource "aws_dynamodb_table" "[^"]+" \{(.*?)\n\}\n', re.S)
ATTRIBUTE_BLOCK = re.compile(r'attribute \{\s*name = "([^"]+)"\s*type = "([^"]+)"\s*\}')
INDEX_BLOCK = re.compile(r'global_secondary_index \{(.*?)\}', re.S)
FIELD = re.compile(r'(\w+)\s*=\s*"([^"]+)"')


def table_definitions(terraform_file):
    definitions = []
    for block in TABLE_BLOCK.findall(Path(terraform_file).read_text() + "\n"):
        if "dynamic " in block:
            continue
        fields = dict(FIELD.findall(block.split("attribute {")[0]))
        key_schema = [{"AttributeName": fields["hash_key"], "KeyType": "HASH"}]
        if "range_key" in fields:
            key_schema.append({"AttributeName": fields["range_key"], "KeyType": "RANGE"})
        definition = {
            "TableName": fields["name"],
            "BillingMode": "PAY_PER_REQUEST",
            "KeySchema": key_schema,
            "AttributeDefinitions": [{"AttributeName": name, "AttributeType": kind} for name, kind in ATTRIBUTE_BLOCK.findall(block)],
        }
        indexes = []
        for body in INDEX_BLOCK.findall(block):
            index = dict(FIELD.findall(body))
            schema = [{"AttributeName": index["hash_key"], "KeyType": "HASH"}]
            if "range_key" in index:
                schema.append({"AttributeName": index["range_key"], "KeyType": "RANGE"})
            indexes.append({"IndexName": index["name"], "KeySchema": schema, "Projection": {"ProjectionType": index["projection_type"]}})
        if indexes:
            definition["GlobalSecondaryIndexes"] = indexes
        definitions.append(definition)
    return definitions


def create_tables(client, terraform_file):
    assert_local_endpoint()
    created = []
    for definition in table_definitions(terraform_file):
        client.create_table(**definition)
        created.append(definition["TableName"])
    return created


def seed_tables(client, source_dir):
    assert_local_endpoint()
    counts = {}
    for path in sorted(Path(source_dir).glob("if-*.json")):
        items = json.loads(path.read_text())
        for item in items:
            client.put_item(TableName=path.stem, Item=item)
        counts[path.stem] = len(items)
    return counts


def moto_client(port):
    assert_local_endpoint()
    return boto3.client("dynamodb", endpoint_url=f"http://127.0.0.1:{port}")


def plain(value):
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain(item) for item in value]
    if isinstance(value, set):
        return sorted(plain(item) for item in value)
    return value


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plain(value), indent=2, sort_keys=True, default=str) + "\n")


def write_plain_source(source_dir):
    deserializer = TypeDeserializer()

    def load(table):
        raw = json.loads((Path(source_dir) / f"{table}.json").read_text())
        return [plain({key: deserializer.deserialize(value) for key, value in item.items()}) for item in raw]

    health = {item["sk"]: item for item in load("if-health")}
    pointer = health["program#current"]
    write_json(Path(source_dir) / "program_pointer.json", pointer)
    write_json(Path(source_dir) / "program.json", health[pointer["ref_sk"]])
    write_json(Path(source_dir) / "glossary.json", health.get("glossary#v1", {}))
    write_json(Path(source_dir) / "weight_log.json", health.get("weight_log#current", {}))
    write_json(Path(source_dir) / "sessions.json", load("if-sessions"))
    write_json(Path(source_dir) / "goals.json", load("if-powerlifting-goals"))
    write_json(Path(source_dir) / "competitions.json", load("if-powerlifting-user-competitions"))
    return plain(health[pointer["ref_sk"]]), load("if-sessions")
