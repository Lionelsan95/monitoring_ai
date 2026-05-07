# ── Secrets Manager ───────────────────────────────────────────────────────────
# Secrets are created empty; populate values via the AWS console or:
#   aws secretsmanager put-secret-value \
#     --secret-id monitoring-ai/openai-api-key \
#     --secret-string "sk-..."

resource "aws_secretsmanager_secret" "openai_key" {
  name        = "${var.project_name}/openai-api-key"
  description = "OpenAI API key for monitoring-ai"
}

resource "aws_secretsmanager_secret" "anthropic_key" {
  name        = "${var.project_name}/anthropic-api-key"
  description = "Anthropic API key for monitoring-ai"
}

# ── IAM: task execution role ──────────────────────────────────────────────────
# Used by ECS to pull the image from ECR and fetch secrets from Secrets Manager.

resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "secrets_access" {
  name = "${var.project_name}-secrets-read"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [
        aws_secretsmanager_secret.openai_key.arn,
        aws_secretsmanager_secret.anthropic_key.arn,
      ]
    }]
  })
}

# ── IAM: task role ────────────────────────────────────────────────────────────
# The role assumed by the running container. Add Bedrock permissions here
# when switching to the bedrock provider (no API key needed — IAM auth).

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

# Uncomment when using Bedrock provider:
# resource "aws_iam_role_policy" "bedrock_access" {
#   name = "${var.project_name}-bedrock-invoke"
#   role = aws_iam_role.ecs_task.id
#   policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [{
#       Effect   = "Allow"
#       Action   = ["bedrock:InvokeModel"]
#       Resource = ["arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/*"]
#     }]
#   })
# }
