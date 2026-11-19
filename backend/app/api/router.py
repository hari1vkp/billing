from fastapi import APIRouter

from app.api import (
    activity,
    analytics,
    auth,
    business,
    customers,
    imports,
    inventory,
    invoices,
    payments,
    pos,
    products,
    public,
    suppliers,
    webhooks,
)
from app.core.config import settings

api_router = APIRouter(prefix=settings.API_PREFIX)

api_router.include_router(auth.router)
api_router.include_router(business.router)
api_router.include_router(customers.router)
# Static import/barcode paths must be registered before /products/{product_id}
# so they are never shadowed by the dynamic product routes.
api_router.include_router(imports.router)
api_router.include_router(imports.barcode_router)
api_router.include_router(imports.ai_router)
api_router.include_router(imports.labels_router)
# Supplier routes are registered before the product CRUD routes. They have
# their own /suppliers prefix so they are never shadowed by product paths.
api_router.include_router(suppliers.router)
api_router.include_router(products.router)
api_router.include_router(invoices.router)
api_router.include_router(payments.router)
api_router.include_router(pos.router)
api_router.include_router(analytics.router)
api_router.include_router(inventory.router)
api_router.include_router(activity.router)
api_router.include_router(public.router)
api_router.include_router(webhooks.router)
