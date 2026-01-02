from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Product
from payments.stripe import stripe
import logging

logger = logging.getLogger(__name__)

@receiver(post_delete, sender=Product)
def archive_stripe_product_on_delete(sender, instance, **kwargs):
    """
    When a Product is deleted in Django, archive its corresponding Stripe Product.
    This keeps historical data while deactivating the product in Stripe.
    """
    if not instance.stripe_product_id:
        logger.info(f"Product {instance.id} has no stripe_product_id; skipping Stripe archive.")
        return

    try:
        logger.info(f"Archiving Stripe product {instance.stripe_product_id} for deleted Django product {instance.id}")
        stripe.Product.modify(
            instance.stripe_product_id,
            active=False,
            description="[Archived] Product deleted from admin"
        )
        logger.info(f"Archived Stripe product {instance.stripe_product_id}")
    except stripe.error.StripeError as e:
        logger.exception(f"Failed to archive Stripe product {instance.stripe_product_id}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error archiving Stripe product {instance.stripe_product_id}: {e}")
