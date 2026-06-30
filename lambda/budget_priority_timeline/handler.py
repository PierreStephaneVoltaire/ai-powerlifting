import asyncio
import json


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


async def _dispatch(args):
    from .budget_timeline_ai import generate_budget_timeline
    payload = {
        "config": args.get("config") if isinstance(args.get("config"), dict) else {},
        "items": args.get("items") if isinstance(args.get("items"), list) else [],
        "competitions": args.get("competitions") if isinstance(args.get("competitions"), list) else [],
        "federation_memberships": args.get("federation_memberships") if isinstance(args.get("federation_memberships"), list) else [],
    }
    return await generate_budget_timeline(payload)


def handler(event, context):
    args = event.get("args", event)
    result = _run_async(_dispatch(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}