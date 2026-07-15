# pl-sessions Lambda Layer

DynamoDB domain layer for the **sessions** domain of the `if-sessions` table.

## Contents
- `python/session_store.py` — copied verbatim from `tools/health/session_store.py`. Contains `SessionStore`, the store module that reads/writes training session state in the `if-sessions` DynamoDB table.

## DynamoDB domain
- Table: `if-sessions`
- Domain: sessions (training session state).

This is a single-domain layer: it contains exactly one store module. It is NOT a monolith — sibling domains (programs, templates, glossary, imports, federation, analysis-cache) live in their own dedicated layers.

## Compatible runtimes
- `compatible_runtimes = ["python3.12"]`

## Attaching
Lambdas attach this layer alongside `pl-boto3`, which provides `boto3` / `botocore` / `s3transfer`. This layer itself has NO pip dependencies — `session_store.py` is pure Python that imports `boto3` at runtime from `/opt/python` (supplied by `pl-boto3`).

Cross-store lazy imports inside `session_store.py` are left as-is. Lambdas that trigger those code paths attach the additional domain layer; intra-package import fixing is the lambda's job, not this layer's.

## Build
```bash
bash utils/powerlifting-app/lambda/layers/pl-sessions/build.sh
```
Produces `pl-sessions.zip` (Lambda layer layout: `python/<modules>`). The build does NOT run `pip install` — it only stages and zips the verbatim `python/` directory.

## Terraform
```hcl
resource "aws_lambda_layer_version" "pl_sessions" {
  layer_name          = "pl-sessions"
  filename            = "${path.module}/../utils/powerlifting-app/lambda/layers/pl-sessions/pl-sessions.zip"
  compatible_runtimes = ["python3.12"]
}
```

## Rules
- Copy store modules VERBATIM. Do not edit imports or refactor.
- No `httpx`, `openrouter`, `OPENROUTER_API_KEY`, `chromadb`, or any `*_ai` module in this layer.
- Only `session_store.py` belongs here — one domain, one store module.