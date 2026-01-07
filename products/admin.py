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
        "formatted_price",
        "currency",
        "stripe_price_id",
        "is_active",
    )
    actions = ["sync_prices_to_stripe", "archive_products"]

    def formatted_price(self, obj):
        """Display price in dollar format"""
        return f"${obj.price_decimal:.2f}"
    formatted_price.short_description = "Price"
    formatted_price.admin_order_field = "price"

    @admin.action(description="Create / update Stripe Price ID")
    def sync_prices_to_stripe(self, request, queryset):
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Starting bulk Stripe sync for {queryset.count()} products")
        success = 0
        failed = 0
        for product in queryset:
            try:
                logger.info(f"Syncing product {product.id} ({product.name})")
                result = ensure_stripe_product_and_price(product)
                if result:
                    logger.info(f"Successfully synced product {product.id}: new price_id={result.id}")
                    success += 1
                else:
                    logger.warning(f"Skipped product {product.id} (already syncing or no action needed)")
            except Exception as e:
                logger.exception(f"Failed to sync product {product.id} to Stripe: {e}")
                failed += 1
        self.message_user(request, f"Stripe sync complete: {success} succeeded, {failed} failed. Check logs for details.")
    
    @admin.action(description="Archive selected products")
    def archive_products(self, request, queryset):
        """Archive selected products by setting is_active to False"""
        count = queryset.count()
        queryset.update(is_active=False)
        self.message_user(request, f"Successfully archived {count} product(s). They will no longer appear in the store.")
    
    list_filter = ['pattern', 'is_sold_out', 'is_active', 'created_at']
    search_fields = ['name', 'custom_pattern']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at', 'stripe_product_id', 'stripe_price_id', 'currency']
    inlines = [ProductImageInline]
    
    class Media:
        js = ('products/js/admin_custom_pattern.js', 'products/js/admin_custom_pattern_vanilla.js')
        css = {
            'all': ('products/css/admin_custom_pattern.css',)
        }
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'lighter_type', 'pattern', 'custom_pattern', 'description')
        }),
        ('Pricing & Inventory', {
            'fields': ('price', 'currency', 'inventory_count', 'is_sold_out', 'is_active'),
            'description': 'Enter price in decimal format (e.g., 45.99). Currency is fixed to USD. Will be stored as cents for Stripe.'
        }),
        ('Stripe Integration', {
            'fields': ('stripe_product_id', 'stripe_price_id'),
            'classes': ('collapse',)
        }),
        ('Shipping', {
            'fields': ('weight_ounces',)
        }),
        ('Product Images', {
            'fields': ('primary_image', 'secondary_image'),
            'description': 'Primary image is displayed in the catalog. Secondary image shows on hover.'
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
