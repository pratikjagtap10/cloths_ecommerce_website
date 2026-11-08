import pytest

pytestmark = pytest.mark.django_db


def test_register_creates_user(api_client):
    res = api_client.post(
        "/api/core/auth/register/",
        {"email": "New@Example.com", "password": "Very-strong-9", "first_name": "New", "last_name": "User"},
        format="json",
    )
    assert res.status_code == 201
    assert res.data["email"] == "new@example.com"
    assert "password" not in res.data


def test_register_duplicate_email_is_case_insensitive(api_client, user):
    res = api_client.post(
        "/api/core/auth/register/",
        {"email": "JANE@example.com", "password": "Very-strong-9", "first_name": "J", "last_name": "D"},
        format="json",
    )
    assert res.status_code == 400
    assert res.data["detail"] == "Email: A user with this email already exists."


def test_register_rejects_weak_password(api_client):
    res = api_client.post(
        "/api/core/auth/register/",
        {"email": "a@b.com", "password": "password", "first_name": "A", "last_name": "B"},
        format="json",
    )
    assert res.status_code == 400
    assert res.data["detail"].startswith("Password:")


def test_login_returns_tokens_and_me_works(api_client, user):
    res = api_client.post(
        "/api/core/auth/login/", {"email": "JANE@example.com", "password": "S3cure-pass!"}, format="json"
    )
    assert res.status_code == 200
    assert {"access", "refresh"} <= set(res.data)

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
    me = api_client.get("/api/core/auth/me/")
    assert me.status_code == 200
    assert me.data == {"id": user.id, "email": user.email, "first_name": "Jane", "last_name": "Doe"}


def test_login_wrong_password(api_client, user):
    res = api_client.post("/api/core/auth/login/", {"email": user.email, "password": "nope"}, format="json")
    assert res.status_code == 401
    assert res.data["detail"] == "Invalid email or password."


def test_me_requires_token(api_client):
    assert api_client.get("/api/core/auth/me/").status_code == 401
