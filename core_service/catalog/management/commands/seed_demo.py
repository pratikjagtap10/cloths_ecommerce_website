"""
python manage.py seed_demo           -> load demo data if the catalog is empty
python manage.py seed_demo --force   -> reload catalog (resets stock!) and missing users/orders

Uses the SAME JSON files as the frontend mock mode (catalog/seed_data/), so the
real backend shows exactly the products you saw while developing the UI.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connection, transaction
from django.utils.dateparse import parse_datetime

from catalog.models import Category, Product, ProductVariant
from orders.models import Order, OrderItem
from users.models import User

DATA_DIR = Path(__file__).resolve().parents[2] / "seed_data"


def load(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


class Command(BaseCommand):
    help = "Load demo categories, products, users and orders."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Reload the catalog even if it exists")

    @transaction.atomic
    def handle(self, *args, force=False, **options):
        if Product.objects.exists() and not force:
            self.stdout.write("Demo data already present - skipping (use --force to reload).")
            return

        self._seed_catalog()
        self._seed_users()
        self._seed_orders()
        self._reset_sequences()
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Category.objects.count()} categories, {Product.objects.count()} products, "
            f"{ProductVariant.objects.count()} variants, {User.objects.count()} users, "
            f"{Order.objects.count()} orders."
        ))

    def _seed_catalog(self):
        # Parents first so children can reference them
        for c in sorted(load("categories.json"), key=lambda c: c["parent"] is not None):
            Category.objects.update_or_create(
                id=c["id"], defaults={"name": c["name"], "slug": c["slug"], "parent_id": c["parent"]}
            )

        for p in load("products.json"):
            product, _ = Product.objects.update_or_create(
                id=p["id"],
                defaults={
                    "name": p["name"],
                    "slug": p["slug"],
                    "description": p["description"],
                    "category_id": p["category"]["id"],
                    "base_price": p["base_price"],
                    "is_active": p["is_active"],
                    "is_featured": p["is_featured"],
                    "created_at": parse_datetime(p["created_at"]),
                },
            )
            for v in p["variants"]:
                ProductVariant.objects.update_or_create(
                    id=v["id"],
                    defaults={
                        "product": product,
                        "size": v["size"],
                        "color": v["color"],
                        "color_hex": v["color_hex"],
                        "sku": v["sku"],
                        "stock": v["stock"],
                        "price_override": v["price"] if v["price"] != p["base_price"] else None,
                    },
                )

    def _seed_users(self):
        for u in load("users.json"):
            if User.objects.filter(email=u["email"]).exists():
                continue
            create = User.objects.create_superuser if u["email"].startswith("admin@") else User.objects.create_user
            create(
                id=u["id"],
                email=u["email"],
                password=u["password"],
                first_name=u["first_name"],
                last_name=u["last_name"],
            )

    def _seed_orders(self):
        for o in load("orders.json"):
            if Order.objects.filter(id=o["id"]).exists():
                continue
            order = Order.objects.create(
                id=o["id"],
                user_id=o["user_id"],
                status=o["status"],
                subtotal=o["total"] - o["shipping_fee"],
                shipping_fee=o["shipping_fee"],
                total=o["total"],
                created_at=parse_datetime(o["created_at"]),
                **o["address"],
            )
            for item in o["items"]:
                OrderItem.objects.create(
                    order=order,
                    variant_id=item["variant_id"],
                    product_name=item["product_name"],
                    product_slug=item["product_slug"],
                    size=item["size"],
                    color=item["color"],
                    color_hex=item["color_hex"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                )

    def _reset_sequences(self):
        # We inserted explicit ids, so tell PostgreSQL where auto-increment should continue
        models = [Category, Product, ProductVariant, User, Order, OrderItem]
        statements = connection.ops.sequence_reset_sql(no_style(), models)
        with connection.cursor() as cursor:
            for sql in statements:
                cursor.execute(sql)
