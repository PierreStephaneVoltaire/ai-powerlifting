from importlib import import_module

_implementation = import_module("lambda.get_analysis_markdown.export")
globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith("__")})
