from ..common import arguments, response
from .core import import_parse_file


def handler(event, context):
    return response(import_parse_file(arguments(event)))
