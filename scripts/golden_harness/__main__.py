import argparse
import os
import sys
from pathlib import Path

from . import safety, seed, topology
from .capture import Caller, Recorder, capture_analytics, capture_rankings, write_manifest

REPO = topology.REPO
BASE_ENV_KEYS = ("PATH", "HOME", "LANG", "USER", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "TMPDIR")


def main():
    parser = argparse.ArgumentParser(description="Offline golden harness: runs the pre-rewrite analytics and rankings code against moto and writes fixtures/operator/golden.")
    parser.add_argument("--baseline", required=True, help="path to the pre-rewrite git worktree (f11cbee6)")
    parser.add_argument("--venv", required=True, help="venv with baseline requirements, moto[server] and fakeredis")
    parser.add_argument("--logs", required=True)
    parser.add_argument("--as-of", default="2026-11-11")
    parser.add_argument("--poll-seconds", type=int, default=120)
    parser.add_argument("--skip-analytics", action="store_true")
    parser.add_argument("--skip-rankings", action="store_true")
    args = parser.parse_args()

    safety.apply_to_current_process(topology.MOTO_PORT)
    topology.require_free_ports()

    baseline = Path(args.baseline).resolve()
    venv = Path(args.venv).resolve()
    fixtures = REPO / "fixtures"
    source_dir = fixtures / "operator" / "source"
    golden_dir = fixtures / "operator" / "golden"
    opl_dir = fixtures / "opl"
    if not (source_dir / "if-health.json").is_file():
        raise SystemExit("run scripts/snapshot_operator_source.py first")

    program, sessions = seed.write_plain_source(source_dir)

    sys.path.insert(0, str(baseline / "src"))
    os.environ["PL_PRINCIPAL_SECRET"] = topology.PRINCIPAL_SECRET
    from services.principal import principal_token

    base = {key: os.environ[key] for key in BASE_ENV_KEYS if key in os.environ}
    env = safety.scrubbed_environment(base, topology.MOTO_PORT)
    gateway_url = f"http://127.0.0.1:{topology.GATEWAY_PORT}"
    valkey_url = f"redis://127.0.0.1:{topology.VALKEY_PORT}"
    shared = {
        "INTERNAL_API_TOKEN": topology.INTERNAL_TOKEN,
        "PL_PRINCIPAL_SECRET": topology.PRINCIPAL_SECRET,
        "HEALTH_PROGRAM_PK": topology.ATHLETE,
        "VALKEY_URL": valkey_url,
        "PL_PROFILE_URL": f"{gateway_url}/profile",
        "PYTHONPATH": f"{baseline / 'src'}:{REPO}",
        "PYTHONUNBUFFERED": "1",
    }
    fleet = topology.Fleet(args.logs)
    python = str(venv / "bin" / "python")
    try:
        fleet.start("moto", [str(venv / "bin" / "moto_server"), "-H", "127.0.0.1", "-p", str(topology.MOTO_PORT)], topology.child_env(env, {}), str(baseline))
        topology.wait_port(topology.MOTO_PORT)
        client = seed.moto_client(topology.MOTO_PORT)
        print("tables:", seed.create_tables(client, REPO / "terraform/modules/powerlifting_dynamodb/main.tf"))
        print("seeded:", seed.seed_tables(client, source_dir))

        fleet.start("valkey", [python, "-c", f"from fakeredis import TcpFakeServer; TcpFakeServer(('127.0.0.1', {topology.VALKEY_PORT})).serve_forever()"], topology.child_env(env, {}), str(baseline))
        topology.wait_port(topology.VALKEY_PORT)

        caller = Caller(topology.ATHLETE, topology.ATHLETE, principal_token, topology.INTERNAL_TOKEN, f"{gateway_url}/analytics", f"http://127.0.0.1:{topology.RANKINGS_PORT}")
        recorder = Recorder(caller, golden_dir, topology.ATHLETE)
        block_keys = []

        if not args.skip_analytics:
            gateway_env = topology.child_env(env, {**shared, "ANALYTICS_NODE_URL": f"http://127.0.0.1:{topology.SIDECAR_PORT}", "ANALYTICS_NODE_TOKEN": topology.INTERNAL_TOKEN})
            fleet.start("gateway", [python, "-m", "uvicorn", "scripts.golden_harness.gateway:app", "--host", "127.0.0.1", "--port", str(topology.GATEWAY_PORT)], gateway_env, str(baseline / "src"))
            sidecar_env = topology.child_env(env, {**shared, "ANALYTICS_NODE_PORT": str(topology.SIDECAR_PORT), "ANALYTICS_NODE_TOKEN": topology.INTERNAL_TOKEN, "POWERLIFTING_SERVICE_BASE_URL": gateway_url, "NODE_OPTIONS": "--max-old-space-size=2048"})
            fleet.start("sidecar", ["npx", "tsx", "src/analyticsSidecar.ts"], sidecar_env, str(baseline / "src" / "backend"))
            topology.wait_http(f"{gateway_url}/health")
            topology.wait_port(topology.SIDECAR_PORT)
            block_keys = capture_analytics(recorder, args.as_of, sessions, args.poll_seconds)

        if not args.skip_rankings:
            rankings_env = topology.child_env(env, {**shared, "PL_DOMAIN": "rankings", "SANDBOX_PATH": str(opl_dir)})
            fleet.start("rankings", [python, "-m", "uvicorn", "scripts.golden_harness.rankings_app:app", "--host", "127.0.0.1", "--port", str(topology.RANKINGS_PORT)], rankings_env, str(baseline / "src"))
            if args.skip_analytics:
                fleet.start("gateway", [python, "-m", "uvicorn", "scripts.golden_harness.gateway:app", "--host", "127.0.0.1", "--port", str(topology.GATEWAY_PORT)], topology.child_env(env, {**shared, "ANALYTICS_NODE_URL": f"http://127.0.0.1:{topology.SIDECAR_PORT}"}), str(baseline / "src"))
                topology.wait_http(f"{gateway_url}/health")
            topology.wait_http(f"http://127.0.0.1:{topology.RANKINGS_PORT}/health", timeout=900)
            capture_rankings(recorder)

        write_manifest(golden_dir, args.as_of, topology.ATHLETE, block_keys, recorder.calls, merge=args.skip_analytics or args.skip_rankings)
        failed = [call for call in recorder.calls if call["status"] != 200]
        print(f"golden files: {len(recorder.calls)}; non-200: {[(c['operation'], c['status']) for c in failed]}")
    finally:
        fleet.stop()


if __name__ == "__main__":
    main()
