# Service-level objectives

These objectives apply only while an AWS runtime lease is `online`. The permanent Vercel project record has a separate availability boundary.

| SLI | Showcase objective | Production objective | Measurement |
|---|---:|---:|---|
| Public project record availability | 99.9% monthly | 99.9% monthly | Vercel external probe |
| Authenticated API availability | Best effort during declared demo | 99.9% monthly | Successful non-5xx requests |
| Scheduler recovery | 99% of expired leases eligible within 2 poll intervals | 99.9% within 2 poll intervals | Persisted task and metric samples |
| Pipeline terminality | 100% of eligible URLs reach a valid terminal state | 100% | Post-run invariant audit |
| Politeness violations | 0 | 0 | Domain lease and request timestamp audit |
| Index completeness | 100% of current, indexable documents present | 100% | Index build expected/actual verification |
| Freshness | p95 current-document index lag under 60 s | p95 under 30 s | Observation, document, and outbox timestamps |
| Recovery point | Latest automated database backup | 5 minutes or better target | RDS backup/PITR configuration |
| Recovery time | Recreate within 90 minutes | Restore within 60 minutes target | Timed recovery exercise |

An SLO is not claimed as achieved until a verified benchmark or production sample exists. The UI must display “no evidence” instead of a target line masquerading as a measurement.
