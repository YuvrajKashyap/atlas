resource "aws_cognito_user_pool" "atlas" {
  name = local.name

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = local.production ? "ACTIVE" : "INACTIVE"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 14
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 1
  }

  mfa_configuration = "OPTIONAL"
  software_token_mfa_configuration { enabled = true }

  user_pool_add_ons {
    advanced_security_mode = local.production ? "ENFORCED" : "AUDIT"
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.atlas.id
  description  = "Atlas administrators may mutate crawl and recovery state"
  precedence   = 10
}

resource "aws_cognito_user_group" "viewer" {
  name         = "viewer"
  user_pool_id = aws_cognito_user_pool.atlas.id
  description  = "Atlas viewers may inspect operations and search the corpus"
  precedence   = 20
}

resource "aws_cognito_user_pool_client" "console" {
  name         = "atlas-console"
  user_pool_id = aws_cognito_user_pool.atlas.id

  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true
  supported_identity_providers         = ["COGNITO"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = var.cognito_callback_urls
  logout_urls                          = var.cognito_logout_urls
  explicit_auth_flows                  = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]
  access_token_validity                = 1
  id_token_validity                    = 1
  refresh_token_validity               = 1

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

resource "aws_cognito_user_pool_domain" "atlas" {
  domain       = substr(replace(local.name, "_", "-"), 0, 63)
  user_pool_id = aws_cognito_user_pool.atlas.id
}
