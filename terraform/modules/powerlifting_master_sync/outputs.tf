output "function_arn" {
  value = aws_lambda_function.powerlifting_master_sync.arn
}

output "function_name" {
  value = aws_lambda_function.powerlifting_master_sync.function_name
}

output "role_arn" {
  value = aws_iam_role.powerlifting_master_sync_lambda.arn
}

output "dlq_arn" {
  value = aws_sqs_queue.powerlifting_master_sync_dlq.arn
}
