variable "aws_region" {
  description = "AWS region for this Atlas runtime."
  type        = string
  default     = "us-east-1"
}

variable "environment_id" {
  description = "Unique, lowercase identifier for this disposable environment."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.environment_id))
    error_message = "environment_id must be 3-31 lowercase letters, numbers, or hyphens."
  }
}

variable "deployment_profile" {
  description = "Cost-bounded showcase or redundant production topology."
  type        = string

  validation {
    condition     = contains(["showcase", "production"], var.deployment_profile)
    error_message = "deployment_profile must be showcase or production."
  }
}

variable "expires_at" {
  description = "Required RFC3339 environment expiration used by policy and cleanup workflows."
  type        = string

  validation {
    condition     = can(timecmp(var.expires_at, "2000-01-01T00:00:00Z"))
    error_message = "expires_at must be an RFC3339 timestamp."
  }
}

variable "container_image" {
  description = "Immutable ECR image URI including a digest or release tag."
  type        = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$|:[A-Za-z0-9._-]+$", var.container_image))
    error_message = "container_image must include an immutable digest or release tag."
  }
}

variable "budget_email" {
  description = "Address that receives AWS Budget threshold notifications."
  type        = string
}

variable "budget_limit_usd" {
  description = "Hard monthly budget signal. Launch workflow also enforces an estimated demo cost."
  type        = number
  default     = 75
}

variable "frontend_origins" {
  description = "Allowed browser origins for the API."
  type        = list(string)
  default = [
    "https://atlas.yuvrajkashyap.com",
    "https://atlas-rho-brown.vercel.app",
  ]
}

variable "cognito_callback_urls" {
  description = "OAuth callback URLs registered on the public Cognito client."
  type        = list(string)
  default     = ["https://atlas.yuvrajkashyap.com/auth/callback"]
}

variable "cognito_logout_urls" {
  description = "OAuth logout destinations."
  type        = list(string)
  default     = ["https://atlas.yuvrajkashyap.com/"]
}

variable "raw_retention_days" {
  description = "Days to retain archived HTML before S3 expiration."
  type        = number
  default     = 30
}

variable "worker_min_count" {
  type    = number
  default = 1
}

variable "worker_max_count" {
  type    = number
  default = 4
}

variable "worker_cpu_target" {
  type    = number
  default = 65
}
