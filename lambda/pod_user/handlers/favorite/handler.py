from .._relationship_handlers import favorite_item


def handler(event, context):
    return favorite_item(event)
