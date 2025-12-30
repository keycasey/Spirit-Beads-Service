from django.contrib import admin
from .models import Product, Category, ProductImage
from .services.stripe_sync import ensure_stripe_product_and_price
from .forms import ProductAdminForm

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image', 'alt_text', 'is_primary', 'order']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = (
        "name",
        "price_decimal",
        "currency",
        "stripe_price_id",
        "is_active",
    )
    actions = ["sync_prices_to_stripe"]

    @admin.action(description="Create / update Stripe Price ID")
    def sync_prices_to_stripe(self, request, queryset):
        for product in queryset:
            ensure_stripe_product_and_price(product)
        self.message_user(request, f"Successfully synced {queryset.count()} products to Stripe")
    
    list_filter = ['pattern', 'is_sold_out', 'is_active', 'created_at']
    search_fields = ['name', 'custom_pattern']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at', 'stripe_product_id', 'stripe_price_id']
    inlines = [ProductImageInline]
    
    class Media:
        js = ('products/js/admin_custom_pattern.js', 'products/js/admin_custom_pattern_vanilla.js')
        css = {
            'all': ('products/css/admin_custom_pattern.css',)
        }
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'pattern', 'custom_pattern', 'description')
        }),
        ('Pricing & Inventory', {
            'fields': ('price', 'currency', 'inventory_count', 'is_sold_out', 'is_active'),
            'description': 'Enter price in dollars (e.g., 45.99). Will be stored as cents for Stripe.'
        }),
        ('Stripe Integration', {
            'fields': ('stripe_product_id', 'stripe_price_id'),
            'classes': ('collapse',)
        }),
        ('Shipping', {
            'fields': ('weight_ounces',)
        }),
        ('Media', {
            'fields': ('image',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'alt_text', 'is_primary', 'order']
    list_filter = ['is_primary']
    ordering = ['product', 'order']
