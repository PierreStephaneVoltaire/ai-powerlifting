from ..common import arguments, response
from .core import import_get_pending


def handler(event, context):
    import asyncio

    return response(asyncio.run(import_get_pending(arguments(event))))
