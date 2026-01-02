import uuid
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from .stripe import stripe
from orders.models import Order, OrderItem
from products.models import Product
from decimal import Decimal
import os

@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def create_checkout_session(request):
    cart_items = request.data.get("items")

    if not cart_items:
        return Response({"error": "Validation failed", "message": "No items provided", "details": []}, status=400)

    # Validate all cart items before processing
    validation_errors = []
    validated_items = []
    total_amount = 0

    for cart_item in cart_items:
        product_id = cart_item.get("product_id")
        quantity = cart_item.get("quantity")

        if not product_id or not quantity:
            validation_errors.append({
                "product_id": product_id or "unknown",
                "error": "invalid_item_data",
                "message": "Missing product_id or quantity"
            })
            continue

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            validation_errors.append({
                "product_id": product_id,
                "error": "product_not_found",
                "message": "This product is no longer available"
            })
            continue

        # Check if product is active
        if not product.is_active:
            validation_errors.append({
                "product_id": product_id,
                "error": "product_not_active",
                "message": "This product is no longer available"
            })
            continue

        # Check if product is sold out
        if product.is_sold_out:
            validation_errors.append({
                "product_id": product_id,
                "error": "product_sold_out",
                "message": "This product is currently sold out"
            })
            continue

        # Check inventory
        if quantity > product.inventory_count:
            validation_errors.append({
                "product_id": product_id,
                "error": "insufficient_inventory",
                "message": f"Only {product.inventory_count} items available, but you requested {quantity}"
            })
            continue

        # Guard: ensure product has Stripe Price ID
        if not product.stripe_price_id:
            validation_errors.append({
                "product_id": product_id,
                "error": "payment_not_available",
                "message": "Payment processing not available for this product"
            })
            continue

        # If all validations pass, add to validated items
        validated_items.append({
            "product": product,
            "quantity": quantity,
            "cart_item": cart_item
        })
        total_amount += product.price * quantity

    # If there are validation errors, return them
    if validation_errors:
        return Response({
            "error": "Validation failed",
            "message": "Some items in your cart are no longer available",
            "details": validation_errors
        }, status=400)

    # If no valid items, return error
    if not validated_items:
        return Response({
            "error": "Validation failed", 
            "message": "No valid items in cart",
            "details": []
        }, status=400)

    order_id = uuid.uuid4()

    # Create line items for Stripe
    line_items = []
    for item in validated_items:
        product = item["product"]
        quantity = item["quantity"]
        
        line_items.append({
            "price": product.stripe_price_id,
            "quantity": quantity,
        })

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=line_items,
            success_url=f"{settings.FRONTEND_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.FRONTEND_URL}/cancel",
            shipping_address_collection={
                "allowed_countries": ["US"]
            },
        )
    except stripe.error.InvalidRequestError as e:
        # Common cause: using a test-mode price ID with a live-mode secret key (or vice versa)
        return Response(
            {
                "error": "payment_setup_error",
                "message": str(e),
                "hint": "If this mentions 'No such price', your product.stripe_price_id in the database likely belongs to Stripe Test mode while the backend is using a Live secret key (or vice versa).",
            },
            status=400,
        )

    order = Order.objects.create(
        id=order_id,
        stripe_session_id=session.id,
        amount_total=total_amount,
        currency="usd",
        status="pending",
    )

    for item in validated_items:
        product = item["product"]
        quantity = item["quantity"]
        
        OrderItem.objects.create(
            order=order,
            product=product,
            unit_price=product.price,
            quantity=quantity,
        )

    return Response({"checkout_url": session.url})

@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    
    print(f"Webhook received:")
    print(f"Payload length: {len(payload)}")
    print(f"Signature header: {sig_header}")
    print(f"STRIPE_WEBHOOK_SECRET: {settings.STRIPE_WEBHOOK_SECRET[:20]}...")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.STRIPE_WEBHOOK_SECRET
        )
        print(f"Webhook signature verified successfully")
    except stripe.error.SignatureVerificationError as e:
        print(f"Signature verification failed: {e}")
        return HttpResponse(status=400)
    except Exception as e:
        print(f"Webhook error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        print(f"Processing checkout.session.completed for session: {session.id}")
        
        # Debug session data
        print(f"Customer details: {session.get('customer_details', {})}")
        print(f"Shipping details: {session.get('shipping_details', {})}")

        try:
            order = Order.objects.get(stripe_session_id=session.id)
            order.status = "paid"
            order.stripe_payment_intent = session.payment_intent
            order.customer_email = session.customer_details.email
            
            # Get address from customer_details (this is where Stripe Checkout stores it)
            if (session.customer_details and 
                hasattr(session.customer_details, 'address') and 
                session.customer_details.address):
                print(f"Address found in customer_details: {session.customer_details.address}")
                order.shipping_address = session.customer_details.address
            else:
                print("No address found")
                order.shipping_address = None
                
            order.save()
            print(f"Order {order.id} marked as paid")
        except Order.DoesNotExist:
            print(f"Order with session_id {session.id} not found")
        except Exception as e:
            print(f"Error updating order: {e}")
            import traceback
            traceback.print_exc()

    return HttpResponse(status=200)
