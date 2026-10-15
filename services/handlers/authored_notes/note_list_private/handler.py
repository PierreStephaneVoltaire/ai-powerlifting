from .._common import execute, person, store


def handler(event, context):
    return execute(lambda: store().list_private(person(event), event))
