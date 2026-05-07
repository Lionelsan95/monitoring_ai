terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state — bootstrap these resources manually once before first apply:
  #   aws s3api create-bucket --bucket <bucket> --region eu-west-1 \
  #     --create-bucket-configuration LocationConstraint=eu-west-1
  #   aws s3api put-bucket-versioning --bucket <bucket> \
  #     --versioning-configuration Status=Enabled
  #   aws dynamodb create-table --table-name monitoring-ai-tfstate-lock \
  #     --attribute-definitions AttributeName=LockID,AttributeType=S \
  #     --key-schema AttributeName=LockID,KeyType=HASH \
  #     --billing-mode PAY_PER_REQUEST --region eu-west-1
  backend "s3" {
    bucket         = "monitoring-ai-tfstate"       # change to your bucket name
    key            = "monitoring-ai/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "monitoring-ai-tfstate-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
