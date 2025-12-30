from django import forms
from decimal import Decimal, InvalidOperation
from .models import Product

class PriceInCentsField(forms.DecimalField):
    """
    A form field that accepts decimal input (like $45.99) but stores it as cents.
    Includes validation for proper price format.
    """
    
    def __init__(self, *args, **kwargs):
        # Set reasonable defaults for price field
        kwargs.setdefault('max_digits', 10)
        kwargs.setdefault('decimal_places', 2)
        kwargs.setdefault('min_value', Decimal('0.01'))
        super().__init__(*args, **kwargs)
    
    def to_python(self, value):
        if value is None:
            return value
        
        # Clean the input - remove common symbols
        if isinstance(value, str):
            # Remove dollar signs and common currency symbols
            value = value.replace('$', '').replace('€', '').replace('£', '')
            # Remove commas (thousands separators)
            value = value.replace(',', '')
        
        try:
            # Convert to decimal for validation
            decimal_value = Decimal(str(value))
            
            # Additional validation
            if decimal_value < Decimal('0.01'):
                raise forms.ValidationError("Price must be at least $0.01")
            
            if decimal_value > Decimal('999999.99'):
                raise forms.ValidationError("Price cannot exceed $999,999.99")
            
            # Convert decimal to cents for storage
            cents = int(decimal_value * Decimal('100'))
            return cents
            
        except (InvalidOperation, ValueError, TypeError):
            raise forms.ValidationError("Enter a valid price (e.g., 45.99 or $45.99)")

class ProductAdminForm(forms.ModelForm):
    price = PriceInCentsField(
        help_text="Enter price in dollars (e.g., 45.99 or $45.99)"
    )
    
    class Meta:
        model = Product
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Convert cents back to decimal for display
        if self.instance and self.instance.pk and self.instance.price:
            decimal_price = Decimal(self.instance.price) / Decimal('100')
            self.fields['price'].initial = decimal_price
