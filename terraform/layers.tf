# ---------------------------------------------------------------------------
# Phase 3 — Lambda layers.
#
# Each layer is built by its build.sh (produces a <layer>.zip under
# lambda/layers/<layer>/). Run the build scripts before `terraform apply`:
#
#   for d in utils/powerlifting-app/lambda/layers/*/; do bash "$d/build.sh"; done
#
# The zip paths below match the README "Terraform" snippets in each layer dir.
# compatible_runtimes is pinned to python3.12 (the runtime all handlers use).
# ---------------------------------------------------------------------------

# Shared AWS SDK layer (boto3 + botocore + s3transfer). Used by all DynamoDB
# lambdas. ~60MB.
resource "aws_lambda_layer_version" "pl_boto3" {
  layer_name          = "pl-boto3"
  filename            = "${path.module}/../lambda/layers/pl-boto3/pl-boto3.zip"
  source_code_hash    = filebase64sha256("${path.module}/../lambda/layers/pl-boto3/pl-boto3.zip")
  compatible_runtimes = ["python3.12"]

}

# Shared scientific-compute layer (pandas + numpy). Used ONLY by the 3 stats
# lambdas (Stream B). ~110MB.
resource "aws_lambda_layer_version" "pl_pandas" {
  layer_name          = "pl-pandas"
  filename            = "${path.module}/../lambda/layers/pl-pandas/pl-pandas.zip"
  source_code_hash    = filebase64sha256("${path.module}/../lambda/layers/pl-pandas/pl-pandas.zip")
  compatible_runtimes = ["python3.12"]

}

# ---------------------------------------------------------------------------
# Domain layers — shared deterministic modules copied from tools/health/.
# Each build.sh produces <layer>.zip under lambda/layers/<layer>/.
# ---------------------------------------------------------------------------

resource "aws_lambda_layer_version" "pl_program" {
  layer_name          = "pl-program"
  filename            = "${path.module}/../lambda/layers/pl-program/pl-program.zip"
  source_code_hash    = filebase64sha256("${path.module}/../lambda/layers/pl-program/pl-program.zip")
  compatible_runtimes = ["python3.12"]

}

resource "aws_lambda_layer_version" "pl_sessions" {
  layer_name          = "pl-sessions"
  filename            = "${path.module}/../lambda/layers/pl-sessions/pl-sessions.zip"
  source_code_hash    = filebase64sha256("${path.module}/../lambda/layers/pl-sessions/pl-sessions.zip")
  compatible_runtimes = ["python3.12"]

}

resource "aws_lambda_layer_version" "pl_glossary" {
  layer_name          = "pl-glossary"
  filename            = "${path.module}/../lambda/layers/pl-glossary/pl-glossary.zip"
  source_code_hash    = filebase64sha256("${path.module}/../lambda/layers/pl-glossary/pl-glossary.zip")
  compatible_runtimes = ["python3.12"]

}

resource "aws_lambda_layer_version" "pl_templates" {
  layer_name          = "pl-templates"
  filename            = "${path.module}/../lambda/layers/pl-templates/pl-templates.zip"
  source_code_hash    = filebase64sha256("${path.module}/../lambda/layers/pl-templates/pl-templates.zip")
  compatible_runtimes = ["python3.12"]

}

resource "aws_lambda_layer_version" "pl_imports" {
  layer_name          = "pl-imports"
  filename            = "${path.module}/../lambda/layers/pl-imports/pl-imports.zip"
  source_code_hash    = filebase64sha256("${path.module}/../lambda/layers/pl-imports/pl-imports.zip")
  compatible_runtimes = ["python3.12"]

}

resource "aws_lambda_layer_version" "pl_federation" {
  layer_name          = "pl-federation"
  filename            = "${path.module}/../lambda/layers/pl-federation/pl-federation.zip"
  source_code_hash    = filebase64sha256("${path.module}/../lambda/layers/pl-federation/pl-federation.zip")
  compatible_runtimes = ["python3.12"]

}

resource "aws_lambda_layer_version" "pl_analysis_cache" {
  layer_name          = "pl-analysis-cache"
  filename            = "${path.module}/../lambda/layers/pl-analysis-cache/pl-analysis-cache.zip"
  source_code_hash    = filebase64sha256("${path.module}/../lambda/layers/pl-analysis-cache/pl-analysis-cache.zip")
  compatible_runtimes = ["python3.12"]

}

# ---------------------------------------------------------------------------
# Local map: layer key (as used in lambda-tools.yaml) -> layer ARN.
# The lambda functions resolve their layers list through this map.
# ---------------------------------------------------------------------------
locals {
  # layer key -> aws_lambda_layer_version ARN
  layer_arns = {
    pl_boto3          = aws_lambda_layer_version.pl_boto3.arn
    pl_pandas         = aws_lambda_layer_version.pl_pandas.arn
    pl_program        = aws_lambda_layer_version.pl_program.arn
    pl_sessions       = aws_lambda_layer_version.pl_sessions.arn
    pl_glossary       = aws_lambda_layer_version.pl_glossary.arn
    pl_templates      = aws_lambda_layer_version.pl_templates.arn
    pl_imports        = aws_lambda_layer_version.pl_imports.arn
    pl_federation     = aws_lambda_layer_version.pl_federation.arn
    pl_analysis_cache = aws_lambda_layer_version.pl_analysis_cache.arn
  }
}