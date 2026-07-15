# pl-glossary Lambda Layer

DynamoDB domain layer for the **glossary** domain of the `if-health` table.

## Contents
- `python/glossary_store.py` — copied verbatim from `tools/health/glossary_store.py`. Contains `GlossaryStore`, the store module that reads/writes glossary items in the `if-health` DynamoDB table.

## DynamoDB domain
- Table: `if-health`
- Domain: glossary items (training glossary term CRUD).

This is a single-domain layer: it contains exactly one store module. It is NOT a monolith — sibling domains (programs, sessions, templates, imports, federation, analysis-cache) live in their own dedicated layers.

## Compatible runtimes
- `compatible_runtimes = ["python3.12"]`

## Attaching
Lambdas attach this layer alongside `pl-boto3`, which provides `boto3` / `botocore` / `s3transfer`. This layer itself has NO pip dependencies — `glossary_store.py` is pure Python that imports `boto3` at runtime from `/opt/python` (supplied by `pl-boto3`).

Cross-store lazy imports inside `glossary_store.py` are left as-is. Lambdas that trigger those code paths attach the additional domain layer; intra-package import fixing is the lambda's job, not this layer's.

## Build
```bash
bash utils/powerlifting-app/lambda/layers/pl-glossary/build.sh
```
Produces `pl-glossary.zip` (Lambda layer layout: `python/<modules>`). The build does NOT run `pip install` — it only stages and zips the verbatim `python/` directory.

## Terraform
```hcl
resource "aws_lambda_layer_version" "pl_glossary" {
  layer_name          = "pl-glossary"
  filename            = "${path.module}/../utils/powerlifting-app/lambda/layers/pl-glossary/pl-glossary.zip"
  compatible_runtimes = ["python3.12"]
}
```

## Rules
- Copy store modules VERBATIM. Do not edit imports or refactor.
- No `httpx`, `openrouter`, `OPENROUTER_API_KEY`, `chromadb`, or any `*_ai` module in this layer.
- Only `glossary_store.py` belongs here — one domain, one store module.