from sqlalchemy.orm import Session

from atlas.auth import Principal
from atlas.models import AuditEvent


def record_audit(
    session: Session,
    principal: Principal,
    action: str,
    resource_type: str,
    resource_id: str | None,
    *,
    payload: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_id=principal.subject,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload or {},
        )
    )
