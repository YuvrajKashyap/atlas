# Infrastructure security exceptions

Atlas runs a permanent static control surface on Vercel and a short-lived AWS
runtime that must be completely destroyable after a demonstration. Checkov is a
hard CI gate. The policies below are skipped only where the scanner cannot model
that architecture or where a control directly conflicts with verified teardown.

## CloudFront-to-ALB transport

Policies: `CKV_AWS_2`, `CKV_AWS_68`, `CKV_AWS_86`, `CKV_AWS_91`,
`CKV_AWS_103`, `CKV_AWS_150`, `CKV_AWS_174`, `CKV_AWS_260`, `CKV_AWS_310`,
`CKV_AWS_374`, `CKV_AWS_378`, `CKV2_AWS_20`, `CKV2_AWS_28`, `CKV2_AWS_42`,
and `CKV2_AWS_47`.

CloudFront is the public TLS boundary and enforces TLS 1.2 or newer. The ALB
accepts port 80 only from AWS's managed CloudFront origin-facing prefix list;
the task security group accepts API traffic only from the ALB. The internal
CloudFront-to-ALB hop therefore uses HTTP without exposing the ALB to arbitrary
internet clients. A second certificate, duplicate WAF, duplicate access-log
bucket, origin failover, and custom domain on this temporary API endpoint would
add persistent cost and teardown state without changing the permanent Vercel
site's availability. CloudFront uses the managed security-headers policy and
AWS logging remains enabled at the application, VPC-flow, and ECS layers.

## Disposable data services

Policies: `CKV_AWS_18`, `CKV_AWS_130`, `CKV_AWS_144`, `CKV_AWS_293`,
`CKV_AWS_318`, `CKV2_AWS_50`, `CKV2_AWS_57`, `CKV2_AWS_59`, and
`CKV2_AWS_62`.

Deletion protection and cross-region replicas conflict with the required
zero-bill teardown. Showcase intentionally uses cost-bounded single-AZ data
services; production enables Multi-AZ RDS, Valkey failover, and multi-node
OpenSearch. Raw HTML is encrypted, private, versioned, and retention-limited;
verified reports are exported before destruction. S3 access is audited in the
application and VPC flow logs. The generated Valkey token lives in encrypted
Secrets Manager but is not rotated during the environment's explicitly bounded
lifetime; recreating the runtime creates a new token. The two public subnets are
reserved for the ALB and NAT gateways, while application and data workloads use
separate subnets.

## Deployment identity and KMS policy

Policies: `CKV_AWS_109`, `CKV_AWS_111`, `CKV_AWS_287`, `CKV_AWS_288`,
`CKV_AWS_289`, `CKV_AWS_290`, `CKV_AWS_355`, and `CKV_AWS_356`.

The deployment role needs lifecycle permissions because Terraform creates and
destroys the entire tagged environment. It has no static credentials: GitHub
OIDC trust is restricted to one repository, audience, and protected GitHub
environment. IAM role operations are additionally restricted to `atlas-*` and
the OpenSearch service-linked role. Service APIs whose ARNs cannot be known
before creation remain account-wide; teardown audits Atlas tags and fails if a
billable resource remains. The KMS key policy's account-root administration
statement is AWS's recovery boundary. CloudWatch access is service-principal
restricted and bound to the Atlas log-group encryption context.

## Scanner limitation

Policy: `CKV_AWS_317`.

The OpenSearch resource explicitly publishes `AUDIT_LOGS` to an encrypted,
365-day CloudWatch log group. Checkov 3.2.495 does not recognize that dynamic
configuration in this resource graph, so the check is documented rather than
allowed to conceal the actual control.

These exceptions must be revisited before converting the on-demand runtime into
an always-on service. Any newly failing Checkov policy remains a CI failure.
