from contextvars import ContextVar

current_athlete = ContextVar('current_athlete', default=None)
