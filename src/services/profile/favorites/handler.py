from .._relationship_handlers import favorites


def handler(event, context):
    return favorites(event)
