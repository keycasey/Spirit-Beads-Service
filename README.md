# Spirit Beads Backend
[![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Django Version](https://img.shields.io/badge/django-6.0-green.svg)](https://www.djangoproject.com/)
[![Django REST Framework](https://img.shields.io/badge/DRF-3.14-red.svg)](https://www.django-rest-framework.org/)
[![Stripe Integration](https://img.shields.io/badge/stripe-integrated-blueviolet.svg)](https://stripe.com)
Spirit Beads Backend is the production-grade, scalable e-commerce engine powering [thebeadedcase.com](https://thebeadedcase.com). Built with Python and the Django Rest Framework, this REST API provides a robust foundation for product management, order orchestration, and secure payment processing. It is a decoupled backend designed for reliability and maintainability.
## 🚀 Live Deployment
This project is currently deployed and serving production traffic at: **[https://thebeadedcase.com](https://thebeadedcase.com)**
## ✨ Key Features
-   **Full E-commerce Logic**: Manages product catalog, inventory, and categories.
-   **Stripe Integration**: Seamless and secure payment processing via Stripe. Products and prices are automatically synced with the Stripe API.
-   **Complete Order Orchestration**: Handles the entire order lifecycle from "pending" to "paid," including automatic inventory reduction for fulfilled orders.
-   **Custom Order Workflow**: A sophisticated process for custom requests, featuring an admin review and approval system. Admins can set a quoted price and generate a unique Stripe payment link for the customer.
-   **REST API Architecture**: A clean, decoupled REST API built with the Django REST Framework, providing structured data for any frontend client.
-   **Modular Design**: Organized into logical Django apps (`products`, `orders`, `payments`, `custom_orders`) for clear separation of concerns and scalability.
## 🛠️ Technical Stack
-   **Backend**: Python, Django 6.0
-   **API**: Django REST Framework
-   **Payment Processing**: Stripe API
-   **Database**: PostgreSQL (in production), SQLite (for local development)
-   **CORS**: `django-cors-headers` for handling cross-origin requests.
-   **Configuration**: `python-decouple` for managing environment variables.
-   **Media Files**: Pillow for image processing and management.
## 🚀 Getting Started
Follow these instructions to get the project running locally for development and testing.
### Prerequisites
-   Python 3.10+
-   `pip` and `venv`
-   A Stripe account and API keys.
### Installation
1.  **Clone the repository:**
    ```sh
    git clone https://github.com/caseyjkey/spirit-beads-backend.git
    cd spirit-beads-backend
    ```
2.  **Create and activate a virtual environment:**
    ```sh
    python -m venv venv
    source venv/bin/activate
    # On Windows, use: venv\Scripts\activate
    ```
3.  **Install dependencies:**
    ```sh
    pip install -r requirements.txt
    ```
### Configuration
1.  Create a `.env` file in the project root directory. Copy the contents of `.env.example` if it exists, or create it from scratch.
2.  Add your configuration details to the `.env` file. At a minimum, you will need to provide your Stripe API keys and a `SECRET_KEY` for Django.
    ```ini
    SECRET_KEY='your-strong-secret-key'
    DEBUG=True
    STRIPE_SECRET_KEY='sk_test_...'
    STRIPE_PUBLISHABLE_KEY='pk_test_...'
    STRIPE_WEBHOOK_SECRET='whsec_...'
    # Add any other required environment variables, like database URL
    DATABASE_URL='sqlite:///db.sqlite3'
    ```
3.  **Run database migrations** to set up your local database schema:
    ```sh
    python manage.py migrate
    ```
## 💡 Usage
Once the installation and configuration are complete, you can run the local development server:
```sh
python manage.py runserver
```
The API will be accessible at `http://127.0.0.1:8000`. You can access the Django admin panel at `http://127.0.0.1:8000/admin`. You may need to create a superuser first:
```sh
python manage.py createsuperuser
```
## 🔍 Technical Deep Dive
This project serves as a powerful example of a scalable e-commerce backend.
-   **Order Orchestration**: When an order's status is updated to `paid` (typically via a Stripe webhook), the `Order.save()` method is triggered. This method intelligently checks the previous status and, if the order is newly paid, invokes a private `_update_inventory()` method. This method iterates through the `OrderItem`s, decrementing the `inventory_count` on the corresponding `Product` model, ensuring the storefront accurately reflects stock levels.
-   **Stripe Synchronization**: The `Product` model features an overridden `save()` method that synchronizes product data with Stripe. When a new product is created or an existing product's price is changed, it calls the `ensure_stripe_product_and_price` service. This service creates a corresponding product and price object in Stripe, storing their IDs (`stripe_product_id`, `stripe_price_id`) in the database. This keeps the local product catalog as the single source of truth while leveraging Stripe's robust infrastructure for transactions.
-   **Custom Order Lifecycle**: The `CustomOrderRequest` model is the centerpiece of the custom order workflow. A request begins in a `pending` state. An administrator can review it via the Django Admin, add notes, and set a `quoted_price`. Upon approval, the system can generate a `stripe_payment_link`. Once the customer completes payment, the request is transitioned to `paid`, and a corresponding `orders.Order` object is created to bring it into the standard order fulfillment pipeline.
## 📚 Related Projects
-   **[lighter-splitter](https://github.com/caseyjkey/lighter-splitter)** - Spirit Beads ecosystem - image processing pipeline
-   **[spirit-beads-service](https://github.com/caseyjkey/spirit-beads-service)** - Service layer architecture
-   **[spirit-beads-ui](https://github.com/caseyjkey/spirit-beads-ui)** - React 18 production frontend


## Related Projects

- **[lighter-splitter](https://github.com/caseyjkey/lighter-splitter)** - Spirit Beads ecosystem - image processing pipeline
- **[spirit-beads-service](https://github.com/caseyjkey/spirit-beads-service)** - Service layer architecture
- **[spirit-beads-ui](https://github.com/caseyjkey/spirit-beads-ui)** - React 18 production frontend
