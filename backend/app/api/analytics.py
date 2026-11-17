import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_owner
from app.models.user import User
from app.schemas.analytics import AnalyticsResponse
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["Business Analytics"])


@router.get("", response_model=AnalyticsResponse)
def analytics(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return analytics_service.build_analytics(db, user.business_id, from_date, to_date)


@router.get("/dashboard", response_model=AnalyticsResponse)
def dashboard(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    return analytics_service.build_analytics(db, user.business_id)


@router.get("/reports/sales.csv")
def sales_report(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    rows = analytics_service.sales_csv_rows(db, user.business_id, from_date, to_date)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Invoice", "Issue Date", "Customer", "Status", "Subtotal",
            "Discount", "Tax", "Total", "Paid", "Balance",
        ]
    )
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sales-report.csv"'},
    )
