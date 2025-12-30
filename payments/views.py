import uuid
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from .stripe import stripe
from orders.models import Order, OrderItem
from products.models import Product
from decimal import Decimal

@api_view(["POST"])
def create_checkout_session(request):
    cart_items = request.data.get("items")

    if not cart_items:
        return Response({"error": "No items provided"}, status=400)

    order_id = uuid.uuid4()

    line_items = []
    total_amount = 0

    for cart_item in cart_items:
        product = Product.objects.get(id=cart_item["product_id"])
        
        # Guard: ensure product has Stripe Price ID
        if not product.stripe_price_id:
            raise ValueError(f"Product {product.name} missing Stripe price ID")

        line_items.append({
            "price": product.stripe_price_id,
            "quantity": cart_item["quantity"],
        })

        total_amount += product.price * cart_item["quantity"]

    session = stripe.checkout.sessions.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=line_items,
        success_url=f"{settings.FRONTEND_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.FRONTEND_URL}/cancel",
        shipping_address_collection={
            "allowed_countries": ["US"]
        },
    )

    order = Order.objects.create(
        id=order_id,
        stripe_session_id=session.id,
        amount_total=total_amount,
        currency="usd",
        status="pending",
    )

    for cart_item in cart_items:
        product = Product.objects.get(id=cart_item["product_id"])
        
        OrderItem.objects.create(
            order=order,
            product=product,
            unit_price=product.price,
            quantity=cart_item["quantity"],
        )

    return Response({"checkout_url": session.url})

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    try:
        event = stripe.webhooks.construct_event(
            payload,
            sig_header,
            settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        order = Order.objects.get(stripe_session_id=session.id)
        order.status = "paid"
        order.stripe_payment_intent = session.payment_intent
        order.customer_email = session.customer_details.email
        order.shipping_address = session.shipping_details.address
        order.save()

    return HttpResponse(status=200)
