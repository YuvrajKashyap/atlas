# ADR 0002: Permanent Vercel record and expiring AWS runtime

Status: accepted

## Context

RDS, ElastiCache, OpenSearch, NAT gateways, and load balancers accrue cost while idle. A portfolio project still needs a stable URL and honest product story between demonstrations.

## Decision

Keep the Vite application and a small runtime-state function on Vercel. Create the AWS execution plane only through a protected, expiring workflow. Publish `online` only after migrations, authentication, health, and a controlled crawl pass. Destroy AWS after use while the public site remains intentionally offline.

## Consequences

The UI must handle offline as a primary state. Cognito discovery is dynamic because the user pool is recreated. A demo requires a lead time for managed services to provision. Ongoing AWS cost can approach zero after a proven teardown.
