from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.models.customer import Customer
from app.models.discount import DiscountRule, DiscountScope, DiscountType
from app.models.product import ProductVariant
from app.schemas.discount import DiscountApplyResult, DiscountCartItem


def _matching_lines(
    rule: DiscountRule, items: list[DiscountCartItem], variants: dict[int, ProductVariant]
) -> list[tuple[float, int]]:
    """Cart lines (unit_price, quantity) that fall under this rule's scope."""
    matched = []
    for item in items:
        variant = variants.get(item.variant_id)
        if not variant:
            continue
        if rule.scope == DiscountScope.ALL:
            matched.append((item.unit_price, item.quantity))
        elif rule.scope == DiscountScope.CATEGORY:
            if variant.product and variant.product.category_id == rule.category_id:
                matched.append((item.unit_price, item.quantity))
        elif rule.scope == DiscountScope.BRAND:
            if (
                variant.product
                and variant.product.brand
                and rule.brand
                and variant.product.brand.strip().lower() == rule.brand.strip().lower()
            ):
                matched.append((item.unit_price, item.quantity))
        elif rule.scope == DiscountScope.PRODUCT:
            if variant.product_id == rule.product_id:
                matched.append((item.unit_price, item.quantity))
    return matched


def _compute_amount(rule: DiscountRule, matching: list[tuple[float, int]]) -> float:
    matching_subtotal = sum(price * qty for price, qty in matching)
    if matching_subtotal <= 0:
        return 0.0

    if rule.discount_type == DiscountType.PERCENTAGE:
        amount = matching_subtotal * float(rule.value) / 100
    elif rule.discount_type == DiscountType.FLAT:
        amount = float(rule.value)
    else:  # BOGO
        if not rule.buy_quantity or not rule.get_quantity:
            return 0.0
        group_size = rule.buy_quantity + rule.get_quantity
        total_qty = sum(qty for _, qty in matching)
        free_units = (total_qty // group_size) * rule.get_quantity
        if free_units <= 0:
            return 0.0
        unit_prices = sorted(
            (price for price, qty in matching for _ in range(qty))
        )
        amount = sum(unit_prices[:free_units])

    if rule.max_discount_amount is not None:
        amount = min(amount, float(rule.max_discount_amount))
    return round(min(amount, matching_subtotal), 2)


def _is_eligible(
    rule: DiscountRule,
    items: list[DiscountCartItem],
    customer: Customer | None,
    today: date,
) -> str | None:
    """Returns an error message if ineligible, else None."""
    if not rule.is_active:
        return "This discount is no longer active"
    if rule.start_date and today < rule.start_date:
        return "This discount hasn't started yet"
    if rule.end_date and today > rule.end_date:
        return "This discount has expired"
    if rule.usage_limit is not None and rule.times_used >= rule.usage_limit:
        return "This discount has reached its usage limit"
    if rule.vip_only and not (customer and customer.is_vip):
        return "This discount is only available to VIP customers"
    cart_subtotal = sum(i.unit_price * i.quantity for i in items)
    if cart_subtotal < float(rule.min_purchase_amount):
        return f"Minimum purchase of ₹{float(rule.min_purchase_amount):.2f} required"
    return None


def find_best_automatic_discount(
    db: Session, items: list[DiscountCartItem], customer: Customer | None
) -> DiscountApplyResult:
    if not items:
        return DiscountApplyResult(applied=False, message="Cart is empty")

    variants = _load_variants(db, items)
    today = date.today()
    rules = (
        db.query(DiscountRule)
        .filter(DiscountRule.code.is_(None), DiscountRule.is_active.is_(True))
        .all()
    )

    best: tuple[DiscountRule, float] | None = None
    for rule in rules:
        if _is_eligible(rule, items, customer, today) is not None:
            continue
        matching = _matching_lines(rule, items, variants)
        amount = _compute_amount(rule, matching)
        if amount <= 0:
            continue
        if best is None or amount > best[1]:
            best = (rule, amount)

    if not best:
        return DiscountApplyResult(applied=False, message="No automatic discounts available")

    rule, amount = best
    return DiscountApplyResult(
        applied=True,
        rule_id=rule.id,
        rule_name=rule.name,
        code=None,
        discount_amount=amount,
        message=f"{rule.name} applied automatically",
    )


def apply_coupon(
    db: Session, code: str, items: list[DiscountCartItem], customer: Customer | None
) -> DiscountApplyResult:
    if not items:
        return DiscountApplyResult(applied=False, message="Cart is empty")

    rule = (
        db.query(DiscountRule)
        .filter(DiscountRule.code.isnot(None), DiscountRule.code.ilike(code.strip()))
        .first()
    )
    if not rule:
        return DiscountApplyResult(applied=False, message="Invalid coupon code")

    error = _is_eligible(rule, items, customer, date.today())
    if error:
        return DiscountApplyResult(applied=False, message=error)

    variants = _load_variants(db, items)
    matching = _matching_lines(rule, items, variants)
    if not matching:
        return DiscountApplyResult(applied=False, message="No items in the cart qualify for this coupon")

    amount = _compute_amount(rule, matching)
    if amount <= 0:
        return DiscountApplyResult(applied=False, message="This coupon doesn't apply any discount to this cart")

    return DiscountApplyResult(
        applied=True,
        rule_id=rule.id,
        rule_name=rule.name,
        code=rule.code,
        discount_amount=amount,
        message=f"Coupon '{rule.code}' applied",
    )


def _load_variants(db: Session, items: list[DiscountCartItem]) -> dict[int, ProductVariant]:
    variant_ids = [i.variant_id for i in items]
    variants = (
        db.query(ProductVariant)
        .options(joinedload(ProductVariant.product))
        .filter(ProductVariant.id.in_(variant_ids))
        .all()
    )
    return {v.id: v for v in variants}
