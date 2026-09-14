import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import quote


BACKEND = "http://127.0.0.1:13005"
FRONTEND = "http://127.0.0.1:13001"
GATEWAY = "http://192.168.2.56"
MEDIA_ORIGIN = "d2kntj88zo3vgy.cloudfront.net"
CANARY_HEADERS = {"Cookie": f"pl_auth={os.environ['PL_CANARY_COOKIE']}"} if os.environ.get("PL_CANARY_COOKIE") else {}


def request(base, path, method="GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{base}{path}", data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers.get_content_type(), response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get_content_type(), error.read()


def main():
    failures = []
    assert request(BACKEND, "/health")[0] == 200
    status, content_type, body = request(BACKEND, "/api/programs")
    assert status == 200 and content_type == "application/json"
    programs = json.loads(body).get("data")
    assert isinstance(programs, list) and programs
    version = programs[0]["sk"].split("#", 1)[-1]
    status, content_type, body = request(BACKEND, f"/api/programs/{quote(version)}")
    if status != 200 or content_type != "application/json":
        failures.append(f"program detail status={status}")
    else:
        program = json.loads(body).get("data")
        sessions = program.get("sessions") if isinstance(program, dict) else []
        if not sessions:
            failures.append("program detail returned no sessions")
        else:
            session = sessions[0]
            path = f"/api/sessions/{quote(version)}/{quote(session['date'])}/{sessions.index(session)}"
            status, content_type, body = request(BACKEND, path)
            if status != 200 or content_type != "application/json" or not isinstance(json.loads(body).get("data"), dict):
                failures.append(f"session detail status={status}")
    assert request(BACKEND, "/api/programs/v001/meta", "PUT", {})[0] == 401
    status, content_type, html = request(FRONTEND, "/")
    assert status == 200 and content_type == "text/html"
    assert b"manifest.webmanifest" in html and b"%CLOUDFRONT_DOMAIN%" not in html
    scripts = re.findall(rb'<script[^>]+src="([^"]+)', html)
    assets = [urllib.request.urlopen(f"{FRONTEND}{path.decode()}", timeout=10).read() for path in scripts]
    assert any(MEDIA_ORIGIN.encode() in asset for asset in assets)
    assert all(b"VITE_CLOUDFRONT_MEDIA_BASE_URL" not in asset for asset in assets)
    status, content_type, _ = request(FRONTEND, "/manifest.webmanifest")
    assert status == 200 and content_type == "application/manifest+json"
    status, content_type, _ = request(FRONTEND, "/sw.js")
    assert status == 200 and content_type in ("application/javascript", "text/javascript")
    status, content_type, _ = request(GATEWAY, "/", headers={"Host": "dev.nolift.training"})
    assert status == 200 and content_type == "text/html"
    status, content_type, body = request(GATEWAY, "/api/programs", headers={"Host": "dev.nolift.training"})
    assert status == 200 and content_type == "application/json" and isinstance(json.loads(body).get("data"), list)
    if CANARY_HEADERS:
        status, content_type, body = request(GATEWAY, "/api/programs/v020", headers={"Host": "dev.nolift.training", **CANARY_HEADERS})
        assert status == 200 and content_type == "application/json"
        sessions = json.loads(body)["data"].get("sessions") or []
        assert sessions
        session = sessions[0]
        path = f"/api/sessions/v020/{quote(session['date'])}/{sessions.index(session)}"
        status, content_type, _ = request(GATEWAY, path, headers={"Host": "dev.nolift.training", **CANARY_HEADERS})
        assert status == 200 and content_type == "application/json"
    if failures:
        print("gateway acceptance failures: " + ", ".join(failures))
        raise SystemExit(1)
    print("gateway acceptance passed: health, safe reads, write denial, PWA assets, media origin")


if __name__ == "__main__":
    main()
