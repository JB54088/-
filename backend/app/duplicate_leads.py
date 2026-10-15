from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Customer
from .utils import is_external_placeholder, normalize_phone


@dataclass(frozen=True)
class DuplicateMatch:
    customer: Customer
    reason: str


def find_duplicate_customer(db: Session, phone: str | None, wechat_id: str | None) -> DuplicateMatch | None:
    """Find an existing customer by phone first, then by exact WeChat ID.

    Names are deliberately not considered. Phone values are normalized in the
    application so old rows with harmless formatting differences still match.
    """
    normalized_phone = normalize_phone(phone)
    if normalized_phone:
        customers = db.scalars(select(Customer).order_by(Customer.id)).all()
        phone_match = next(
            (customer for customer in customers if not customer.is_deleted and not is_external_placeholder(customer) and normalize_phone(customer.phone) == normalized_phone),
            None,
        )
        if phone_match:
            return DuplicateMatch(phone_match, "phone")

    normalized_wechat = wechat_id.strip() if wechat_id and wechat_id.strip() else None
    if normalized_wechat:
        wechat_match = next(
            (customer for customer in db.scalars(select(Customer).where(Customer.wechat_id == normalized_wechat, Customer.is_deleted.is_(False)).order_by(Customer.id)).all() if not is_external_placeholder(customer)),
            None,
        )
        if wechat_match:
            return DuplicateMatch(wechat_match, "wechat")

    return None
