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


def lift_profile_estimate_stimulus(args):
    from lift_profile_ai import estimate_lift_profile_stimulus
    return _run_async(estimate_lift_profile_stimulus(args["profile"]))
