import uuid
import requests
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

def get_customer_country(request):
    """
    Detect customer country from IP address.
    Falls back to US if detection fails.
    """
    # Check for Cloudflare country header first (if using Cloudflare)
    cf_country = request.META.get('HTTP_CF_IPCOUNTRY')
    if cf_country:
        return cf_country

    # Fall back to ipinfo.io API
    try:
        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')

        # Get ipinfo token from env if available (optional, increases rate limits)
        ipinfo_token = os.getenv('IPINFO_TOKEN')

        # Build URL with or without token
        if ipinfo_token:
            url = f'https://ipinfo.io/{ip}?token={ipinfo_token}'
        else:
            url = f'https://ipinfo.io/{ip}'  # No token = lower rate limits

        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            data = response.json()
            return data.get('country', 'US')  # Default to US if not found
    except Exception as e:
        print(f"Could not detect country from IP: {e}")

    return 'US'  # Default to US

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

    # Detect customer country from IP address
    customer_country = get_customer_country(request)
    print(f"Detected customer country: {customer_country}")

    # Set up shipping option based on detected country
    SHIPPING_COST_USA = 500  # $5.00
    SHIPPING_COST_CANADA_MEXICO = 1500  # $15.00
    SHIPPING_COST_INTERNATIONAL = 2000  # $20.00

    shipping_options = []

    try:
        if customer_country == 'US':
            # USA customer - show $5 shipping
            shipping_options.append({
                "shipping_rate_data": {
                    "display_name": "USA Shipping (3-5 business days)",
                    "fixed_amount": {"amount": SHIPPING_COST_USA, "currency": "usd"},
                    "type": "fixed_amount",
                    "delivery_estimate": {
                        "minimum": {"unit": "business_day", "value": 3},
                        "maximum": {"unit": "business_day", "value": 5},
                    },
                    "tax_behavior": "exclusive",
                    "tax_code": "txcd_92010001",
                }
            })
        elif customer_country in ['CA', 'MX']:
            # Canada/Mexico customer - show $15 shipping
            shipping_options.append({
                "shipping_rate_data": {
                    "display_name": "North America Shipping (5-10 business days)",
                    "fixed_amount": {"amount": SHIPPING_COST_CANADA_MEXICO, "currency": "usd"},
                    "type": "fixed_amount",
                    "delivery_estimate": {
                        "minimum": {"unit": "business_day", "value": 5},
                        "maximum": {"unit": "business_day", "value": 10},
                    },
                    "tax_behavior": "exclusive",
                }
            })
        else:
            # International customer - show $20 shipping
            shipping_options.append({
                "shipping_rate_data": {
                    "display_name": "International Shipping (10-20 business days)",
                    "fixed_amount": {"amount": SHIPPING_COST_INTERNATIONAL, "currency": "usd"},
                    "type": "fixed_amount",
                    "delivery_estimate": {
                        "minimum": {"unit": "business_day", "value": 10},
                        "maximum": {"unit": "business_day", "value": 20},
                    },
                    "tax_behavior": "exclusive",
                }
            })
    except Exception as e:
        print(f"Warning: Could not create shipping options: {e}")

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=line_items,
            shipping_options=shipping_options,
            success_url=f"{origin}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/cancel",
            # Allow shipping to most countries - Stripe requires explicit country list
            shipping_address_collection={
                "allowed_countries": [
                    "US", "CA", "GB", "AU", "DE", "FR", "ES", "IT", "NL", "BE", "AT", "CH",
                    "IE", "PT", "SE", "NO", "DK", "FI", "PL", "CZ", "GR", "HU", "RO",
                    "BG", "HR", "SI", "SK", "LT", "LV", "EE", "MX", "BR", "AR", "CL",
                    "CO", "PE", "UY", "NZ", "JP", "SG", "HK", "KR", "TW", "MY", "TH",
                    "ID", "PH", "VN", "IN", "IL", "AE", "ZA", "NG", "KE", "EG", "MA",
                    "TN", "ZA", "IS", "NO", "LU", "MT", "CY"
                ]
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

                # Get shipping address from shipping_details (when shipping_address_collection is enabled)
                # Stripe stores shipping address in shipping_details, not customer_details
                if session.get('shipping_details') and session['shipping_details'].get('address'):
                    shipping_address = session['shipping_details']['address']
                    # Add name from shipping details if available
                    if session['shipping_details'].get('name'):
                        shipping_address['name'] = session['shipping_details']['name']
                    order.shipping_address = shipping_address
                    print(f"Shipping address found: {shipping_address}")
                else:
                    print("No shipping address found in shipping_details")
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
