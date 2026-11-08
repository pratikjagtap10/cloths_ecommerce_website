# Backend Developer Guide: Threads Microservices

This guide explains how to **run, understand and change** the backend of the
Threads clothing store on your machine with Docker.

- To test the APIs with Postman, see `BACKEND_POSTMAN_TESTING_GUIDE.md`.
- For the UI, see `FRONTEND_DEVELOPER_GUIDE.md` and `UI_DEVELOPER_GUIDE.md`.

---

## Contents

1. [Architecture](#1-architecture)
2. [Prerequisites](#2-prerequisites)
3. [Quick start](#3-quick-start)
4. [URLs and demo accounts](#4-urls-and-demo-accounts)
5. [Everyday Docker commands](#5-everyday-docker-commands)
6. [Running the automated tests](#6-running-the-automated-tests)
7. [Project structure](#7-project-structure)
8. [API reference](#8-api-reference)
9. [How the microservices communicate](#9-how-the-microservices-communicate)
10. [Configuration (.env)](#10-configuration-env)
11. [Making changes](#11-making-changes)
12. [Troubleshooting](#12-troubleshooting)
13. [Simplifications and next steps](#13-simplifications-and-next-steps)

---

## 1. Architecture

```
                              Browser / Postman
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │  nginx  (API gateway)   :80    │  http://localhost
                    └──┬──────────────┬───────────┬──┘
           /           │ /api/core/*  │           │ /api/shop/*
           /admin/     │              │           │
   ┌───────▼──────┐  ┌─▼──────────────▼──┐     ┌──▼──────────────────┐
   │  frontend    │  │  core_service     │◄────│  shop_service       │
   │  Next.js     │  │  Django + DRF     │ REST│  FastAPI            │
   │  :3000       │  │  :8000            │(sync│  :8001              │
   └──────────────┘  │  users, catalog,  │ +key│  cart, checkout,    │
                     │  orders, admin    │)    │  payments           │
                     └──┬─────────┬──────┘     └───┬───────────┬─────┘
                        │         │    Redis Pub/Sub│           │
                        │   ┌─────▼─────────────────▼──┐        │
                        │   │  redis :6379  "events"   │        │
                        │   └─────▲────────────────────┘        │
                        │         │ subscribes                  │
                        │   ┌─────┴──────────┐                  │
                        │   │  core_worker   │ (same image as   │
                        │   │  event consumer│  core_service)   │
                        │   └─────┬──────────┘                  │
                   ┌────▼─────────▼──┐                  ┌───────▼────────┐
                   │ core_db          │                  │ shop_db        │
                   │ PostgreSQL :5433 │                  │ PostgreSQL:5434│
                   └──────────────────┘                  └────────────────┘
```

| Container | Technology | Responsibility | Owns database |
| --- | --- | --- | --- |
| `core_service` | Python 3.12, Django 5.2, Django REST Framework, SimpleJWT | Users and login (issues JWT), catalog, orders, admin panel, internal APIs | `core_db` |
| `core_worker` | same image | Listens to Redis events: `payment.succeeded` → order PAID and stock reduced | `core_db` |
| `shop_service` | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, httpx | Cart, checkout, mock payments; verifies JWTs; calls core; publishes events | `shop_db` |
| `core_db`, `shop_db` | PostgreSQL 16 | One database per service | |
| `redis` | Redis 7 | Message broker (Pub/Sub channel `events`) | |
| `nginx` | Nginx 1.27 | API gateway: single entry point, routing, rate limit, blocks `/internal/` | |
| `frontend` | Next.js 15 | Storefront UI (now uses the real APIs) | |

---

## 2. Prerequisites

- **Docker Desktop** (running). Everything else (Python, PostgreSQL, Redis) runs inside containers.
- Free ports: **80, 3000, 8000, 8001, 5433, 5434**.
- Optional: **Postman** for manual API testing, and **Node.js 20+** only if you want to run the frontend outside Docker.

---

## 3. Quick start

From the project root (`C:\ecommerce_demo`):

```bash
# 1. Create your local settings (only once)
cp .env.example .env            # PowerShell: Copy-Item .env.example .env

# 2. Build and start all 8 containers
docker compose up --build -d

# 3. Wait until everything is healthy (about 30-60 s the first time)
docker compose ps
```

Expected `docker compose ps` result: `core_db`, `shop_db`, `redis`, `core_service` and
`shop_service` show **(healthy)**, and `core_worker`, `frontend` and `nginx` show **Up**.

On first start the core service automatically:
1. applies database migrations,
2. loads the demo data (12 categories, 17 products, 136 variants, 2 users, 2 orders).

The shop service applies its own migrations with Alembic.

Then open **http://localhost** and shop. 🎉

> The first build downloads Python/Node/PostgreSQL images and packages. With a
> slow connection it can take 10+ minutes. Later builds are much faster
> because Docker caches the layers.

---

## 4. URLs and demo accounts

| What | URL |
| --- | --- |
| Storefront (through gateway) | http://localhost |
| Django admin panel | http://localhost/admin/ |
| FastAPI interactive docs (Swagger) | http://localhost/api/shop/docs |
| Core API (gateway) | http://localhost/api/core/ ... |
| Shop API (gateway) | http://localhost/api/shop/ ... |
| Core service directly (debugging, internal API) | http://localhost:8000 |
| Shop service directly | http://localhost:8001 |
| Django REST browsable API | http://localhost/api/core/products/ (open in a browser) |
| core_db from pgAdmin/DBeaver | `localhost:5433`, db `core_db`, user/pass `core`/`core` |
| shop_db | `localhost:5434`, db `shop_db`, user/pass `shop`/`shop` |

| Account | Email | Password | Can use admin? |
| --- | --- | --- | --- |
| Customer | `demo@clothstore.com` | `demo1234` | no |
| Admin | `admin@clothstore.com` | `admin1234` | **yes** |

### Try the admin panel
1. Log in at http://localhost/admin/ as the admin.
2. **Catalog → Products**: edit prices, stock per size/colour, mark products featured.
3. **Orders → Orders**: select a **PAID** order, choose the action
   *"Mark selected PAID orders as SHIPPED"*, and click **Go**. This publishes an
   `order.shipped` event, and the shop service logs a mock "shipped" email
   (`docker compose logs shop_service`).

---

## 5. Everyday Docker commands

| Task | Command |
| --- | --- |
| Start everything | `docker compose up -d` |
| Rebuild after code changes | `docker compose up --build -d` |
| Rebuild just one service | `docker compose up --build -d shop_service` |
| Status and health | `docker compose ps` |
| Follow logs (all) | `docker compose logs -f` |
| Logs of one service | `docker compose logs -f core_service` |
| Watch the event flow | `docker compose logs -f core_worker shop_service` |
| Restart one service | `docker compose restart core_worker` |
| Stop (keep data) | `docker compose down` |
| Stop and **delete all data** | `docker compose down -v` |
| Django shell | `docker compose exec core_service python manage.py shell` |
| Create another admin | `docker compose exec core_service python manage.py createsuperuser` |
| Reset catalog and stock to demo values | `docker compose exec core_service python manage.py seed_demo --force` |
| SQL console (core) | `docker compose exec core_db psql -U core -d core_db` |
| SQL console (shop) | `docker compose exec shop_db psql -U shop -d shop_db` |
| Watch Redis events live | `docker compose exec redis redis-cli SUBSCRIBE events` |

> Code is **copied into the images** at build time, so after editing Python files
> run `docker compose up --build -d <service>`.

---

## 6. Running the automated tests

Both services have pytest suites that run inside Docker.

```bash
# FastAPI shop service: 11 tests. Uses a temporary SQLite DB and a fake core
# service, so it doesn't need other containers.
docker compose run --rm --no-deps -e RUN_MIGRATIONS=0 shop_service pytest

# Django core service: 22 tests. Uses a temporary PostgreSQL test database.
docker compose up -d core_db redis
docker compose run --rm --no-deps -e RUN_STARTUP_TASKS=0 core_service pytest --create-db
```

What the tests cover:

| Service | Tests |
| --- | --- |
| core | register/login/JWT/me, weak password and duplicate email errors, catalog filters/search/sort/pagination, internal API key security, order creation with server-side prices, free shipping rule, out-of-stock 409, users see only their own orders, `payment.succeeded` event marks PAID and is idempotent |
| shop | JWT required/expired/wrong type, cart add/merge/update/remove, stock limit, core service down → 503, separate carts per user, address validation messages, full checkout → failed payment → successful payment → event published → cart cleared, payment ownership |

For the **end-to-end** check across all services, run the Postman collection (see the Postman guide).

---

## 7. Project structure

```
ecommerce_demo/
├── docker-compose.yml            # all 8 containers
├── .env.example → .env           # local settings (secrets, DB passwords)
├── nginx/default.conf            # API gateway routes
├── postman/                      # Postman collection + environment
│
├── core_service/                 # ── DJANGO ──────────────────────────────
│   ├── Dockerfile, entrypoint.sh # entrypoint: migrate + seed, then start
│   ├── requirements.txt
│   ├── core/                     # project: settings, urls, error format,
│   │   ├── settings.py           #   internal-key permission, health view
│   │   ├── urls.py               # /admin/  /api/core/...  /internal/...
│   │   ├── exceptions.py         # {"detail": "..."} error format
│   │   └── permissions.py        # HasInternalApiKey (X-Internal-Key)
│   ├── users/                    # custom User (email login), register, JWT login, me
│   ├── catalog/                  # Category, Product, ProductVariant, ProductImage
│   │   ├── filters.py            # category/size/color/price filters, ordering alias
│   │   ├── seed_data/*.json      # SAME data as the frontend mocks
│   │   └── management/commands/seed_demo.py
│   ├── orders/                   # Order, OrderItem
│   │   ├── services.py           # create_order(), mark_order_paid() business logic
│   │   └── admin.py              # "mark shipped" action → publishes order.shipped
│   ├── events/                   # Redis Pub/Sub
│   │   ├── bus.py                # publish()
│   │   ├── handlers.py           # event type → handler
│   │   └── management/commands/run_event_consumer.py   # core_worker
│   └── tests/
│
└── shop_service/                 # ── FASTAPI ─────────────────────────────
    ├── Dockerfile, entrypoint.sh # entrypoint: alembic upgrade head, then uvicorn
    ├── alembic/versions/         # database migrations
    ├── app/
    │   ├── main.py               # app, CORS, routers, lifespan (event listener)
    │   ├── config.py             # settings from env vars (pydantic-settings)
    │   ├── database.py           # async SQLAlchemy engine + get_db dependency
    │   ├── models.py             # Cart, CartItem, Payment
    │   ├── schemas.py            # Pydantic request/response models + validation
    │   ├── security.py           # verifies Django-issued JWT → CurrentUser
    │   ├── errors.py             # {"detail": "..."} error format
    │   ├── routers/              # cart.py, checkout.py, payments.py, health.py
    │   └── services/
    │       ├── core_client.py    # HTTP client to Django (timeouts, retries)
    │       ├── events.py         # publish + listen (Redis)
    │       └── notifications.py  # mock emails (logged)
    └── tests/
```

---

## 8. API reference

All public URLs below go through the gateway `http://localhost`. Responses are
JSON. Errors always have a readable `detail` field.

### Core service (Django): `/api/core/`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/api/core/health/` | – | Health check |
| POST | `/api/core/auth/register/` | – | `{email, password, first_name, last_name}` → user |
| POST | `/api/core/auth/login/` | – | `{email, password}` → `{access, refresh}` |
| POST | `/api/core/auth/refresh/` | – | `{refresh}` → `{access}` |
| GET | `/api/core/auth/me/` | Bearer | Current user |
| GET | `/api/core/categories/` | – | All categories (tree via `parent`) |
| GET | `/api/core/products/` | – | Paginated (8/page). Query: `category`, `size`, `color`, `min_price`, `max_price`, `featured=true`, `search`, `ordering` (`price`, `-price`, `name`, `-created_at`), `page` |
| GET | `/api/core/products/{slug}/` | – | Product with variants |
| GET | `/api/core/orders/` | Bearer | My orders (newest first) |
| GET | `/api/core/orders/{id}/` | Bearer | One of my orders (others → 404) |

### Shop service (FastAPI): `/api/shop/`

Full interactive docs: **http://localhost/api/shop/docs**

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/api/shop/health/` | – | Health (DB + Redis) |
| GET | `/api/shop/cart/` | Bearer | My cart `{items, subtotal}` |
| POST | `/api/shop/cart/items/` | Bearer | `{variant_id, quantity}`: checks stock with core |
| PATCH | `/api/shop/cart/items/{id}/` | Bearer | `{quantity}` |
| DELETE | `/api/shop/cart/items/{id}/` | Bearer | Remove item |
| POST | `/api/shop/checkout/` | Bearer | `{address:{...}}` → `{order, payment}` |
| GET | `/api/shop/payments/{id}/` | Bearer | Payment status |
| POST | `/api/shop/payments/{id}/confirm/` | Bearer | `{success: true/false}`: mock payment |

### Internal API (service-to-service only)

Blocked by Nginx. Reachable only inside Docker, or on `localhost:8000` for debugging.
Requires the header `X-Internal-Key: <INTERNAL_API_KEY>`.

| Method | Path | Called by | Description |
| --- | --- | --- | --- |
| GET | `/internal/variants/{id}/` | shop service | Price, stock, product info |
| POST | `/internal/orders/` | shop service | `{user_id, address, items:[{variant_id, quantity}]}` → order (PENDING) |

### Status codes used

| Code | Meaning here |
| --- | --- |
| 200 / 201 | OK / created |
| 400 | Invalid input or not enough stock in cart |
| 401 | Missing, invalid or expired token |
| 403 | Missing/wrong internal API key |
| 404 | Not found (or not yours) |
| 409 | Stock changed between cart and checkout |
| 422 | FastAPI request validation failed |
| 429 | Too many login attempts (Nginx rate limit) |
| 503 | A service it depends on is down |

---

## 9. How the microservices communicate

### 9.1 Database per service
`core_service` only talks to `core_db`; `shop_service` only to `shop_db`. The cart stores
`user_id` and `variant_id` as plain numbers. There are **no foreign keys across
databases**. To get data owned by another service, ask that service.

### 9.2 Shared JWT authentication (stateless)
```
Browser ──login──► Django: checks password, signs JWT with JWT_SECRET
                   token payload: {user_id, email, first_name, token_type, exp}
Browser ──Bearer token──► FastAPI: verifies signature with the SAME JWT_SECRET
                                    (no call to Django needed)
```
Code: `core_service/users/serializers.py` (`LoginSerializer`), `shop_service/app/security.py`.

### 9.3 Synchronous REST (request/response)
The shop service asks Django and **waits** for the answer:

| When | Call | Why |
| --- | --- | --- |
| Add/update cart item | `GET /internal/variants/{id}/` | Current price and stock (Django is the source of truth) |
| Checkout | `POST /internal/orders/` | Django re-checks stock with row locks and creates the order using ITS prices |

Resilience in `shop_service/app/services/core_client.py`:
- **Timeout** of 3 s on every call.
- **Retry** with backoff on connection errors (GET only for timeouts. A POST is not retried
  after a timeout because it might create a duplicate order).
- If Django is down, the shop answers **503** with a clear message instead of crashing.
- Secured with the **`X-Internal-Key`** header (`core_service/core/permissions.py`).

### 9.4 Asynchronous events (Redis Pub/Sub)
The publisher does **not wait**. Subscribers react when the message arrives.

Channel: `events`. Message: `{"type": "<event>", "data": {...}}`

| Event | Published by | Consumed by | Effect |
| --- | --- | --- | --- |
| `payment.succeeded` | shop_service (`routers/payments.py`) | core_worker (`events/handlers.py`) | Order → PAID, stock reduced (idempotent) |
| `order.shipped` | core_service admin action | shop_service listener (`services/events.py`) | Mock "shipped" email logged |

### 9.5 Complete checkout flow

```
Frontend            Nginx      shop_service (FastAPI)          core_service (Django)     core_worker
   │ POST /api/shop/checkout/ ─►│                                       │                     │
   │                            │ 1 read cart (shop_db)                 │                     │
   │                            │ 2 POST /internal/orders/ ────────────►│ lock rows, check    │
   │                            │                                       │ stock, use own      │
   │                            │◄──────────── order (PENDING) ─────────│ prices, save order  │
   │                            │ 3 save Payment(PENDING)               │                     │
   │◄─────────── {order, payment} ─┤                                    │                     │
   │ POST /payments/{id}/confirm/ {success:true}                        │                     │
   │                            │ 4 Payment=SUCCESS, clear cart         │                     │
   │                            │ 5 PUBLISH payment.succeeded ──► Redis ─────────────────────►│
   │                            │ 6 BackgroundTask: mock email          │   7 order=PAID,     │
   │◄──────────── {status:"SUCCESS"}                                    │     stock -= qty    │
   │ GET /api/core/orders/{id}/ ───────────────────────────────────────►│ (status PAID)       │
```

Watch it happen live: `docker compose logs -f core_worker shop_service` and place an order in the UI.

### 9.6 API gateway (Nginx)
`nginx/default.conf`:
- Routes by path prefix, so the browser sees **one origin** and has no CORS issues.
- Blocks `/internal/` from outside.
- Rate-limits login to 30 requests/minute per IP (brute-force protection). Too many → **429**.
- Adds an `X-Request-ID` header to every request (useful for tracing logs).
- Re-resolves container names via Docker DNS, so rebuilding a service doesn't cause 502 errors.

---

## 10. Configuration (.env)

`docker compose` reads `.env` automatically. Main variables:

| Variable | Used by | Purpose |
| --- | --- | --- |
| `JWT_SECRET` | core + shop | Signs/verifies login tokens. **Must be identical** in both services and ≥ 32 characters |
| `INTERNAL_API_KEY` | core + shop | Service-to-service authentication |
| `REDIS_URL`, `EVENTS_CHANNEL` | core, worker, shop | Event bus |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` | core | Django security and debug pages |
| `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS` | core | Token lifetimes (30 min / 7 days) |
| `SEED_DEMO_DATA` | core | `1` = load demo data if the catalog is empty |
| `CORE_DB_*`, `SHOP_DB_*` | databases | Names and credentials |
| `NEXT_PUBLIC_USE_MOCK` | frontend build | `false` = real backend, `true` = JSON mocks |

After changing `.env`, run `docker compose up -d` (and `--build` for `NEXT_PUBLIC_*`,
which are baked into the frontend at build time).

---

## 11. Making changes

### Add or change a Django model
```bash
# 1. Edit core_service/<app>/models.py
# 2. Generate the migration file into your source folder (bind-mount)
docker compose run --rm --no-deps --user root -e RUN_STARTUP_TASKS=0 -v ./core_service:/app core_service python manage.py makemigrations
# 3. Rebuild + restart (entrypoint applies migrations)
docker compose up --build -d core_service core_worker
```

### Add or change a FastAPI (SQLAlchemy) model
```bash
# 1. Edit shop_service/app/models.py
# 2. Autogenerate an Alembic migration (needs shop_db running)
docker compose run --rm --user root -e RUN_MIGRATIONS=0 -v ./shop_service:/app shop_service alembic revision --autogenerate -m "add wishlist"
# 3. Review the file in shop_service/alembic/versions/, then rebuild
docker compose up --build -d shop_service
```

### Add an endpoint
- **Django:** serializer (`serializers.py`) → view (`views.py`) → route (`urls.py`) → test.
- **FastAPI:** Pydantic schema (`schemas.py`) → function in a router (`routers/*.py`) → test.
  It appears automatically in `/api/shop/docs`.
- **New URL prefix?** Add a `location` in `nginx/default.conf`.
- **Frontend uses it?** Add a method to `ApiClient` in `frontend/src/types/index.ts` and implement
  it in both `mockApi.ts` and `httpApi.ts`.

### Add a new event
1. Publish: `publish("order.cancelled", {...})` (`events/bus.py` in Django or `services/events.py` in FastAPI).
2. Consume: add a handler to `HANDLERS` in `core_service/events/handlers.py`, or to `_handle()` in
   `shop_service/app/services/events.py`.
3. Make handlers **idempotent**: the same event may arrive twice.

### Run the frontend on mock data again
```bash
# PowerShell: $env:NEXT_PUBLIC_USE_MOCK="true"; docker compose up --build -d frontend
NEXT_PUBLIC_USE_MOCK=true docker compose up --build -d frontend
```
(or set `NEXT_PUBLIC_USE_MOCK=true` in `.env`)

---

## 12. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `Bind for 0.0.0.0:80 failed: port is already allocated` | Another program uses port 80 (IIS, Skype, another web server). Stop it, or change `"80:80"` to `"8080:80"` in docker-compose.yml **and** `NEXT_PUBLIC_API_URL` to `http://localhost:8080/api`, then rebuild the frontend. |
| A container keeps restarting | `docker compose logs <service>` shows the error. Most often the DB wasn't ready or a setting is wrong in `.env`. |
| `exec ./entrypoint.sh: no such file or directory` | Windows line endings in the script. The Dockerfiles already convert them; rebuild with `docker compose build --no-cache <service>`. |
| `Invalid HTTP_HOST header: 'core_service:8000'` | Django rejects underscores in host names. Call Django as `core-service` (an alias already defined in docker-compose.yml). |
| 502 Bad Gateway right after starting | The service is still starting. Wait for `(healthy)` in `docker compose ps`. |
| Order stays **PENDING** after a successful payment | `core_worker` wasn't running when the event was published (Pub/Sub doesn't store messages). Check `docker compose ps core_worker` and its logs. To fix one order, use the Django shell: `from orders.services import mark_order_paid; mark_order_paid(<id>)` |
| 401 "Session expired" | Access token lasts 30 minutes. The frontend refreshes it automatically; in Postman run **Login** again. |
| 429 Too Many Requests on login | Nginx rate limit. Wait one minute. |
| "Only N left in stock" everywhere | Test purchases used up stock: `docker compose exec core_service python manage.py seed_demo --force` |
| Want a completely fresh start | `docker compose down -v` then `docker compose up --build -d` (deletes all data and re-seeds) |
| Code change not visible | Rebuild: `docker compose up --build -d <service>` |

---

## 13. Simplifications and next steps

This is a learning project. These shortcuts are intentional and should change before production:

| Simplification | Production approach |
| --- | --- |
| Redis Pub/Sub loses messages if no subscriber is running | Redis Streams / RabbitMQ / Kafka with acknowledgements |
| Event published after the DB commit (could be lost if Redis is down) | Transactional **outbox** pattern |
| Mock payment endpoint | Real gateway (Razorpay/Stripe) with signed webhooks |
| Emails are only logged | Email provider (SES, SendGrid) in a background worker (Celery) |
| Secrets in `.env`, `DJANGO_DEBUG=1` | Secret manager, DEBUG off, HTTPS at the gateway |
| Tokens stored in localStorage | httpOnly secure cookies |
| Product images are placeholders | Upload to S3/Cloudinary, serve via CDN |

Suggested next learning steps: CI pipeline (GitHub Actions running both pytest suites and
the Postman collection with Newman), structured logging using `X-Request-ID`, and
Redis caching for the product list.
