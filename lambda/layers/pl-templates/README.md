# pl-templates Lambda Layer

DynamoDB domain layer for the **templates** domain of the `if-health-templates` table.

## Contents
- `python/template_store.py` — copied verbatim from `tools/health/template_store.py`. Contains `TemplateStore`, the store module that reads/writes reusable training program templates in the `if-health-templates` DynamoDB table.

## DynamoDB domain
- Table: `if-health-templates`
- Domain: templates (reusable training program template CRUD).

This is a single-domain layer: it contains exactly one store module. It is NOT a monolith — sibling domains (programs, sessions, glossary, imports, federation, analysis-cache) live in their own dedicated layers.

## Compatible runtimes
- `compatible_runtimes = ["python3.12"]`

## Attaching
Lambdas attach this layer alongside `pl-boto3`, which provides `boto3` / `botocore` / `s3transfer`. This layer itself has NO pip dependencies — `template_store.py` is pure Python that imports `boto3` at runtime from `/opt/python` (supplied by `pl-boto3`).

Cross-store lazy imports inside `template_store.py` are left as-is. Lambdas that trigger those code paths attach the additional domain layer; intra-package import fixing is the lambda's job, not this layer's.

## Build
```bash
bash utils/powerlifting-app/lambda/layers/pl-templates/build.sh
```
Produces `pl-templates.zip` (Lambda layer layout: `python/<modules>`). The build does NOT run `pip install` — it only stages and zips the verbatim `python/` directory.

## Terraform
```hcl
resource "aws_lambda_layer_version" "pl_templates" {
  layer_name          = "pl-templates"
  filename            = "${path.module}/../utils/powerlifting-app/lambda/layers/pl-templates/pl-templates.zip"
  compatible_runtimes = ["python3.12"]
}
```

## Rules
- Copy store modules VERBATIM. Do not edit imports or refactor.
- No `httpx`, `openrouter`, `OPENROUTER_API_KEY`, `chromadb`, or any `*_ai` module in this layer.
- Only `template_store.py` belongs here — one domain, one store module.