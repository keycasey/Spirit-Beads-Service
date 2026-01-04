# Generated migration for refactoring product images
from django.db import migrations, models


def migrate_existing_images(apps, schema_editor):
    """Migrate existing image field to primary_image"""
    Product = apps.get_model('products', 'Product')
    for product in Product.objects.all():
        if product.image:
            product.primary_image = product.image
            product.save(update_fields=['primary_image'])


def reverse_migrate_existing_images(apps, schema_editor):
    """Reverse migration: move primary_image back to image"""
    Product = apps.get_model('products', 'Product')
    for product in Product.objects.all():
        if product.primary_image:
            product.image = product.primary_image
            product.save(update_fields=['image'])


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        # Add new fields to Product model
        migrations.AddField(
            model_name='product',
            name='primary_image',
            field=models.ImageField(blank=True, null=True, upload_to='products/'),
        ),
        migrations.AddField(
            model_name='product',
            name='secondary_image',
            field=models.ImageField(blank=True, null=True, upload_to='products/'),
        ),
        
        # Migrate data from existing image field to primary_image
        migrations.RunPython(migrate_existing_images, reverse_migrate_existing_images),
        
        # Remove old image field
        migrations.RemoveField(
            model_name='product',
            name='image',
        ),
    ]
