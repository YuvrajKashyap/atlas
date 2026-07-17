output "api_base_url" {
  description = "Temporary TLS API origin published to Edge Config after verification."
  value       = "https://${aws_cloudfront_distribution.api.domain_name}"
}

output "environment_id" { value = var.environment_id }
output "expires_at" { value = var.expires_at }
output "cluster_name" { value = aws_ecs_cluster.atlas.name }
output "raw_bucket" { value = aws_s3_bucket.raw.bucket }
output "ecr_repository_url" { value = aws_ecr_repository.atlas.repository_url }
output "cognito_user_pool_id" { value = aws_cognito_user_pool.atlas.id }
output "cognito_client_id" { value = aws_cognito_user_pool_client.console.id }
output "cognito_domain" { value = "https://${aws_cognito_user_pool_domain.atlas.domain}.auth.${var.aws_region}.amazoncognito.com" }
output "database_secret_arn" {
  value     = aws_db_instance.postgres.master_user_secret[0].secret_arn
  sensitive = true
}
