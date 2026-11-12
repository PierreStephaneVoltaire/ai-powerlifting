import os
from urllib.parse import urlparse

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
DUMMY_ACCESS_KEY = "testing"
DUMMY_REGION = "ca-central-1"


def local_endpoint(port):
    return f"http://127.0.0.1:{port}"


def assert_local_endpoint():
    endpoint = os.environ.get("AWS_ENDPOINT_URL", "")
    host = urlparse(endpoint).hostname
    if host not in LOCAL_HOSTS:
        raise SystemExit(f"refusing to run: AWS_ENDPOINT_URL={endpoint!r} is not a local moto endpoint")
    if os.environ.get("AWS_ACCESS_KEY_ID") != DUMMY_ACCESS_KEY:
        raise SystemExit("refusing to run: AWS credentials are not the dummy test credentials")


def scrubbed_environment(base, moto_port):
    env = {key: value for key, value in base.items() if not key.startswith("AWS_") and key not in {"BOTO_CONFIG"}}
    endpoint = local_endpoint(moto_port)
    env.update(
        {
            "AWS_ACCESS_KEY_ID": DUMMY_ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": DUMMY_ACCESS_KEY,
            "AWS_DEFAULT_REGION": DUMMY_REGION,
            "AWS_REGION": DUMMY_REGION,
            "AWS_ENDPOINT_URL": endpoint,
            "AWS_ENDPOINT_URL_DYNAMODB": endpoint,
            "AWS_ENDPOINT_URL_S3": endpoint,
            "AWS_CONFIG_FILE": "/dev/null",
            "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
            "AWS_EC2_METADATA_DISABLED": "true",
        }
    )
    return env


def apply_to_current_process(moto_port):
    scrubbed = scrubbed_environment(os.environ, moto_port)
    os.environ.clear()
    os.environ.update(scrubbed)
    assert_local_endpoint()
