import json
import re
from urllib.parse import urlsplit

from envoy.config.core.v3 import base_pb2
from envoy.service.auth.v3 import external_auth_pb2, external_auth_pb2_grpc
from google.rpc import code_pb2, status_pb2

from services.access_store import current_context
from services.authorization import check_context
from . import credentials
from .app import OPERATIONS


MAX_BODY = 10 * 1024 * 1024


def deny(status=403):
    return external_auth_pb2.CheckResponse(status=status_pb2.Status(code=code_pb2.PERMISSION_DENIED), denied_response=external_auth_pb2.DeniedHttpResponse(status={'code': status}, body='Authorization denied'))


def allow(destination, headers):
    headers['x-pl-authorized-destination'] = destination
    return external_auth_pb2.CheckResponse(status=status_pb2.Status(code=code_pb2.OK), ok_response=external_auth_pb2.OkHttpResponse(
        headers=[base_pb2.HeaderValueOption(header=base_pb2.HeaderValue(key=key, value=value), append_action=base_pb2.HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD) for key, value in headers.items()]))


def envelope(http):
    headers = {key.lower(): value for key, value in http.headers.items()}
    raw = http.raw_body or http.body.encode()
    if headers.get('x-envoy-auth-partial-body', '').lower() == 'true' or len(raw) > MAX_BODY:
        raise OverflowError('Body too large')
    length = headers.get('content-length')
    if length:
        if not length.isdecimal():
            raise ValueError('Invalid length')
        if int(length) > MAX_BODY:
            raise OverflowError('Body too large')
        if int(length) != len(raw):
            raise ValueError('Incomplete body')
    return headers, raw


def operation_for(destination, method, path, raw):
    if destination == 'pl-coach':
        if path.endswith('/turns') and method == 'POST':
            return 'conversation_turn', {}
        if '/conversations/' in path and method == 'DELETE':
            return 'conversation_reset', {}
        if path == '/v1/jobs' and method == 'POST':
            body = json.loads(raw)
            payload = body.get('payload', {})
            return payload.get('operation', ''), payload.get('arguments', {})
        if path.startswith('/v1/jobs/'):
            return ('domain_job_cancel' if path.endswith('/cancel') and method == 'POST' else 'domain_job_read'), {}
        raise ValueError('Unsupported Coach path')
    if path.startswith('/operations/') and method == 'POST':
        name = path.removeprefix('/operations/')
        operation = OPERATIONS.get(name)
        if not operation or destination != 'pl-' + operation.domain:
            raise ValueError('Unknown operation')
        arguments = json.loads(raw)
        if not isinstance(arguments, dict):
            raise ValueError('Invalid arguments')
        return name, arguments
    if path.startswith('/executions/') and method == 'POST':
        if not isinstance(json.loads(raw), dict):
            raise ValueError('Invalid continuation')
        return 'domain_resume', {}
    if path.startswith('/generations/') and method == 'GET':
        return 'generation_status', {}
    if path == '/mcp' and method == 'POST':
        body = json.loads(raw)
        if not isinstance(body, dict) or body.get('jsonrpc') != '2.0' or not isinstance(body.get('method'), str):
            raise ValueError('Invalid MCP envelope')
        rpc = body['method']
        if rpc == 'notifications/initialized' and 'id' not in body:
            return '', {}
        if rpc in {'initialize', 'ping', 'tools/list'} and 'id' in body:
            return '', {}
        if rpc != 'tools/call' or 'id' not in body or not isinstance(body.get('params'), dict):
            raise ValueError('Unsupported MCP method')
        params = body['params']
        name, arguments = params.get('name'), params.get('arguments', {})
        if name not in OPERATIONS or destination != 'pl-' + OPERATIONS[name].domain or not isinstance(arguments, dict):
            raise ValueError('Unknown MCP tool')
        return name, arguments
    raise ValueError('Unsupported path')


def control_destination(http):
    authority = http.host.lower()
    parsed = urlsplit('//' + authority)
    if not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('Invalid authority')
    destination = credentials.mapping('PL_SECURITY_AUTHORITIES').get(parsed.hostname)
    if not isinstance(destination, str) or not destination.startswith('pl-'):
        raise ValueError('Unknown authority')
    return destination


class Authorization(external_auth_pb2_grpc.AuthorizationServicer):
    def Check(self, request, context):
        try:
            attributes = request.attributes
            http = attributes.request.http
            headers, raw = envelope(http)
            source = credentials.workload(headers.get('x-pl-source-principal') or attributes.source.principal)
            source_service = credentials.service_for(source)
            path = urlsplit(http.path).path
            if http.method == 'POST' and path in {'/v1/identity', '/v1/principals', '/v1/access', '/v1/job-capabilities'}:
                destination = 'pl-security'
                credentials.allowed_edge(source, destination)
                return allow(destination, {'x-pl-mesh-caller': source})
            if path == '/v1/servers' or path.startswith('/v1/servers/'):
                destination = 'pl-coach-discord'
                credentials.allowed_edge(source, destination)
                if source_service != 'pl-backend' or not ((path == '/v1/servers' and http.method in {'POST', 'GET'}) or (re.fullmatch(r'/v1/servers/[^/]+', path) and http.method == 'DELETE') or (re.fullmatch(r'/v1/servers/[^/]+/restart', path) and http.method == 'POST')):
                    raise ValueError('Unsupported Discord management endpoint')
                return allow(destination, {'x-pl-access-context': json.dumps({'workload': source}, separators=(',', ':'))})
            body = json.loads(raw) if path == '/mcp' and http.method == 'POST' else None
            control = isinstance(body, dict) and body.get('method') in {'initialize', 'ping', 'tools/list', 'notifications/initialized'}
            if control:
                destination = control_destination(http)
                claims = None
            else:
                claims = credentials.verify(headers.get('x-pl-principal', ''), caller=source)
                destination = claims['destination']
            credentials.allowed_edge(source, destination)
            operation, arguments = operation_for(destination, http.method, path, raw)
            if not operation:
                return allow(destination, {'x-pl-access-context': '{}'})
            if claims is None or claims['operation'] != operation:
                raise ValueError('Principal scope mismatch')
            if headers.get('x-person-pk') and headers['x-person-pk'] != claims['sub'] or headers.get('x-athlete-pk') and headers['x-athlete-pk'] != claims['athlete']:
                raise ValueError('Header scope mismatch')
            access = current_context(claims['sub'], claims['athlete'])
            if operation in {'conversation_turn', 'conversation_reset', 'domain_job_read', 'domain_job_cancel', 'domain_resume'}:
                if not claims['sub']:
                    raise ValueError('Authenticated Person required')
            else:
                check_context(operation, arguments, claims, access)
            value = json.dumps({'person': claims['sub'], 'athlete': claims['athlete'], 'operation': operation, 'context': access}, separators=(',', ':'), ensure_ascii=True)
            return allow(destination, {'x-pl-access-context': value})
        except OverflowError:
            return deny(413)
        except Exception:
            return deny()
