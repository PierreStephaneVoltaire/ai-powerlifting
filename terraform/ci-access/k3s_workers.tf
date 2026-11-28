resource "aws_iam_role_policy" "k3s_workers" {
  name = "nolift-k3s-workers-terraform"
  role = var.ci_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:Describe*", "ec2:CreateVpc", "ec2:ModifyVpcAttribute", "ec2:CreateInternetGateway", "ec2:AttachInternetGateway",
          "ec2:CreateSubnet", "ec2:ModifySubnetAttribute", "ec2:CreateRouteTable", "ec2:CreateRoute", "ec2:ReplaceRoute", "ec2:DeleteRoute", "ec2:AssociateRouteTable", "ec2:ReplaceRouteTableAssociation",
          "ec2:CreateVpcEndpoint", "ec2:ModifyVpcEndpoint", "ec2:CreateSecurityGroup", "ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupIngress",
          "ec2:AuthorizeSecurityGroupEgress", "ec2:RevokeSecurityGroupEgress", "ec2:CreateLaunchTemplate", "ec2:CreateLaunchTemplateVersion",
          "ec2:ModifyLaunchTemplate", "ec2:CreateTags", "ec2:DeleteTags", "ec2:RunInstances"
        ]
        Resource = "*"
      },
      {
        Effect    = "Allow"
        Action    = ["ec2:ModifyInstanceAttribute", "ec2:ModifyInstanceMetadataOptions", "ec2:StartInstances", "ec2:StopInstances"]
        Resource  = "arn:aws:ec2:${var.region}:${local.account}:instance/*"
        Condition = { StringEquals = { "ec2:ResourceTag/Name" = "nolift-k3s-fck-nat" } }
      },
      {
        Effect    = "Allow"
        Action    = ["ec2:ModifyNetworkInterfaceAttribute"]
        Resource  = "arn:aws:ec2:${var.region}:${local.account}:network-interface/*"
        Condition = { StringEquals = { "ec2:Attribute" = "groupSet" } }
      },
      {
        Effect   = "Allow"
        Action   = ["autoscaling:Describe*"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["autoscaling:CreateAutoScalingGroup", "autoscaling:UpdateAutoScalingGroup", "autoscaling:CreateOrUpdateTags", "autoscaling:DeleteTags", "autoscaling:PutLifecycleHook", "autoscaling:StartInstanceRefresh", "autoscaling:CancelInstanceRefresh"]
        Resource = "arn:aws:autoscaling:${var.region}:${local.account}:autoScalingGroup:*:autoScalingGroupName/nolift-k3s-workers"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:CreateQueue", "sqs:GetQueueUrl", "sqs:GetQueueAttributes", "sqs:SetQueueAttributes", "sqs:TagQueue", "sqs:ListQueueTags"]
        Resource = "arn:aws:sqs:${var.region}:${local.account}:nolift-k3s-*"
      },
      {
        Effect   = "Allow"
        Action   = ["events:PutRule", "events:DescribeRule", "events:PutTargets", "events:ListTargetsByRule", "events:ListTagsForResource", "events:TagResource"]
        Resource = "arn:aws:events:${var.region}:${local.account}:rule/nolift-k3s-*"
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:PutParameter", "ssm:AddTagsToResource", "ssm:ListTagsForResource"]
        Resource = ["arn:aws:ssm:${var.region}:${local.account}:parameter/nolift/k3s/*", "arn:aws:ssm:${var.region}::parameter/aws/service/canonical/ubuntu/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["iam:CreateInstanceProfile", "iam:GetInstanceProfile", "iam:AddRoleToInstanceProfile", "iam:TagInstanceProfile", "iam:ListInstanceProfileTags"]
        Resource = "arn:aws:iam::${local.account}:instance-profile/nolift-k3s-workers"
      },
      {
        Effect    = "Allow"
        Action    = ["iam:AttachRolePolicy"]
        Resource  = "arn:aws:iam::${local.account}:role/nolift-k3s-workers"
        Condition = { ArnEquals = { "iam:PolicyARN" = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore" } }
      },
      {
        Effect    = "Allow"
        Action    = ["iam:PassRole"]
        Resource  = "arn:aws:iam::${local.account}:role/nolift-k3s-workers"
        Condition = { StringEquals = { "iam:PassedToService" = "ec2.amazonaws.com" } }
      }
    ]
  })
}
