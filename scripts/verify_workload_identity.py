#!/usr/bin/env python3
"""Check Kubernetes projected-token trust against AWS STS without logging JWTs."""

import argparse
import subprocess
import sys


def run(command):
    return subprocess.run(command, text=True, capture_output=True, check=False)


def token(namespace, service_account, audience):
    result = run(
        [
            "kubectl",
            "-n",
            namespace,
            "create",
            "token",
            service_account,
            "--audience",
            audience,
            "--duration=10m",
        ]
    )
    if result.returncode:
        raise RuntimeError(f"TokenRequest failed for {namespace}/{service_account}; check API connectivity and RBAC")
    value = result.stdout.strip()
    if not value or any(char.isspace() for char in value):
        raise RuntimeError("TokenRequest returned an invalid token")
    return value


def assume(role_arn, jwt, region):
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    from botocore.exceptions import ClientError

    client = boto3.client("sts", region_name=region, config=Config(signature_version=UNSIGNED))
    try:
        return client.assume_role_with_web_identity(
            RoleArn=role_arn,
            RoleSessionName="workload-identity-check",
            WebIdentityToken=jwt,
        ), None
    except ClientError as error:
        details = error.response.get("Error", {})
        return None, (details.get("Code", ""), details.get("Message", ""))
    except Exception as error:
        raise RuntimeError("STS request failed; check AWS connectivity and issuer/JWKS availability") from None


def expected_denial(code, message, wrong_audience=False):
    if wrong_audience:
        return code == "InvalidIdentityToken" and "audience" in message.lower()
    if code in {"AccessDenied", "AccessDeniedException"}:
        return True
    return False


def check_allowed(role_arn, jwt, region, expected_account):
    result, error = assume(role_arn, jwt, region)
    if error:
        if expected_denial(*error):
            raise RuntimeError("Expected role assumption was denied; verify issuer, JWKS, audience, and exact subject trust")
        raise RuntimeError("STS request failed; check AWS connectivity and issuer/JWKS availability")
    credentials = result["Credentials"]
    import boto3

    session = boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )
    try:
        arn = session.client("sts", region_name=region).get_caller_identity()["Arn"]
    except Exception:
        raise RuntimeError("Assumed credentials could not call GetCallerIdentity") from None
    if not arn.startswith(f"arn:aws:sts::{expected_account}:assumed-role/{role_arn.rsplit('/', 1)[-1]}/"):
        raise RuntimeError("STS returned an unexpected account or role ARN")


def check_denied(role_arn, jwt, region, label, wrong_audience=False):
    result, error = assume(role_arn, jwt, region)
    if error is None:
        raise RuntimeError(f"Negative check unexpectedly assumed role: {label}")
    if not expected_denial(*error, wrong_audience=wrong_audience):
        raise RuntimeError(f"Negative check had a transport or issuer error, not an authorization denial: {label}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="powerlifting")
    parser.add_argument("--region", default="ca-central-1")
    parser.add_argument("--account-id")
    parser.add_argument("--service-account", required=True)
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--unrelated-service-account", default="default")
    parser.add_argument("--other-role-arn")
    parser.add_argument("--other-service-account")
    args = parser.parse_args()
    if bool(args.other_role_arn) != bool(args.other_service_account):
        parser.error("--other-role-arn and --other-service-account must be supplied together")
    if args.service_account == args.unrelated_service_account:
        parser.error("--unrelated-service-account must differ from --service-account")
    account = args.account_id
    if not account:
        import boto3

        try:
            account = boto3.client("sts", region_name=args.region).get_caller_identity()["Account"]
        except Exception:
            raise RuntimeError("Unable to derive AWS account ID; pass --account-id or check AWS credentials") from None

    valid = token(args.namespace, args.service_account, "sts.amazonaws.com")
    check_allowed(args.role_arn, valid, args.region, account)
    wrong_audience = token(args.namespace, args.service_account, "workload-identity-negative-test")
    check_denied(args.role_arn, wrong_audience, args.region, "wrong audience", wrong_audience=True)
    unrelated = token(args.namespace, args.unrelated_service_account, "sts.amazonaws.com")
    check_denied(args.role_arn, unrelated, args.region, "unrelated service account")
    if args.other_role_arn:
        other_role_token = token(args.namespace, args.other_service_account, "sts.amazonaws.com")
        check_allowed(args.other_role_arn, other_role_token, args.region, account)
        check_denied(args.other_role_arn, valid, args.region, "cross-role service-account trust")
    print("Workload identity allow and deny checks passed.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
