from sqlalchemy.orm import Session

from app.models.customer import Customer, CustomerInteraction
from app.repositories.customer_repo import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerDetail, CustomerUpdate, InteractionCreate
from app.services import audit_service


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


def list_customers(db: Session, business_id: str, query, skip, limit):
    return CustomerRepository(db).search(business_id, query, skip, limit)


def get_customer(db: Session, business_id: str, customer_id: str) -> Customer:
    customer = CustomerRepository(db).get_for_business(business_id, customer_id)
    if not customer:
        raise NotFoundError("Customer not found")
    return customer


def get_customer_detail(db: Session, business_id: str, customer_id: str) -> CustomerDetail:
    repo = CustomerRepository(db)
    customer = get_customer(db, business_id, customer_id)
    stats = repo.stats(business_id, customer_id)
    detail = CustomerDetail.model_validate(customer)
    from app.schemas.customer import CustomerStats, InteractionOut

    detail.stats = CustomerStats(**stats)
    detail.interactions = [
        InteractionOut.model_validate(i) for i in repo.interactions(business_id, customer_id)
    ]
    return detail


def create_customer(
    db: Session, business_id: str, data: CustomerCreate, user_id: str | None = None
) -> Customer:
    customer = Customer(business_id=business_id, **data.model_dump())
    db.add(customer)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="customer.create",
        category="customer",
        reference=customer.phone,
        entity_type="customer",
        entity_id=customer.id,
        details={"name": customer.name},
    )
    return customer


def update_customer(
    db: Session,
    business_id: str,
    customer_id: str,
    data: CustomerUpdate,
    user_id: str | None = None,
) -> Customer:
    customer = get_customer(db, business_id, customer_id)
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(customer, key, value)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="customer.update",
        category="customer",
        reference=customer.phone,
        entity_type="customer",
        entity_id=customer.id,
        details={"changed_fields": sorted(payload.keys())},
    )
    return customer


def delete_customer(
    db: Session, business_id: str, customer_id: str, user_id: str | None = None
) -> None:
    customer = get_customer(db, business_id, customer_id)
    from app.models.invoice import Invoice

    has_invoices = db.query(Invoice).filter(Invoice.customer_id == customer_id).first()
    if has_invoices:
        raise ConflictError("Customer has invoices and cannot be deleted; deactivate instead")
    name, phone = customer.name, customer.phone
    db.delete(customer)
    db.flush()
    audit_service.log_activity(
        db,
        business_id,
        user_id=user_id,
        action="customer.delete",
        category="customer",
        reference=phone,
        entity_type="customer",
        entity_id=customer_id,
        details={"name": name},
    )


def add_interaction(
    db: Session,
    business_id: str,
    customer_id: str,
    user_id: str,
    data: InteractionCreate,
) -> CustomerInteraction:
    get_customer(db, business_id, customer_id)
    interaction = CustomerInteraction(
        business_id=business_id,
        customer_id=customer_id,
        created_by=user_id,
        type=data.type,
        content=data.content,
    )
    return CustomerRepository(db).add_interaction(interaction)
