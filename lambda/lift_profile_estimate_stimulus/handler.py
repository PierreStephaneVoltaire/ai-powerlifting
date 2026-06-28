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


def lift_profile_estimate_stimulus(args):
    from lift_profile_ai import estimate_lift_profile_stimulus
    return _run_async(estimate_lift_profile_stimulus(args["profile"]))


def handler(event, context):
    args = event.get("args", event)
    result = lift_profile_estimate_stimulus(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}