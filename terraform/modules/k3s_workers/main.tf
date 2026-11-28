data "aws_caller_identity" "current" {}
data "aws_ssm_parameter" "ami" { name = var.ami_ssm_parameter }

locals {
  vpc_cidr        = "10.60.0.0/16"
  forbidden_cidrs = ["10.42.0.0/16", "10.43.0.0/16", "100.64.0.0/10", var.home_lan_cidr]
}

resource "aws_vpc" "workers" {
  cidr_block           = local.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "nolift-workers" }
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = try(alltrue([for cidr in local.forbidden_cidrs : cidrhost("${split("/", local.vpc_cidr)[0]}/${min(tonumber(split("/", local.vpc_cidr)[1]), tonumber(split("/", cidr)[1]))}", 0) != cidrhost("${split("/", cidr)[0]}/${min(tonumber(split("/", local.vpc_cidr)[1]), tonumber(split("/", cidr)[1]))}", 0)]), false)
      error_message = "The worker VPC CIDR overlaps the pod, service, home LAN, or Tailscale network."
    }
    precondition {
      condition     = var.min <= var.desired && var.desired <= var.max && var.min >= 0
      error_message = "Worker capacity must satisfy 0 <= min <= desired <= max."
    }
  }
}
resource "aws_internet_gateway" "workers" {
  lifecycle { prevent_destroy = true }
  vpc_id = aws_vpc.workers.id
}
resource "aws_subnet" "workers" {
  lifecycle { prevent_destroy = true }
  for_each                = { for i, az in var.azs : az => i }
  vpc_id                  = aws_vpc.workers.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(local.vpc_cidr, 8, each.value)
  map_public_ip_on_launch = false
}
resource "aws_route_table" "workers" {
  lifecycle { prevent_destroy = true }
  vpc_id = aws_vpc.workers.id
  route {
    cidr_block           = "0.0.0.0/0"
    network_interface_id = aws_instance.fck_nat.primary_network_interface_id
  }
}
resource "aws_route_table_association" "workers" {
  lifecycle { prevent_destroy = true }
  for_each       = aws_subnet.workers
  subnet_id      = each.value.id
  route_table_id = aws_route_table.workers.id
}
resource "aws_vpc_endpoint" "s3" {
  lifecycle { prevent_destroy = true }
  vpc_id          = aws_vpc.workers.id
  service_name    = "com.amazonaws.${var.region}.s3"
  route_table_ids = [aws_route_table.workers.id]
}
resource "aws_security_group" "workers" {
  lifecycle { prevent_destroy = true }
  name   = "nolift-k3s-workers"
  vpc_id = aws_vpc.workers.id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_iam_role" "workers" {
  lifecycle { prevent_destroy = true }
  name               = "nolift-k3s-workers"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "ssm" {
  lifecycle { prevent_destroy = true }
  role       = aws_iam_role.workers.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "parameters" {
  lifecycle { prevent_destroy = true }
  role   = aws_iam_role.workers.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["ssm:GetParameter", "ssm:GetParameters"], Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/nolift/k3s/*" }] })
}
resource "aws_iam_instance_profile" "workers" {
  lifecycle { prevent_destroy = true }
  name = "nolift-k3s-workers"
  role = aws_iam_role.workers.name
}
resource "aws_launch_template" "workers" {
  lifecycle { prevent_destroy = true }
  name_prefix                          = "nolift-k3s-worker-"
  image_id                             = data.aws_ssm_parameter.ami.value
  instance_initiated_shutdown_behavior = "terminate"
  iam_instance_profile { name = aws_iam_instance_profile.workers.name }
  network_interfaces {
    associate_public_ip_address = false
    device_index                = 0
    security_groups             = [aws_security_group.workers.id]
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size           = var.root_volume_gib
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
  user_data = base64encode("#cloud-config\n${yamlencode({
    packages = ["ansible-core"]
    write_files = [
      { path = "/etc/nolift/worker.yml", content = file("${path.module}/worker.yml") },
      { path = "/etc/nolift/worker-health.yml", content = file("${path.module}/worker-health.yml") }
    ]
    runcmd = [
      ["ansible-playbook", "/etc/nolift/worker.yml"],
      ["sh", "-c", "test -f /etc/nolift/worker-ready || shutdown -h now"]
    ]
  })}")
}
resource "aws_autoscaling_group" "workers" {
  lifecycle { prevent_destroy = true }
  depends_on          = [aws_route_table_association.workers]
  name                = "nolift-k3s-workers"
  min_size            = var.min
  desired_capacity    = var.desired
  max_size            = var.max
  vpc_zone_identifier = [for subnet in aws_subnet.workers : subnet.id]
  capacity_rebalance  = true
  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "price-capacity-optimized"
      spot_max_price                           = var.spot_max_price
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.workers.id
        version            = aws_launch_template.workers.latest_version
      }
      dynamic "override" {
        for_each = var.instance_types
        content {
          instance_type = override.value
        }
      }
    }
  }
  initial_lifecycle_hook {
    name                 = "nolift-worker-drain"
    lifecycle_transition = "autoscaling:EC2_INSTANCE_TERMINATING"
    heartbeat_timeout    = 300
    default_result       = "CONTINUE"
  }
  instance_refresh {
    strategy = "Rolling"
    preferences { min_healthy_percentage = 100 }
  }
  tag {
    key                 = "aws-node-termination-handler/managed"
    value               = "true"
    propagate_at_launch = true
  }
  tag {
    key                 = "Name"
    value               = "nolift-k3s-worker"
    propagate_at_launch = true
  }
}
resource "aws_sqs_queue" "interruptions" {
  lifecycle { prevent_destroy = true }
  name                    = "nolift-k3s-interruptions"
  sqs_managed_sse_enabled = true
}
resource "aws_cloudwatch_event_rule" "interruptions" {
  lifecycle { prevent_destroy = true }
  for_each = {
    spot      = { source = ["aws.ec2"], detail-type = ["EC2 Spot Instance Interruption Warning", "EC2 Instance Rebalance Recommendation"] }
    state     = { source = ["aws.ec2"], detail-type = ["EC2 Instance State-change Notification"] }
    lifecycle = { source = ["aws.autoscaling"], detail-type = ["EC2 Instance-terminate Lifecycle Action"], detail = { AutoScalingGroupName = [aws_autoscaling_group.workers.name] } }
  }
  name          = "nolift-k3s-${each.key}"
  event_pattern = jsonencode(each.value)
}
resource "aws_cloudwatch_event_target" "interruptions" {
  lifecycle { prevent_destroy = true }
  for_each = aws_cloudwatch_event_rule.interruptions
  rule     = each.value.name
  arn      = aws_sqs_queue.interruptions.arn
}
resource "aws_sqs_queue_policy" "interruptions" {
  lifecycle { prevent_destroy = true }
  queue_url = aws_sqs_queue.interruptions.id
  policy    = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sqs:SendMessage", Resource = aws_sqs_queue.interruptions.arn, Condition = { ArnEquals = { "aws:SourceArn" = [for rule in aws_cloudwatch_event_rule.interruptions : rule.arn] } } }] })
}
output "queue_url" { value = aws_sqs_queue.interruptions.url }
output "queue_arn" { value = aws_sqs_queue.interruptions.arn }
