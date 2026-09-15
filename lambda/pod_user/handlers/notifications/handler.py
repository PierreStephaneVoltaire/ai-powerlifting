from .._relationship_handlers import notifications


def handler(event, context):
    return notifications(event)
