import json
import sys


def validate(plan):
    deletions = [
        resource["address"]
        for resource in plan.get("resource_changes", [])
        if resource.get("mode", "managed") == "managed"
        and resource["type"].startswith("aws_")
        and "delete" in resource["change"]["actions"]
    ]
    if deletions:
        raise ValueError("AWS resource deletion or replacement is forbidden: " + ", ".join(deletions))


if __name__ == "__main__":
    try:
        validate(json.load(sys.stdin))
    except (ValueError, KeyError, TypeError) as error:
        sys.exit(str(error))
