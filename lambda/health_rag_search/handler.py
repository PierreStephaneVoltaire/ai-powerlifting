import asyncio
import json

from rag import index_docs, query, rebuild


def handler(event, context):
    args = event.get("args", event)
    action = args.get("action", "search")
    if action == "search":
        q = args.get("query", "")
        n_results = int(args.get("n_results", 4))
        result = asyncio.run(query(q, n_results=n_results))
    elif action == "index":
        asyncio.run(index_docs())
        result = {"status": "indexed"}
    elif action == "rebuild":
        asyncio.run(rebuild())
        result = {"status": "rebuilt"}
    else:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"unknown action: {action}"}),
        }
    return {"statusCode": 200, "body": json.dumps(result, default=str)}