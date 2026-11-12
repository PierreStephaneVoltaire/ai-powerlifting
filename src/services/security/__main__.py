from concurrent import futures

import grpc
import uvicorn
from envoy.service.auth.v3 import external_auth_pb2_grpc

from .app import app
from .ext_authz import Authorization, MAX_BODY


def main():
    with futures.ThreadPoolExecutor(max_workers=16) as executor:
        server = grpc.server(executor, options=[('grpc.max_receive_message_length', MAX_BODY + 1024 * 1024)])
        external_auth_pb2_grpc.add_AuthorizationServicer_to_server(Authorization(), server)
        if not server.add_insecure_port('[::]:9000'):
            raise RuntimeError('Could not bind ext_authz port')
        server.start()
        try:
            uvicorn.run(app, host='0.0.0.0', port=8000)
        finally:
            server.stop(5).wait()


if __name__ == '__main__':
    main()
