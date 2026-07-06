# pl-boto3 Lambda Layer

Shared AWS SDK layer for the DynamoDB-backed health lambdas.

## Contents
- `boto3`, `botocore`, `s3transfer` (+ transitive deps: `jmespath`, `urllib3`, `python-dateutil`, `six`)

## Used by
All 63 DynamoDB lambdas (Streams D, E, F, G, H, I, and the deterministic-analytics lambdas in Stream C that read DynamoDB). The 10 pure-math lambdas (Stream A) use **no layer**. The 3 stats lambdas (Stream B) use `pl-pandas` and may also attach `pl-boto3` if they read from S3.

## Build
```bash
bash utils/powerlifting-app/lambda/layers/pl-boto3/build.sh
```
Produces `pl-boto3.zip` (Lambda layer layout: `python/lib/python3.12/site-packages/...`).

## Terraform
```hcl
resource "aws_lambda_layer_version" "pl_boto3" {
  layer_name          = "pl-boto3"
  filename            = "${path.module}/../utils/powerlifting-app/lambda/layers/pl-boto3/pl-boto3.zip"
  compatible_runtimes = ["python3.12"]
}
```

## Rules
- NO `httpx`, `openrouter`, `OPENROUTER_API_KEY`, `prompts/loader.py`, `chromadb`, or any `*_ai` module in this layer.
- Pinned versions live in `requirements.txt`.