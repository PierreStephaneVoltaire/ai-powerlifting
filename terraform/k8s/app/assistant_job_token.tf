resource "tls_private_key" "job_token" {
  algorithm   = "ECDSA"
  ecdsa_curve = "P256"
}

locals {
  job_token_public_key = tls_private_key.job_token.public_key_pem
}

resource "kubernetes_secret_v1" "assistant_job_token" {
  metadata {
    name      = "assistant-job-token"
    namespace = var.namespace
  }

  data = {
    PL_JOB_TOKEN_PRIVATE_KEY = tls_private_key.job_token.private_key_pem_pkcs8
  }
}
