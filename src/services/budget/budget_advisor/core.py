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


async def _dispatch(args):
    from .budget_advisor_ai import generate_budget_advisor
    payload = {
        "config": args.get("config") if isinstance(args.get("config"), dict) else {},
        "items": args.get("items") if isinstance(args.get("items"), list) else [],
        "competitions": args.get("competitions") if isinstance(args.get("competitions"), list) else [],
    }
    spent = args.get("spent_this_month")
    if isinstance(spent, (int, float)):
        payload["spent_this_month"] = float(spent)
    return await generate_budget_advisor(payload)


def budget_advisor(args):
    return _run_async(_dispatch(args))
