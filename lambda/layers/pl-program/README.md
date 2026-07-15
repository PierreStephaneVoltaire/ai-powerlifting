# pl-program Lambda Layer

DynamoDB domain layer for the **programs** domain of the `if-health` table.

## Contents
- `python/program_store.py` — copied verbatim from `tools/health/program_store.py`. Contains `ProgramStore`, the store module that reads/writes program rows in the `if-health` DynamoDB table.

## DynamoDB domain
- Table: `if-health`
- Domain: programs (training program CRUD).

This is a single-domain layer: it contains exactly one store module. It is NOT a monolith — sibling domains (sessions, templates, glossary, imports, federation, analysis-cache) live in their own dedicated layers.

## Compatible runtimes
- `compatible_runtimes = ["python3.12"]`

## Attaching
Lambdas attach this layer alongside `pl-boto3`, which provides `boto3` / `botocore` / `s3transfer`. This layer itself has NO pip dependencies — `program_store.py` is pure Python that imports `boto3` at runtime from `/opt/python` (supplied by `pl-boto3`).

Cross-store lazy imports inside `program_store.py` (e.g. `from session_store import SessionStore`) are left as-is. Lambdas that trigger those code paths attach the additional domain layer; intra-package import fixing is the lambda's job, not this layer's.

## Build
```bash
bash utils/powerlifting-app/lambda/layers/pl-program/build.sh
```
Produces `pl-program.zip` (Lambda layer layout: `python/<modules>`). The build does NOT run `pip install` — it only stages and zips the verbatim `python/` directory.

## Terraform
```hcl
resource "aws_lambda_layer_version" "pl_program" {
  layer_name          = "pl-program"
  filename            = "${path.module}/../utils/powerlifting-app/lambda/layers/pl-program/pl-program.zip"
  compatible_runtimes = ["python3.12"]
}
```

## Rules
- Copy store modules VERBATIM. Do not edit imports or refactor.
- No `httpx`, `openrouter`, `OPENROUTER_API_KEY`, `chromadb`, or any `*_ai` module in this layer.
- Only `program_store.py` belongs here — one domain, one store module.