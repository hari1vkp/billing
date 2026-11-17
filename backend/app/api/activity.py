from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_owner
from app.schemas.activity import ActivityLogOut
from app.schemas.common import Paginated
from app.services import audit_service

router = APIRouter(prefix="/activity", tags=["Activity Audit Log"])


@router.get("", response_model=Paginated[ActivityLogOut])
def list_activity(
    category: str | None = None,
    action: str | None = None,
    user_id: str | None = None,
    query: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user=Depends(require_owner),
    db: Session = Depends(get_db),
):
    items, total = audit_service.list_activity(
        db,
        user.business_id,
        category=category,
        action=action,
        user_id=user_id,
        query=query,
        from_date=from_date,
        to_date=to_date,
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return Paginated(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, (total + page_size - 1) // page_size),
    )
