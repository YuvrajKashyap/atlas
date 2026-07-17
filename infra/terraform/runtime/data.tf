data "aws_iam_policy_document" "kms" {
  statement {
    sid       = "AccountAdministration"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  statement {
    sid    = "CloudWatchLogsEncryption"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey*",
      "kms:ReEncrypt*",
      "kms:DescribeKey",
    ]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${var.aws_region}.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/atlas/*"]
    }
  }
}

resource "aws_kms_key" "atlas" {
  description             = "Atlas ${var.environment_id} data encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms.json
}

resource "aws_kms_alias" "atlas" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.atlas.key_id
}

resource "aws_s3_bucket" "raw" {
  bucket_prefix = "${local.name}-raw-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket = aws_s3_bucket.raw.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.atlas.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    id     = "retention"
    status = "Enabled"
    filter {}

    expiration { days = var.raw_retention_days }
    noncurrent_version_expiration { noncurrent_days = 7 }
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
}

resource "aws_ecr_repository" "atlas" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration { scan_on_push = true }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.atlas.arn
  }
}

resource "aws_iam_role" "rds_monitoring" {
  name = "${local.name}-rds-monitoring"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "monitoring.rds.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

resource "aws_db_subnet_group" "postgres" {
  name       = local.name
  subnet_ids = aws_subnet.data[*].id
}

resource "aws_db_parameter_group" "postgres" {
  name   = "${local.name}-postgres17"
  family = "postgres17"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  parameter {
    name  = "log_statement"
    value = "ddl"
  }
}

resource "aws_db_instance" "postgres" {
  identifier                          = local.name
  engine                              = "postgres"
  engine_version                      = "17"
  instance_class                      = local.rds_class
  allocated_storage                   = local.production ? 100 : 20
  max_allocated_storage               = local.production ? 500 : 50
  storage_type                        = "gp3"
  storage_encrypted                   = true
  kms_key_id                          = aws_kms_key.atlas.arn
  db_name                             = "atlas"
  username                            = "atlasadmin"
  manage_master_user_password         = true
  master_user_secret_kms_key_id       = aws_kms_key.atlas.arn
  port                                = 5432
  db_subnet_group_name                = aws_db_subnet_group.postgres.name
  parameter_group_name                = aws_db_parameter_group.postgres.name
  vpc_security_group_ids              = [aws_security_group.database.id]
  publicly_accessible                 = false
  multi_az                            = local.production
  backup_retention_period             = local.rds_backup_days
  backup_window                       = "06:00-07:00"
  maintenance_window                  = "sun:07:00-sun:08:00"
  auto_minor_version_upgrade          = true
  iam_database_authentication_enabled = true
  deletion_protection                 = false
  skip_final_snapshot                 = true
  delete_automated_backups            = true
  performance_insights_enabled        = local.production
  performance_insights_kms_key_id     = local.production ? aws_kms_key.atlas.arn : null
  monitoring_interval                 = 60
  monitoring_role_arn                 = aws_iam_role.rds_monitoring.arn
  copy_tags_to_snapshot               = true
  enabled_cloudwatch_logs_exports     = ["postgresql", "upgrade"]

}

resource "aws_elasticache_subnet_group" "redis" {
  name       = local.name
  subnet_ids = aws_subnet.data[*].id
}

resource "random_password" "redis" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "redis" {
  name                    = "${local.name}/redis-auth-token"
  kms_key_id              = aws_kms_key.atlas.arn
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "redis" {
  secret_id     = aws_secretsmanager_secret.redis.id
  secret_string = random_password.redis.result
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = local.name
  description                = "Atlas notification transport"
  engine                     = "valkey"
  node_type                  = local.redis_class
  num_cache_clusters         = local.redis_replicas + 1
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.atlas.arn
  transit_encryption_enabled = true
  transit_encryption_mode    = "required"
  auth_token                 = random_password.redis.result
  auth_token_update_strategy = "SET"
  automatic_failover_enabled = local.production
  multi_az_enabled           = local.production
  snapshot_retention_limit   = local.production ? 7 : 0
  apply_immediately          = true

  depends_on = [aws_secretsmanager_secret_version.redis]
}

resource "aws_opensearch_domain" "documents" {
  domain_name    = substr(local.name, 0, 28)
  engine_version = "OpenSearch_3.3"

  cluster_config {
    instance_type          = local.opensearch_instance
    instance_count         = local.opensearch_nodes
    zone_awareness_enabled = local.production

    dynamic "zone_awareness_config" {
      for_each = local.production ? [1] : []
      content { availability_zone_count = 2 }
    }
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = local.opensearch_volume_gib
  }

  vpc_options {
    subnet_ids         = local.production ? aws_subnet.data[*].id : [aws_subnet.data[0].id]
    security_group_ids = [aws_security_group.search.id]
  }

  encrypt_at_rest {
    enabled    = true
    kms_key_id = aws_kms_key.atlas.arn
  }
  node_to_node_encryption { enabled = true }
  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }
  advanced_security_options {
    enabled                        = true
    internal_user_database_enabled = false
  }

  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = aws_iam_role.task.arn }
      Action    = "es:ESHttp*"
      Resource  = "arn:aws:es:${var.aws_region}:${data.aws_caller_identity.current.account_id}:domain/${substr(local.name, 0, 28)}/*"
    }]
  })

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch.arn
    log_type                 = "ES_APPLICATION_LOGS"
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch.arn
    log_type                 = "INDEX_SLOW_LOGS"
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch.arn
    log_type                 = "SEARCH_SLOW_LOGS"
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch.arn
    log_type                 = "AUDIT_LOGS"
  }

  depends_on = [aws_cloudwatch_log_resource_policy.opensearch]
}
