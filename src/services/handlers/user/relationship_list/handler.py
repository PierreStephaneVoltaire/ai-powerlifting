from .._relationship_handlers import list_all


def handler(event, context):
    return list_all(event)
