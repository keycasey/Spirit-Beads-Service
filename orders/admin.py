from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product', 'unit_price', 'quantity']
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer_email', 'status', 'amount_total_display', 'is_custom_order', 'created_at', 'shipped_at']
    list_filter = ['status', 'is_custom_order', 'created_at', 'shipped_at']
    search_fields = ['id', 'customer_email', 'stripe_payment_intent']
    readonly_fields = ['id', 'stripe_session_id', 'stripe_payment_intent', 'amount_total', 'created_at']
    inlines = [OrderItemInline]

    fieldsets = (
        ('Order Information', {
            'fields': ('status', 'customer_email', 'is_custom_order')
        }),
        ('Payment Details', {
            'fields': ('stripe_session_id', 'stripe_payment_intent', 'amount_total', 'currency'),
            'classes': ('collapse',)
        }),
        ('Shipping Information', {
            'fields': ('shipping_address', 'shipped_at', 'tracking_number', 'shipping_carrier', 'product_image')
        }),
        ('System Information', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['mark_as_shipped']

    def amount_total_display(self, obj):
        """Display amount in dollars"""
        return f"${obj.amount_total / 100:.2f}"
    amount_total_display.short_description = 'Total'

    def mark_as_shipped(self, request, queryset):
        """Mark selected orders as shipped and send notification emails"""
        from django.utils import timezone
        from .utils import send_order_shipped_email
        import os
        from email.mime.image import MIMEImage
        from django.core.mail import EmailMessage
        from django.template.loader import render_to_string
        from django.conf import settings

        count = 0
        for order in queryset.filter(status='paid'):
            # Check if tracking number is set
            if not order.tracking_number:
                self.message_user(
                    request,
                    f"Cannot mark order {order.id} as shipped: No tracking number set. Please add tracking info first.",
                    messages.WARNING
                )
                continue

            # Update status and shipped_at
            order.status = 'shipped'
            order.shipped_at = timezone.now()
            order.save()

            # Send shipping notification email
            try:
                send_order_shipped_email(order)
                count += 1
                self.message_user(
                    request,
                    f"Marked order {order.id} as shipped and emailed customer",
                    messages.SUCCESS
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"Error sending shipped email for order {order.id}: {str(e)}",
                    messages.ERROR
                )

        if count > 0:
            self.message_user(
                request,
                f"Successfully marked {count} order(s) as shipped",
                messages.SUCCESS
            )
    mark_as_shipped.short_description = "Mark as shipped and notify customer"
