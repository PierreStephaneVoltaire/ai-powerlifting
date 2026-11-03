import asyncio


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
