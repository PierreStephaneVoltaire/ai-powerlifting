resource "aws_ecr_repository" "this" {
  for_each            = toset(var.repository_names)
  name                 = "${var.repository_prefix}-${each.value}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "keep_5" {
  # Key off the static set of names so the keys are known at plan time
  # (keying off aws_ecr_repository.this produces "known only after apply"
  # which blocks plan and import).
  for_each = toset(var.repository_names)

  repository = "${var.repository_prefix}-${each.value}"

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
