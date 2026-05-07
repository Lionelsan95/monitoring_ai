output "task_execution_role_arn" { value = aws_iam_role.ecs_task_execution.arn }
output "task_role_arn"           { value = aws_iam_role.ecs_task.arn }
output "openai_secret_arn"       { value = aws_secretsmanager_secret.openai_key.arn }
output "anthropic_secret_arn"    { value = aws_secretsmanager_secret.anthropic_key.arn }
