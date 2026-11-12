from .._common import access, athlete, execute, person, store


def handler(event, context):
    return execute(lambda: {"attachment": store().share(athlete(event), person(event), event, access(event))})
