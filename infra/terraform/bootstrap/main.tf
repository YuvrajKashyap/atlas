resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

resource "aws_iam_role" "github" {
  name = "AtlasGitHubDeployRole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_owner}/${var.github_repository}:environment:${var.github_environment}"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github" {
  name = "AtlasEnvironmentLifecycle"
  role = aws_iam_role.github.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AtlasServices"
        Effect = "Allow"
        Action = [
          "application-autoscaling:*",
          "budgets:*",
          "cloudfront:*",
          "cloudwatch:*",
          "cognito-idp:*",
          "ec2:*",
          "ecr:*",
          "ecs:*",
          "elasticache:*",
          "elasticloadbalancing:*",
          "es:*",
          "kms:*",
          "logs:*",
          "rds:*",
          "s3:*",
          "secretsmanager:*",
          "servicequotas:GetServiceQuota",
          "sts:GetCallerIdentity"
        ]
        Resource = "*"
      },
      {
        Sid    = "AtlasIamRoles"
        Effect = "Allow"
        Action = ["iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PassRole", "iam:TagRole", "iam:UntagRole", "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy", "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:CreateServiceLinkedRole", "iam:DeleteServiceLinkedRole", "iam:GetServiceLinkedRoleDeletionStatus"]
        Resource = [
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/atlas-*",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/opensearchservice.amazonaws.com/*"
        ]
      }
    ]
  })
}

output "github_role_arn" { value = aws_iam_role.github.arn }
