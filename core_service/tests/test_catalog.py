import pytest

pytestmark = pytest.mark.django_db


def slugs(res):
    return [p["slug"] for p in res.data["results"]]


def test_categories_list_is_public(api_client, catalog):
    res = api_client.get("/api/core/categories/")
    assert res.status_code == 200
    assert {"id", "name", "slug", "parent"} == set(res.data[0])


def test_products_hide_inactive_and_paginate(api_client, catalog):
    res = api_client.get("/api/core/products/")
    assert res.status_code == 200
    assert res.data["count"] == 2
    assert "old-tee" not in slugs(res)


def test_parent_category_includes_children(api_client, catalog):
    res = api_client.get("/api/core/products/?category=men")
    assert slugs(res) == ["basic-tee"]


def test_filters_size_color_price_featured_search(api_client, catalog):
    assert slugs(api_client.get("/api/core/products/?size=S")) == ["linen-dress"]
    assert slugs(api_client.get("/api/core/products/?color=white")) == ["basic-tee"]
    assert slugs(api_client.get("/api/core/products/?min_price=1000")) == ["linen-dress"]
    assert slugs(api_client.get("/api/core/products/?featured=true")) == ["basic-tee"]
    assert slugs(api_client.get("/api/core/products/?search=linen")) == ["linen-dress"]


def test_ordering_alias_price(api_client, catalog):
    assert slugs(api_client.get("/api/core/products/?ordering=price")) == ["basic-tee", "linen-dress"]
    assert slugs(api_client.get("/api/core/products/?ordering=-price")) == ["linen-dress", "basic-tee"]


def test_product_detail_with_variant_price(api_client, catalog):
    res = api_client.get("/api/core/products/basic-tee/")
    assert res.status_code == 200
    prices = {v["size"]: v["price"] for v in res.data["variants"]}
    assert prices == {"M": 500, "XL": 600}
    assert res.data["category"] == {"id": catalog["tee"].category_id, "name": "T-Shirts", "slug": "men-tshirts"}


def test_unknown_product_404(api_client, catalog):
    assert api_client.get("/api/core/products/nope/").status_code == 404
