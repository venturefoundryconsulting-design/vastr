from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def _json_safe(value):
    """Make audit details serializable by the JSON column.

    Money and stock quantities are Decimal (see app.core.money), and json.dumps
    refuses Decimal outright - so an audited sale would raise on insert rather
    than merely logging something ugly. Decimals become floats here because
    audit details are for humans reading a log, not for arithmetic; the
    authoritative values live in the typed columns.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


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
            details=_json_safe(details),
        )
    )
