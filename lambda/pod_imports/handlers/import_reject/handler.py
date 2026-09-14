from ..common import arguments, response
from .core import import_reject


def handler(event, context):
    import asyncio

    return response(asyncio.run(import_reject(arguments(event))))
