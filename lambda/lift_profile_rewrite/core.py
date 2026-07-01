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


def lift_profile_rewrite(args):
    from lift_profile_ai import rewrite_lift_profile
    return _run_async(rewrite_lift_profile(args["profile"]))
