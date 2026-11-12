import asyncio
import logging
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from services.access import permission_map
from services.access_store import current_context
from services.authorization import check_context
from services.contract import load_operations
from services.dispatch import OperationError
from . import credentials


logger = logging.getLogger('pl-security')
app = FastAPI(title='Powerlifting security')
OPERATIONS = load_operations()
PSEUDO = {'domain_resume', 'generation_status', 'domain_job_read', 'domain_job_cancel', 'conversation_turn', 'conversation_reset'}


class IdentityRequest(BaseModel):
    id_token: str


class PrincipalRequest(BaseModel):
    identity_token: str = ''
    discord_subject: str = ''
    principal: str = ''
    capability: str = ''
    job_id: str = ''
    athlete: str = ''
    operation: str
    destination: str


class AccessRequest(BaseModel):
    principal: str
    operation: str
    arguments: dict = Field(default_factory=dict)
    destination: str


class JobCapabilityRequest(BaseModel):
    principal: str
    job_id: str


def caller(value):
    if not value:
        raise ValueError('Workload identity required')
    credentials.service_for(value)
    return credentials.workload(value)


def validate_target(operation, destination):
    if operation in OPERATIONS:
        if destination != 'pl-' + OPERATIONS[operation].domain and destination != 'pl-coach':
            raise ValueError('Operation destination mismatch')
        if operation not in permission_map():
            raise ValueError('Operation has no permission mapping')
    elif operation not in PSEUDO or destination != 'pl-coach' and operation not in {'domain_resume', 'generation_status'}:
        raise ValueError('Unknown operation')


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.post('/v1/identity')
async def identity(request: IdentityRequest, x_pl_mesh_caller: str = Header(default='')):
    try:
        source = caller(x_pl_mesh_caller)
        if credentials.service_for(source) != 'pl-backend':
            raise ValueError('Workload is not the gateway')
        return await asyncio.to_thread(credentials.resolve_identity, request.id_token)
    except Exception as exc:
        raise HTTPException(401, 'Identity verification failed') from exc


@app.post('/v1/principals')
async def principals(request: PrincipalRequest, x_pl_mesh_caller: str = Header(default='')):
    try:
        source = caller(x_pl_mesh_caller)
        source_service = credentials.service_for(source)
        credentials.allowed_edge(source, request.destination)
        validate_target(request.operation, request.destination)
        methods = sum(bool(value) for value in (request.identity_token, request.discord_subject, request.principal, request.capability))
        if methods > 1:
            raise ValueError('Conflicting credentials')
        if request.identity_token:
            if source_service != 'pl-backend':
                raise ValueError('OIDC identity is gateway-only')
            settings = await asyncio.to_thread(credentials.existing_identity, request.identity_token)
            person = str(settings['pk'])
            origin = source_service
        elif request.discord_subject:
            if source_service != 'pl-coach-discord':
                raise ValueError('Discord identity is bot-only')
            settings = await asyncio.to_thread(credentials.discord_identity, request.discord_subject)
            person = str(settings['pk'])
            origin = source_service
        elif request.capability:
            if source_service != 'pl-coach':
                raise ValueError('Job capabilities are Coach-only')
            job = credentials.verify_job(request.capability, request.job_id)
            children = credentials.mapping('PL_SECURITY_DELEGATION').get(job['operation'], [])
            if not isinstance(children, list) or any(not isinstance(name, str) for name in children) or credentials.delegation_hash(children) != job['delegation_hash']:
                raise ValueError('Job delegation changed')
            if request.athlete != job['athlete'] or request.operation != job['operation'] and request.operation not in children:
                raise ValueError('Job capability scope mismatch')
            person, origin = job['sub'], job['origin']
        elif request.principal:
            parent = credentials.verify(request.principal)
            if parent['destination'] != source_service or request.athlete != parent['athlete']:
                raise ValueError('Delegation scope mismatch')
            children = credentials.mapping('PL_SECURITY_DELEGATION').get(parent['operation'], [])
            if request.operation != parent['operation'] and (not isinstance(children, list) or request.operation not in children):
                raise ValueError('Delegated operation denied')
            person, origin = parent['sub'], parent['origin']
        else:
            if source_service != 'pl-backend':
                raise ValueError('Anonymous principal is gateway-only')
            person, origin = '', source_service
        return {'principal': credentials.sign(person, request.athlete, request.operation, source, request.destination, origin)}
    except Exception as exc:
        logger.warning('principal denied operation=%s destination=%s caller=%s reason=%s', request.operation, request.destination, x_pl_mesh_caller, exc)
        raise HTTPException(403, 'Principal issuance denied') from exc


@app.post('/v1/job-capabilities')
async def job_capabilities(request: JobCapabilityRequest, x_pl_mesh_caller: str = Header(default='')):
    try:
        source = caller(x_pl_mesh_caller)
        if credentials.service_for(source) != 'pl-coach' or not request.job_id or len(request.job_id) > 128:
            raise ValueError('Invalid job workload or ID')
        parent = credentials.verify(request.principal, destination='pl-coach')
        if not parent['sub']:
            raise ValueError('Anonymous jobs are forbidden')
        allowed = credentials.mapping('PL_SECURITY_DELEGATION').get(parent['operation'], [])
        if not isinstance(allowed, list) or any(not isinstance(name, str) for name in allowed):
            raise ValueError('Invalid job operation list')
        return {'capability': credentials.sign_job(parent, request.job_id, allowed)}
    except Exception as exc:
        raise HTTPException(403, 'Job capability issuance denied') from exc


@app.post('/v1/access')
async def access(request: AccessRequest, x_pl_mesh_caller: str = Header(default='')):
    try:
        source = caller(x_pl_mesh_caller)
        credentials.allowed_edge(source, request.destination)
        validate_target(request.operation, request.destination)
        claims = credentials.verify(request.principal, request.operation, source, request.destination)
        context = await asyncio.to_thread(current_context, claims['sub'], claims['athlete'])
        return {'claims': claims, 'context': check_context(request.operation, request.arguments, claims, context)}
    except OperationError as exc:
        raise HTTPException(exc.status, 'Access denied') from exc
    except Exception as exc:
        logger.warning('access denied reason=%s', exc)
        raise HTTPException(403, 'Access denied') from exc
