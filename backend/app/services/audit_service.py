"""Best-effort activity audit logging.

Every write happens inside a SAVEPOINT: a failure to log (bad JSON, a DB
hiccup, ...) is rolled back in isolation and can never break the business
transaction that triggered it. The main entity change stays intact.
"""

import logging
from datetime import date

from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.user import User

logger = logging.getLogger(__name__)


def actor_name(db: Session, user_id: str | None, fallback: str | None = None) -> str:
    """Resolve a stable snapshot name for the actor of an action."""
    if fallback:
        return fallback
    if not user_id:
        return "system"
    user = db.get(User, user_id)
    return user.full_name if user else "unknown"


def log_activity(
    db: Session,
    business_id: str,
    user_id: str | None = None,
    user_name: str | None = None,
    action: str = "",
    category: str = "",
    reference: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict | None = None,
) -> ActivityLog | None:
    """Append an activity entry without ever failing the caller's request."""
    entry = ActivityLog(
        business_id=business_id,
        user_id=user_id,
        user_name=actor_name(db, user_id, user_name),
        action=action,
        category=category,
        reference=reference,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    try:
        with db.begin_nested():
            db.add(entry)
        return entry
    except Exception:
        logger.exception("Could not write activity log for action=%s", action)
        return None


def list_activity(
    db: Session,
    business_id: str,
    *,
    category: str | None = None,
    action: str | None = None,
    user_id: str | None = None,
    query: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    skip: int = 0,
    limit: int = 20,
):
    stmt = select(ActivityLog).where(ActivityLog.business_id == business_id)
    if category:
        stmt = stmt.where(ActivityLog.category == category)
    if action:
        stmt = stmt.where(ActivityLog.action == action)
    if user_id:
        stmt = stmt.where(ActivityLog.user_id == user_id)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            or_(
                ActivityLog.user_name.ilike(like),
                ActivityLog.action.ilike(like),
                ActivityLog.category.ilike(like),
                func.coalesce(ActivityLog.reference, "").ilike(like),
                func.coalesce(ActivityLog.entity_id, "").ilike(like),
            )
        )
    if from_date:
        stmt = stmt.where(cast(ActivityLog.created_at, Date) >= from_date)
    if to_date:
        stmt = stmt.where(cast(ActivityLog.created_at, Date) <= to_date)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    items = list(
        db.execute(
            stmt.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
            .offset(skip)
            .limit(limit)
        ).scalars().all()
    )
    return items, total
