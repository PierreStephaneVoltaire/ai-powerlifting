import asyncio


def lift_profile_suggest(args):
    from services.lift_profiles.lift_profile_ai import suggest_options
    return asyncio.run(suggest_options(args["lift"], args.get("description", ""), args.get("profile")))
