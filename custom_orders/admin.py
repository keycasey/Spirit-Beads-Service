from django.contrib import admin
from django.utils.html import format_html
from django.http import HttpResponse
from django.contrib import messages
from django import forms
from django.db.models import DecimalField
from decimal import Decimal, InvalidOperation
import re
from .models import CustomOrderRequest
from .utils import send_approval_email, send_rejection_email, send_shipped_email


class PriceInput(forms.TextInput):
    """Custom widget for price input that accepts commas and dollar signs"""

    def value_from_datadict(self, data, files, name):
        value = super().value_from_datadict(data, files, name)
        if value:
            # Strip dollar signs and spaces for the form value
            return value.replace('$', '').replace(' ', '')
        return value


class CustomOrderRequestAdminForm(forms.ModelForm):
    class Meta:
        model = CustomOrderRequest
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Change the widget for quoted_price to our custom widget
        if 'quoted_price' in self.fields:
            self.fields['quoted_price'].widget = PriceInput(attrs={
                'placeholder': 'e.g., $1,111.11 or 1,111.11'
            })
            self.fields['quoted_price'].help_text = 'Quoted price in USD'
            self.fields['quoted_price'].required = False

        # Format initial value with commas for better UX
        if self.instance and self.instance.pk and self.instance.quoted_price is not None:
            # Format as number with commas, no decimal if whole number, 2 decimals otherwise
            price = self.instance.quoted_price
            if price == price.to_integral_value():
                # Whole number, show as 1,111
                formatted = f"{price:,.0f}"
            else:
                # Has decimals, show as 1,111.11
                formatted = f"{price:,.2f}"
            self.initial['quoted_price'] = formatted

    def clean_quoted_price(self):
        value = self.cleaned_data.get('quoted_price')

        # Allow empty/None values
        if value is None or value == '':
            return None

        # Convert to string for parsing
        # Widget already stripped $ and spaces, but we still handle commas
        price_str = str(value).strip()

        # Remove any remaining dollar signs or spaces (for safety)
        price_str = price_str.replace('$', '').replace(' ', '')

        # Remove commas for parsing
        price_str_clean = price_str.replace(',', '')

        # If empty after cleaning, return None
        if not price_str_clean:
            return None

        try:
            # Parse the cleaned string
            price = Decimal(price_str_clean)

            # Check for negative
            if price < 0:
                raise forms.ValidationError('Quoted price cannot be negative.')

            # Check decimal places on the original input (before comma removal)
            original_for_check = price_str.replace(',', '')

            if '.' in original_for_check:
                # Has decimal point - must have exactly 2 decimal places
                decimal_part = original_for_check.split('.')[1]
                if len(decimal_part) != 2:
                    raise forms.ValidationError(
                        'Price with decimals must have exactly 2 decimal places (e.g., $1,111.11 or 1,111.11)'
                    )
            else:
                # No decimal point - this is fine (e.g., 100, 1000)
                pass

            return price

        except (InvalidOperation, ValueError):
            raise forms.ValidationError(
                'Invalid price format. Use format like $1,111.11 or 1,111.11 (must have 0 or 2 decimal places)'
            )


@admin.register(CustomOrderRequest)
class CustomOrderRequestAdmin(admin.ModelAdmin):
    form = CustomOrderRequestAdminForm
    list_display = ['id', 'name', 'email', 'status', 'quoted_price', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'email', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at', 'images_display', 'stripe_payment_link']
    fieldsets = (
        ('Customer Information', {
            'fields': ('name', 'email')
        }),
        ('Request Details', {
            'fields': ('description', 'colors', 'images_display')
        }),
        ('Status & Notes', {
            'fields': ('status', 'admin_notes', 'quoted_price', 'stripe_payment_link')
        }),
        ('System Information', {
            'fields': ('id', 'created_at', 'updated_at', 'related_order'),
            'classes': ('collapse',)
        }),
    )

    def images_display(self, obj):
        if not obj.images:
            return "No images"
        images_html = ""
        for i, img in enumerate(obj.images):
            if isinstance(img, str) and img.startswith('data:'):
                # This is a base64 image, we can't display it directly
                images_html += format_html('<div style="margin: 5px;">Image {} (base64 encoded - {} bytes)</div>', i + 1, len(img) // 2)
            elif isinstance(img, str) and img.startswith('blob:'):
                # Blob URLs are temporary and can't be displayed in admin
                # Extract filename from blob URL if available
                blob_id = img.split('/')[-1] if '/' in img else 'unknown'
                images_html += format_html('<div style="margin: 5px; color: #666;">Image {} (blob URL - not accessible in admin)</div>', i + 1)
            elif isinstance(img, str):
                # Regular URL - show link
                images_html += format_html('<div style="margin: 5px;"><a href="{}" target="_blank" rel="noopener">Image {}</a> <span style="color: #888; font-size: 11px;">(click to open)</span></div>', img, i + 1)
            else:
                images_html += format_html('<div style="margin: 5px;">Image {} (invalid format)</div>', i + 1)
        from django.utils.safestring import mark_safe
        return mark_safe(images_html)
    images_display.short_description = 'Images'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('related_order')

    actions = ['approve_requests', 'reject_requests', 'mark_as_shipped']

    def approve_requests(self, request, queryset):
        """Approve selected requests and send quotes"""
        count = 0
        for request_obj in queryset.filter(status='pending'):
            # Check if price is set
            if not request_obj.quoted_price:
                self.message_user(
                    request,
                    f"Cannot approve request {request_obj.id}: No price quoted. Please set a price first.",
                    messages.WARNING
                )
                continue

            # Generate Stripe payment link
            try:
                from django.conf import settings
                import stripe
                stripe.api_key = settings.STRIPE_SECRET_KEY

                # Create a Payment Link in Stripe
                payment_link = stripe.PaymentLink.create(
                    line_items=[
                        {
                            "price_data": {
                                "currency": "usd",
                                "product_data": {
                                    "name": f"Custom Order from {request_obj.name}",
                                    "description": request_obj.description[:50],
                                },
                                "unit_amount": int(request_obj.quoted_price * 100),  # Convert to cents
                            },
                            "quantity": 1,
                        }
                    ],
                    metadata={"custom_request_id": str(request_obj.id)},
                    after_completion={
                        "type": "redirect",
                        "redirect": {"url": f"{settings.FRONTEND_URL}/custom-order-success"}
                    }
                )

                request_obj.stripe_payment_link = payment_link.url
                request_obj.status = 'approved'
                request_obj.save()

                # Send approval email
                send_approval_email(request_obj)

                count += 1
                self.message_user(
                    request,
                    f"Approved request {request_obj.id} and sent payment link",
                    messages.SUCCESS
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"Error creating payment link for request {request_obj.id}: {str(e)}",
                    messages.ERROR
                )

        if count > 0:
            self.message_user(
                request,
                f"Successfully approved {count} request(s) and generated payment links",
                messages.SUCCESS
            )
    approve_requests.short_description = "Approve and send payment link"

    def reject_requests(self, request, queryset):
        """Reject selected requests"""
        count = queryset.filter(status='pending').update(status='rejected')

        # Send rejection emails
        for request_obj in queryset.filter(status='rejected'):
            if request_obj.admin_notes:
                send_rejection_email(request_obj)

        self.message_user(
            request,
            f"{count} request(s) rejected and emails sent",
            messages.SUCCESS if count > 0 else messages.WARNING
        )
    reject_requests.short_description = "Reject and send email"

    def mark_as_shipped(self, request, queryset):
        """Mark custom orders as shipped"""
        from django.utils import timezone
        from orders.utils import send_order_shipped_email

        count = 0
        for request_obj in queryset.filter(status='in_production'):
            if not request_obj.related_order:
                self.message_user(
                    request,
                    f"Cannot mark as shipped: Request {request_obj.id} has no related order",
                    messages.WARNING
                )
                continue

            order = request_obj.related_order

            # Check if tracking number is set on the order
            if not order.tracking_number:
                self.message_user(
                    request,
                    f"Cannot mark as shipped: Order {order.id} has no tracking number. Please add tracking info to the order first.",
                    messages.WARNING
                )
                continue

            # Update custom request status
            request_obj.status = 'shipped'
            request_obj.save()

            # Update order with shipped status and timestamp
            order.status = 'shipped'
            order.shipped_at = timezone.now()
            order.save()

            # Send shipped email using unified function
            try:
                send_order_shipped_email(order)
                count += 1
                self.message_user(
                    request,
                    f"Marked request {request_obj.id} as shipped and emailed customer",
                    messages.SUCCESS
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"Error sending shipped email for request {request_obj.id}: {str(e)}",
                    messages.ERROR
                )

        if count > 0:
            self.message_user(
                request,
                f"Successfully marked {count} order(s) as shipped",
                messages.SUCCESS
            )
    mark_as_shipped.short_description = "Mark as shipped and notify customer"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # If status changed to approved and price exists but no payment link
        if change:
            old_obj = CustomOrderRequest.objects.get(pk=obj.pk)
            if old_obj.status != 'approved' and obj.status == 'approved':
                if obj.quoted_price and not obj.stripe_payment_link:
                    self.message_user(
                        request,
                        f"Request approved but no payment link. Use 'Approve and send payment link' action from the list view.",
                        messages.WARNING
                    )
