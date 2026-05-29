resource "aws_ecr_repository" "if_agent_api" {
  name                 = "${var.ecr_repository_prefix}-agent-api"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "portal_backends" {
  for_each = toset([
    "main-portal-backend",
    "finance-portal-backend",
    "diary-portal-backend",
    "proposals-portal-backend",
    "powerlifting-app-backend",
    "directives-portal-backend"
  ])

  name                 = "${var.ecr_repository_prefix}-${each.key}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "portal_frontends" {
  for_each = toset([
    "main-portal-frontend",
    "finance-portal-frontend",
    "diary-portal-frontend",
    "proposals-portal-frontend",
    "powerlifting-app-frontend",
    "directives-portal-frontend"
  ])

  name                 = "${var.ecr_repository_prefix}-${each.key}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "keep_5" {
  for_each = merge(
    { "if-agent-api" = aws_ecr_repository.if_agent_api.name },
    { for k, v in aws_ecr_repository.portal_backends : k => v.name },
    { for k, v in aws_ecr_repository.portal_frontends : k => v.name }
  )

  repository = each.value

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 5 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

locals {
  docker_hash = filesha1("${path.module}/../docker/build.pkr.hcl")

  main_api_hash = sha1(join("", [
    for f in fileset("${path.module}/../app/src", "**/*") :
    filesha1("${path.module}/../app/src/${f}")
  ]))

  portal_backend_hashes = {
    for name, config in local.portals : name => sha1(join("", [
      for f in fileset("${path.module}/../utils/${name}/backend", "**/*") :
      filesha1("${path.module}/../utils/${name}/backend/${f}")
    ]))
  }

  portal_frontend_hashes = {
    for name, config in local.portals : name => sha1(join("", [
      for f in fileset("${path.module}/../utils/${name}/frontend", "**/*") :
      filesha1("${path.module}/../utils/${name}/frontend/${f}")
    ]))
  }

  portal_api_paths = {
    "main-portal"       = "/main"
    "finance-portal"    = "/finance"
    "diary-portal"      = "/diary"
    "proposals-portal"  = "/proposals"
    "powerlifting-app"  = "/api"
    "directives-portal" = "/api"
  }
}

resource "null_resource" "packer_build_main_api" {
  triggers = {
    dir_sha1    = local.docker_hash
    source_sha1 = local.main_api_hash
    repo_url    = aws_ecr_repository.if_agent_api.repository_url
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../docker"
    command     = <<-EOT
      aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
      aws ecr get-login-password --region ${var.region} | docker login --username AWS --password-stdin $(echo ${aws_ecr_repository.if_agent_api.repository_url} | cut -d'/' -f1)
      packer init build.pkr.hcl
      packer build -var "image_repository=${aws_ecr_repository.if_agent_api.repository_url}" -var "image_tag=latest" build.pkr.hcl
    EOT
  }
  depends_on = [aws_ecr_repository.if_agent_api]
}

resource "null_resource" "rollout_restart_main_api" {
  triggers = {
    source_sha1 = local.main_api_hash
  }

  provisioner "local-exec" {
    command = "kubectl rollout restart deployment/if-agent-api -n if-portals"
  }

  depends_on = [
    null_resource.packer_build_main_api,
    kubernetes_deployment.if_agent_api,
  ]
}

resource "null_resource" "packer_build_portal_backends" {
  for_each = local.portals

  triggers = {
    dir_sha1    = filesha1("${path.module}/../docker/portals-backend.pkr.hcl")
    source_sha1 = local.portal_backend_hashes[each.key]
    repo_url    = aws_ecr_repository.portal_backends["${each.key}-backend"].repository_url
    portal_name = each.key
    port        = each.value.port
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../docker"
    command     = <<-EOT
      aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
      aws ecr get-login-password --region ${var.region} | docker login --username AWS --password-stdin $(echo ${aws_ecr_repository.portal_backends["${each.key}-backend"].repository_url} | cut -d'/' -f1)
      packer init portals-backend.pkr.hcl
      packer build -var "image_repository=${aws_ecr_repository.portal_backends["${each.key}-backend"].repository_url}" -var "image_tag=latest" -var "portal_name=${each.key}" -var "portal_port=${each.value.port}" portals-backend.pkr.hcl
    EOT
  }

  depends_on = [aws_ecr_repository.portal_backends]
}

resource "null_resource" "rollout_restart_portal_backends" {
  for_each = local.portals

  triggers = {
    source_sha1 = local.portal_backend_hashes[each.key]
  }

  provisioner "local-exec" {
    command = "kubectl rollout restart deployment/${each.key}-backend -n if-portals"
  }

  depends_on = [
    null_resource.packer_build_portal_backends,
    kubernetes_deployment.portal_backends,
  ]
}

resource "null_resource" "packer_build_portal_frontends" {
  for_each = local.portals

  triggers = {
    dir_sha1    = filesha1("${path.module}/../docker/portals-frontend.pkr.hcl")
    source_sha1 = local.portal_frontend_hashes[each.key]
    repo_url    = aws_ecr_repository.portal_frontends["${each.key}-frontend"].repository_url
    portal_name = each.key
    api_path    = local.portal_api_paths[each.key]
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../docker"
    command     = <<-EOT
      # Login to both public ECR (base images) and private ECR (push target)
      aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
      aws ecr get-login-password --region ${var.region} | docker login --username AWS --password-stdin $(echo ${aws_ecr_repository.portal_frontends["${each.key}-frontend"].repository_url} | cut -d'/' -f1)
      packer init portals-frontend.pkr.hcl
      packer build -var "image_repository=${aws_ecr_repository.portal_frontends["${each.key}-frontend"].repository_url}" -var "image_tag=latest" -var "portal_name=${each.key}" -var "api_url=${local.portal_api_paths[each.key]}" portals-frontend.pkr.hcl
    EOT
  }

  depends_on = [aws_ecr_repository.portal_frontends]
}

resource "null_resource" "rollout_restart_portal_frontends" {
  for_each = local.portals

  triggers = {
    source_sha1 = local.portal_frontend_hashes[each.key]
  }

  provisioner "local-exec" {
    command = "kubectl rollout restart deployment/${each.key}-frontend -n if-portals"
  }

  depends_on = [
    null_resource.packer_build_portal_frontends,
    kubernetes_deployment.portal_frontends,
  ]
}

