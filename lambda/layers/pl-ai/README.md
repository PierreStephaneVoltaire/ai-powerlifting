# pl-ai Lambda Layer

LLM integration layer for the powerlifting health lambdas.

## Contents
- `httpx` (pip-installed, transitive deps included)
- `jinja2` (pip-installed, transitive deps included)
- `python/ai_config.py` - re-exports model-name constants from env with the same defaults as `app/src/config.py`
- `python/prompts/loader.py` - verbatim copy of `tools/health/prompts/loader.py`
- `python/prompts/*.j2` - verbatim copy of the Jinja2 prompt templates from `tools/health/prompts/`

## Build
```bash
bash utils/powerlifting-app/lambda/layers/pl-ai/build.sh
```
Produces `pl-ai.zip` (Lambda layer layout: `python/lib/python3.12/site-packages/...` plus `python/prompts/` and `python/ai_config.py`).

## Terraform
```hcl
resource "aws_lambda_layer_version" "pl_ai" {
  layer_name          = "pl-ai"
  filename            = "${path.module}/../lambda/layers/pl-ai/pl-ai.zip"
  compatible_runtimes = ["python3.12"]
}
```

## Rules
- `loader.py` and the `.j2` templates are copied VERBATIM from `tools/health/prompts/`.
- `ai_config.py` reads every value from `os.getenv` with defaults matching `app/src/config.py`.
- No `AWS_REGION` or reserved env var re-exported here.
