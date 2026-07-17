data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Only CloudFront origin traffic reaches the public load balancer"
  vpc_id      = aws_vpc.atlas.id

}

resource "aws_security_group" "tasks" {
  name        = "${local.name}-tasks"
  description = "Atlas ECS tasks"
  vpc_id      = aws_vpc.atlas.id

}

resource "aws_security_group" "database" {
  name        = "${local.name}-postgres"
  description = "PostgreSQL from Atlas tasks only"
  vpc_id      = aws_vpc.atlas.id

}

resource "aws_security_group" "redis" {
  name        = "${local.name}-redis"
  description = "Valkey from Atlas tasks only"
  vpc_id      = aws_vpc.atlas.id

}

resource "aws_security_group" "search" {
  name        = "${local.name}-search"
  description = "OpenSearch from Atlas tasks only"
  vpc_id      = aws_vpc.atlas.id

}

resource "aws_vpc_security_group_ingress_rule" "alb_cloudfront" {
  security_group_id = aws_security_group.alb.id
  description       = "CloudFront origin-facing HTTP"
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "alb_api" {
  security_group_id            = aws_security_group.alb.id
  description                  = "API target group"
  referenced_security_group_id = aws_security_group.tasks.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "tasks_alb" {
  security_group_id            = aws_security_group.tasks.id
  description                  = "API traffic from the load balancer"
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "tasks_outbound" {
  security_group_id = aws_security_group.tasks.id
  description       = "HTTPS dependencies and allowlisted public crawl targets"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_ingress_rule" "database_tasks" {
  security_group_id            = aws_security_group.database.id
  description                  = "PostgreSQL from Atlas tasks"
  referenced_security_group_id = aws_security_group.tasks.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "redis_tasks" {
  security_group_id            = aws_security_group.redis.id
  description                  = "Valkey TLS from Atlas tasks"
  referenced_security_group_id = aws_security_group.tasks.id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "search_tasks" {
  security_group_id            = aws_security_group.search.id
  description                  = "OpenSearch HTTPS from Atlas tasks"
  referenced_security_group_id = aws_security_group.tasks.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_iam_role" "ecs_execution" {
  name = "${local.name}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "managed-database-secret"
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
      Resource = [
        aws_db_instance.postgres.master_user_secret[0].secret_arn,
        aws_secretsmanager_secret.redis.arn,
        aws_kms_key.atlas.arn,
      ]
    }]
  })
}

resource "aws_iam_role" "task" {
  name = "${local.name}-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "task" {
  name = "atlas-runtime"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "RawObjectStore"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [aws_s3_bucket.raw.arn, "${aws_s3_bucket.raw.arn}/*"]
      },
      {
        Sid      = "BlobEncryption"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
        Resource = aws_kms_key.atlas.arn
      },
      {
        Sid      = "SearchDocuments"
        Effect   = "Allow"
        Action   = ["es:ESHttpDelete", "es:ESHttpGet", "es:ESHttpHead", "es:ESHttpPatch", "es:ESHttpPost", "es:ESHttpPut"]
        Resource = "${aws_opensearch_domain.documents.arn}/*"
      }
    ]
  })
}
