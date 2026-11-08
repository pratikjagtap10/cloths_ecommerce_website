# 🧥 Threads: Microservices Clothing Store

A full-stack e-commerce demo for a clothing store, built to show the core concepts
of modern web development **and communication between microservices**. One command
runs everything locally with Docker.

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS 4 |
| Core service | Python 3.12, Django 5.2, Django REST Framework, SimpleJWT |
| Shop service | FastAPI, async SQLAlchemy 2, Alembic, Pydantic |
| Data | PostgreSQL 16 (one database per service), Redis 7 (events) |
| Gateway | Nginx (routing, rate limiting, internal API blocking) |
| Shipping | Docker multi-stage builds + Docker Compose (8 containers) |
| Testing | pytest (33 tests), Postman / Newman (61 end-to-end assertions) |

---

## ✨ Features

- Browse products by category, size, colour and price, with search, sorting and pagination
- Product variants (size × colour) with per-variant stock
- Register / login with **JWT** (access + refresh tokens, automatic refresh)
- Cart, checkout with address validation, and a **mock payment** (success / failure)
- Order history and order details
- Django **admin panel**: manage products and stock, ship orders
- **Synchronous** service calls (REST + internal API key, timeouts, retries)
- **Asynchronous** events over Redis (`payment.succeeded`, `order.shipped`)
- **Network-aware images**: detects slow connections and serves lighter images
- Frontend **mock mode**: the UI works without any backend (JSON data)

---

## 🏗️ Architecture

```
                                   Browser
                                      │
                           ┌──────────▼───────────┐
                           │  NGINX API GATEWAY   │  http://localhost
                           └──┬────────┬───────┬──┘
                     /        │        │       │  /api/shop/*
              ┌───────▼──┐ ┌──▼────────▼──┐  ┌─▼─────────────────┐
              │ Next.js  │ │ CORE SERVICE │◄─│ SHOP SERVICE      │
              │ frontend │ │ Django + DRF │ R│ FastAPI           │
              └──────────┘ │ users, auth, │ E│ cart, checkout,   │
                           │ catalog,     │ S│ payments          │
                           │ orders, admin│ T│                   │
                           └──┬───────┬───┘  └───┬──────────┬────┘
                              │       │  REDIS   │          │
                              │       └─events───┘          │
                           core_db   core_worker          shop_db
```

- **Nginx** is the single entry point: `/api/core/*` → Django, `/api/shop/*` → FastAPI, `/` → Next.js.
- **Database per service**: the core service owns users, catalog and orders; the shop service owns carts and payments.
- **Sync**: the shop service asks the core service for price/stock and to create orders.
- **Async**: after payment, the shop publishes `payment.succeeded`; `core_worker` marks the order PAID and reduces stock.
- **Shared identity**: Django signs JWTs; FastAPI verifies them with the same secret.

---

## ✅ Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running)
- [Git](https://git-scm.com/downloads)
- Free ports: **80, 3000, 8000, 8001, 5433, 5434**

Nothing else is needed: Python, Node.js, PostgreSQL and Redis all run inside containers.

---

## 🚀 Run locally with Docker

```bash
# 1. Clone the repository
git clone https://github.com/pratikjagtap10/cloths_ecommerce_website.git
cd cloths_ecommerce_website

# 2. Create your local settings file
cp .env.example .env
#    Windows PowerShell:  Copy-Item .env.example .env

# 3. Build and start all containers
docker compose up --build -d

# 4. Check that everything is up (wait until services show "healthy", ~1 minute)
docker compose ps
```

Then open **http://localhost** 🎉

> ⏳ The **first build** downloads base images and packages and can take 5-15
> minutes depending on your internet speed. Later starts take under a minute.

On first start the backend automatically applies database migrations and loads
demo data (12 categories, 17 products, 136 variants, demo users and orders).

### Expected `docker compose ps`

| Service | Status |
| --- | --- |
| core_db, shop_db, redis | Up (healthy) |
| core_service, shop_service | Up (healthy) |
| frontend | Up (healthy) |
| core_worker, nginx | Up |

---

## 🔗 URLs

| What | URL |
| --- | --- |
| **Storefront** | http://localhost |
| Django admin | http://localhost/admin/ |
| Shop API docs (Swagger) | http://localhost/api/shop/docs |
| Core API (browsable) | http://localhost/api/core/products/ |
| Core service directly | http://localhost:8000 |
| Shop service directly | http://localhost:8001 |

## 👤 Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Customer | `demo@clothstore.com` | `demo1234` |
| Admin (admin panel) | `admin@clothstore.com` | `admin1234` |

### Try the full flow
1. Log in as the customer, add a product to the cart, and check out.
2. Click **Simulate failure**, then **Pay now (success)**.
3. The order becomes **PAID** and the stock goes down (done by the event worker).
4. In the admin, select the order and use **"Mark selected PAID orders as SHIPPED"**.

Watch the services talk to each other while you do it:

```bash
docker compose logs -f core_worker shop_service
```

---

## 🛠️ Useful commands

| Task | Command |
| --- | --- |
| Start (after the first build) | `docker compose up -d` |
| Rebuild after code changes | `docker compose up --build -d` |
| Rebuild one service | `docker compose up --build -d shop_service` |
| Logs of a service | `docker compose logs -f core_service` |
| Stop (keep data) | `docker compose down` |
| Stop and delete all data | `docker compose down -v` |
| Reset demo stock/catalog | `docker compose exec core_service python manage.py seed_demo --force` |
| Django shell | `docker compose exec core_service python manage.py shell` |
| Database console | `docker compose exec core_db psql -U core -d core_db` |
| Watch events live | `docker compose exec redis redis-cli SUBSCRIBE events` |

### Frontend only (mock data, no backend)

```bash
# macOS / Linux / Git Bash
NEXT_PUBLIC_USE_MOCK=true docker compose up --build -d --no-deps frontend
# Windows PowerShell
$env:NEXT_PUBLIC_USE_MOCK="true"; docker compose up --build -d --no-deps frontend
```
Open http://localhost:3000. An amber "Mock mode" banner confirms it.

### Hot-reload frontend development

```bash
docker compose --profile dev up --build frontend-dev     # http://localhost:3001
```

---

## 🧪 Tests

```bash
# Shop service (FastAPI): 11 tests
docker compose run --rm --no-deps -e RUN_MIGRATIONS=0 shop_service pytest

# Core service (Django): 22 tests, needs the database
docker compose up -d core_db redis
docker compose run --rm --no-deps -e RUN_STARTUP_TASKS=0 core_service pytest --create-db

# End-to-end API tests (stack must be running; needs Node.js for npx)
npx newman run postman/Threads-Backend.postman_collection.json \
  -e postman/Threads-Local.postman_environment.json
```

Or import the two files from `postman/` into Postman and use **Run collection**
(see the [Postman testing guide](BACKEND_POSTMAN_TESTING_GUIDE.md)).

---

## 📁 Project structure

```
.
├── frontend/            Next.js storefront (pages, components, contexts, API clients)
├── core_service/        Django: users/JWT, catalog, orders, admin, event worker
├── shop_service/        FastAPI: cart, checkout, payments, events
├── nginx/               API gateway configuration
├── postman/             Postman collection + environment (end-to-end tests)
├── docker-compose.yml   The whole stack (8 containers)
├── .env.example         Local settings template (copy to .env)
└── *.md / *.txt         Documentation (see below)
```

---

## 📚 Documentation

| Document | What it covers |
| --- | --- |
| [BACKEND_DEVELOPER_GUIDE.md](BACKEND_DEVELOPER_GUIDE.md) | Architecture, API reference, service communication, configuration, troubleshooting |
| [BACKEND_POSTMAN_TESTING_GUIDE.md](BACKEND_POSTMAN_TESTING_GUIDE.md) | Testing every API with Postman / Newman |
| [FRONTEND_DEVELOPER_GUIDE.md](FRONTEND_DEVELOPER_GUIDE.md) | Running the frontend, mock data, mock vs real mode |
| [UI_DEVELOPER_GUIDE.md](UI_DEVELOPER_GUIDE.md) | Routing, rendering, UI architecture and data flow |
| [JUNIOR_DEVELOPER_ECOMMERCE_FLOW.md](JUNIOR_DEVELOPER_ECOMMERCE_FLOW.md) | End-to-end walkthrough of every user journey, with exercises |
| [ARCHITECTURE_QA.txt](ARCHITECTURE_QA.txt) | Failure handling, scaling to 1M users, caching, API security |
| [DEMO_PRESENTATION_SCRIPT.txt](DEMO_PRESENTATION_SCRIPT.txt) | Script for presenting the project to a team |
| [ecommerce_cloth_store_plan.txt](ecommerce_cloth_store_plan.txt) | The original development plan |

---

## 🩺 Troubleshooting

| Problem | Fix |
| --- | --- |
| `port is already allocated` (80 or another port) | Stop the program using that port, or change the left side of the port mapping in `docker-compose.yml` |
| `502 Bad Gateway` right after starting | Services are still starting. Wait for `(healthy)` in `docker compose ps` |
| Order stays **PENDING** after paying | Make sure `core_worker` is running: `docker compose ps core_worker` |
| "Only N left in stock" everywhere | Reset demo data: `docker compose exec core_service python manage.py seed_demo --force` |
| Code changes not visible | Rebuild: `docker compose up --build -d <service>` |
| Start completely fresh | `docker compose down -v && docker compose up --build -d` |

More in the [backend guide](BACKEND_DEVELOPER_GUIDE.md#12-troubleshooting).

---

## ⚠️ Note on secrets

All keys and passwords in `.env.example` and `postman/` are **local development
values only**. Never reuse them in a real deployment; generate new, long random
secrets and set `DJANGO_DEBUG=0`.
