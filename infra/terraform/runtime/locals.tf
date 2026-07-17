locals {
  name               = "atlas-${var.environment_id}"
  production         = var.deployment_profile == "production"
  availability_zones = slice(data.aws_availability_zones.available.names, 0, 2)

  api_count       = local.production ? 2 : 1
  scheduler_count = local.production ? 2 : 1
  worker_count    = local.production ? max(2, var.worker_min_count) : var.worker_min_count

  rds_class              = local.production ? "db.r7g.large" : "db.t4g.micro"
  redis_class            = local.production ? "cache.r7g.large" : "cache.t4g.micro"
  redis_replicas         = local.production ? 1 : 0
  opensearch_instance    = local.production ? "m7g.large.search" : "t3.small.search"
  opensearch_nodes       = local.production ? 2 : 1
  opensearch_volume_gib  = local.production ? 100 : 10
  log_retention_days     = 365
  rds_backup_days        = local.production ? 30 : 1
  assign_public_ip       = !local.production
  application_subnet_ids = local.production ? aws_subnet.application[*].id : aws_subnet.public[*].id

  common_environment = [
    { name = "ENVIRONMENT", value = "production" },
    { name = "ATLAS_AUTH_MODE", value = "oidc" },
    { name = "ATLAS_DB_HOST", value = aws_db_instance.postgres.address },
    { name = "ATLAS_DB_PORT", value = tostring(aws_db_instance.postgres.port) },
    { name = "ATLAS_DB_NAME", value = aws_db_instance.postgres.db_name },
    { name = "REDIS_URL", value = "rediss://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0" },
    { name = "OPENSEARCH_URL", value = "https://${aws_opensearch_domain.documents.endpoint}" },
    { name = "ATLAS_OPENSEARCH_AWS_REGION", value = var.aws_region },
    { name = "OPENSEARCH_VERIFY_CERTS", value = "true" },
    { name = "ATLAS_BLOB_STORE_BACKEND", value = "s3" },
    { name = "ATLAS_S3_BUCKET", value = aws_s3_bucket.raw.bucket },
    { name = "ATLAS_S3_KMS_KEY_ID", value = aws_kms_key.atlas.arn },
    { name = "ATLAS_CORS_ORIGINS", value = jsonencode(var.frontend_origins) },
    { name = "ATLAS_OIDC_ISSUER", value = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.atlas.id}" },
    { name = "ATLAS_OIDC_AUDIENCE", value = aws_cognito_user_pool_client.console.id },
    { name = "ATLAS_OIDC_JWKS_URL", value = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.atlas.id}/.well-known/jwks.json" },
    { name = "ATLAS_OIDC_ADMIN_GROUP", value = "admin" },
    { name = "ATLAS_OIDC_VIEWER_GROUP", value = "viewer" },
    { name = "ATLAS_COGNITO_DOMAIN", value = "https://${aws_cognito_user_pool_domain.atlas.domain}.auth.${var.aws_region}.amazoncognito.com" },
    { name = "ATLAS_COGNITO_CLIENT_ID", value = aws_cognito_user_pool_client.console.id },
    { name = "ATLAS_LOG_LEVEL", value = "INFO" },
    { name = "ATLAS_PROMETHEUS_ENDPOINT_ENABLED", value = "false" },
  ]

  common_secrets = [
    { name = "ATLAS_DB_USER", valueFrom = "${aws_db_instance.postgres.master_user_secret[0].secret_arn}:username::" },
    { name = "ATLAS_DB_PASSWORD", valueFrom = "${aws_db_instance.postgres.master_user_secret[0].secret_arn}:password::" },
    { name = "ATLAS_REDIS_PASSWORD", valueFrom = aws_secretsmanager_secret.redis.arn },
  ]
}
