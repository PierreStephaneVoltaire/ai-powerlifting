mock_provider "aws" {}

run "fresh_pair" {
  command = plan

  override_data {
    target = data.aws_ssm_parameters_by_path.security
    values = { names = [] }
  }

  assert {
    condition     = length(local.existing) == 0 && length(aws_ssm_parameter.principal) == 2
    error_message = "A fresh deployment must create both parameters."
  }
}

run "existing_pair" {
  command = plan

  override_resource {
    target = aws_ssm_parameter.principal["private"]
    values = { id = "/powerlifting/security/principal-signing-private-key" }
  }

  override_resource {
    target = aws_ssm_parameter.principal["public"]
    values = { id = "/powerlifting/security/principal-signing-public-key" }
  }

  override_data {
    target = data.aws_ssm_parameters_by_path.security
    values = { names = ["/powerlifting/security/principal-signing-private-key", "/powerlifting/security/principal-signing-public-key"] }
  }

  assert {
    condition     = length(local.existing) == 2
    error_message = "An existing pair must be adopted."
  }
}

run "reject_partial_pair" {
  command = plan

  override_resource {
    target = aws_ssm_parameter.principal["private"]
    values = { id = "/powerlifting/security/principal-signing-private-key" }
  }

  override_data {
    target = data.aws_ssm_parameters_by_path.security
    values = { names = ["/powerlifting/security/principal-signing-private-key"] }
  }

  expect_failures = [aws_ssm_parameter.principal["private"], aws_ssm_parameter.principal["public"]]
}
