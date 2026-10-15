from .._common import access, athlete, execute, store


def handler(event, context):
    return execute(lambda: store().list_attachments(athlete(event), event, access(event)))
