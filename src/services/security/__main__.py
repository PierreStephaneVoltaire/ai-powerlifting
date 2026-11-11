import json
import os
from concurrent import futures

import grpc
import uvicorn
from envoy.service.auth.v3 import external_auth_pb2_grpc

from .app import app
from .ext_authz import Authorization, MAX_BODY


def main():
    destinations = json.loads(os.environ['PL_SECURITY_DESTINATIONS'])
    if not isinstance(destinations, dict) or not destinations or len(set(destinations.values())) != len(destinations):
        raise ValueError('Invalid security listener configuration')
    servers = []
    for destination, port in destinations.items():
        if not isinstance(destination, str) or not destination.startswith('pl-') or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError('Invalid security listener')
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=16), options=[('grpc.max_receive_message_length', MAX_BODY + 1024 * 1024)])
        external_auth_pb2_grpc.add_AuthorizationServicer_to_server(Authorization(destination), server)
        if not server.add_insecure_port(f'[::]:{port}'):
            raise RuntimeError('Could not bind ext_authz port')
        servers.append(server)
    for server in servers:
        server.start()
    try:
        uvicorn.run(app, host='0.0.0.0', port=8000)
    finally:
        for server in servers:
            server.stop(5).wait()


if __name__ == '__main__':
    main()
