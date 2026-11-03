from .._relationship_handlers import revoke


def handler(event, context):
    return revoke(event)
