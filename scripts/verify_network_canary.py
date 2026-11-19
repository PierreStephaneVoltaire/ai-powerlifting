import argparse
import ipaddress
import re
import subprocess
import sys
from urllib.parse import urlparse


def curl(namespace, pod, container, url, options=()):
    command = ["kubectl", "-n", namespace, "exec", pod]
    if container:
        command += ["-c", container]
    command += ["--", "curl", "--silent", "--show-error", "--max-time", "10", "--output", "/dev/null", "--write-out", "%{http_code}", *options, url]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    remote_exit = re.search(r"command terminated with exit code (\d+)", result.stderr)
    return (int(remote_exit.group(1)) if remote_exit else result.returncode), result.stdout.strip()


def blocked(result):
    return result[0] in {7, 28, 52, 56}


def ingress_blocked(result):
    return blocked(result) or result == (0, "403")


def main():
    parser = argparse.ArgumentParser(description="Check an already isolated canary from existing curl-capable containers.")
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--canary-pod", required=True)
    parser.add_argument("--canary-container")
    parser.add_argument("--authorized-pod", required=True)
    parser.add_argument("--authorized-container")
    parser.add_argument("--unauthorized-pod", required=True)
    parser.add_argument("--unauthorized-container")
    parser.add_argument("--allowed-url", required=True)
    parser.add_argument("--allowed-status", required=True)
    parser.add_argument("--unknown-url", required=True)
    parser.add_argument("--public-ip", type=ipaddress.IPv4Address, required=True, help="Public HTTPS IP independently verified reachable without isolation")
    parser.add_argument("--ingress-url", required=True, help="Canary service health URL")
    parser.add_argument("--ingress-status", default="200")
    args = parser.parse_args()
    parsed = urlparse(args.allowed_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443):
        parser.error("--allowed-url must be HTTPS on port 443")
    if not args.public_ip.is_global:
        parser.error("--public-ip must be a globally routable IPv4 address")
    unknown = urlparse(args.unknown_url)
    if unknown.scheme != "https" or not unknown.hostname or unknown.hostname == parsed.hostname:
        parser.error("--unknown-url must be HTTPS on a different hostname")
    if not re.fullmatch(r"[1-5][0-9]{2}", args.allowed_status) or args.allowed_status == "403":
        parser.error("--allowed-status must be an HTTP status that distinguishes the upstream response from a waypoint denial")
    checks = [
        ("allowed external host", curl(args.namespace, args.canary_pod, args.canary_container, args.allowed_url), lambda result: result == (0, args.allowed_status)),
        ("unknown external host", curl(args.namespace, args.canary_pod, args.canary_container, args.unknown_url), blocked),
        ("raw public IP", curl(args.namespace, args.canary_pod, args.canary_container, f"https://{args.public_ip}/", ["--insecure"]), blocked),
        ("allowed authority at unrelated IP", curl(args.namespace, args.canary_pod, args.canary_container, args.allowed_url, ["--insecure", "--resolve", f"{parsed.hostname}:443:{args.public_ip}"]), blocked),
        ("authorized ingress", curl(args.namespace, args.authorized_pod, args.authorized_container, args.ingress_url), lambda result: result == (0, args.ingress_status)),
        ("unauthorized ingress", curl(args.namespace, args.unauthorized_pod, args.unauthorized_container, args.ingress_url), ingress_blocked),
    ]
    for name, result, predicate in checks:
        print(f"{'PASS' if predicate(result) else 'FAIL'} {name}: curl exit={result[0]}, HTTP={result[1] or 'none'}")
    return 0 if all(predicate(result) for _, result, predicate in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
