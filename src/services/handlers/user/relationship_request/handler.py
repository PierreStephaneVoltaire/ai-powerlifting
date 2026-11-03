from .._relationship_handlers import request


def handler(event, context):
    return request(event)
