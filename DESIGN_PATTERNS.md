# Design Patterns Used in the Threads E-commerce Demo

This document lists the design patterns used in this project and shows where each one lives in the code.
For each pattern you get:

- **What** the pattern means, in one or two lines.
- **Where** it is used (file links).
- **Why** we used it, and what problem it solves in this shop.

The patterns are grouped by layer:

1. [Architecture / microservice patterns](#1-architecture--microservice-patterns)
2. [Reliability and data consistency patterns](#2-reliability-and-data-consistency-patterns)
3. [Django core service patterns](#3-django-core-service-patterns)
4. [FastAPI shop service patterns](#4-fastapi-shop-service-patterns)
5. [Next.js / React frontend patterns](#5-nextjs--react-frontend-patterns)
6. [Docker / DevOps patterns](#6-docker--devops-patterns)
7. [Testing patterns](#7-testing-patterns)
8. [Patterns we did not use yet (and where they would fit)](#8-patterns-we-did-not-use-yet-and-where-they-would-fit)
9. [Quick reference table](#9-quick-reference-table)

---

## The system in one picture

```
Browser
   │
   ▼
Nginx API Gateway (:80) ─────────────┬──────────────────────────┐
   │ /                               │ /api/core/*              │ /api/shop/*
   ▼                                 ▼                          ▼
Next.js frontend (:3000)     Django core_service (:8000)   FastAPI shop_service (:8001)
                              users, catalog, orders        cart, checkout, payments
                                  │        ▲  REST (sync)        │
                                  │        └─ /internal/* ───────┤
                                  ▼                              ▼
                              core_db (Postgres)             shop_db (Postgres)
                                  ▲                              │
                         core_worker (event consumer)            │
                                  ▲      Redis Pub/Sub "events"  │
                                  └──── payment.succeeded ◄──────┘
                                        order.shipped ──────────►
```

---

## 1. Architecture / microservice patterns

### 1.1 Microservices: split by business capability
- **What:** The application is split into small services. Each service owns one business area and can be deployed on its own.
- **Where:**
  - [core_service/](core_service/): users, catalog and orders (Django)
  - [shop_service/](shop_service/): cart, checkout and payments (FastAPI)
  - [frontend/](frontend/): the UI (Next.js)
- **Why:** Each part can be built, scaled and released on its own. The cart and payment traffic (FastAPI, async) can scale separately from the catalog.

### 1.2 Database per service
- **What:** Every service has its **own** database. No other service reads it directly.
- **Where:** `core_db` and `shop_db` in [docker-compose.yml](docker-compose.yml). Django uses its ORM migrations; FastAPI uses Alembic ([shop_service/alembic/versions/](shop_service/alembic/versions/)).
- **Why:** Services stay loosely coupled. A schema change in one service cannot break the other. To get data from another service, you call its API.

### 1.3 API Gateway
- **What:** One entry point in front of all services. It routes each request to the right service and applies shared rules.
- **Where:** [nginx/default.conf](nginx/default.conf)
  - `/api/core/*` goes to Django, `/api/shop/*` goes to FastAPI, `/` goes to Next.js
  - `/internal/*` is **blocked** from the outside (`return 404`)
  - Rate limiting on login (`limit_req_zone`, 30 requests/minute per IP)
  - Adds an `X-Request-ID` to every request
- **Why:** The browser sees a single origin, so there are no CORS problems. Internal ports stay hidden. Security rules live in one place.

### 1.4 Synchronous communication: request/response over REST
- **What:** One service calls another over HTTP and waits for the answer.
- **Where:** [shop_service/app/services/core_client.py](shop_service/app/services/core_client.py) calls Django's internal API:
  - `GET /internal/variants/{id}/`: current price and stock when adding to the cart
  - `POST /internal/orders/`: create the order at checkout
- **Why:** These calls need an answer right now (Is it in stock? What is the price?).

### 1.5 Asynchronous communication: event-driven Publish/Subscribe
- **What:** A service publishes an event and does not wait. Other services subscribe and react.
- **Where:**
  - Publisher (FastAPI): `publish("payment.succeeded", ...)` in [shop_service/app/routers/payments.py](shop_service/app/routers/payments.py)
  - Bus: [core_service/events/bus.py](core_service/events/bus.py) and [shop_service/app/services/events.py](shop_service/app/services/events.py) (Redis Pub/Sub, channel `events`)
  - Subscriber (Django worker): [core_service/events/management/commands/run_event_consumer.py](core_service/events/management/commands/run_event_consumer.py) marks the order PAID
  - Reverse direction: the Django admin action publishes `order.shipped`, and FastAPI's listener sends a (mock) email
- **Why:** The payment response is fast because it does not wait for Django. If Django is slow, payment still works.

### 1.6 Saga (choreography style)
- **What:** One business process spans several services. Each step is a local transaction, and the steps are linked by events instead of one central coordinator.
- **Where:** The checkout flow:
  1. FastAPI asks Django to create the order (PENDING).
  2. FastAPI creates the payment (PENDING).
  3. Payment succeeds, so FastAPI publishes `payment.succeeded`.
  4. The Django worker marks the order PAID and reduces stock.
- **Why:** There is no distributed transaction across two databases. Each service stays consistent locally, and the whole system becomes consistent a moment later (**eventual consistency**).
- **Note:** A failed payment leaves the order PENDING (the user can retry). A **compensating action** (cancel the order after N minutes) is not implemented yet. See section 8.

### 1.7 Stateless authentication with a shared JWT
- **What:** One service issues a signed token. Other services only **verify** the signature and never call the issuer.
- **Where:**
  - Issuer: `LoginSerializer.get_token` in [core_service/users/serializers.py](core_service/users/serializers.py) (adds `email` and `first_name` claims)
  - Verifier: `get_current_user` in [shop_service/app/security.py](shop_service/app/security.py)
- **Why:** FastAPI knows who the user is without an extra network call to Django on every request.

### 1.8 Service-to-service authentication (shared API key)
- **What:** Internal endpoints accept only callers that send a secret header.
- **Where:** `HasInternalApiKey` in [core_service/core/permissions.py](core_service/core/permissions.py) checks `X-Internal-Key` with `hmac.compare_digest` (a constant-time compare that prevents timing attacks).
- **Why:** Browsers can never call `/internal/*`. There are two layers of defence: the gateway blocks the path, and the API key is checked.

### 1.9 Single source of truth
- **What:** Each piece of data has exactly one owner. Everyone else asks the owner.
- **Where:** Django owns price and stock. `create_order` in [core_service/orders/services.py](core_service/orders/services.py) **re-reads prices from its own database** and never trusts prices sent by the shop service.
- **Why:** A tampered or stale cart can never create an order at the wrong price.

### 1.10 Data snapshot (denormalisation)
- **What:** Copy the important fields at the moment of an event, instead of only keeping a reference.
- **Where:** `OrderItem` stores `product_name`, `size`, `color` and `unit_price`. `CartItem` in [shop_service/app/models.py](shop_service/app/models.py) stores the product name and price as well.
- **Why:** If a product is renamed or its price changes later, old orders still show what the customer actually bought. The cart can also be displayed without calling Django.

### 1.11 Health Check API
- **What:** Each service exposes an endpoint that reports whether it is healthy.
- **Where:** `health` in [core_service/core/views.py](core_service/core/views.py) (checks the DB, returns 503 if it is down) and [shop_service/app/routers/health.py](shop_service/app/routers/health.py). Docker `healthcheck` entries use them.
- **Why:** Docker starts services in the right order and can detect broken containers.

### 1.12 Correlation ID
- **What:** One ID follows a request through every service, so its logs can be linked together.
- **Where:** `proxy_set_header X-Request-ID $request_id` in [nginx/default.conf](nginx/default.conf)
- **Why:** You can trace one user action across the gateway and the services.

### 1.13 Externalised configuration (12-factor)
- **What:** All settings come from environment variables, not from code.
- **Where:** [.env.example](.env.example), [core_service/core/settings.py](core_service/core/settings.py), `Settings` (pydantic-settings) in [shop_service/app/config.py](shop_service/app/config.py), [frontend/src/lib/config.ts](frontend/src/lib/config.ts)
- **Why:** The same Docker image runs in dev, test and production with different settings.

---

## 2. Reliability and data consistency patterns

### 2.1 Idempotency Key (Stripe-style)
- **What:** The client sends a unique key with a request. If the same request arrives again with the same key, the server returns the **first result** instead of doing the work twice.
- **Where (end to end):**
  - Frontend creates and reuses the key: [frontend/src/lib/idempotency.ts](frontend/src/lib/idempotency.ts), [frontend/src/app/checkout/page.tsx](frontend/src/app/checkout/page.tsx)
  - Shop service stores the key and the result: `IdempotencyRecord` in [shop_service/app/models.py](shop_service/app/models.py), with `claim` and `release` in [shop_service/app/services/idempotency.py](shop_service/app/services/idempotency.py)
  - Core service has its own key on `Order.idempotency_key`: `create_order_idempotent` in [core_service/orders/services.py](core_service/orders/services.py)
- **Rules:**
  - Same key, same body → replay the stored response (header `Idempotent-Replayed: true`)
  - Same key, different body → 422
  - Same key while the first request is still running → 409 with `Retry-After: 2`
- **Why:** A slow network, a double click, a page refresh or a second tab never creates two orders.

### 2.2 Idempotent Consumer
- **What:** An event handler that can safely run more than once for the same event.
- **Where:** `mark_order_paid` in [core_service/orders/services.py](core_service/orders/services.py) does nothing if the order is no longer PENDING. `confirm_payment` in [shop_service/app/routers/payments.py](shop_service/app/routers/payments.py) returns the existing payment if it is already SUCCESS.
- **Why:** Messages and retries can be duplicated. Stock is reduced only once.

### 2.3 Pessimistic locking (SELECT ... FOR UPDATE)
- **What:** Lock a database row while you work on it, so a parallel request waits.
- **Where:**
  - `select_for_update()` on product variants in `create_order`, so two buyers can't both take the last item
  - `select_for_update()` on the order in `mark_order_paid`
  - `with_for_update()` on the payment in `_get_own_payment(..., lock=True)`, so a double "Pay" click charges only once
- **Why:** Prevents race conditions under concurrent requests.

### 2.4 Unique constraint as a concurrency guard
- **What:** Let the database reject duplicates, then catch the error and return the existing row.
- **Where:** `Order.idempotency_key` (unique) with `IntegrityError` handling in `create_order_idempotent`; `UniqueConstraint("user_id", "key")` on `IdempotencyRecord`; `uq_cart_variant` on `CartItem`.
- **Why:** Application checks alone have race windows. The database is the final referee.

### 2.5 Retry with exponential backoff
- **What:** When a call fails for a temporary reason, try again after waiting 0.2s, then 0.4s, and so on.
- **Where:** `CoreClient._request` in [shop_service/app/services/core_client.py](shop_service/app/services/core_client.py). Timeouts on `create_order` are retried **only when an idempotency key is present**, because only then is a retry safe.
- **Why:** It handles short network glitches and container restarts.

### 2.6 Timeout and fail fast
- **What:** Never wait forever for another service. Return a clear error instead.
- **Where:** `core_timeout_seconds = 3.0` in [shop_service/app/config.py](shop_service/app/config.py). When Django is down, `CoreServiceError(503, "Catalog service is unavailable...")` is returned.
- **Why:** A slow service must not hang the whole system. The user gets a friendly 503 message, not a 500.

### 2.7 Client-side retry that respects `Retry-After`
- **What:** The client waits the number of seconds the server asks for, then retries with the **same** idempotency key.
- **Where:** The retry loop (up to 5 attempts) in [frontend/src/app/checkout/page.tsx](frontend/src/app/checkout/page.tsx). `ApiError.retryAfter` is parsed in [frontend/src/lib/httpApi.ts](frontend/src/lib/httpApi.ts).

### 2.8 Self-healing listener (reconnect loop)
- **What:** A background worker reconnects by itself if its connection drops.
- **Where:** The `while True` loop with `time.sleep(3)` in `run_event_consumer.py` and `listen_for_events()` in [shop_service/app/services/events.py](shop_service/app/services/events.py). One bad message is logged and skipped; it does not stop the worker.

### 2.9 State machine (order status)
- **What:** An object moves only through allowed states.
- **Where:** `Order.Status` (`TextChoices`: PENDING → PAID → SHIPPED / CANCELLED) in [core_service/orders/models.py](core_service/orders/models.py). Transitions happen only in services or admin actions, never by editing the field: `status` is in `readonly_fields` in [core_service/orders/admin.py](core_service/orders/admin.py). The same idea applies to Payment (PENDING / SUCCESS / FAILED) and `IdempotencyRecord` (IN_PROGRESS / COMPLETED).

---

## 3. Django core service patterns

### 3.1 Layered architecture with a Service Layer
- **What:** Views handle HTTP only. Business rules live in a separate "services" module.
- **Where:** [core_service/orders/services.py](core_service/orders/services.py) (`create_order`, `create_order_idempotent`, `mark_order_paid`). The same function is reused by the API view, the event worker, the admin and the tests.
- **Why:** No duplicated logic, and the rules are easy to test without HTTP.

### 3.2 MVT (Model-View-Template) / Active Record
- **What:** Django's version of MVC. A model class is a table, and each object knows how to save itself (`order.save()`): this is **Active Record**.
- **Where:** `models.py` in [catalog](core_service/catalog/models.py), [orders](core_service/orders/models.py) and [users](core_service/users/models.py). Here the "template" is JSON produced by serializers.

### 3.3 Repository via the ORM Manager / QuerySet
- **What:** One object hides how data is queried.
- **Where:** `Product.objects.filter(is_active=True).select_related(...).prefetch_related(...)` in `ProductViewSet.get_queryset` ([core_service/catalog/views.py](core_service/catalog/views.py)). The custom `UserManager` lives in [core_service/users/models.py](core_service/users/models.py).
- **Bonus:** `select_related` and `prefetch_related` avoid the **N+1 query** problem.

### 3.4 Factory Method
- **What:** A method creates objects with the correct defaults, so callers don't need to know the details.
- **Where:** `UserManager.create_user()` and `create_superuser()` normalise the email, hash the password and set flags.

### 3.5 DTO + Validator (serializers)
- **What:** A Data Transfer Object controls what goes in and out of the API, and validates input.
- **Where:** [core_service/users/serializers.py](core_service/users/serializers.py) (`RegisterSerializer` validates the email and password strength) and [core_service/orders/serializers.py](core_service/orders/serializers.py) (`InternalOrderCreateSerializer` with `RegexField` for the idempotency key).
- **Why:** The database model is never exposed directly (for example, the password is `write_only`).

### 3.6 Template Method (generic class-based views)
- **What:** A base class defines the algorithm, and subclasses override only some steps.
- **Where:**
  - `ListAPIView`, `RetrieveAPIView`, `ReadOnlyModelViewSet`: we override `get_queryset()`, `get_object()` and `filter_queryset()`
  - `AliasOrderingFilter.get_ordering()` in [core_service/catalog/filters.py](core_service/catalog/filters.py) overrides one step of DRF's `OrderingFilter`

### 3.7 Strategy (pluggable policies)
- **What:** Choose behaviour by plugging in a class instead of writing `if/else`.
- **Where:** On every view:
  - `permission_classes = [AllowAny]` / `[IsAuthenticated]` / `[HasInternalApiKey]`
  - `authentication_classes`
  - `filter_backends = [DjangoFilterBackend, SearchFilter, AliasOrderingFilter]`
  - `pagination_class`

### 3.8 Chain of Responsibility
- **What:** A request passes through a chain of handlers, and each one can stop it or pass it on.
- **Where:** The Django middleware stack in [core_service/core/settings.py](core_service/core/settings.py) (security, CORS, WhiteNoise, auth, ...). DRF runs the permission classes and filter backends one after another.

### 3.9 Decorator
- **What:** Adds behaviour to a function without changing its code.
- **Where:** `@transaction.atomic` (all-or-nothing DB work), `@api_view`, `@permission_classes`, `@admin.register`, `@admin.action`, `@property` (`ProductVariant.price`).

### 3.10 Unit of Work (database transaction)
- **What:** Group several writes so they succeed or fail together.
- **Where:** `@transaction.atomic` on `create_order`: the order and all of its items are created together, or nothing is.

### 3.11 Command pattern (management commands)
- **What:** Wrap an action in an object that can be run by name.
- **Where:** `python manage.py seed_demo` ([core_service/catalog/management/commands/seed_demo.py](core_service/catalog/management/commands/seed_demo.py)) and `python manage.py run_event_consumer`.

### 3.12 Registry / Dispatcher (event handler map)
- **What:** A dictionary maps a message type to the function that handles it.
- **Where:** `HANDLERS = {"payment.succeeded": handle_payment_succeeded}` and `dispatch()` in [core_service/events/handlers.py](core_service/events/handlers.py).
- **Why:** To add a new event, add one line. Unknown events are ignored safely.

### 3.13 Centralised exception handling (Adapter for errors)
- **What:** One function converts every error into the same JSON shape: `{"detail": "...", "errors": {...}}`.
- **Where:** `api_exception_handler` in [core_service/core/exceptions.py](core_service/core/exceptions.py). Custom domain errors (`OutOfStock`, `IdempotencyKeyConflict`) are `APIException` subclasses with their own HTTP status.
- **Why:** The frontend always reads `detail`, whichever service failed.

### 3.14 Object-level security through query scoping
- **What:** Only query the current user's data, so other users' data is "not found".
- **Where:** `Order.objects.filter(user=self.request.user)` in `OrderViewSet` ([core_service/orders/views.py](core_service/orders/views.py)). Someone else's order returns **404, not 403**, so its existence isn't revealed.

### 3.15 Observer through admin actions
- **What:** A state change notifies other parts of the system.
- **Where:** `mark_shipped` in [core_service/orders/admin.py](core_service/orders/admin.py) changes the status **and** publishes `order.shipped`.

---

## 4. FastAPI shop service patterns

### 4.1 Dependency Injection
- **What:** A function declares what it needs, and the framework provides it.
- **Where:** `Depends(get_db)`, `Depends(get_current_user)` and `Depends(get_core_client)` in [shop_service/app/routers/](shop_service/app/routers/).
- **Why:** The code stays loosely coupled, and tests can swap in fakes with `app.dependency_overrides` (see section 7).

### 4.2 Gateway / Proxy client for a remote service
- **What:** One class wraps all calls to another service, with timeouts, retries, error mapping and the auth header.
- **Where:** `CoreClient` in [shop_service/app/services/core_client.py](shop_service/app/services/core_client.py).
- **Why:** The routers call `core.get_variant(id)` like a local function and never deal with raw HTTP details.

### 4.3 Unit of Work (async SQLAlchemy session)
- **What:** One session per request collects all changes and commits them once.
- **Where:** `get_db()` in [shop_service/app/database.py](shop_service/app/database.py). In `_place_order` ([shop_service/app/routers/checkout.py](shop_service/app/routers/checkout.py)), the payment and the COMPLETED idempotency record are saved **in the same commit**.

### 4.4 DTOs with Pydantic schemas
- **What:** Typed input and output models with validation.
- **Where:** [shop_service/app/schemas.py](shop_service/app/schemas.py) (`CheckoutIn`, `CartOut`, `PaymentOut`, ...). FastAPI uses them to validate requests and to generate the Swagger docs at `/api/shop/docs`.

### 4.5 Singleton (module-level shared instances)
- **What:** One shared instance for the whole process.
- **Where:** `settings = Settings()` in [shop_service/app/config.py](shop_service/app/config.py), `_client = CoreClient()` in `core_client.py`, the DB `engine`, and the lazily created `_redis` in [shop_service/app/services/events.py](shop_service/app/services/events.py) (lazy initialisation).
- **Why:** Connection pools are reused instead of being created on every request.

### 4.6 Lifespan / resource management
- **What:** Start resources when the app starts and clean them up when it stops.
- **Where:** `lifespan()` in [shop_service/app/main.py](shop_service/app/main.py) starts the Redis listener task, then cancels it and closes Redis and the DB engine on shutdown.

### 4.7 Fire-and-forget background tasks
- **What:** Do slow, non-critical work after the response has been sent.
- **Where:** `background.add_task(send_order_confirmation, ...)` in `confirm_payment` ([shop_service/app/routers/payments.py](shop_service/app/routers/payments.py)).

### 4.8 Ports and Adapters seam (replaceable notifier)
- **What:** Callers depend on a simple function, so the real implementation can be swapped later.
- **Where:** [shop_service/app/services/notifications.py](shop_service/app/services/notifications.py) only writes to the log today. A real email or SMS provider can replace it without changing the routers.

### 4.9 Router modules (modular monolith inside a service)
- **What:** Split endpoints by feature into separate routers.
- **Where:** `cart.py`, `checkout.py`, `payments.py` and `health.py`, registered with `app.include_router(...)`.

### 4.10 Centralised exception handlers
- **Where:** `register_exception_handlers` in [shop_service/app/errors.py](shop_service/app/errors.py). `CoreServiceError` and validation errors are converted to the same `{"detail": ...}` shape that Django uses.

---

## 5. Next.js / React frontend patterns

### 5.1 Component-based architecture and composition
- **What:** The UI is built from small reusable components.
- **Where:** [frontend/src/components/](frontend/src/components/) (`ProductCard`, `ProductImage`, `Pagination`, `OrderStatusBadge`, ...) are composed into pages in [frontend/src/app/](frontend/src/app/).

### 5.2 File-based routing (App Router)
- **What:** The folder structure defines the URLs.
- **Where:** `app/products/[slug]/page.tsx` serves `/products/:slug`, and `app/orders/[id]/page.tsx` serves `/orders/:id`. Special files: `layout.tsx`, `loading.tsx`, `error.tsx` and `not-found.tsx`.

### 5.3 Server Components + Client "islands"
- **What:** Most of the page is rendered on the server. Only the interactive parts run in the browser.
- **Where:** [frontend/src/app/products/[slug]/page.tsx](frontend/src/app/products/[slug]/page.tsx) is a server component, and `<AddToCart>` (`"use client"`) is the interactive island.
- **Why:** Less JavaScript in the browser, faster first load and better SEO.

### 5.4 Strategy + Adapter: a swappable API client (Dependency Inversion)
- **What:** Components depend on an **interface**, not on a concrete implementation.
- **Where:**
  - Interface: `ApiClient` in [frontend/src/types/index.ts](frontend/src/types/index.ts)
  - Implementations: `mockApi` ([frontend/src/lib/mockApi.ts](frontend/src/lib/mockApi.ts)), which reads JSON and localStorage, and `httpApi` ([frontend/src/lib/httpApi.ts](frontend/src/lib/httpApi.ts)), which calls the real services
  - Selector: `api = USE_MOCK ? mockApi : httpApi` in [frontend/src/lib/api.ts](frontend/src/lib/api.ts)
- **Why:** The whole UI ran on mock data before the backend existed. Switching to the real backend needed **zero UI changes**.

### 5.5 Facade (single data-access entry point)
- **What:** One simple object hides a more complex subsystem.
- **Where:** Every component imports only `api` from `@/lib/api`. Tokens, base URLs, refresh logic and error parsing are hidden behind it.

### 5.6 Interceptor (automatic token refresh)
- **What:** Code that runs around every request.
- **Where:** `request()` in [frontend/src/lib/httpApi.ts](frontend/src/lib/httpApi.ts) adds the `Authorization` header. On a **401** it refreshes the access token **once** and repeats the request. It also converts error bodies into `ApiError`.

### 5.7 Provider pattern (React Context) for global state
- **What:** Share state across the component tree without passing props through every level.
- **Where:** [frontend/src/context/](frontend/src/context/): `AuthContext` (user, login, logout), `CartContext` (cart, count, add, update, remove) and `NetworkContext` (connection quality), composed in `Providers.tsx`.

### 5.8 Custom hooks
- **What:** Reusable stateful logic behind a simple function.
- **Where:** `useAuth()`, `useCart()` and `useNetwork()`. Each throws a clear error if it is used outside its provider (a fail-fast guard).

### 5.9 Route guard (middleware)
- **What:** Check access before a page renders.
- **Where:** [frontend/src/middleware.ts](frontend/src/middleware.ts) protects `/checkout` and `/orders/*`. Without an `access_token` cookie, it redirects to `/login?next=...`.

### 5.10 URL as the source of truth for state
- **What:** Filters, sorting and pagination are stored in the query string, not in component state.
- **Where:** [frontend/src/components/ProductFilters.tsx](frontend/src/components/ProductFilters.tsx) builds the URL, and [frontend/src/app/products/page.tsx](frontend/src/app/products/page.tsx) reads `searchParams` on the server.
- **Why:** Links can be shared and bookmarked, the back button works, and pages are SEO-friendly.

### 5.11 Schema-based form validation
- **What:** One schema defines the rules, and the form library applies them.
- **Where:** Zod `addressSchema` + React Hook Form `zodResolver` in [frontend/src/app/checkout/page.tsx](frontend/src/app/checkout/page.tsx), plus the login and register pages.

### 5.12 Error Boundary and fallback UIs
- **Where:** [frontend/src/app/error.tsx](frontend/src/app/error.tsx) (error with a "Try again" button), `loading.tsx` (loading state) and `not-found.tsx` (404, triggered by `notFound()`).

### 5.13 Adaptive loading / progressive enhancement (network-aware images)
- **What:** The page adapts to the user's connection speed.
- **Where:**
  - Detection uses the **Network Information API** first, then a 100 KB speed test as a fallback: [frontend/src/lib/network.ts](frontend/src/lib/network.ts)
  - `IMAGE_PROFILES`: low / medium / high quality levels
  - [frontend/src/components/ProductImage.tsx](frontend/src/components/ProductImage.tsx): shows an SVG placeholder first, a "Load photo" button on slow networks, and WebP images through `next/image`
- **Patterns inside:**
  - **Placeholder / lazy loading**
  - A **pure function** (`classify`) for easy testing
  - **Observer** (`connection.addEventListener("change", ...)` re-detects the speed)
  - **User override wins** (Auto / Data saver / HD)

### 5.14 Client-generated idempotency key (fingerprint-based)
- **What:** Same cart + same address = same checkout = same key.
- **Where:** `getCheckoutKey(userId, fingerprint)` in [frontend/src/lib/idempotency.ts](frontend/src/lib/idempotency.ts). The key is stored in `localStorage` so that **all tabs** share it, and it is cleared after a successful payment.

### 5.15 Mock backend (fake service)
- **What:** A fake implementation that behaves like the real API, including latency, errors and idempotency.
- **Where:** [frontend/src/lib/mockApi.ts](frontend/src/lib/mockApi.ts) and [frontend/src/mocks/](frontend/src/mocks/).
- **Why:** Frontend work, demos and UI testing don't depend on the backend.

### 5.16 Memoisation of callbacks
- **Where:** `useCallback` for `login`, `add`, `refresh` and others in the contexts. Functions keep the same identity, so consumers don't re-render or re-run effects without a reason.

---

## 6. Docker / DevOps patterns

| Pattern | Where | Why |
|---|---|---|
| **Multi-stage Docker build** | [frontend/Dockerfile](frontend/Dockerfile) (`deps` → `builder` → `runner`, plus a `dev` stage) | Small production image without build tools |
| **One container per service** | [docker-compose.yml](docker-compose.yml) (8 services) | Isolation, independent scaling and restarts |
| **Init / entrypoint pattern** | [core_service/entrypoint.sh](core_service/entrypoint.sh) (migrate + seed), [shop_service/entrypoint.sh](shop_service/entrypoint.sh) (`alembic upgrade head`), then `exec "$@"` | The DB is always ready before the app starts |
| **Health-check based startup order** | `depends_on: condition: service_healthy` | A service starts only when its DB, Redis or upstream service is really ready |
| **Same image, different role** | `core_service` (gunicorn) and `core_worker` (event consumer) use one image with different commands | No duplicated build |
| **Compose profiles** | `frontend-dev` with `profiles: ["dev"]` | Hot-reload dev mode only when you ask for it |
| **Network alias** | `aliases: [core-service]` | Django rejects hostnames with `_`, so a hyphen alias is used |
| **Dynamic service discovery** | `resolver 127.0.0.11` + variables in `proxy_pass` (nginx) | No 502 errors after a container gets a new IP |
| **Line-ending normalisation** | [.gitattributes](.gitattributes) | Shell scripts keep LF line endings, so they work in Linux containers built on Windows |

---

## 7. Testing patterns

- **Fake object + dependency override:** `FakeCore` in [shop_service/tests/conftest.py](shop_service/tests/conftest.py) replaces the real Django client through `app.dependency_overrides[get_core_client]`. It even simulates idempotency (`by_key`) and an outage (`down` flag) to test the 503 path.
- **Test fixtures (pytest):** [core_service/tests/conftest.py](core_service/tests/conftest.py) and [shop_service/tests/conftest.py](shop_service/tests/conftest.py) build users, tokens, clients and a clean database for each test.
- **Arrange-Act-Assert:** Each test in [core_service/tests/](core_service/tests/) and [shop_service/tests/test_shop.py](shop_service/tests/test_shop.py) sets up data, calls the API once and checks the result.
- **Contract / API testing:** The Postman collection [postman/Threads-Backend.postman_collection.json](postman/Threads-Backend.postman_collection.json) runs the full flow through the gateway, with assertions.

---

## 8. Patterns we did not use yet (and where they would fit)

These are good "next step" answers in an interview.

| Pattern | Problem today | Where it would go |
|---|---|---|
| **Transactional Outbox** | If Redis is down at the moment of payment, `payment.succeeded` is lost (Pub/Sub is fire-and-forget). | Save the event in an `outbox` table in the same commit as the payment, and let a relay publish it later. |
| **Durable message queue** | Pub/Sub drops messages when no subscriber is listening. | Redis Streams / RabbitMQ / Kafka with consumer groups and acknowledgements. |
| **Circuit Breaker** | The shop service retries Django even when Django is clearly down. | Wrap `CoreClient._request` so it stops calling for N seconds after repeated failures. |
| **Saga compensation** | A PENDING order with a failed or abandoned payment stays PENDING forever. | A scheduled job (or a `payment.failed` event) that cancels old PENDING orders. |
| **Cache-aside** | Every catalog request hits Postgres. | Cache product lists and details in Redis, and invalidate on admin changes. |
| **CQRS / read replicas** | Reads and writes share one database. | A separate read model or read replica for the catalog at large scale. |
| **API versioning** | URLs have no version. | `/api/v1/...` so mobile apps don't break on changes. |
| **Request cancellation (AbortController)** | Some `useEffect` fetches are not cancelled on unmount. | Pass `signal` into `api` calls and abort it in the cleanup function. |
| **Optimistic UI** | The cart badge waits for the server response. | Update the state first, then roll back on error. |
| **Explicit Repository layer** | Routers in the shop service query SQLAlchemy directly. | A `CartRepository` class to separate data access from HTTP code. |

---

## 9. Quick reference table

| # | Pattern | Category | Main file(s) |
|---|---|---|---|
| 1 | Microservices | Architecture | `core_service/`, `shop_service/`, `frontend/` |
| 2 | Database per service | Architecture | `docker-compose.yml` |
| 3 | API Gateway | Architecture | `nginx/default.conf` |
| 4 | Sync REST communication | Architecture | `shop_service/app/services/core_client.py` |
| 5 | Publish/Subscribe events | Architecture | `core_service/events/`, `shop_service/app/services/events.py` |
| 6 | Saga (choreography) | Architecture | checkout → payment → `payment.succeeded` → PAID |
| 7 | Stateless JWT auth | Security | `users/serializers.py`, `shop_service/app/security.py` |
| 8 | Service API key | Security | `core_service/core/permissions.py` |
| 9 | Single source of truth | Data | `orders/services.py` (`create_order`) |
| 10 | Data snapshot | Data | `OrderItem`, `CartItem` models |
| 11 | Health Check API | Ops | `core/views.py`, `routers/health.py` |
| 12 | Correlation ID | Ops | `nginx/default.conf` |
| 13 | Externalised config | Ops | `.env.example`, `config.py`, `settings.py` |
| 14 | Idempotency Key | Reliability | `idempotency.ts`, `services/idempotency.py`, `orders/services.py` |
| 15 | Idempotent Consumer | Reliability | `mark_order_paid`, `confirm_payment` |
| 16 | Pessimistic locking | Reliability | `select_for_update`, `with_for_update` |
| 17 | Unique constraint guard | Reliability | `Order.idempotency_key`, `uq_idempotency_user_key` |
| 18 | Retry with backoff | Reliability | `CoreClient._request` |
| 19 | Timeout + fail fast (503) | Reliability | `CoreClient`, `config.py` |
| 20 | Self-healing listener | Reliability | `run_event_consumer.py`, `listen_for_events` |
| 21 | State machine | Domain | `Order.Status`, `Payment.status` |
| 22 | Service layer | Django | `orders/services.py` |
| 23 | MVT / Active Record | Django | `models.py` |
| 24 | Repository (ORM manager) | Django | `get_queryset`, `UserManager` |
| 25 | Factory method | Django | `UserManager.create_user` |
| 26 | DTO + validator | Django / FastAPI | `serializers.py`, `schemas.py` |
| 27 | Template Method | Django | generic views, `AliasOrderingFilter` |
| 28 | Strategy | Django / Frontend | `permission_classes`, `filter_backends`, `ApiClient` |
| 29 | Chain of Responsibility | Django | middleware, permissions |
| 30 | Decorator | Django | `@transaction.atomic`, `@admin.action` |
| 31 | Unit of Work | Django / FastAPI | `transaction.atomic`, `AsyncSession` |
| 32 | Command | Django | `seed_demo`, `run_event_consumer` |
| 33 | Registry / Dispatcher | Django | `events/handlers.py` |
| 34 | Central error handling | Both backends | `core/exceptions.py`, `app/errors.py` |
| 35 | Query-scoped object security | Django | `OrderViewSet.get_queryset` |
| 36 | Dependency Injection | FastAPI | `Depends(...)` |
| 37 | Remote proxy client | FastAPI | `CoreClient` |
| 38 | Singleton / lazy init | FastAPI | `settings`, `_client`, `_redis` |
| 39 | Lifespan resource mgmt | FastAPI | `main.py` |
| 40 | Background tasks | FastAPI | `confirm_payment` |
| 41 | Ports and Adapters seam | FastAPI | `notifications.py` |
| 42 | Components + composition | Frontend | `components/` |
| 43 | File-based routing | Frontend | `app/` |
| 44 | Server Components + islands | Frontend | `products/[slug]/page.tsx` + `AddToCart` |
| 45 | Facade | Frontend | `lib/api.ts` |
| 46 | Interceptor (token refresh) | Frontend | `lib/httpApi.ts` |
| 47 | Provider (Context) | Frontend | `context/` |
| 48 | Custom hooks | Frontend | `useAuth`, `useCart`, `useNetwork` |
| 49 | Route guard | Frontend | `middleware.ts` |
| 50 | URL as state | Frontend | `ProductFilters.tsx`, `products/page.tsx` |
| 51 | Schema validation | Frontend | Zod + React Hook Form |
| 52 | Error boundary | Frontend | `error.tsx`, `not-found.tsx`, `loading.tsx` |
| 53 | Adaptive loading | Frontend | `lib/network.ts`, `ProductImage.tsx` |
| 54 | Mock backend | Frontend | `lib/mockApi.ts`, `mocks/` |
| 55 | Multi-stage build | DevOps | `frontend/Dockerfile` |
| 56 | Init / entrypoint | DevOps | `entrypoint.sh` |
| 57 | Health-based startup order | DevOps | `docker-compose.yml` |
| 58 | Fake object + DI override | Testing | `shop_service/tests/conftest.py` |
