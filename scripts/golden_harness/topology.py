import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MEMORY_GUARD = ["systemd-run", "--user", "--scope", "-p", "MemoryMax=5G", "-p", "MemorySwapMax=0", "--quiet", "--"]

MOTO_PORT = 18500
VALKEY_PORT = 18501
GATEWAY_PORT = 18502
RANKINGS_PORT = 18503
SIDECAR_PORT = 18091

INTERNAL_TOKEN = "golden-harness-internal-token"
PRINCIPAL_SECRET = "golden-harness-principal-secret-0123456789abcdef"
ATHLETE = "operator"


class Fleet:
    def __init__(self, log_dir):
        self.processes = []
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def start(self, name, command, env, cwd):
        log = open(self.log_dir / f"{name}.log", "wb")
        process = subprocess.Popen(MEMORY_GUARD + command, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append((name, process))
        return process

    def stop(self):
        for _, process in reversed(self.processes):
            self._signal(process, signal.SIGTERM)
        for _, process in reversed(self.processes):
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._signal(process, signal.SIGKILL)

    @staticmethod
    def _signal(process, number):
        try:
            os.killpg(process.pid, number)
        except ProcessLookupError:
            pass


def port_free(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def require_free_ports():
    busy = [port for port in (MOTO_PORT, VALKEY_PORT, GATEWAY_PORT, RANKINGS_PORT, SIDECAR_PORT) if not port_free(port)]
    if busy:
        raise SystemExit(f"ports already in use: {busy}")


def wait_http(url, timeout=300, ok=(200,)):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status in ok:
                    return
        except Exception:
            time.sleep(1)
    raise SystemExit(f"timed out waiting for {url}")


def wait_port(port, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_free(port):
            return
        time.sleep(0.5)
    raise SystemExit(f"timed out waiting for port {port}")


def python():
    return sys.executable


def child_env(base, extra):
    env = dict(base)
    env.update(extra)
    return env
