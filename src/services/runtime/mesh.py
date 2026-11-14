BACKEND_ACCOUNT = 'powerlifting-app-backend'


def caller(value: str) -> str:
    return value.removeprefix('spiffe://')


def is_account(principal: str, account: str) -> bool:
    return principal.endswith('/sa/' + account)
