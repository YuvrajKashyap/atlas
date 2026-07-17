# Teardown runbook

Run **destroy Atlas runtime** with the exact environment ID and original profile. The workflow is intentionally valid even after the public lease has expired.

1. Read Terraform outputs from the environment-specific versioned state bucket.
2. Publish `stopping`.
3. Authenticate, request stops for active runs, and wait for leased tasks to drain.
4. Export runs, metrics, events, tasks, incidents, workers, index builds, and system state.
5. Scale ECS services to zero.
6. Publish `offline` before removing the API.
7. Destroy Terraform resources.
8. Delete all versions and delete markers from the state bucket, then remove the bucket.
9. Query the Resource Groups Tagging API until no active non-KMS Atlas resource remains.

KMS keys enter AWS’s mandatory pending-deletion window and are excluded from the active-resource failure because pending keys do not serve traffic. Any other surviving tagged ARN fails teardown and requires investigation before the environment is considered closed.

The expiration backstop checks Edge Config every fifteen minutes and dispatches this workflow if the lease is overdue. It is a safety net, not a substitute for deliberate teardown after a demo.
