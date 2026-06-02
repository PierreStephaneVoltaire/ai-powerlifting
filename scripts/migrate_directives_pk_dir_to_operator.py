
import argparse
import sys

import boto3
from boto3.dynamodb.conditions import Key

def migrate(table_name: str, region: str, dry_run: bool) -> None:
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    print(f"Scanning {table_name} for items with pk='DIR' in region {region}...")
    response = table.query(KeyConditionExpression=Key("pk").eq("DIR"))
    items = response.get("Items", [])

    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=Key("pk").eq("DIR"),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    print(f"Found {len(items)} items with pk='DIR'")

    if not items:
        print("Nothing to migrate.")
        return

    if dry_run:
        print(f"[DRY RUN] Would migrate {len(items)} items from pk='DIR' to pk='operator':")
        for item in items[:5]:
            print(f"  sk={item['sk']}, label={item.get('label', 'N/A')}")
        if len(items) > 5:
            print(f"  ... and {len(items) - 5} more")
        return

    migrated = 0
    errors = 0

    for item in items:
        sk = item["sk"]
        try:
            new_item = dict(item)
            new_item["pk"] = "operator"

            table.put_item(Item=new_item)
            table.delete_item(Key={"pk": "DIR", "sk": sk})
            migrated += 1

            if migrated % 20 == 0:
                print(f"  Migrated {migrated}/{len(items)}...")
        except Exception as e:
            errors += 1
            print(f"  ERROR on sk={sk}: {e}")

    print(f"\nDone. Migrated: {migrated}, Errors: {errors}")

    if errors > 0:
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate directive pk from DIR to operator")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--table", default="if-core", help="DynamoDB table name")
    parser.add_argument("--region", default="ca-central-1", help="AWS region")
    args = parser.parse_args()

    migrate(args.table, args.region, args.dry_run)
