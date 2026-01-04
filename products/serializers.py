from rest_framework import serializers
from .models import Product, Category, ProductImage

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description']

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary', 'order']

class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    pattern_display = serializers.CharField(read_only=True)
    is_in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'pattern', 'custom_pattern', 'pattern_display', 
            'price', 'description', 'primary_image', 'secondary_image', 'is_sold_out', 'is_active', 
            'inventory_count', 'weight_ounces', 'images', 'is_in_stock',
            'created_at', 'updated_at'
        ]

class ProductListSerializer(serializers.ModelSerializer):
    pattern_display = serializers.CharField(read_only=True)
    is_in_stock = serializers.BooleanField(read_only=True)
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'pattern', 'custom_pattern', 'pattern_display',
            'price', 'is_sold_out', 'inventory_count', 'primary_image', 'is_in_stock'
        ]

    def get_primary_image(self, obj):
        # Check if product has a primary_image
        if obj.primary_image:
            return obj.primary_image.url
        # Then check ProductImage relationships
        primary_image = obj.images.filter(is_primary=True).first()
        if primary_image:
            return primary_image.image.url
        elif obj.images.exists():
            return obj.images.first().image.url
        return None
