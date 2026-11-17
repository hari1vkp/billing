from datetime import datetime

from app.schemas.common import ORMModel


class ActivityLogOut(ORMModel):
    id: str
    business_id: str
    user_id: str | None = None
    user_name: str
    action: str
    category: str
    reference: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    details: dict | None = None
    created_at: datetime
