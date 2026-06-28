
resource "aws_lambda_layer_version" "pl_boto3" {
  layer_name          = "pl-boto3"
  filename            = "${path.module}/../lambda/layers/pl-boto3/pl-boto3.zip"
  source_code_hash    = filebase64sha256("${path.module}/../lambda/layers/pl-boto3/pl-boto3.zip")
  compatible_runtimes = ["python3.12"]

}

resource "aws_lambda_layer_version" "pl_pandas" {
  layer_name          = "pl-pandas"
  filename            = "${path.module}/../lambda/layers/pl-pandas/pl-pandas.zip"
  source_code_hash    = filebase64sha256("${path.module}/../lambda/layers/pl-pandas/pl-pandas.zip")
  compatible_runtimes = ["python3.12"]

}


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

locals {
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
