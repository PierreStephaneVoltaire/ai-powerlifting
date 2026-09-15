import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from botocore.exceptions import ClientError
from services.access_store import database, pages
from services.tag_catalog import catalog, selected_tags, table


def main():
    parser = argparse.ArgumentParser(description='Register legacy profile tag names as pending global vocabulary without changing profiles.')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    names = {tag['tag'] for person in pages(database().Table('if-user'), 'scan', ConsistentRead=True) for tag in selected_tags(person.get('tags'), {})}
    known = catalog()
    for name in sorted(names - known.keys()):
        print(('Registering pending: ' if args.apply else 'Would register pending: ') + name)
        if args.apply:
            try:
                table().put_item(Item={'pk': 'Catalog', 'sk': 'Tag#' + name, 'tag': name, 'status': 'pending', 'revision': 1, 'source': 'legacy_association', 'created_at': datetime.now(timezone.utc).isoformat()}, ConditionExpression='attribute_not_exists(pk)')
            except ClientError as exc:
                if exc.response['Error']['Code'] != 'ConditionalCheckFailedException':
                    raise


if __name__ == '__main__':
    main()
