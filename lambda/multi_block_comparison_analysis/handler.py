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


def multi_block_comparison_analysis(args):
    from multi_block_comparison_ai import generate_multi_block_comparison_report

    payload = args.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    return _run_async(generate_multi_block_comparison_report(payload))


def handler(event, context):
    args = event.get("args", event)
    result = multi_block_comparison_analysis(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}