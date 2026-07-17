# Launch runbook

## Preconditions

1. The public repository default branch is green.
2. The `atlas-showcase` GitHub Environment requires an approving reviewer.
3. Repository secrets exist for the AWS OIDC role, Vercel management token/team/Edge Config IDs, Infracost, budget email, and demo password.
4. The demo user email is controlled by the operator.
5. No other Atlas runtime is `starting`, `online`, `degraded`, or `stopping`.

## Procedure

Run **launch Atlas runtime** with profile, explicit lifetime, cost ceiling, and demo email. The operator-entered ceiling is enforced against a read-only Infracost plan before resource creation. The workflow will:

1. Validate every required secret, the bounded lifetime, environment ID, and operator-entered cost ceiling.
2. Authenticate through GitHub OIDC and create a read-only Terraform plan with the backend disabled.
3. Produce the prorated Infracost estimate and stop before creating any AWS resource when it exceeds the declared ceiling.
4. Create the versioned, encrypted environment-specific state bucket only after the cost gate passes.
5. Publish `starting` to Edge Config.
6. Build an immutable ECR image and apply Terraform.
7. Wait for migration-guarded ECS services.
8. Provision the temporary Cognito administrator.
9. Prove unauthenticated denial, authenticated access, and a one-page crawl through indexing.
10. Publish the verified CloudFront API URL and expiration as `online`.
11. Run Playwright against the permanent domain with the ephemeral Cognito token, verify the operational surfaces, and capture browser evidence.

Do not manually set Edge Config to `online`. If a launch fails, its failure path attempts a complete Terraform rollback and returns the public state to `offline`.

## Verification

- `/api/runtime` says `online` with the expected environment and expiration.
- `/status` reports browser verification.
- `/console` accepts the ephemeral Cognito-issued token and renders persisted operational data without API or browser errors.
- The workflow artifact contains the persisted smoke run, authenticated-browser JSON and screenshot, and cost estimate.
