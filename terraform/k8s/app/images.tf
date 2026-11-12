data "aws_ecr_repository" "app" {
  for_each = var.repositories
  name     = each.value
}

data "aws_ecr_image" "app" {
  for_each        = var.repositories
  repository_name = each.value
  image_tag       = var.image_tag
}

locals {
  images = {
    for key, repo in data.aws_ecr_repository.app :
    key => "${repo.repository_url}@${data.aws_ecr_image.app[key].image_digest}"
  }
}
