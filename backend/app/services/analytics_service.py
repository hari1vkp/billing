"""Business analytics computed exclusively from persisted records."""

from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import Date, func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.product import Product
from app.repositories.invoice_repo import InvoiceRepository
from app.repositories.payment_repo import PaymentRepository
from app.schemas.analytics import (
    AnalyticsResponse,
    MethodBreakdown,
    StatusBreakdown,
    Summary,
    TopCustomer,
    TopProduct,
    TrendPoint,
)


def _f(value) -> float:
    return round(float(value or 0), 2)


def _payment_date_col():
    # Confirmed payments use payment_date when supplied, else creation date.
    return func.coalesce(Payment.payment_date, func.cast(Payment.created_at, Date))


def _sales_sum(db, business_id, start: date | None, end: date | None) -> float:
    stmt = select(func.coalesce(func.sum(Invoice.total_amount), 0)).where(
        Invoice.business_id == business_id, Invoice.status != "cancelled"
    )
    if start:
        stmt = stmt.where(Invoice.issue_date >= start)
    if end:
        stmt = stmt.where(Invoice.issue_date <= end)
    return _f(db.execute(stmt).scalar_one())


def _invoice_count(db, business_id, start, end) -> int:
    stmt = select(func.count(Invoice.id)).where(
        Invoice.business_id == business_id, Invoice.status != "cancelled"
    )
    if start:
        stmt = stmt.where(Invoice.issue_date >= start)
    if end:
        stmt = stmt.where(Invoice.issue_date <= end)
    return int(db.execute(stmt).scalar_one())


def _collections_sum(db, business_id, start, end) -> float:
    stmt = select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.business_id == business_id, Payment.status == "confirmed"
    )
    if start:
        stmt = stmt.where(_payment_date_col() >= start)
    if end:
        stmt = stmt.where(_payment_date_col() <= end)
    return _f(db.execute(stmt).scalar_one())


def _collection_count(db, business_id, start, end) -> int:
    stmt = select(func.count(Payment.id)).where(
        Payment.business_id == business_id, Payment.status == "confirmed"
    )
    if start:
        stmt = stmt.where(_payment_date_col() >= start)
    if end:
        stmt = stmt.where(_payment_date_col() <= end)
    return int(db.execute(stmt).scalar_one())


def _month_bounds(d: date) -> tuple[date, date]:
    return d.replace(day=1), d.replace(day=monthrange(d.year, d.month)[1])


def build_analytics(
    db: Session, business_id: str, from_date: date | None = None, to_date: date | None = None
) -> AnalyticsResponse:
    today = date.today()
    month_start, month_end = _month_bounds(today)
    year_start, year_end = date(today.year, 1, 1), date(today.year, 12, 31)

    # Snapshots (independent of the selected report range)
    today_sales = _sales_sum(db, business_id, today, today)
    today_transactions = _invoice_count(db, business_id, today, today)
    today_collections = _collections_sum(db, business_id, today, today)
    week_start = today - timedelta(days=6)
    week_sales = _sales_sum(db, business_id, week_start, today)
    week_collections = _collections_sum(db, business_id, week_start, today)
    month_sales = _sales_sum(db, business_id, month_start, month_end)
    month_collections = _collections_sum(db, business_id, month_start, month_end)
    year_sales = _sales_sum(db, business_id, year_start, year_end)

    prev_month_end = month_start - timedelta(days=1)
    prev_month_start, prev_month_end = _month_bounds(prev_month_end)
    prev_month_sales = _sales_sum(db, business_id, prev_month_start, prev_month_end)
    growth = (
        round(((month_sales - prev_month_sales) / prev_month_sales) * 100, 2)
        if prev_month_sales > 0
        else (100.0 if month_sales > 0 else 0.0)
    )

    # Filtered aggregates
    total_sales = _sales_sum(db, business_id, from_date, to_date)
    total_collections = _collections_sum(db, business_id, from_date, to_date)
    total_invoices = _invoice_count(db, business_id, from_date, to_date)
    total_transactions = _collection_count(db, business_id, from_date, to_date)

    outstanding_row = db.execute(
        select(
            func.coalesce(func.sum(Invoice.balance_amount), 0),
            func.count(Invoice.id),
        ).where(
            Invoice.business_id == business_id,
            Invoice.status.in_(["unpaid", "partially_paid"]),
        )
    ).one()
    pending_amount, pending_invoices = _f(outstanding_row[0]), int(outstanding_row[1])

    avg_invoice = round(total_sales / total_invoices, 2) if total_invoices else 0.0
    summary = Summary(
        total_sales=total_sales,
        total_collections=total_collections,
        total_invoices=total_invoices,
        total_transactions=total_transactions,
        outstanding=pending_amount,
        growth_percent=growth,
        average_invoice_value=avg_invoice,
    )

    # Monthly sales / collections trend (last 12 months ending at to_date).
    anchor = to_date or today
    trend: list[TrendPoint] = []
    cursor = anchor.replace(day=1)
    for _ in range(12):
        m_start, m_end = _month_bounds(cursor)
        sales = _sales_sum(db, business_id, m_start, m_end)
        collections = _collections_sum(db, business_id, m_start, m_end)
        count = _invoice_count(db, business_id, m_start, m_end)
        trend.append(
            TrendPoint(
                period=cursor.strftime("%b %Y"),
                sales=sales,
                collections=collections,
                invoices=count,
            )
        )
        cursor = (m_start - timedelta(days=1)).replace(day=1)
    trend.reverse()

    # Weekly trend over the last 8 weeks ending today
    weekly_trend = []
    for w in range(8, 0, -1):
        w_end = anchor - timedelta(days=7 * (w - 1))
        w_start = w_end - timedelta(days=6)
        weekly_trend.append(
            TrendPoint(
                period=w_start.strftime("%d %b"),
                sales=_sales_sum(db, business_id, w_start, w_end),
                collections=_collections_sum(db, business_id, w_start, w_end),
                invoices=_invoice_count(db, business_id, w_start, w_end),
            )
        )

    # Payment methods
    methods_raw = PaymentRepository(db).method_breakdown(business_id, from_date, to_date)
    method_total = sum(float(r[1]) for r in methods_raw) or 1
    methods = [
        MethodBreakdown(
            method=r[0],
            amount=_f(r[1]),
            count=int(r[2]),
            percentage=round(float(r[1]) / method_total * 100, 2),
        )
        for r in methods_raw
    ]

    # Top products
    products = [
        TopProduct(
            product_id=r[0],
            name=r[1] or "Item",
            quantity_sold=_f(r[2]),
            revenue=_f(r[3]),
            invoice_count=int(r[4]),
        )
        for r in InvoiceRepository(db).top_products(business_id, from_date, to_date, 5)
    ]

    # Most valuable customers
    cust_stmt = (
        select(
            Customer.id,
            Customer.name,
            func.coalesce(func.sum(Invoice.total_amount), 0),
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.balance_amount), 0),
        )
        .join(Invoice, Invoice.customer_id == Customer.id)
        .where(Invoice.business_id == business_id, Invoice.status != "cancelled")
        .group_by(Customer.id, Customer.name)
        .order_by(func.sum(Invoice.total_amount).desc())
        .limit(5)
    )
    if from_date:
        cust_stmt = cust_stmt.where(Invoice.issue_date >= from_date)
    if to_date:
        cust_stmt = cust_stmt.where(Invoice.issue_date <= to_date)
    top_customers = [
        TopCustomer(
            customer_id=r[0], name=r[1], total_purchases=_f(r[2]),
            invoice_count=int(r[3]), outstanding=_f(r[4]),
        )
        for r in db.execute(cust_stmt).all()
    ]

    # Status breakdown
    statuses = [
        StatusBreakdown(status=r[0], count=int(r[1]), amount=_f(r[2]))
        for r in InvoiceRepository(db).status_breakdown(business_id, from_date, to_date)
    ]

    # Customer / stock KPIs
    total_customers = int(
        db.execute(
            select(func.count(Customer.id)).where(
                Customer.business_id == business_id, Customer.is_active.is_(True)
            )
        ).scalar_one()
    )
    cutoff = today - timedelta(days=90)
    active_customers = int(
        db.execute(
            select(func.count(func.distinct(Invoice.customer_id))).where(
                Invoice.business_id == business_id, Invoice.issue_date >= cutoff
            )
        ).scalar_one()
    )
    low_stock = int(
        db.execute(
            select(func.count(Product.id)).where(
                Product.business_id == business_id,
                Product.track_inventory.is_(True),
                Product.stock <= Product.low_stock_threshold,
            )
        ).scalar_one()
    )

    # Recent activity feed
    recent_invoices = [
        {
            "id": i.id,
            "invoice_number": i.invoice_number,
            "customer_name": cname,
            "total_amount": _f(i.total_amount),
            "status": i.status,
            "issue_date": str(i.issue_date),
        }
        for i, cname in InvoiceRepository(db).list_detailed(
            business_id, skip=0, limit=5
        )[0]
    ]
    payments_rows, _ = PaymentRepository(db).list_detailed(
        business_id, skip=0, limit=5
    )
    recent_payments = [
        {
            "id": p.id,
            "invoice_number": num,
            "customer_name": cname,
            "amount": _f(p.amount),
            "method": p.method,
            "status": p.status,
            "created_at": str(p.created_at),
        }
        for p, num, cname in payments_rows
    ]

    return AnalyticsResponse(
        from_date=from_date,
        to_date=to_date,
        summary=summary,
        today_sales=today_sales,
        today_transactions=today_transactions,
        today_collections=today_collections,
        week_sales=week_sales,
        week_collections=week_collections,
        month_sales=month_sales,
        month_collections=month_collections,
        year_sales=year_sales,
        weekly_trend=weekly_trend,
        pending_amount=pending_amount,
        pending_invoices=pending_invoices,
        low_stock_products=low_stock,
        total_customers=total_customers,
        active_customers=active_customers,
        sales_trend=trend,
        payment_methods=methods,
        top_products=products,
        top_customers=top_customers,
        status_breakdown=statuses,
        recent_invoices=recent_invoices,
        recent_payments=recent_payments,
    )


def sales_csv_rows(db, business_id, from_date, to_date):
    """Rows for the downloadable sales report (real invoice records)."""
    rows, _ = InvoiceRepository(db).list_detailed(
        business_id, skip=0, limit=100000, date_from=from_date, date_to=to_date
    )
    out = []
    for invoice, customer_name in rows:
        out.append(
            [
                invoice.invoice_number,
                str(invoice.issue_date),
                customer_name or "",
                invoice.status,
                _f(invoice.subtotal),
                _f(invoice.discount_amount),
                _f(invoice.tax_amount),
                _f(invoice.total_amount),
                _f(invoice.paid_amount),
                _f(invoice.balance_amount),
            ]
        )
    return out
