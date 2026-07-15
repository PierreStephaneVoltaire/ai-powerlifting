output "analysis_cache_table_arn" {
  value = aws_dynamodb_table.if_powerlifting_analysis_cache.arn
}

output "master_competitions_table_arn" {
  value = aws_dynamodb_table.if_powerlifting_master_competitions.arn
}

output "master_competitions_stream_arn" {
  value = aws_dynamodb_table.if_powerlifting_master_competitions.stream_arn
}

output "user_competitions_table_arn" {
  value = aws_dynamodb_table.if_powerlifting_user_competitions.arn
}

output "user_competitions_table_name" {
  value = aws_dynamodb_table.if_powerlifting_user_competitions.name
}

output "master_federations_table_arn" {
  value = aws_dynamodb_table.if_powerlifting_master_federations.arn
}

output "master_federations_stream_arn" {
  value = aws_dynamodb_table.if_powerlifting_master_federations.stream_arn
}

output "user_federations_table_arn" {
  value = aws_dynamodb_table.if_powerlifting_user_federations.arn
}

output "user_federations_table_name" {
  value = aws_dynamodb_table.if_powerlifting_user_federations.name
}

output "goals_table_arn" {
  value = aws_dynamodb_table.if_powerlifting_goals.arn
}
