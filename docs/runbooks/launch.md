# Launch runbook

## Preconditions

1. The public repository default branch is green.
2. The `atlas-showcase` GitHub Environment requires an approving reviewer.
3. Repository secrets exist for the AWS OIDC role, Vercel management token/team/Edge Config IDs, Infracost, budget email, and demo password.
4. The demo user email is controlled by the operator.
5. No other Atlas runtime is `starting`, `online`, `degraded`, or `stopping`.

## Procedure

Run **launch Atlas runtime** with profile, explicit lifetime, cost ceiling, and demo email. Review the Infracost output before approving the protected environment. The workflow will:

1. Create a versioned, encrypted environment-specific state bucket.
2. Plan the entire topology and reject a prorated estimate over the declared ceiling.
3. Publish `starting` to Edge Config.
4. Build an immutable ECR image and apply Terraform.
5. Wait for migration-guarded ECS services.
6. Provision the temporary Cognito administrator.
7. Prove unauthenticated denial, authenticated access, and a one-page crawl through indexing.
8. Publish the verified CloudFront API URL and expiration as `online`.

Do not manually set Edge Config to `online`. If a launch fails, its failure path attempts a complete Terraform rollback and returns the public state to `offline`.

## Verification

- `/api/runtime` says `online` with the expected environment and expiration.
- `/status` reports browser verification.
- `/console` redirects to Cognito and returns with an authorized session.
- The workflow artifact contains the persisted smoke run and cost estimate.
