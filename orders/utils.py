import os
from email.mime.image import MIMEImage
from django.core.mail import EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
import mimetypes


def send_order_confirmation_email(order):
    """Send order confirmation email to customer and admin after successful checkout"""
    # Prepare order items with product details and collect images
    order_items = []
    images_to_embed = []
    item_index = 0

    for item in order.items.all():
        product = item.product
        image_cid = None
        image_path = None

        # Get image file path for embedding
        if product.primary_image:
            image_path = product.primary_image.path
            if os.path.exists(image_path):
                image_cid = f'product{item_index}'
                images_to_embed.append({
                    'cid': image_cid,
                    'path': image_path,
                })

        order_items.append({
            'name': product.name,
            'collection': product.category.name if product.category else 'Uncategorized',
            'size': product.get_lighter_type_display(),
            'quantity': item.quantity,
            'unit_price': item.unit_price_decimal,
            'total_price': item.unit_price_decimal * item.quantity,
            'image': f'cid:{image_cid}' if image_cid else None,
        })
        item_index += 1

    # Format shipping address from JSONField
    shipping_address = order.shipping_address
    formatted_address = None
    if shipping_address:
        # Stripe address format: {line1, line2, city, state, postal_code, country}
        parts = []
        if shipping_address.get('line1'):
            parts.append(shipping_address['line1'])
        if shipping_address.get('line2'):
            parts.append(shipping_address['line2'])
        city_state_zip = []
        if shipping_address.get('city'):
            city_state_zip.append(shipping_address['city'])
        if shipping_address.get('state'):
            city_state_zip.append(shipping_address['state'])
        if shipping_address.get('postal_code'):
            city_state_zip.append(shipping_address['postal_code'])
        if city_state_zip:
            parts.append(', '.join(city_state_zip))
        if shipping_address.get('country'):
            parts.append(shipping_address['country'])
        formatted_address = '\n'.join(parts)

    # Calculate order total
    total_amount = sum(item['total_price'] for item in order_items)

    # Context for template
    context = {
        'customer_name': shipping_address.get('name', '') if shipping_address else '',
        'order_id': str(order.id),
        'order_items': order_items,
        'shipping_address': formatted_address,
        'total_amount': total_amount,
    }

    # Render HTML email content
    subject = 'Order Confirmation - Spirit Beads'
    html_message = render_to_string('orders/order_confirmation_email.html', context)

    # Create HTML email
    email = EmailMessage(
        subject=subject,
        body=html_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.customer_email],  # Send to customer
        cc=[settings.DEFAULT_FROM_EMAIL],  # CC to admin (lynn.braveheart@thebeadedcase.com)
    )
    email.content_subtype = 'html'

    # Embed images as CID attachments
    for img_data in images_to_embed:
        with open(img_data['path'], 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-ID', f'<{img_data["cid"]}>')
            img.add_header('Content-Disposition', 'inline', filename=os.path.basename(img_data['path']))
            email.attach(img)

    email.send(fail_silently=False)


def send_order_shipped_email(order):
    """Send shipping confirmation email to customer"""
    # Prepare order items list
    order_items = []
    for item in order.items.all():
        order_items.append({
            'name': item.product.name,
            'quantity': item.quantity,
        })

    # Get customer name from shipping address
    customer_name = None
    if order.shipping_address:
        customer_name = order.shipping_address.get('name', '')

    # Build context
    context = {
        'customer_name': customer_name,
        'name': customer_name,  # For backwards compatibility with template
        'order_id': str(order.id),
        'tracking_number': order.tracking_number,
        'shipping_carrier': order.shipping_carrier,
        'shipped_date': order.shipped_at.strftime('%B %d, %Y') if order.shipped_at else '',
        'is_custom_order': order.is_custom_order,
        'product_image': None,  # Will be set to 'cid:product_image' if image exists
    }

    # For custom orders, add description and colors
    if order.is_custom_order and hasattr(order, 'custom_request') and order.custom_request:
        context.update({
            'description': order.custom_request.description,
            'colors': order.custom_request.colors,
        })
    elif not order.is_custom_order:
        # For regular orders, add the items list
        context['order_items'] = order_items

    # Render HTML email content
    subject = 'Your Order Has Shipped! - Spirit Beads'
    html_message = render_to_string('orders/shipped_email.html', context)

    # Create HTML email
    email = EmailMessage(
        subject=subject,
        body=html_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.customer_email],
    )
    email.content_subtype = 'html'

    # Embed product image if available
    if order.product_image and order.product_image.path and os.path.exists(order.product_image.path):
        with open(order.product_image.path, 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-ID', '<product_image>')
            img.add_header('Content-Disposition', 'inline', filename=os.path.basename(order.product_image.path))
            email.attach(img)
        # Update context to reference the CID image
        context['product_image'] = 'cid:product_image'
        # Re-render with the image reference
        html_message = render_to_string('orders/shipped_email.html', context)
        email.body = html_message

    email.send(fail_silently=False)
