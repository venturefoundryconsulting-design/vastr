from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def log_activity(
    db: Session,
    *,
    action: str,
    tenant_id: int | None,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: dict | None = None,
) -> None:
    """Appends an audit row to the current transaction - doesn't commit itself,
    so it rides along with whatever commit the calling endpoint already does."""
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
    )
