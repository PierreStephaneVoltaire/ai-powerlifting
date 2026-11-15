data "aws_ssm_parameter" "job_token" {
  for_each        = toset(["private_key", "public_key"])
  name            = "/powerlifting/assistant/job_token_${each.key}"
  with_decryption = true
}

locals {
  job_token_public_key = nonsensitive(data.aws_ssm_parameter.job_token["public_key"].value)
}

resource "kubernetes_secret_v1" "assistant_job_token" {
  metadata {
    name      = "assistant-job-token"
    namespace = var.namespace
  }

  data = {
    PL_JOB_TOKEN_PRIVATE_KEY = data.aws_ssm_parameter.job_token["private_key"].value
  }
}
