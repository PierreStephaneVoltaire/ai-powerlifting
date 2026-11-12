from .._relationship_handlers import respond


def handler(event, context):
    return respond(event)
