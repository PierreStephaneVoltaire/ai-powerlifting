from contextvars import ContextVar

current_athlete = ContextVar('current_athlete', default=None)
current_owner_aliases = ContextVar('current_owner_aliases', default=frozenset())
