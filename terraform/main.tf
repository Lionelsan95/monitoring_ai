module "networking" {
  source       = "./modules/networking"
  project_name = var.project_name
  vpc_cidr     = "10.0.0.0/16"
}

module "ecr" {
  source          = "./modules/ecr"
  repository_name = var.project_name
}

module "secrets" {
  source       = "./modules/secrets"
  project_name = var.project_name
  aws_region   = var.aws_region
}

module "ecs" {
  source       = "./modules/ecs"
  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  ecr_repository_url      = module.ecr.repository_url
  image_tag               = var.image_tag
  task_cpu                = var.task_cpu
  task_memory             = var.task_memory
  desired_count           = var.desired_count

  vpc_id                  = module.networking.vpc_id
  public_subnet_ids       = module.networking.public_subnet_ids
  alb_security_group_id   = module.networking.alb_security_group_id
  ecs_security_group_id   = module.networking.ecs_security_group_id

  task_execution_role_arn = module.secrets.task_execution_role_arn
  task_role_arn           = module.secrets.task_role_arn
  openai_secret_arn       = module.secrets.openai_secret_arn
  anthropic_secret_arn    = module.secrets.anthropic_secret_arn
}
