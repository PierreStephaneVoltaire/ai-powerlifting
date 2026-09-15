from .._common import access, athlete, execute, store


def handler(event, context):
    return execute(lambda: store().detach(athlete(event), event, access(event)))
