# Crawler safety policy

Atlas is designed for small, controlled, public-web crawls.

## Enforced boundaries

- Only `http` and `https` URLs are accepted.
- Seed URLs and every redirect target must match the crawl-run allowlist.
- URL credentials, localhost names, private IP ranges, link-local addresses, loopback addresses, and cloud metadata destinations are rejected.
- DNS is resolved before fetching and redirect targets are revalidated.
- Each run has a maximum page count and maximum discovery depth.
- Each host has a conservative delay and at most one scheduled fetch at a time in the MVP.
- Robots policies are cached and decisions are persisted.
- Responses have strict time, redirect, and byte limits.
- Only HTML/XHTML responses enter the extraction pipeline.

## Explicit non-goals

Atlas does not bypass authentication, paywalls, CAPTCHAs, anti-bot systems, or access controls. It does not rotate proxies to evade restrictions and does not support anonymous public crawl creation.

## Deployment boundary

The MVP console and API do not include end-user authentication. Keep the local stack on trusted
interfaces only. Any internet-facing deployment must add identity, authorization, API rate limits,
TLS termination, secret management, and network restrictions before it is considered production-safe.
