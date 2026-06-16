resource "aws_ecr_repository" "powerlifting_backend" {
  name                 = "${var.ecr_repository_prefix}-powerlifting-app-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "powerlifting_frontend" {
  name                 = "${var.ecr_repository_prefix}-powerlifting-app-frontend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "keep_5" {
  for_each = {
    backend  = aws_ecr_repository.powerlifting_backend.name
    frontend = aws_ecr_repository.powerlifting_frontend.name
  }

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
