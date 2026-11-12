from .._common import execute, person, store


def handler(event, context):
    return execute(lambda: {"note": store().save_private(person(event), event)})
