from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_owner
from app.models.user import User
from app.schemas.common import Paginated
from app.schemas.inventory import StockAdjustCreate, StockMovementOut
from app.services import inventory_service

router = APIRouter(prefix="/inventory", tags=["Inventory Movements"])


@router.post("/adjust", response_model=StockMovementOut)
def adjust_stock(
    data: StockAdjustCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Apply a manual stock adjustment (cashiers have reason/size limits)."""
    try:
        return inventory_service.adjust_stock(db, user.business_id, user, data)
    except inventory_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except inventory_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/movements", response_model=Paginated[StockMovementOut])
def list_movements(
    product_id: str | None = None,
    reason: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    items, total = inventory_service.list_movements(
        db,
        user.business_id,
        product_id=product_id,
        reason=reason,
        from_date=from_date,
        to_date=to_date,
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return Paginated(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, (total + page_size - 1) // page_size),
    )
