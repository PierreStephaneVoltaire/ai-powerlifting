# ---------------------------------------------------------------------------
# Phase 3 — Lambda functions for the 76 health tools.
#
# Source of truth: lambda-tools.yaml (one entry per tool: layers, memory, timeout).
# This file reads that YAML with yamldecode and generates one aws_lambda_function
# per entry via for_each. Adding a tool = add a YAML line; no Terraform edit needed.
#
# Each function's source is its self-contained lambda/<tool>/ folder, zipped with
# data.archive_file. Handler = handler.handler, runtime = python3.12, timeout = 900.
# All functions share aws_iam_role.lambda_exec.
# ---------------------------------------------------------------------------

locals {
  # Parse the tool config YAML once. Each entry is an object with keys:
  #   layers  (list of layer keys), memory (number), timeout (number), s3_read (bool, optional)
  lambda_tools = yamldecode(file("${path.module}/lambda-tools.yaml"))

  # Build the for_each map: tool_name -> merged config object.
  # Normalize missing optional fields (s3_read defaults to false).
  lambda_function_configs = {
    for name, cfg in local.lambda_tools : name => {
      layers  = cfg.layers
      memory  = cfg.memory
      timeout = cfg.timeout
      s3_read = lookup(cfg, "s3_read", false)
      # Resolve each layer key to its ARN via the local layer_arns map (defined in layers.tf).
      layer_arns = [for key in cfg.layers : local.layer_arns[key]]
    }
  }

  # Shared env vars every health lambda gets (table names + region + sandbox path).
  # The handlers' config.py reads these via os.getenv; they match the defaults in
  # each lambda/<tool>/config.py but are pinned here so prod never accidentally
  # falls back to the "operator" dev PK.
  lambda_common_env = {
    AWS_REGION                = var.region
    SANDBOX_PATH              = "/tmp/sandbox"
    IF_HEALTH_TABLE_NAME      = var.dynamodb_health_table
    IF_TEMPLATES_TABLE_NAME   = var.dynamodb_templates_table
    IF_SESSIONS_TABLE_NAME    = var.dynamodb_sessions_table
    IF_PROPOSALS_TABLE_NAME   = var.dynamodb_proposals_table
    ANALYSIS_CACHE_TABLE_NAME = var.dynamodb_analysis_cache_table
    HEALTH_PROGRAM_PK         = "operator"
  }

  # Stats lambdas (Stream B) also get the S3 dataset bucket name.
  lambda_stats_env = {
    POWERLIFTING_S3_BUCKET = var.powerlifting_s3_bucket
  }
}

# ---------------------------------------------------------------------------
# Zip each tool's self-contained source folder. Matches the pattern used by
# the existing video-thumbnail Lambda (data.archive_file in videos.tf).
# ---------------------------------------------------------------------------
data "archive_file" "lambda_tool" {
  for_each    = local.lambda_function_configs
  type        = "zip"
  output_path = "${path.module}/build/${each.key}.zip"
  source_dir  = "${path.module}/../lambda/${each.key}"
}

# ---------------------------------------------------------------------------
# One aws_lambda_function per tool. for_each over the config map so the
# function_name, memory, layers, and env vars all come from the YAML.
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "health_tool" {
  for_each = local.lambda_function_configs

  function_name = "${var.lambda_function_prefix}${each.key}"
  role          = aws_iam_role.lambda_exec.arn
  handler       = var.lambda_handler
  runtime       = var.lambda_runtime
  memory_size   = each.value.memory
  timeout       = each.value.timeout

  filename         = data.archive_file.lambda_tool[each.key].output_path
  source_code_hash = data.archive_file.lambda_tool[each.key].output_base64sha256

  # Attach the layers resolved from the YAML config (empty list for pure-math).
  layers = each.value.layer_arns

  environment {
    variables = merge(
      local.lambda_common_env,
      # Stats lambdas get the S3 bucket env var; others don't.
      each.value.s3_read ? local.lambda_stats_env : {},
    )
  }

  tags = {
    Project = "powerlifting-app"
    Service = "health-lambda"
    Tool    = each.key
  }

  depends_on = [aws_iam_role_policy.lambda_exec]
}

# ---------------------------------------------------------------------------
# Optional provisioned concurrency for the stats lambdas (Stream B) to cut
# cold-start. Off by default (var.stats_provisioned_concurrency = 0). When > 0,
# an aws_lambda_provisioned_concurrency_config is attached to each stats fn.
# TODO: enable once warm-start strategy is validated (see plan Phase 1 Stream B).
# ---------------------------------------------------------------------------
resource "aws_lambda_provisioned_concurrency_config" "stats" {
  for_each = {
    for name, cfg in local.lambda_function_configs : name => cfg if cfg.s3_read
  }

  function_name                     = aws_lambda_function.health_tool[each.key].function_name
  provisioned_concurrent_executions = var.stats_provisioned_concurrency
  qualifier                         = "$LATEST"
}

# ---------------------------------------------------------------------------
# API Gateway (optional) — SKIPPED per the migration plan ("optional").
#
# The portal backend invokes these lambdas directly via the AWS SDK
# (LambdaClient.InvokeCommand), so an HTTP API is not required for the Phase 2
# rewiring. If a public/HTTP entrypoint is needed later, add an aws_apigatewayv2_api
# with a per-tool `/{tool}` proxy route + aws_apigatewayv2_integration per function.
# That is deliberately left as a TODO to avoid over-engineering the first cut.
# ---------------------------------------------------------------------------