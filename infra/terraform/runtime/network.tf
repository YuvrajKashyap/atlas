resource "aws_vpc" "atlas" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = local.name }
}

resource "aws_default_security_group" "atlas" {
  vpc_id = aws_vpc.atlas.id
}

resource "aws_cloudwatch_log_group" "vpc_flow" {
  name              = "/atlas/${var.environment_id}/vpc-flow"
  retention_in_days = local.log_retention_days
  kms_key_id        = aws_kms_key.atlas.arn
}

resource "aws_iam_role" "vpc_flow" {
  name = "${local.name}-vpc-flow"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "vpc-flow-logs.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "vpc_flow" {
  name = "cloudwatch-delivery"
  role = aws_iam_role.vpc_flow.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogGroups", "logs:DescribeLogStreams"]
      Resource = "${aws_cloudwatch_log_group.vpc_flow.arn}:*"
    }]
  })
}

resource "aws_flow_log" "atlas" {
  iam_role_arn    = aws_iam_role.vpc_flow.arn
  log_destination = aws_cloudwatch_log_group.vpc_flow.arn
  traffic_type    = "ALL"
  vpc_id          = aws_vpc.atlas.id
}

resource "aws_internet_gateway" "atlas" {
  vpc_id = aws_vpc.atlas.id
  tags   = { Name = local.name }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.atlas.id
  availability_zone       = local.availability_zones[count.index]
  cidr_block              = cidrsubnet(aws_vpc.atlas.cidr_block, 4, count.index)
  map_public_ip_on_launch = true

  tags = { Name = "${local.name}-public-${count.index + 1}" }
}

resource "aws_subnet" "application" {
  count             = 2
  vpc_id            = aws_vpc.atlas.id
  availability_zone = local.availability_zones[count.index]
  cidr_block        = cidrsubnet(aws_vpc.atlas.cidr_block, 4, count.index + 2)

  tags = { Name = "${local.name}-app-${count.index + 1}" }
}

resource "aws_subnet" "data" {
  count             = 2
  vpc_id            = aws_vpc.atlas.id
  availability_zone = local.availability_zones[count.index]
  cidr_block        = cidrsubnet(aws_vpc.atlas.cidr_block, 4, count.index + 4)

  tags = { Name = "${local.name}-data-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.atlas.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.atlas.id
  }
  tags = { Name = "${local.name}-public" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count  = local.production ? 2 : 0
  domain = "vpc"
  tags   = { Name = "${local.name}-nat-${count.index + 1}" }
}

resource "aws_nat_gateway" "nat" {
  count         = local.production ? 2 : 0
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  depends_on = [aws_internet_gateway.atlas]
  tags       = { Name = "${local.name}-nat-${count.index + 1}" }
}

resource "aws_route_table" "application" {
  count  = 2
  vpc_id = aws_vpc.atlas.id

  dynamic "route" {
    for_each = local.production ? [1] : []
    content {
      cidr_block     = "0.0.0.0/0"
      nat_gateway_id = aws_nat_gateway.nat[count.index].id
    }
  }

  tags = { Name = "${local.name}-app-${count.index + 1}" }
}

resource "aws_route_table_association" "application" {
  count          = 2
  subnet_id      = aws_subnet.application[count.index].id
  route_table_id = aws_route_table.application[count.index].id
}

resource "aws_route_table" "data" {
  vpc_id = aws_vpc.atlas.id
  tags   = { Name = "${local.name}-data" }
}

resource "aws_route_table_association" "data" {
  count          = 2
  subnet_id      = aws_subnet.data[count.index].id
  route_table_id = aws_route_table.data.id
}
