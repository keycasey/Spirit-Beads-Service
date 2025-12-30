from payments.stripe import stripe

def ensure_stripe_product_and_price(product):
    """
    Ensures Stripe Product exists and creates a NEW Stripe Price.
    Stripe Prices are immutable, so this always creates a new price.
    """

    # Create Stripe Product if missing
    if not product.stripe_product_id:
        stripe_product = stripe.Product.create(
            name=product.name,
            metadata={"product_id": product.id}
        )
        product.stripe_product_id = stripe_product.id
        product.save(update_fields=["stripe_product_id"])

    # Create Stripe Price
    stripe_price = stripe.Price.create(
        product=product.stripe_product_id,
        unit_amount=product.price,
        currency=product.currency,
    )

    product.stripe_price_id = stripe_price.id
    product.save(update_fields=["stripe_price_id"])

    return stripe_price
