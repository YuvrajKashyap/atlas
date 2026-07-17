resource "aws_cloudwatch_log_group" "api" {
  name              = "/atlas/${var.environment_id}/api"
  retention_in_days = local.log_retention_days
  kms_key_id        = aws_kms_key.atlas.arn
}

resource "aws_cloudwatch_log_group" "scheduler" {
  name              = "/atlas/${var.environment_id}/scheduler"
  retention_in_days = local.log_retention_days
  kms_key_id        = aws_kms_key.atlas.arn
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/atlas/${var.environment_id}/worker"
  retention_in_days = local.log_retention_days
  kms_key_id        = aws_kms_key.atlas.arn
}

resource "aws_cloudwatch_log_group" "opensearch" {
  name              = "/atlas/${var.environment_id}/opensearch"
  retention_in_days = local.log_retention_days
  kms_key_id        = aws_kms_key.atlas.arn
}

resource "aws_cloudwatch_log_resource_policy" "opensearch" {
  policy_name = "${local.name}-opensearch-logs"
  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "es.amazonaws.com" }
      Action    = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource  = "${aws_cloudwatch_log_group.opensearch.arn}:*"
    }]
  })
}

resource "aws_ecs_cluster" "atlas" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "atlas" {
  cluster_name       = aws_ecs_cluster.atlas.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = local.production ? "FARGATE" : "FARGATE_SPOT"
    weight            = 1
  }
}

resource "aws_lb" "api" {
  name               = substr(local.name, 0, 32)
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = false
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "api" {
  name        = substr("${local.name}-api", 0, 32)
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.atlas.id

  health_check {
    enabled             = true
    path                = "/health"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 20
    timeout             = 5
  }

  deregistration_delay = 30
}

resource "aws_lb_listener" "api" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_cloudfront_distribution" "api" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Atlas ${var.environment_id} API TLS boundary"
  price_class         = "PriceClass_100"
  http_version        = "http2and3"
  default_root_object = "health"

  origin {
    domain_name = aws_lb.api.dns_name
    origin_id   = "atlas-alb"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id           = "atlas-alb"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods             = ["GET", "HEAD"]
    cache_policy_id            = "413f160f-3c16-4f65-9b81-d5527b1b5e43"
    origin_request_policy_id   = "216adef6-5c7f-47e4-b989-5492eafa07d3"
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
    compress                   = true
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    minimum_protocol_version       = "TLSv1.2_2021"
  }
}

data "aws_cloudfront_response_headers_policy" "security" {
  name = "Managed-SecurityHeadersPolicy"
}

locals {
  log_configuration = {
    api = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }
    scheduler = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.scheduler.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "scheduler"
      }
    }
    worker = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.worker.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "worker"
      }
    }
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = local.production ? 1024 : 512
  memory                   = local.production ? 2048 : 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name             = "api"
    image            = var.container_image
    essential        = true
    command          = ["python", "-m", "atlas.runtime", "api"]
    environment      = local.common_environment
    secrets          = local.common_secrets
    portMappings     = [{ containerPort = 8000, hostPort = 8000, protocol = "tcp" }]
    logConfiguration = local.log_configuration.api
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\""]
      interval    = 20
      timeout     = 5
      retries     = 3
      startPeriod = 45
    }
  }])
}

resource "aws_ecs_task_definition" "scheduler" {
  family                   = "${local.name}-scheduler"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name             = "scheduler"
    image            = var.container_image
    essential        = true
    command          = ["python", "-m", "atlas.runtime", "scheduler"]
    environment      = local.common_environment
    secrets          = local.common_secrets
    logConfiguration = local.log_configuration.scheduler
  }])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = local.production ? 2048 : 1024
  memory                   = local.production ? 4096 : 2048
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name             = "worker"
    image            = var.container_image
    essential        = true
    command          = ["python", "-m", "atlas.runtime", "worker"]
    environment      = local.common_environment
    secrets          = local.common_secrets
    logConfiguration = local.log_configuration.worker
  }])
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.atlas.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = local.api_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.application_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = local.assign_public_ip
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  deployment_minimum_healthy_percent = local.production ? 100 : 0
  deployment_maximum_percent         = 200

  depends_on = [aws_lb_listener.api]
}

resource "aws_ecs_service" "scheduler" {
  name            = "scheduler"
  cluster         = aws_ecs_cluster.atlas.id
  task_definition = aws_ecs_task_definition.scheduler.arn
  desired_count   = local.scheduler_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.application_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = local.assign_public_ip
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}

resource "aws_ecs_service" "worker" {
  name            = "worker"
  cluster         = aws_ecs_cluster.atlas.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = local.worker_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.application_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = local.assign_public_ip
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}
