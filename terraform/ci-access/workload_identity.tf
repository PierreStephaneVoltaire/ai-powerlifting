locals {
  workload_identity_bucket = "powerlifting-workload-identity-${local.account}-ca-central-1"
  workload_identity_issuer = "${local.workload_identity_bucket}.s3.ca-central-1.amazonaws.com"
}

resource "aws_iam_role_policy" "workload_identity" {
  name = "nolift-workload-identity-terraform"
  role = var.ci_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:CreateBucket", "s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketPolicy", "s3:PutBucketPolicy", "s3:GetBucketPublicAccessBlock", "s3:PutBucketPublicAccessBlock", "s3:GetBucketVersioning", "s3:GetEncryptionConfiguration", "s3:GetBucketTagging", "s3:GetBucketAcl", "s3:GetBucketCORS", "s3:GetLifecycleConfiguration", "s3:GetBucketLogging", "s3:GetBucketObjectLockConfiguration", "s3:GetReplicationConfiguration", "s3:GetAccelerateConfiguration", "s3:GetBucketRequestPayment", "s3:GetBucketWebsite"]
        Resource = "arn:aws:s3:::${local.workload_identity_bucket}"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = ["arn:aws:s3:::${local.workload_identity_bucket}/.well-known/openid-configuration", "arn:aws:s3:::${local.workload_identity_bucket}/openid/v1/jwks"]
      },
      {
        Effect   = "Allow"
        Action   = ["iam:CreateOpenIDConnectProvider", "iam:GetOpenIDConnectProvider", "iam:UpdateOpenIDConnectProviderThumbprint", "iam:TagOpenIDConnectProvider", "iam:ListOpenIDConnectProviderTags", "iam:UntagOpenIDConnectProvider", "iam:AddClientIDToOpenIDConnectProvider"]
        Resource = "arn:aws:iam::${local.account}:oidc-provider/${local.workload_identity_issuer}"
      },
      {
        Effect   = "Allow"
        Action   = ["iam:CreateRole", "iam:GetRole", "iam:UpdateAssumeRolePolicy", "iam:UpdateRole", "iam:TagRole", "iam:ListRoleTags", "iam:UntagRole", "iam:ListRolePolicies", "iam:GetRolePolicy", "iam:PutRolePolicy", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole"]
        Resource = "arn:aws:iam::${local.account}:role/nolift-*"
      },
    ]
  })
}
