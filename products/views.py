from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from .models import Product, Category
from .serializers import ProductSerializer, ProductListSerializer, CategorySerializer

class ProductViewSet(viewsets.ModelViewSet):
    """
    API endpoint for products
    """
    queryset = Product.objects.all()
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        'lighter_type': ['exact', 'in'],
        'is_sold_out': ['exact'],
        'is_active': ['exact'],
        'category': ['exact', 'in'],
    }
    ordering_fields = ['lighter_type', 'name', 'price', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        """Filter out inactive products for list and retrieve actions"""
        if self.action in ['list', 'retrieve', 'batch']:
            return Product.objects.filter(is_active=True)
        return Product.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductSerializer

    @action(detail=False, methods=['get'], url_path='batch')
    def batch(self, request):
        """Retrieve multiple products by their IDs"""
        ids_param = request.query_params.get('ids', '')
        if not ids_param:
            return Response(
                {'error': 'ids parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Split the IDs and strip whitespace
            id_list = [id_str.strip() for id_str in ids_param.split(',') if id_str.strip()]
            if not id_list:
                return Response(
                    {'error': 'No valid IDs provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Limit the number of IDs to prevent performance issues
            if len(id_list) > 100:
                return Response(
                    {'error': 'Maximum 100 IDs allowed per request'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get products that are active and match the provided IDs
            products = Product.objects.filter(
                id__in=id_list, 
                is_active=True
            )
            
            # Serialize the products
            serializer = ProductListSerializer(products, many=True)
            
            return Response({
                'products': serializer.data,
                'count': len(serializer.data),
                'requested_ids': id_list,
                'found_ids': [product.id for product in products]
            })
            
        except Exception as e:
            return Response(
                {'error': f'Invalid request: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def archive(self, request, pk=None):
        """Archive a product by setting is_active to False"""
        product = self.get_object()
        product.is_active = False
        product.save()
        
        return Response({
            'message': f'Product {product.id} has been archived',
            'product_id': product.id,
            'is_active': product.is_active
        })

    @action(detail=True, methods=['get'])
    def check_availability(self, request, pk=None):
        """Check if product is available for purchase"""
        product = self.get_object()
        return Response({
            'is_in_stock': product.is_in_stock,
            'inventory_count': product.inventory_count,
            'is_sold_out': product.is_sold_out
        })

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for categories
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
