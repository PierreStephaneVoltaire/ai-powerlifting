
locals {
  tool_resource_paths = fileset("${path.module}/../lambda", "*/resources.yaml")

  lambda_tool_configs = {
    for rel_path in local.tool_resource_paths :
    dirname(rel_path) => yamldecode(file("${path.module}/../lambda/${rel_path}"))
  }

  lambda_function_configs = {
    for name, cfg in local.lambda_tool_configs : name => {
      layers     = cfg.layers
      memory     = cfg.memory
      timeout    = cfg.timeout
      s3_read             = lookup(cfg, "s3_read", false)
      reserved_concurrency = lookup(cfg, "reserved_concurrency", null)
      layer_arns          = [for key in cfg.layers : local.layer_arns[key]]
    }
  }

  lambda_common_env = {
    SANDBOX_PATH              = "/tmp/sandbox"
    IF_HEALTH_TABLE_NAME      = var.dynamodb_health_table
    IF_TEMPLATES_TABLE_NAME   = var.dynamodb_templates_table
    IF_SESSIONS_TABLE_NAME    = var.dynamodb_sessions_table
    IF_PROPOSALS_TABLE_NAME   = var.dynamodb_proposals_table
    ANALYSIS_CACHE_TABLE_NAME = var.dynamodb_analysis_cache_table
    HEALTH_PROGRAM_PK         = "operator"
    OPENROUTER_API_KEY               = data.aws_ssm_parameter.openrouter_key.value
    LLM_BASE_URL                      = "https://openrouter.ai/api/v1"
    ANALYSIS_MODEL                    = "anthropic/claude-sonnet-4.6"
    ESTIMATE_MODEL                     = "anthropic/claude-sonnet-4.6"
    IMPORT_FAST_MODEL                 = "anthropic/claude-haiku-4.5"
    GLOSSARY_TEXT_MODEL                = "google/gemini-3.1-flash-lite"
    ESTIMATE_MODEL_REASONING_EFFORT   = "xhigh"
    ESTIMATE_MODEL_VERBOSITY          = "max"
  }

  lambda_stats_env = {
    POWERLIFTING_S3_BUCKET = var.powerlifting_s3_bucket
  }
}

data "archive_file" "lambda_tool" {
  for_each    = local.lambda_function_configs
  type        = "zip"
  output_path = "${path.module}/build/${each.key}.zip"
  source_dir  = "${path.module}/../lambda/${each.key}"
}

resource "aws_lambda_function" "health_tool" {
  for_each = local.lambda_function_configs

  function_name = "${var.lambda_function_prefix}${each.key}"
  role          = aws_iam_role.lambda_exec.arn
  handler       = var.lambda_handler
  runtime       = var.lambda_runtime
  memory_size   = each.value.memory
  timeout       = each.value.timeout

  reserved_concurrent_executions = lookup(each.value, "reserved_concurrency", null)

  filename         = data.archive_file.lambda_tool[each.key].output_path
  source_code_hash = data.archive_file.lambda_tool[each.key].output_base64sha256

  layers = each.value.layer_arns

  environment {
    variables = merge(
      local.lambda_common_env,
      each.value.s3_read ? local.lambda_stats_env : {},
    )
  }
}
