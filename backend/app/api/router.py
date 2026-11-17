from fastapi import APIRouter

from app.api import (
    activity,
    analytics,
    auth,
    business,
    customers,
    inventory,
    invoices,
    payments,
    products,
    public,
    webhooks,
)
from app.core.config import settings

api_router = APIRouter(prefix=settings.API_PREFIX)

api_router.include_router(auth.router)
api_router.include_router(business.router)
api_router.include_router(customers.router)
api_router.include_router(products.router)
api_router.include_router(invoices.router)
api_router.include_router(payments.router)
api_router.include_router(analytics.router)
api_router.include_router(inventory.router)
api_router.include_router(activity.router)
api_router.include_router(public.router)
api_router.include_router(webhooks.router)
