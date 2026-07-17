# Incident and recovery runbook

## Queue loss

Stop Redis/Valkey delivery, retain PostgreSQL, and allow the scheduler to scan `ready` and `retry_scheduled` tasks. Confirm new RQ IDs are generated from stable task IDs and generations. No frontier row should be reset manually.

## Worker termination or stale lease

Verify the heartbeat stopped and the lease passed `lease_expires_at`. The scheduler should clear domain permits and return the task to an eligible state. A late worker commit must fail its lease-token update.

## OpenSearch outage

Keep fetch and extract workers running if PostgreSQL/S3 are healthy. Index operations should move to retry state without new fetch attempts. After search recovery, verify outbox terminality and compare active index count to authoritative current documents.

## PostgreSQL interruption

Workers should fail the current transaction without committing partial state. Restore connectivity, inspect incidents and expired leases, then allow normal recovery. For data loss, restore RDS to the selected point in time and rebuild Redis notifications and OpenSearch from PostgreSQL/S3.

## Suspected crawl-policy violation

Publish `degraded`, stop new runs, request stop on active runs, and preserve events, fetch attempts, DNS/redirect evidence, and domain permits. Do not resume until the URL policy and affected target range are understood.

## Index rebuild failure

Keep the current read alias. Mark the build failed with the physical index and error. Repair or delete only the failed physical index. A failed build must never switch the alias.

## Escalation and closure

Create or retain an `OperationalIncident`, record severity and scope, acknowledge it, and resolve only after the relevant invariant query passes. Export evidence before destroying an affected disposable environment.
