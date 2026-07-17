variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "github_owner" {
  description = "GitHub organization or user that owns the Atlas repository."
  type        = string
}

variable "github_repository" {
  description = "GitHub repository name without the owner."
  type        = string
  default     = "atlas"
}

variable "github_environment" {
  description = "Protected GitHub Environment required for AWS deployment."
  type        = string
  default     = "atlas-showcase"
}
