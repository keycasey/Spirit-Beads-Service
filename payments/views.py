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

    # Get origin from request for dynamic redirects
    origin = request.META.get('HTTP_ORIGIN', 'http://localhost:8080')
    # Remove trailing slash for consistent URL construction
    origin = origin.rstrip('/')

    # Set up shipping options by region - Stripe will show correct option based on customer address
    SHIPPING_COST_USA = 500  # $5.00
    SHIPPING_COST_CANADA_MEXICO = 1500  # $15.00
    SHIPPING_COST_INTERNATIONAL = 2000  # $20.00

    # Create or find shipping rates for each region
    try:
        existing_rates = stripe.ShippingRate.list(limit=100, active=True)

        # USA shipping rate
        usa_rate = next(
            (r for r in existing_rates.data
             if r.fixed_amount.amount == SHIPPING_COST_USA
             and r.fixed_amount.currency == "usd"
             and r.display_name == "USA Shipping"),
            None
        )
        if not usa_rate:
            usa_rate = stripe.ShippingRate.create(
                display_name="USA Shipping",
                fixed_amount={"amount": SHIPPING_COST_USA, "currency": "usd"},
                type="fixed_amount",
                delivery_estimate={"minimum": {"unit": "business_day", "value": 3}, "maximum": {"unit": "business_day", "value": 5}},
                tax_behavior="exclusive",
                tax_code="txcd_92010001",  # Shipping tax code
            )

        # Canada/Mexico shipping rate
        na_rate = next(
            (r for r in existing_rates.data
             if r.fixed_amount.amount == SHIPPING_COST_CANADA_MEXICO
             and r.fixed_amount.currency == "usd"
             and r.display_name == "Canada/Mexico Shipping"),
            None
        )
        if not na_rate:
            na_rate = stripe.ShippingRate.create(
                display_name="Canada/Mexico Shipping",
                fixed_amount={"amount": SHIPPING_COST_CANADA_MEXICO, "currency": "usd"},
                type="fixed_amount",
                delivery_estimate={"minimum": {"unit": "business_day", "value": 5}, "maximum": {"unit": "business_day", "value": 10}},
                tax_behavior="exclusive",
            )

        # International shipping rate
        intl_rate = next(
            (r for r in existing_rates.data
             if r.fixed_amount.amount == SHIPPING_COST_INTERNATIONAL
             and r.fixed_amount.currency == "usd"
             and r.display_name == "International Shipping"),
            None
        )
        if not intl_rate:
            intl_rate = stripe.ShippingRate.create(
                display_name="International Shipping",
                fixed_amount={"amount": SHIPPING_COST_INTERNATIONAL, "currency": "usd"},
                type="fixed_amount",
                delivery_estimate={"minimum": {"unit": "business_day", "value": 10}, "maximum": {"unit": "business_day", "value": 20}},
                tax_behavior="exclusive",
            )

        shipping_options = [
            {"shipping_rate": usa_rate.id},
            {"shipping_rate": na_rate.id},
            {"shipping_rate": intl_rate.id},
        ]
    except Exception as e:
        print(f"Warning: Could not create shipping rates: {e}")
        shipping_options = []

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=line_items,
            shipping_options=shipping_options,
            success_url=f"{origin}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/cancel",
            # Remove country restriction - allow all countries
            shipping_address_collection={"allowed_countries": []},  # Empty list = all countries
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

    # Create order with product total only - shipping will be added in webhook when customer selects option
    order = Order.objects.create(
        id=order_id,
        stripe_session_id=session.id,
        amount_total=total_amount,  # Will be updated in webhook with shipping
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
        print(f"Session metadata: {session.get('metadata', {})}")

        # Check if this is a custom order payment (has custom_request_id in metadata)
        custom_request_id = session.metadata.get('custom_request_id')

        if custom_request_id:
            print(f"Processing custom order payment for request_id: {custom_request_id}")
            try:
                from custom_orders.models import CustomOrderRequest
                from custom_orders.utils import send_payment_confirmation_email
                from decimal import Decimal

                custom_request = CustomOrderRequest.objects.get(id=custom_request_id)

                # Create Order for custom order
                import uuid
                order_id = uuid.uuid4()
                order = Order.objects.create(
                    id=order_id,
                    stripe_session_id=session.id,
                    stripe_payment_intent=session.payment_intent,
                    amount_total=int(session.amount_total),  # Amount in cents
                    currency="usd",
                    status="paid",
                    customer_email=session.customer_details.email,
                    is_custom_order=True,
                )

                # Link order to custom request
                custom_request.related_order = order
                custom_request.status = 'paid'
                custom_request.stripe_payment_intent = session.payment_intent
                custom_request.save()

                print(f"Custom Order {order.id} created and linked to request {custom_request_id}")

                # Send payment confirmation email
                try:
                    send_payment_confirmation_email(custom_request, order)
                    print(f"Payment confirmation email sent to {custom_request.email}")
                except Exception as email_error:
                    print(f"Error sending payment confirmation email: {email_error}")

            except CustomOrderRequest.DoesNotExist:
                print(f"Custom order request {custom_request_id} not found")
            except Exception as e:
                print(f"Error processing custom order payment: {e}")
                import traceback
                traceback.print_exc()
        else:
            # Regular product order
            try:
                from orders.utils import send_order_confirmation_email

                order = Order.objects.get(stripe_session_id=session.id)
                order.status = "paid"
                order.stripe_payment_intent = session.payment_intent
                order.customer_email = session.customer_details.email
                # Update amount_total to include shipping selected by customer
                order.amount_total = int(session.amount_total)

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
                print(f"Order {order.id} marked as paid with total ${order.amount_total / 100:.2f}")

                # Send order confirmation email
                try:
                    send_order_confirmation_email(order)
                    print(f"Order confirmation email sent to {order.customer_email}")
                except Exception as email_error:
                    print(f"Error sending order confirmation email: {email_error}")
                    import traceback
                    traceback.print_exc()

            except Order.DoesNotExist:
                print(f"Order with session_id {session.id} not found")
            except Exception as e:
                print(f"Error updating order: {e}")
                import traceback
                traceback.print_exc()

    return HttpResponse(status=200)
