#!/usr/bin/env python3
import argparse
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


PARTITIONS = ("sir_simpalot", "operator")
FIELDS = ("supplements", "supplement_phases")
SOURCE_TABLE = "if-health"
DESTINATION_TABLE = "if-supplements"


def query_programs(client, table, partition):
    response = client.query(
        TableName=table,
        KeyConditionExpression="#pk = :pk AND begins_with(#sk, :prefix)",
        ExpressionAttributeNames={"#pk": "pk", "#sk": "sk"},
        ExpressionAttributeValues={":pk": {"S": partition}, ":prefix": {"S": "program#v"}},
        ConsistentRead=True,
    )
    items = response.get("Items", [])
    while response.get("LastEvaluatedKey"):
        response = client.query(
            TableName=table,
            KeyConditionExpression="#pk = :pk AND begins_with(#sk, :prefix)",
            ExpressionAttributeNames={"#pk": "pk", "#sk": "sk"},
            ExpressionAttributeValues={":pk": {"S": partition}, ":prefix": {"S": "program#v"}},
            ConsistentRead=True,
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))
    return items


def backup(items_by_partition, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(items_by_partition, output, indent=2, sort_keys=True)
        output.write("\n")


def migrated_item(source):
    return {"pk": source["pk"], "sk": source["sk"], **{field: source[field] for field in FIELDS if field in source}}


def get_item(client, table, key):
    return client.get_item(TableName=table, Key=key, ConsistentRead=True).get("Item")


def destination_matches(existing, expected):
    return existing is not None and all(existing.get(field) == expected.get(field) for field in ("pk", "sk", *FIELDS))


def copy_item(client, source, source_table, destination_table):
    target = migrated_item(source)
    key = {"pk": source["pk"], "sk": source["sk"]}
    existing = get_item(client, destination_table, key)
    if existing is not None:
        if destination_matches(existing, target):
            return "already-copied"
        raise RuntimeError(f"destination conflict at {source['pk']['S']}/{source['sk']['S']}")
    names = {"#pk": "pk", "#sk": "sk"}
    values = {}
    predicates = ["attribute_exists(#pk)", "attribute_exists(#sk)"]
    for index, field in enumerate(FIELDS):
        name = f"#f{index}"
        names[name] = field
        if field in source:
            value = f":v{index}"
            values[value] = source[field]
            predicates.append(f"{name} = {value}")
        else:
            predicates.append(f"attribute_not_exists({name})")
    try:
        client.transact_write_items(TransactItems=[
            {"ConditionCheck": {
                "TableName": source_table,
                "Key": key,
                "ConditionExpression": " AND ".join(predicates),
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }},
            {"Put": {
                "TableName": destination_table,
                "Item": target,
                "ConditionExpression": "attribute_not_exists(#pk) AND attribute_not_exists(#sk)",
                "ExpressionAttributeNames": {"#pk": "pk", "#sk": "sk"},
            }},
        ])
    except Exception as error:
        existing = get_item(client, destination_table, key)
        if destination_matches(existing, target):
            return "already-copied"
        current_source = get_item(client, source_table, key)
        if current_source is None or any(current_source.get(field) != source.get(field) for field in FIELDS):
            raise RuntimeError(f"source changed during copy at {source['pk']['S']}/{source['sk']['S']}") from error
        if "ConditionalCheckFailed" in str(error) or "TransactionCanceled" in str(error):
            raise RuntimeError(f"destination conflict at {source['pk']['S']}/{source['sk']['S']}") from error
        raise
    if not destination_matches(get_item(client, destination_table, key), target):
        raise RuntimeError(f"destination verification failed at {source['pk']['S']}/{source['sk']['S']}")
    return "copied"


def cleanup_item(client, source, source_table, destination_table):
    key = {"pk": source["pk"], "sk": source["sk"]}
    target = get_item(client, destination_table, key)
    expected = migrated_item(source)
    if not destination_matches(target, expected):
        raise RuntimeError(f"destination incomplete or conflicting at {source['pk']['S']}/{source['sk']['S']}")
    present = [field for field in FIELDS if field in source]
    if not present:
        return "already-clean"
    names = {"#pk": "pk", "#sk": "sk"}
    values = {}
    predicates = ["attribute_exists(#pk)", "attribute_exists(#sk)"]
    for index, field in enumerate(FIELDS):
        name = f"#f{index}"
        names[name] = field
        if field in source:
            value = f":v{index}"
            values[value] = source[field]
            predicates.append(f"{name} = {value}")
        else:
            predicates.append(f"attribute_not_exists({name})")
    remove = ", ".join(f"#f{FIELDS.index(field)}" for field in present)
    try:
        client.transact_write_items(TransactItems=[
            {"ConditionCheck": {
                "TableName": destination_table,
                "Key": key,
                "ConditionExpression": " AND ".join(
                    ["attribute_exists(#pk)", "attribute_exists(#sk)"] + [
                        f"#f{index} = :v{index}" if field in expected else f"attribute_not_exists(#f{index})"
                        for index, field in enumerate(FIELDS)
                    ]
                ),
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": {f":v{index}": source[field] for index, field in enumerate(FIELDS) if field in source},
            }},
            {"Update": {
                "TableName": source_table,
                "Key": key,
                "UpdateExpression": f"REMOVE {remove}",
                "ConditionExpression": " AND ".join(predicates),
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }},
        ])
    except Exception as error:
        raise RuntimeError(f"cleanup condition failed at {source['pk']['S']}/{source['sk']['S']}; source retained") from error
    return "cleaned"


def main():
    parser = argparse.ArgumentParser(description="Move supplements from two if-health partitions to if-supplements.")
    parser.add_argument("action", choices=("copy", "cleanup"))
    parser.add_argument("--execute", action="store_true", help="perform writes; without this, print the planned actions")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--source-table", default=os.getenv("IF_HEALTH_TABLE_NAME", SOURCE_TABLE))
    parser.add_argument("--destination-table", default=os.getenv("IF_SUPPLEMENTS_TABLE_NAME", DESTINATION_TABLE))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "ca-central-1"))
    args = parser.parse_args()
    import boto3

    client = boto3.client("dynamodb", region_name=args.region)
    items = {partition: query_programs(client, args.source_table, partition) for partition in PARTITIONS}
    backup_path = args.backup or Path("backups") / f"supplements-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    backup(items, backup_path)
    print(f"Raw DynamoDB backup: {backup_path}")
    for partition, records in items.items():
        for source in records:
            fields = [field for field in FIELDS if field in source]
            if not fields:
                continue
            if args.execute:
                result = copy_item(client, source, args.source_table, args.destination_table) if args.action == "copy" else cleanup_item(client, source, args.source_table, args.destination_table)
            else:
                result = "would-copy" if args.action == "copy" else "would-cleanup"
            print(f"{partition}/{source['sk']['S']}: {result}")


if __name__ == "__main__":
    main()
