locals {
  repositories = toset(["if-powerlifting-coach-agent", "if-powerlifting-coach-discord"])
}

data "aws_ecr_repository" "coach" {
  for_each = local.repositories
  name     = each.value
}

data "aws_ecr_image" "coach" {
  for_each        = local.repositories
  repository_name = data.aws_ecr_repository.coach[each.value].name
  image_tag       = "latest"
}
