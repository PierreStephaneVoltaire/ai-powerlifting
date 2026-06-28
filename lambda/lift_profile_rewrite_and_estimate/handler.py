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


def lift_profile_rewrite_and_estimate(args):
    from lift_profile_ai import rewrite_and_estimate_lift_profile
    return _run_async(rewrite_and_estimate_lift_profile(args["profile"]))


def handler(event, context):
    args = event.get("args", event)
    result = lift_profile_rewrite_and_estimate(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}