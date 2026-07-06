# pl-pandas Lambda Layer

Shared scientific-compute layer for the OpenPowerlifting stats lambdas.

## Contents
- `pandas`, `numpy` (+ transitive deps: `python-dateutil`, `pytz`, `tzdata`, `six`)

## Used by
ONLY the 3 stats lambdas (Stream B):
- `pl_powerlifting_filter_categories`
- `pl_powerlifting_ranking_percentile`
- `pl_analyze_powerlifting_stats`

These lambdas read the OpenPowerlifting CSV dataset from S3 (`POWERLIFTING_S3_BUCKET`) and compute filter categories / rankings / percentile cards, which require pandas + numpy. No other lambda needs this layer — keep it off the DynamoDB and pure-math lambdas so they stay small.

## Build
```bash
bash utils/powerlifting-app/lambda/layers/pl-pandas/build.sh
```
Produces `pl-pandas.zip` (~110MB; fits the 250MB unzipped layer limit).

## Terraform
```hcl
resource "aws_lambda_layer_version" "pl_pandas" {
  layer_name          = "pl-pandas"
  filename            = "${path.module}/../utils/powerlifting-app/lambda/layers/pl-pandas/pl-pandas.zip"
  compatible_runtimes = ["python3.12"]
}
```

## Rules
- NO `httpx`, `openrouter`, `OPENROUTER_API_KEY`, `prompts/loader.py`, `chromadb`, or any `*_ai` module in this layer.
- Pinned versions live in `requirements.txt`.
- Stats lambdas that also read S3 should attach `pl-boto3` alongside this layer.