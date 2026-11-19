mock_provider "aws" {
  mock_resource "aws_s3_bucket" {
    override_during = plan
    defaults        = { arn = "arn:aws:s3:::mock-bucket" }
  }
  mock_resource "aws_iam_openid_connect_provider" {
    override_during = plan
    defaults        = { arn = "arn:aws:iam::429310424269:oidc-provider/example" }
  }
  mock_data "aws_caller_identity" {
    override_during = plan
    defaults        = { account_id = "429310424269" }
  }
}
mock_provider "cloudflare" {}
mock_provider "tls" {}
mock_provider "archive" {}
mock_provider "random" {}
mock_provider "kubernetes" {}
mock_provider "helm" {}
mock_provider "kubectl" {}

run "enabled_workload_identity" {
  command = plan

  variables {
    workload_identity_enabled      = true
    workload_identity_jwks         = jsonencode({ keys = [{ kty = "RSA", n = "public-modulus", e = "AQAB" }] })
    cloudflare_api_token           = "mock"
    cloudflare_account_id          = "mock"
    tunnel_origin_url              = "https://localhost"
    app_domain                     = "example.com"
    app_zone                       = "example.com"
    cloudflare_zone_plan           = "free"
    auth_domain                    = "auth.example.com"
    llm_domain                     = "llm.example.com"
    glossary_table_name            = "if-powerlifting-glossary"
    glossary_catalog_function_name = "glossary-catalog"
  }

  assert {
    condition     = jsondecode(aws_s3_bucket_policy.workload_identity[0].policy).Statement[0].Action == "s3:GetObject" && jsondecode(aws_s3_bucket_policy.workload_identity[0].policy).Statement[0].Principal == "*" && toset(jsondecode(aws_s3_bucket_policy.workload_identity[0].policy).Statement[0].Resource) == toset(["arn:aws:s3:::mock-bucket/.well-known/openid-configuration", "arn:aws:s3:::mock-bucket/openid/v1/jwks"])
    error_message = "Only the two OIDC documents may be publicly readable."
  }

  assert {
    condition     = alltrue([for service in ["pl-rankings", "pl-assistant"] : length(jsondecode(aws_iam_role.workload_identity[service].assume_role_policy).Statement) == 1 && jsondecode(aws_iam_role.workload_identity[service].assume_role_policy).Statement[0].Action == "sts:AssumeRoleWithWebIdentity" && jsondecode(aws_iam_role.workload_identity[service].assume_role_policy).Statement[0].Principal.Federated == "arn:aws:iam::429310424269:oidc-provider/example" && jsondecode(aws_iam_role.workload_identity[service].assume_role_policy).Statement[0].Condition.StringEquals["powerlifting-workload-identity-429310424269-ca-central-1.s3.ca-central-1.amazonaws.com:aud"] == "sts.amazonaws.com" && jsondecode(aws_iam_role.workload_identity[service].assume_role_policy).Statement[0].Condition.StringEquals["powerlifting-workload-identity-429310424269-ca-central-1.s3.ca-central-1.amazonaws.com:sub"] == "system:serviceaccount:powerlifting:${service}"])
    error_message = "Roles must require the exact service account and STS audience."
  }
  assert {
    condition     = length(regexall("dynamodb:", aws_iam_role_policy.workload_identity["powerlifting-app-backend"].policy)) == 0
    error_message = "The backend must not receive DynamoDB permissions."
  }

  assert {
    condition     = anytrue([for statement in jsondecode(aws_iam_role_policy.workload_identity["pl-analytics"].policy).Statement : try(contains(statement.Action, "s3:ListBucket") && statement.Condition.StringLike["s3:prefix"] == "analysis/*", false)]) && anytrue([for statement in jsondecode(aws_iam_role_policy.workload_identity["pl-coach"].policy).Statement : try(contains(statement.Resource, "arn:aws:s3:::powerlifting-data-2b0f699b/lifetime/*/latest.md"), false)])
    error_message = "Analytics listing and Coach object access must stay within their prefixes."
  }

}
