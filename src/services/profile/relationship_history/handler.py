from .._relationship_handlers import history


def handler(event, context):
    return history(event)
