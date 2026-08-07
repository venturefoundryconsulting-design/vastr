from pydantic import BaseModel


class CreateOrderRequest(BaseModel):
    slug: str


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int  # paise, as Razorpay returns it
    currency: str
    key_id: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
