from .._relationship_handlers import notifications_read


def handler(event, context):
    return notifications_read(event)
