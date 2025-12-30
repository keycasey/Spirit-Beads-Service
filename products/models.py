from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name

class Product(models.Model):
    PATTERN_CHOICES = [
        ('chevron', 'Chevron Pattern'),
        ('geometric', 'Geometric Pattern'),
        ('sunburst', 'Sunburst Pattern'),
        ('diamond', 'Diamond Pattern'),
        ('mountain', 'Mountain Pattern'),
        ('arrow', 'Arrow Pattern'),
        ('custom', 'Custom Pattern'),
    ]

    id = models.CharField(primary_key=True, max_length=100)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=200, unique=True)
    pattern = models.CharField(max_length=50, choices=PATTERN_CHOICES)
    custom_pattern = models.CharField(max_length=100, blank=True, help_text="Enter custom pattern name")
    
    price = models.IntegerField(
        help_text="Price in cents (admin editable)"
    )
    currency = models.CharField(
        max_length=10,
        default="usd"
    )
    
    stripe_product_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        editable=False
    )
    stripe_price_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        editable=False
    )
    
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_sold_out = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    inventory_count = models.PositiveIntegerField(default=1)
    weight_ounces = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        default=Decimal('2.0'),
        help_text="Weight in ounces for shipping calculations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        if self.pattern == 'custom' and self.custom_pattern:
            return f"{self.name} - {self.custom_pattern}"
        return f"{self.name} - {self.get_pattern_display()}"

    @property
    def pattern_display(self):
        if self.pattern == 'custom' and self.custom_pattern:
            return self.custom_pattern
        return self.get_pattern_display()

    @property
    def is_in_stock(self):
        return not self.is_sold_out and self.inventory_count > 0

    @property
    def price_decimal(self):
        """Convert cents to decimal for display purposes"""
        return Decimal(self.price) / Decimal(100)

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.product.name} - Image {self.order}"
