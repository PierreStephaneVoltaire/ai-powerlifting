from ..common import arguments, response
from .core import import_list_pending


def handler(event, context):
    import asyncio

    return response(asyncio.run(import_list_pending(arguments(event))))
