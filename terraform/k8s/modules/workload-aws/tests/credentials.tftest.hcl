variables {
  region             = "ca-central-1"
  shared_secret_name = "pl-aws-credentials"
  role_arn           = null
}

run "legacy_credentials" {
  command = plan

  assert {
    condition     = output.secret_names == tolist(["pl-aws-credentials"]) && length(output.token_paths) == 0
    error_message = "An unmigrated workload must keep its shared secret."
  }

  assert {
    condition     = output.env.AWS_SHARED_CREDENTIALS_FILE == "/secrets/aws/credentials" && !contains(keys(output.env), "AWS_ROLE_ARN")
    error_message = "Legacy credentials must configure only the shared-file provider."
  }
}

run "projected_credentials" {
  command = plan

  variables {
    role_arn = "arn:aws:iam::123456789012:role/nolift-pl-rankings"
  }

  assert {
    condition     = length(output.secret_names) == 0 && output.token_paths == tolist(["web-identity-token"])
    error_message = "Migrated workloads must only mount the projected token."
  }

  assert {
    condition     = output.env.AWS_WEB_IDENTITY_TOKEN_FILE == "/secrets/aws/web-identity-token" && output.env.AWS_ROLE_ARN == var.role_arn && !contains(keys(output.env), "AWS_SHARED_CREDENTIALS_FILE")
    error_message = "The SDK must use the projected token and the workload's role."
  }
}

run "no_aws_credentials" {
  command = plan

  variables {
    shared_secret_name = null
  }

  assert {
    condition     = length(output.secret_names) == 0 && length(output.token_paths) == 0 && !contains(keys(output.env), "AWS_ROLE_ARN") && !contains(keys(output.env), "AWS_SHARED_CREDENTIALS_FILE")
    error_message = "A credentialless workload must not receive either credential source."
  }
}
