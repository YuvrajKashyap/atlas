# Threat model

## Protected assets

- AWS and Vercel control credentials
- Cognito identities and role claims
- Crawl definitions, frontier state, and audit history
- Raw fetched HTML and extracted corpus content
- Network access available to workers
- Search integrity and public benchmark evidence

## Trust boundaries

The public browser, Vercel function, Cognito, FastAPI, PostgreSQL, disposable workers, public websites, object storage, and OpenSearch are separate trust zones. Only PostgreSQL can authorize a pipeline transition. Only FastAPI accepts operator mutations. Workers are treated as restartable and potentially stale.

## Primary threats and controls

| Threat | Controls | Residual risk |
|---|---|---|
| SSRF / cloud metadata access | HTTP(S) only, ports 80/443, DNS public-address validation, pinned resolver, redirect revalidation, no credentials in URLs | Public services that proxy private content remain an application-level risk |
| DNS rebinding | Resolve and validate before connection; connector uses approved IPs; redirects repeat policy | Long-lived connection behavior depends on aiohttp connector semantics and is fault-tested |
| Crawl escape | Explicit allowed domains, normalized hosts, optional subdomains, depth/page/duration budgets | A compromised administrator can intentionally allow a broad domain |
| Queue loss or duplication | PostgreSQL task ledger, unique stage generation, leases, token-checked commits, scheduler recovery | Database corruption requires backup recovery |
| Stale worker writes | Opaque UUID lease token required for heartbeat and completion | Long database stalls may force safe duplicate computation |
| Unauthorized operations | Cognito OIDC signature/issuer/audience validation, viewer/admin groups, API-side checks, Redis rate limits | Session tokens remain bearer credentials; XSS prevention matters |
| Raw-content disclosure | Private S3 bucket, public access block, KMS encryption, task-scoped IAM, retention | Crawled public pages may still contain accidentally exposed personal data |
| Search tampering / drift | Durable outbox, stable IDs, versioned builds, expected-count verification, alias promotion | Relevance quality still requires benchmark review |
| Fake operational evidence | Dashboards query persisted metrics; benchmark page accepts only checked-in artifacts | A malicious committer could falsify an artifact; signed releases are a future control |
| Cost runaway | Pre-apply Infracost ceiling, required expiration, autoscaling caps, AWS Budgets, protected workflows, cleanup cron, tag audit | Provider outages can delay destruction; budget alerts are not hard spend stops |
| Supply-chain compromise | Lockfiles, Dependabot, CodeQL, Trivy, SBOM, immutable ECR tags, GitHub OIDC | Upstream zero-days remain possible |

## Explicit non-goals

Atlas does not bypass authentication, CAPTCHAs, paywalls, or anti-bot mechanisms. It is not a browser-exploitation sandbox and does not execute fetched JavaScript. Multi-tenant untrusted customer crawling is outside the current authorization model.
