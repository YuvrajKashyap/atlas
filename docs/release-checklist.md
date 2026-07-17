# Release checklist

- [x] Permanent Vite site deployed to the personal Vercel project
- [x] Edge Config runtime contract created and initialized offline
- [x] Browser verifies backend health before enabling console actions
- [x] Missing or invalid runtime state fails closed
- [x] OIDC viewer/admin enforcement and audit events implemented
- [x] Transactional stage tasks, leases, heartbeats, retries, and dead letters implemented
- [x] Durable index outbox and versioned index builds implemented
- [x] Document resources, observations, versions, change classes, and duplicate clusters implemented
- [x] Terraform `showcase` and `production` profiles validate
- [x] Protected launch, teardown, cost, expiration, and cleanup workflows pass `actionlint`
- [x] Backend coverage at least 85%; critical scheduler/worker/fetch/robots/task/index modules at least 90%
- [x] Deterministic 10,000-page fault run passed and [artifact published](../web/public/benchmarks/latest.json)
- [ ] Authenticated Playwright live-console journey passed
- [ ] AWS recovery exercise met RPO/RTO target
- [ ] Teardown audit proved no active billable Atlas resources
- [ ] Clean-checkout AWS runtime recreation passed
- [x] Public GitHub repository published with green CI and CodeQL
- [ ] Signed release tag, final screenshots, and demo recording published

Unchecked items are release blockers, not aspirational polish.

## Published evidence

- Permanent project record: <https://atlas.yuvrajkashyap.com>
- Verified benchmark workflow: <https://github.com/YuvrajKashyap/atlas/actions/runs/29606520125>
- Tested benchmark commit: [`cedd63358985fbae7ceff8b8041a90d40657f3ba`](https://github.com/YuvrajKashyap/atlas/commit/cedd63358985fbae7ceff8b8041a90d40657f3ba)
- Verified corpus artifact: [`web/public/benchmarks/latest.json`](../web/public/benchmarks/latest.json)

The launch workflow now treats the authenticated Playwright journey as a release gate and uploads its JSON evidence plus screenshot. The remaining unchecked items cannot be claimed until the expiring AWS rehearsal and teardown complete.
