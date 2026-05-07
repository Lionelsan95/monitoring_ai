output "api_url" {
  description = "Public URL of the API load balancer"
  value       = "http://${module.ecs.alb_dns_name}"
}

output "ecr_repository_url" {
  description = "ECR repository URL — use as image prefix in CI/CD"
  value       = module.ecr.repository_url
}

output "ecr_push_command" {
  description = "One-liner to authenticate Docker to ECR"
  value       = "aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${module.ecr.repository_url}"
}
