import asyncio, json
from .core import import_apply
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(import_apply(args["import_id"], args.get("merge_strategy","append"), args.get("conflict_resolutions"), args.get("start_date"), args.get("actor_pk") or args.get("pk"), args.get("author")))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
