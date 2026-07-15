# pl-analysis-cache Lambda Layer

DynamoDB domain layer for the **analysis cache** domain of the `if-powerlifting-analysis-cache` table.

## Contents
- `python/analysis_cache.py` — copied verbatim from `tools/health/analysis_cache.py`. The store module that reads/writes cached powerlifting weekly analyses in the `if-powerlifting-analysis-cache` DynamoDB table.
- `python/cache_invalidation.py` — copied verbatim from `tools/health/cache_invalidation.py`. A tiny cross-cutting util that operates on the analysis-cache table (cache invalidation). It is bundled in this layer to keep it within the single analysis-cache domain rather than spawning its own layer.

## DynamoDB domain
- Table: `if-powerlifting-analysis-cache`
- Domain: analysis cache (cached weekly analyses + cache invalidation).

This is a single-domain layer: it contains the analysis-cache store plus its tightly-coupled invalidation util. It is NOT a monolith — sibling domains (programs, sessions, templates, glossary, imports, federation) live in their own dedicated layers.

## Compatible runtimes
- `compatible_runtimes = ["python3.12"]`

## Attaching
Lambdas attach this layer alongside `pl-boto3`, which provides `boto3` / `botocore` / `s3transfer`. This layer itself has NO pip dependencies — `analysis_cache.py` and `cache_invalidation.py` are pure Python that import `boto3` at runtime from `/opt/python` (supplied by `pl-boto3`).

Cross-store lazy imports inside the copied modules are left as-is. Lambdas that trigger those code paths attach the additional domain layer; intra-package import fixing is the lambda's job, not this layer's.

## Build
```bash
bash utils/powerlifting-app/lambda/layers/pl-analysis-cache/build.sh
```
Produces `pl-analysis-cache.zip` (Lambda layer layout: `python/<modules>`). The build does NOT run `pip install` — it only stages and zips the verbatim `python/` directory.

## Terraform
```hcl
resource "aws_lambda_layer_version" "pl_analysis_cache" {
  layer_name          = "pl-analysis-cache"
  filename            = "${path.module}/../utils/powerlifting-app/lambda/layers/pl-analysis-cache/pl-analysis-cache.zip"
  compatible_runtimes = ["python3.12"]
}
```

## Rules
- Copy store modules VERBATIM. Do not edit imports or refactor.
- No `httpx`, `openrouter`, `OPENROUTER_API_KEY`, `chromadb`, or any `*_ai` module in this layer.
- Only `analysis_cache.py` and `cache_invalidation.py` belong here — one domain (analysis cache).