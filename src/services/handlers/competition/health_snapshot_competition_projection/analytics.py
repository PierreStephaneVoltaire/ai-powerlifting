from importlib import import_module

_implementation = import_module("services.handlers.analysis_reports.analytics")
globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith("__")})
