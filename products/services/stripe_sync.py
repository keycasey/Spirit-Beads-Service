from payments.stripe import stripe

def ensure_stripe_product_and_price(product):
    """
    Ensures Stripe Product exists and creates a NEW Stripe Price.
    Stripe Prices are immutable, so this always creates a new price.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Prevent recursion if we're already syncing
    if getattr(product, '_stripe_syncing', False):
        logger.debug(f"Skipping sync for {product.id}: already syncing")
        return None
    product._stripe_syncing = True

    try:
        logger.info(f"Syncing product {product.id} ({product.name}) - price={product.price} {product.currency}")

        # Create Stripe Product if missing
        if not product.stripe_product_id:
            logger.info(f"Creating Stripe product for {product.id}")
            stripe_product = stripe.Product.create(
                name=product.name,
                metadata={"product_id": product.id}
            )
            product.stripe_product_id = stripe_product.id
            product.save(update_fields=["stripe_product_id"])
            logger.info(f"Created Stripe product {stripe_product.id} for product {product.id}")
        else:
            logger.info(f"Using existing Stripe product {product.stripe_product_id} for product {product.id}")

        # Create Stripe Price
        logger.info(f"Creating Stripe price for product {product.id} ({product.stripe_product_id})")
        stripe_price = stripe.Price.create(
            product=product.stripe_product_id,
            unit_amount=product.price,
            currency=product.currency,
        )
        logger.info(f"Created Stripe price {stripe_price.id} for product {product.id}")

        product.stripe_price_id = stripe_price.id
        product.save(update_fields=["stripe_price_id"])
        logger.info(f"Updated product {product.id} with stripe_price_id={stripe_price.id}")

        return stripe_price
    except stripe.error.StripeError as e:
        logger.exception(f"Stripe API error for product {product.id}: {e}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error syncing product {product.id}: {e}")
        raise
    finally:
        product._stripe_syncing = False
