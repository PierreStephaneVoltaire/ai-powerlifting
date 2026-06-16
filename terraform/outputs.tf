output "backend_repository_url" {
  value = aws_ecr_repository.powerlifting_backend.repository_url
}

output "frontend_repository_url" {
  value = aws_ecr_repository.powerlifting_frontend.repository_url
}
