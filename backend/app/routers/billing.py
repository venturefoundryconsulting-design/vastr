"""Optional "activate now instead of waiting out the trial" payment flow.
Every plan already starts with a 30-day free trial at registration time
(app.routers.auth.register) - this is only reached if the owner chooses to
pay immediately and skip the wait, from the post-signup screen or later from
their own Settings > Subscription page. Not a recurring-billing/webhook
integration - Razorpay Subscriptions is a larger integration left for when
recurring renewal actually needs enforcing.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.platform_settings import Payment
from app.models.tenant import SubscriptionPlanName, SubscriptionStatus, Tenant
from app.schemas.billing import CreateOrderRequest, CreateOrderResponse, VerifyPaymentRequest
from app.services import razorpay
from app.services.audit import log_activity

router = APIRouter(prefix="/api/billing", tags=["billing"])

_PLAN_PRICES = {
    SubscriptionPlanName.STARTER: 1999,
    SubscriptionPlanName.PROFESSIONAL: 4999,
}


@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(payload: CreateOrderRequest, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.slug == payload.slug).first()
    if not tenant:
        raise HTTPException(404, "Store not found")
    if tenant.subscription_plan not in _PLAN_PRICES:
        raise HTTPException(400, "This plan isn't self-serve payable - contact us for Enterprise pricing")
    amount = _PLAN_PRICES[tenant.subscription_plan]

    config = razorpay.get_config(db)
    if not razorpay.is_configured(config):
        raise HTTPException(503, "Online payments aren't set up yet - your free trial is still active")

    order = razorpay.create_order(
        config,
        amount_rupees=amount,
        receipt=f"tenant-{tenant.id}",
        notes={"tenant_id": str(tenant.id), "plan": tenant.subscription_plan.value},
    )
    payment = Payment(
        tenant_id=tenant.id,
        plan=tenant.subscription_plan.value,
        amount=amount,
        currency="INR",
        status="created",
        razorpay_order_id=order["id"],
    )
    db.add(payment)
    db.commit()
    return CreateOrderResponse(
        order_id=order["id"], amount=order["amount"], currency=order["currency"], key_id=config.razorpay_key_id
    )


@router.post("/verify-payment")
def verify_payment(payload: VerifyPaymentRequest, db: Session = Depends(get_db)) -> dict:
    payment = db.query(Payment).filter(Payment.razorpay_order_id == payload.razorpay_order_id).first()
    if not payment:
        raise HTTPException(404, "Order not found")

    config = razorpay.get_config(db)
    if not razorpay.verify_payment_signature(
        config,
        order_id=payload.razorpay_order_id,
        payment_id=payload.razorpay_payment_id,
        signature=payload.razorpay_signature,
    ):
        payment.status = "failed"
        db.commit()
        raise HTTPException(400, "Payment verification failed")

    payment.status = "paid"
    payment.razorpay_payment_id = payload.razorpay_payment_id
    payment.razorpay_signature = payload.razorpay_signature

    tenant = db.get(Tenant, payment.tenant_id)
    if tenant:
        tenant.subscription_status = SubscriptionStatus.ACTIVE
        log_activity(
            db, action="billing.payment_success", tenant_id=tenant.id, user_id=None,
            entity_type="Payment", entity_id=payment.id,
            details={"plan": payment.plan, "amount": float(payment.amount)},
        )
    db.commit()
    return {"ok": True}
