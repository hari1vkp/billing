from datetime import date

from pydantic import BaseModel


class TrendPoint(BaseModel):
    period: str
    sales: float = 0
    collections: float = 0
    invoices: int = 0


class MethodBreakdown(BaseModel):
    method: str
    amount: float
    count: int
    percentage: float


class TopProduct(BaseModel):
    product_id: str | None = None
    name: str
    quantity_sold: float
    revenue: float
    invoice_count: int


class TopCustomer(BaseModel):
    customer_id: str
    name: str
    total_purchases: float
    invoice_count: int
    outstanding: float


class StatusBreakdown(BaseModel):
    status: str
    count: int
    amount: float


class Summary(BaseModel):
    total_sales: float = 0
    total_collections: float = 0
    total_invoices: int = 0
    total_transactions: int = 0
    outstanding: float = 0
    growth_percent: float = 0
    average_invoice_value: float = 0


class AnalyticsResponse(BaseModel):
    from_date: date | None = None
    to_date: date | None = None
    summary: Summary
    # Today / current period snapshots (always computed from real records)
    today_sales: float = 0
    today_transactions: int = 0
    today_collections: float = 0
    week_sales: float = 0
    week_collections: float = 0
    month_sales: float = 0
    month_collections: float = 0
    year_sales: float = 0
    weekly_trend: list[TrendPoint] = []
    pending_amount: float = 0
    pending_invoices: int = 0
    low_stock_products: int = 0
    total_customers: int = 0
    active_customers: int = 0
    sales_trend: list[TrendPoint] = []
    payment_methods: list[MethodBreakdown] = []
    top_products: list[TopProduct] = []
    top_customers: list[TopCustomer] = []
    status_breakdown: list[StatusBreakdown] = []

    # Recent records for the dashboard feed
    recent_invoices: list[dict] = []
    recent_payments: list[dict] = []
