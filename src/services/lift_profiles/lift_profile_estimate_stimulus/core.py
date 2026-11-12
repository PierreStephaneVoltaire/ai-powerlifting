import asyncio


def lift_profile_estimate_stimulus(args):
    from services.lift_profiles.lift_profile_ai import estimate_stimulus
    return asyncio.run(estimate_stimulus(args["profile"]))
