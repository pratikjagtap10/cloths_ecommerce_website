import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from catalog.models import Category, Product, ProductVariant
from users.models import User

INTERNAL_KEY = "test-internal-key"


@pytest.fixture(autouse=True)
def _settings():
    with override_settings(INTERNAL_API_KEY=INTERNAL_KEY):
        yield


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="jane@example.com", password="S3cure-pass!", first_name="Jane", last_name="Doe"
    )


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def internal_client():
    client = APIClient()
    client.credentials(HTTP_X_INTERNAL_KEY=INTERNAL_KEY)
    return client


@pytest.fixture
def catalog(db):
    men = Category.objects.create(name="Men", slug="men")
    tees = Category.objects.create(name="T-Shirts", slug="men-tshirts", parent=men)
    women = Category.objects.create(name="Women", slug="women")
    dresses = Category.objects.create(name="Dresses", slug="women-dresses", parent=women)

    tee = Product.objects.create(name="Basic Tee", slug="basic-tee", category=tees, base_price=500, is_featured=True)
    dress = Product.objects.create(name="Linen Dress", slug="linen-dress", category=dresses, base_price=2500)
    hidden = Product.objects.create(name="Old Tee", slug="old-tee", category=tees, base_price=100, is_active=False)

    tee_m = ProductVariant.objects.create(product=tee, size="M", color="Black", sku="T-BLK-M", stock=5)
    tee_xl = ProductVariant.objects.create(
        product=tee, size="XL", color="White", sku="T-WHT-XL", stock=1, price_override=600
    )
    dress_s = ProductVariant.objects.create(product=dress, size="S", color="Beige", sku="D-BEI-S", stock=2)
    ProductVariant.objects.create(product=hidden, size="M", color="Grey", sku="O-GRY-M", stock=9)
    return {"tee": tee, "dress": dress, "tee_m": tee_m, "tee_xl": tee_xl, "dress_s": dress_s}


@pytest.fixture
def address():
    return {
        "full_name": "Jane Doe",
        "phone": "9876543210",
        "line1": "12 MG Road",
        "city": "Pune",
        "state": "Maharashtra",
        "postal_code": "411001",
    }
