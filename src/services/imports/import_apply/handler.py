from ..common import arguments, response
from .core import import_apply


def handler(event, context):
    import asyncio

    return response(asyncio.run(import_apply(arguments(event))))
