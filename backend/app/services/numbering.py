from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session


def next_document_number(db: Session, model, column, prefix: str) -> str:
    """Generates PREFIX-YYYYMM-#### numbers, sequential per calendar month."""
    year_month = datetime.utcnow().strftime("%Y%m")
    like_pattern = f"{prefix}-{year_month}-%"
    count = db.query(func.count()).select_from(model).filter(column.like(like_pattern)).scalar()
    return f"{prefix}-{year_month}-{count + 1:04d}"
