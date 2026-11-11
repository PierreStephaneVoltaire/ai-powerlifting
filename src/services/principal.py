import os
import httpx


async def delegated_principal(parent: str, athlete: str, operation: str, destination: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(os.getenv('PL_SECURITY_URL', 'http://pl-security:8000').rstrip('/') + '/v1/principals',
            json={'principal': parent, 'athlete': athlete, 'operation': operation, 'destination': destination})
        response.raise_for_status()
        token = response.json().get('principal')
        if not isinstance(token, str) or not token:
            raise ValueError('Principal delegation failed')
        return token

