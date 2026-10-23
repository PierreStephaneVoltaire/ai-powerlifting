import argparse

import boto3
from boto3.dynamodb.conditions import Key

TABLES = [
    "if-health",
    "if-sessions",
    "if-health-templates",
    "if-user",
    "if-powerlifting-requests",
    "if-powerlifting-budget",
    "if-powerlifting-goals",
    "if-powerlifting-analysis-cache",
    "if-powerlifting-user-competitions",
    "if-powerlifting-user-federations",
    "if-powerlifting-notifications",
]


def partition_values(pk: str) -> list[str]:
    return [pk, f"Grant#{pk}"]


def table_items(table, partition_key: str, value: str):
    kwargs = {"KeyConditionExpression": Key(partition_key).eq(value), "ProjectionExpression": "#k0" + (", #k1" if len(table.key_schema) > 1 else "")}
    names = {f"#k{index}": key["AttributeName"] for index, key in enumerate(table.key_schema)}
    kwargs["ExpressionAttributeNames"] = names
    while True:
        response = table.query(**kwargs)
        yield from response.get("Items", [])
        if "LastEvaluatedKey" not in response:
            return
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pk", default="live-acceptance-luna")
    parser.add_argument("--region", default="ca-central-1")
    parser.add_argument("--tables", nargs="*", default=TABLES)
    parser.add_argument("--delete", action="store_true")
    args = parser.parse_args()

    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    total = 0
    for name in args.tables:
        table = dynamodb.Table(name)
        try:
            partition_key = next(key["AttributeName"] for key in table.key_schema if key["KeyType"] == "HASH")
        except dynamodb.meta.client.exceptions.ResourceNotFoundException:
            print(f"{name}: table not found, skipped")
            continue
        keys = [item for value in partition_values(args.pk) for item in table_items(table, partition_key, value)]
        total += len(keys)
        print(f"{name}: {len(keys)} items")
        if args.delete and keys:
            with table.batch_writer() as batch:
                for key in keys:
                    batch.delete_item(Key=key)
    print(f"{'deleted' if args.delete else 'would delete'} {total} items for {args.pk}")


if __name__ == "__main__":
    main()
