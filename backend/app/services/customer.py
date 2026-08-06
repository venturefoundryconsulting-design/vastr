from sqlalchemy.orm import Session

from app.models.customer import (
    BalanceType,
    Customer,
    CustomerBalanceAdjustment,
    CustomerLoyaltyAdjustment,
)


def adjust_credit_balance(
    db: Session,
    *,
    customer_id: int,
    amount_delta: float,
    balance_type: BalanceType = BalanceType.CREDIT,
    reference_type: str | None = None,
    reference_id: int | None = None,
    reason: str | None = None,
    created_by_id: int | None = None,
) -> CustomerBalanceAdjustment:
    """Adjusts a customer's credit_balance and writes an audit adjustment row.

    Positive amount_delta = balance increases, negative = balance decreases.
    Callers are responsible for committing the surrounding transaction.
    """
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ValueError(f"Customer {customer_id} not found")

    customer.credit_balance = float(customer.credit_balance) + amount_delta

    adjustment = CustomerBalanceAdjustment(
        customer_id=customer_id,
        balance_type=balance_type,
        amount_delta=amount_delta,
        reference_type=reference_type,
        reference_id=reference_id,
        reason=reason,
        created_by_id=created_by_id,
    )
    db.add(adjustment)
    db.flush()
    return adjustment


def adjust_loyalty_points(
    db: Session,
    *,
    customer_id: int,
    points_delta: int,
    reference_type: str | None = None,
    reference_id: int | None = None,
    reason: str | None = None,
    created_by_id: int | None = None,
) -> CustomerLoyaltyAdjustment:
    """Adjusts a customer's loyalty_points and writes an audit adjustment row.

    Positive points_delta = points earned/granted, negative = points redeemed.
    Callers are responsible for committing the surrounding transaction.
    """
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ValueError(f"Customer {customer_id} not found")

    customer.loyalty_points += points_delta

    adjustment = CustomerLoyaltyAdjustment(
        customer_id=customer_id,
        points_delta=points_delta,
        reference_type=reference_type,
        reference_id=reference_id,
        reason=reason,
        created_by_id=created_by_id,
    )
    db.add(adjustment)
    db.flush()
    return adjustment
