# Interview Questions & Answers: Threads Microservices Clothing Store

Interview preparation based on **this project**. Every answer is grounded in
code that exists in the repository, with file references, so you can explain it
with confidence and open the code if asked.

**How to use this list**
- Read the answer, then explain it **out loud in your own words** using an example from the project.
- Tags: 🟢 basic · 🟡 intermediate · 🔴 advanced
- Section 1 ("Tell me about your project") is asked in almost every interview. Practise it until it's smooth.

---

## Contents

1. [Project overview](#1-project-overview)
2. [React & Next.js](#2-react--nextjs)
3. [Frontend architecture & TypeScript](#3-frontend-architecture--typescript)
4. [Django & Django REST Framework](#4-django--django-rest-framework)
5. [FastAPI & async Python](#5-fastapi--async-python)
6. [Databases & data modelling](#6-databases--data-modelling)
7. [Authentication & security](#7-authentication--security)
8. [Microservices communication & resilience](#8-microservices-communication--resilience)
9. [Docker, Docker Compose & Nginx](#9-docker-docker-compose--nginx)
10. [Testing](#10-testing)
11. [Performance, caching & scaling](#11-performance-caching--scaling)
12. [Scenario & debugging questions](#12-scenario--debugging-questions)
13. [Behavioural questions (STAR answers from this project)](#13-behavioural-questions-star-answers-from-this-project)
14. [Quick-fire round](#14-quick-fire-round)

---

## 1. Project overview

### Q1. 🟢 Tell me about your project.
**A.** "I built Threads, a clothing e-commerce store with a microservice architecture that runs locally with one `docker compose up`.
- The **frontend** is Next.js 15 with React 19 and TypeScript.
- The backend is two services. A **Django** core service owns users and JWT login, the product catalog with size/colour variants and stock, orders, and the admin panel. A **FastAPI** shop service owns the cart, checkout and payments.
- Each service has its **own PostgreSQL database**.
- They communicate in two ways: **synchronous REST**, where the shop asks Django for price and stock and to create orders, and **asynchronous events** over Redis, where a successful payment publishes `payment.succeeded` and a Django worker marks the order paid and reduces stock.
- An **Nginx gateway** gives the browser a single entry point.
- I covered it with 33 pytest tests and a Postman collection with 61 end-to-end assertions."

### Q2. 🟢 Why did you choose a microservice architecture?
**A.** Mainly to learn and demonstrate the concepts: service boundaries, database per service, sync vs async communication, failure handling and independent deployment. In a real startup I would usually **start with a modular monolith** and split only when teams or scaling needs require it, because microservices add network failures, distributed data and operational overhead. I kept the split small (two services plus a worker) for that reason.

### Q3. 🟡 How did you decide the service boundaries?
**A.** By **data ownership and business capability**. The core service owns data that is permanent and needs strong consistency: users, catalog, stock, orders. The shop service owns the shopping session: carts, which change constantly and are temporary, and payments. A rule of thumb I followed: whoever owns the data is the only one allowed to change it. That's why the shop service can't write orders directly and must call Django's internal API.

### Q4. 🟡 Why two different backend frameworks?
**A.** To show that microservices can be polyglot, and to use each framework's strengths. Django gives an ORM, migrations, authentication and a **free admin panel**, ideal for catalog and order management. FastAPI is async, fast and generates **OpenAPI/Swagger docs automatically**, which suits a high-traffic cart/checkout API. In a company I'd weigh this against the cost of maintaining two stacks.

### Q5. 🟡 What was the hardest part?
**A.** Keeping the services consistent without a shared database. For example, preventing overselling: two users checking out the last T-shirt at the same time. I solved it inside the service that owns stock: Django's `create_order()` runs in a transaction and locks the variant rows with `SELECT ... FOR UPDATE`, re-checks stock and uses its own prices. The second checkout waits for the lock, then gets a 409. *(core_service/orders/services.py)*

### Q6. 🟡 How did you build the UI before the backend existed?
**A.** I defined an `ApiClient` TypeScript interface and wrote two implementations: `mockApi` (JSON files + localStorage) and `httpApi` (real HTTP calls). Pages only import `api` from `lib/api.ts`, which picks one via the `NEXT_PUBLIC_USE_MOCK` env variable. The mock JSON had the same shape as the planned API responses, so when the backend was ready **no page code changed**. The same JSON files later became the backend's seed data.

### Q7. 🟢 What would you improve if you had more time?
**A.** Durable messaging (Redis Streams or RabbitMQ) plus the **transactional outbox pattern**, because Pub/Sub can lose events. A **circuit breaker** in the shop's core client. httpOnly cookies instead of localStorage for tokens. A Redis cache for the catalog. Real payment gateway webhooks. Frontend tests (Jest/RTL, Playwright). A CI pipeline running all tests on every pull request.

---

## 2. React & Next.js

### Q8. 🟢 What is the difference between Server and Client Components?
**A.** In the App Router, components are **server components by default**: they run only on the server, can `await` data directly, and send no JavaScript to the browser. Adding `"use client"` makes a **client component**, which can use state, effects and event handlers and runs in the browser after hydration. In my project, `app/products/page.tsx` is a server component that fetches products, while `ProductFilters`, `AddToCart` and `Navbar` are client components because they handle clicks and state.

### Q9. 🟡 Can a server component render a client component?
**A.** Yes, and it can pass serializable props. My product detail page (server) fetches the product and renders `<AddToCart product={product} />` (client). This is the "client islands" pattern: most of the page is static HTML and only interactive parts ship JS. A client component **cannot import** a server component, but it can receive one as `children`. That's how `Providers` (client) wraps server-rendered pages in `layout.tsx`.

### Q10. 🟢 Explain SSR, SSG, ISR and CSR with examples from your project.
**A.**
- **SSR** (rendered per request): `/products`, because it reads `searchParams` for filters.
- **SSG** (rendered at build time): static shells like `/login`.
- **ISR** (static, regenerated periodically): the home page has `export const revalidate = 60` in mock mode.
- **CSR** (data fetched in the browser): `/cart` and `/orders`. They need the user's token, which only exists in the browser.

### Q11. 🔴 Why did you call `connection()` in the root layout?
**A.** With the real backend, `next build` runs inside `docker build`, where the APIs don't exist, so static prerendering of pages that fetch data **failed**. Calling `await connection()` (only when not in mock mode) tells Next.js to render at request time instead of at build time, and data is always fresh. Trade-off: no static caching, so in production I'd add ISR/fetch caching with revalidation tags. *(frontend/src/app/layout.tsx)*

### Q12. 🟢 How does routing work in the App Router?
**A.** File-system based: each folder with a `page.tsx` is a route. `app/products/[slug]/page.tsx` is a **dynamic route**; in Next.js 15 `params` and `searchParams` are Promises you `await`. Special files apply to their folder: `layout.tsx` (persistent wrapper), `loading.tsx` (Suspense fallback), `error.tsx` (error boundary), `not-found.tsx` (404). Navigation uses `<Link>` (client-side, prefetched) or `router.push()`.

### Q13. 🟡 How do you protect routes like /checkout?
**A.** `middleware.ts` runs on the server before matching routes (`matcher: ["/checkout", "/orders/:path*"]`). If there's no `access_token` cookie, it redirects to `/login?next=/checkout`. The token is mirrored into a cookie because **middleware can't read localStorage**. This is only a UX guard: the real security is the backend rejecting requests without a valid JWT.

### Q14. 🟡 Why are filters stored in the URL instead of React state?
**A.** The URL is the single source of truth: users can bookmark, share, refresh and use the Back button and get the same results, and the server component can read the filters to render the right products. `ProductFilters` just calls `router.push("/products?...")`.

### Q15. 🟡 Why does `<ProductFilters>` have `key={JSON.stringify(query)}`?
**A.** Changing a component's `key` makes React **unmount and remount** it, resetting its local state. The price inputs keep local state while typing. When the URL query changes (e.g. "Clear all filters"), the key changes, so the inputs reset to match the URL. It's a clean alternative to syncing state with `useEffect`.

### Q16. 🟡 Why wrap `useSearchParams()` in `<Suspense>`?
**A.** In Next.js 15, a client component using `useSearchParams()` in a statically rendered page must be inside a Suspense boundary, otherwise the build fails ("missing Suspense boundary with useSearchParams"). The login and register pages wrap their form in `<Suspense>`.

### Q17. 🟢 What is hydration?
**A.** The server sends HTML so the user sees content immediately. Then React loads in the browser and attaches event handlers to the existing HTML for client components. Before hydration buttons don't respond. A **hydration mismatch** happens when server and client render different output, which is why my network-aware image starts in a `"pending"` state on both sides and only switches after `useEffect` runs in the browser.

### Q18. 🟢 Which React hooks did you use and why?
**A.** `useState` (selected size/colour, form status), `useEffect` (fetch orders, restore session on load), `useMemo` (variants for the chosen colour), `useCallback` (stable context functions), `useContext` through custom hooks (`useAuth`, `useCart`, `useNetwork`). Next.js hooks: `useRouter`, `useSearchParams`, `useParams`, `usePathname`.

### Q19. 🟡 How do you handle forms and validation?
**A.** React Hook Form with a Zod schema through `zodResolver`. Zod defines rules like `phone: /^[6-9]\d{9}$/` and `postal_code: /^\d{6}$/`, and React Hook Form shows field errors without re-rendering on every keystroke. The backend validates **again** (DRF serializers, Pydantic), because client validation is only for UX and attackers can bypass it with Postman.

### Q20. 🟢 How do you show loading and error states?
**A.** For server pages: `loading.tsx` (skeleton via Suspense) and `error.tsx` (error boundary with "Try again" calling `reset()`). For client actions: local state (`busy`, `error`) in the component that started the action, e.g. "Adding…" on the button and a red message under it.

---

## 3. Frontend architecture & TypeScript

### Q21. 🟡 Why Context API and not Redux?
**A.** The global state is small: the logged-in user, the cart and the network quality. Context plus custom hooks is enough and has no extra dependency. Server data (products) is fetched in server components, not stored globally. I'd consider Redux Toolkit or Zustand if state became large or updated very frequently (Context re-renders all consumers on every change), and React Query/SWR for client-side server-state caching.

### Q22. 🟡 Why do the hooks throw if used outside the provider?
**A.** `useCart()` checks `if (!ctx) throw new Error("useCart must be used inside <CartProvider>")`. It fails fast with a clear message instead of a confusing `undefined` error later. It's a common pattern for context-based custom hooks.

### Q23. 🔴 How does the frontend refresh an expired JWT?
**A.** In `httpApi.ts`'s `request()`: if a call returns **401** and we haven't retried yet, it calls `/api/core/auth/refresh/` with the refresh token, saves the new access token and **retries the original request once**. If the refresh fails, tokens are cleared and the error is thrown. The user only notices if the refresh token itself expired (7 days).

### Q24. 🟡 How do errors from the backend reach the UI?
**A.** Both backends return `{"detail": "readable message"}`. `httpApi` throws `ApiError(status, detail)`; context functions re-throw; the component that started the action catches it and shows `errorMessage(e)`. A 401 on "Add to cart" shows a "Please log in" message with a login link.

### Q25. 🟡 Explain the network-aware image feature.
**A.** Product photos are most of a page's weight. `lib/network.ts` detects quality via the **Network Information API** (`navigator.connection.effectiveType`, `downlink`, `saveData`), or, where unavailable (Safari/Firefox), by timing the download of a 100 KB file once per session. It classifies the connection as low/medium/high. `ProductImage`:
- **Low:** shows a zero-byte SVG illustration, with an optional "Load photo" button.
- **Medium:** a smaller, quality-45 WebP.
- **High:** a quality-80 WebP.

Users can override it (Auto / Data saver / HD). For one card image this means 5.3 KB (HD) vs 1.7 KB (medium) vs 0 KB (low).

### Q26. 🟢 What does `next/image` do for you?
**A.** It resizes to the needed width, converts to WebP/AVIF, generates `srcset` from `sizes`, lazy-loads below-the-fold images, prevents layout shift (with `fill` or width/height) and caches optimised versions on the server (`minimumCacheTTL`, 30 days in my config).

### Q27. 🟡 Why are `NEXT_PUBLIC_*` variables special?
**A.** They're **inlined into the JavaScript bundle at build time** so the browser can read them. Changing one requires a rebuild, not just a restart. That's why `NEXT_PUBLIC_USE_MOCK` is a Docker **build arg**. Non-public variables (like `API_INTERNAL_URL`) are read at runtime, on the server only.

### Q28. 🟡 Why does server-side rendering use `http://nginx/api` but the browser uses `http://localhost/api`?
**A.** Inside the frontend container, `localhost` means the container itself, not the host. Server components must use the Docker service name (`nginx`), while the browser runs on the host and uses `localhost`. `httpApi` picks `INTERNAL_API_URL` when `typeof window === "undefined"`.

---

## 4. Django & Django REST Framework

### Q29. 🟢 Why a custom User model from the start?
**A.** I wanted login by email (`USERNAME_FIELD = "email"`, `username = None`). Django strongly recommends defining a custom user model **before the first migration**, because swapping it later is painful. It also needed a custom `UserManager` and custom admin forms. *(core_service/users/models.py)*

### Q30. 🟡 How does the register endpoint validate input?
**A.** `RegisterSerializer`:
- Email is lower-cased and checked case-insensitively for duplicates. I declared `email` explicitly to replace the model's case-sensitive unique validator.
- `validate()` runs Django's password validators (min length 8, common passwords, numeric-only, similarity to email/name) and converts Django's `ValidationError` into a DRF one.
- `create()` calls `create_user()`, which hashes the password.

### Q31. 🟡 How did you make all API errors look the same?
**A.** A custom DRF `EXCEPTION_HANDLER` (`core/exceptions.py`) converts every error to `{"detail": "..."}`. Field errors like `{"email": ["..."]}` become `"Email: A user with this email already exists."`, with the raw `errors` kept alongside. The frontend can then always display `detail`.

### Q32. 🟡 How do category filters include subcategories?
**A.** In `ProductFilter.filter_category`: `Q(category__slug=value) | Q(category__parent__slug=value)`. So `?category=men` returns products in "Men" or any child category (T-Shirts, Jeans…). Categories are a self-referencing tree (`parent` FK to `self`).

### Q33. 🔴 Why do you call `.distinct()` in `ProductViewSet.filter_queryset`?
**A.** Filtering by `variants__size` or `variants__color` **joins** the variant table, so a product with several matching variants appears multiple times. `.distinct()` removes duplicates. Without it, pagination counts and results would be wrong.

### Q34. 🟡 The frontend sends `?ordering=price`, but the field is `base_price`. How?
**A.** A custom `AliasOrderingFilter` maps friendly names (`price` → `base_price`), only allows fields in `ordering_fields` (so users can't sort by arbitrary columns) and appends `id` as a tie-breaker so **pagination order is stable**.

### Q35. 🟢 What is the N+1 query problem and how did you avoid it?
**A.** Loading 8 products, then running one extra query per product for its category and variants: 1 + N queries. `select_related("category")` (SQL JOIN for foreign keys) and `prefetch_related("variants", "images")` (one extra query per relation) bring it down to a constant few queries.

### Q36. 🟡 How do users only see their own orders?
**A.** `OrderViewSet.get_queryset()` returns `Order.objects.filter(user=self.request.user)`. Requesting someone else's order id gives **404**, not 403, which also hides that the order exists. This prevents IDOR, the #1 risk in the OWASP API Top 10.

### Q37. 🟡 What does `AddressSerializer(source="*")` do?
**A.** The address is stored as flat columns on `Order` (`full_name`, `city`…), but the API returns a nested `address` object. `source="*"` passes the whole Order instance to the nested serializer, which reads those fields. The API shape is independent of the table layout.

### Q38. 🟡 Why keep business logic in `services.py` instead of views?
**A.** `create_order()` and `mark_order_paid()` are used by the internal API, the event worker, the admin and tests. Keeping them in a service layer makes views thin and the logic reusable and testable without HTTP.

### Q39. 🟡 How is the seed command made safe?
**A.** `seed_demo` skips if products exist (stock isn't reset on every restart) and supports `--force`. It inserts **explicit ids** (to match the frontend mock data), then resets PostgreSQL sequences with `connection.ops.sequence_reset_sql()`. Otherwise the next auto-generated id would collide.

### Q40. 🟢 How are admin static files served in Docker?
**A.** WhiteNoise middleware serves them from gunicorn; `collectstatic` runs at **image build time**. I used `STATIC_URL = "/django-static/"` so it doesn't clash with Next.js paths behind the same gateway.

### Q41. 🟡 Why is the order status read-only in the admin?
**A.** Status changes must publish events. The admin uses custom **actions** ("Mark selected PAID orders as SHIPPED") that update the status and publish `order.shipped`. If staff could edit the field directly, the event would be skipped.

---

## 5. FastAPI & async Python

### Q42. 🟢 What is dependency injection in FastAPI and where did you use it?
**A.** `Depends()` declares what an endpoint needs and FastAPI provides it: `get_current_user` (decoded JWT), `get_db` (one async DB session per request) and `get_core_client` (HTTP client). The big win is testing: `app.dependency_overrides` swaps in a SQLite session and a `FakeCore` without touching the endpoint code.

### Q43. 🟡 Why async SQLAlchemy and `expire_on_commit=False`?
**A.** Async lets the server handle other requests while waiting for the DB or the core service. With the default `expire_on_commit=True`, accessing attributes after `commit()` would trigger a lazy load, which **fails in async** (no implicit IO). Setting it to `False` keeps loaded values. Relationships use `lazy="selectin"` so they're loaded eagerly in the same `await`.

### Q44. 🟡 How does FastAPI authenticate users without calling Django?
**A.** `security.py` decodes the JWT with the **shared `JWT_SECRET`**, checks the signature and expiry, and requires `token_type == "access"` so a refresh token can't be used as an access token. It returns `CurrentUser(id, email, first_name)` from the claims. `HTTPBearer(auto_error=False)` lets me return my own message ("Please log in to continue.").

### Q45. 🟡 How do you return readable validation errors in FastAPI?
**A.** Pydantic `field_validator`s raise `ValueError("Enter a valid 10-digit mobile number")`. A custom `RequestValidationError` handler (`app/errors.py`) builds `detail = "Phone: Enter a valid 10-digit mobile number"` (stripping Pydantic's "Value error, " prefix) and keeps the full error list in `errors`. Same format as Django.

### Q46. 🟢 What are BackgroundTasks?
**A.** Functions FastAPI runs **after sending the response**. After a successful payment I add `send_order_confirmation` as a background task, so the user isn't waiting on email sending. For heavy or critical jobs I'd use a real queue (Celery/RQ/BullMQ) with retries.

### Q47. 🟡 What is the `lifespan` function used for?
**A.** Startup/shutdown logic. On startup it starts the Redis listener (`asyncio.create_task(listen_for_events())`) for `order.shipped`. On shutdown it cancels the task, closes Redis and disposes the DB engine for a clean exit.

### Q48. 🟡 Why Alembic, and how does it work with an async app?
**A.** Alembic versions schema changes like Django migrations do. `env.py` uses a **sync** engine with the same `postgresql+psycopg` URL, because psycopg 3 supports both sync and async. The entrypoint runs `alembic upgrade head` before uvicorn starts. I verified models and migrations match with `alembic check`.

---

## 6. Databases & data modelling

### Q49. 🟢 What is "database per service"?
**A.** Each service has its own database and is the only one that touches it: `core_db` for Django, `shop_db` for FastAPI. Other services get data through APIs or events. Benefits: independent schema changes and scaling, and a failure in one DB doesn't corrupt the other. Cost: no cross-service joins or foreign keys, and you need eventual consistency.

### Q50. 🟡 How do you reference a user or product across databases?
**A.** As plain integers: `Cart.user_id`, `CartItem.variant_id`, `Payment.order_id`. There are **no foreign keys across databases**. Validity is checked by calling the owning service, e.g. FastAPI calls `/internal/variants/{id}/` before adding to the cart.

### Q51. 🟡 Why store product name and price in cart items and order items?
**A.** They're **snapshots**. An order must show what the customer actually paid even if the price or name changes later. Snapshots in the cart also avoid one API call per item when showing the cart.

### Q52. 🟢 Why store prices as integers?
**A.** Whole rupees as `PositiveIntegerField`/`Integer` avoid floating-point rounding errors (0.1 + 0.2 ≠ 0.3). For paise I'd store amounts in the smallest unit (integer paise) or use `Decimal`. Never floats for money.

### Q53. 🔴 Explain `SELECT ... FOR UPDATE` in `create_order`.
**A.** Inside `transaction.atomic`, `select_for_update(of=("self",))` locks the variant rows until the transaction ends. A concurrent checkout for the same variant **waits**, then reads the updated stock and fails with 409 if it's insufficient. `of=("self",)` locks only variant rows, not the joined product rows. This prevents overselling, a classic race condition.

### Q54. 🟡 How is stock reduced safely?
**A.** In `mark_order_paid`: `ProductVariant.objects.filter(pk=...).update(stock=Greatest(F("stock") - qty, 0))`. `F()` performs the subtraction **in the database** (atomic, no read-modify-write race), and `Greatest(..., 0)` ensures stock never goes negative.

### Q55. 🟢 Which indexes did you add?
**A.** Unique indexes on `slug`, `sku` and `email`; a composite index on `(is_active, is_featured)` for product listing; unique `(product, size, color)` for variants; `Cart.user_id` unique; `Payment.order_id`/`user_id`; `Order.status` (`db_index`).

---

## 7. Authentication & security

### Q56. 🟢 How does JWT authentication work here?
**A.** On login Django checks the password and signs two tokens with HS256:
- an **access** token (30 min) with `user_id`, `email`, `first_name`, `token_type`, `exp`
- a **refresh** token (7 days).

The client sends `Authorization: Bearer <access>`. Any service with the secret can verify it locally, which makes authentication **stateless** and fast.

### Q57. 🟡 Access vs refresh token: why two?
**A.** The access token is sent on every request, so it's short-lived to limit damage if stolen. The refresh token is used only to get new access tokens, so it's exposed less. Improvement: refresh-token **rotation and blacklisting** (SimpleJWT's `token_blacklist`), so a stolen refresh token works at most once and logout really revokes it.

### Q58. 🟡 Where are tokens stored, and what's the risk?
**A.** In `localStorage` (read by the API client), with the access token mirrored to a cookie for middleware. The risk is **XSS**: injected JavaScript could read localStorage. In production I'd use **httpOnly, Secure, SameSite cookies** (JavaScript can't read them) plus CSRF protection.

### Q59. 🟡 How are internal APIs protected?
**A.** Two layers:
- Nginx returns 404 for `/internal/` from outside.
- Django requires an `X-Internal-Key` header, compared with `hmac.compare_digest` (constant time, so no timing attacks).

In production: private network only, and mTLS or short-lived service tokens instead of one static key.

### Q60. 🟡 Why don't you trust prices sent by the shop service?
**A.** Prices can change, and any client value can be tampered with. Django recalculates every line from **its own database** when creating an order (`create_order()`). The shop only sends `variant_id` and `quantity`.

### Q61. 🟢 How do you protect login from brute force?
**A.** Nginx `limit_req` allows 30 login requests per minute per IP (429 above that). The same error message is returned for unknown emails and wrong passwords, so attackers can't enumerate accounts. Next steps: per-account lockout (django-axes), CAPTCHA after failures, rate limits on all endpoints.

### Q62. 🔴 Why must the JWT secret be at least 32 bytes?
**A.** For HS256, RFC 7518 recommends a key at least as long as the hash output (256 bits). PyJWT warned about my short dev key, so I lengthened it. Short secrets can be brute-forced offline from any captured token, and the attacker could then forge tokens for any user.

### Q63. 🟡 Name the main API security measures you would add for production.
**A.**
- HTTPS + HSTS, and security headers (CSP, X-Frame-Options).
- httpOnly cookies, refresh rotation, RS256 keys so only Django can sign.
- Rate limiting everywhere, plus a WAF/bot protection.
- Idempotency keys and signed payment webhooks.
- Secrets in a secret manager, `DEBUG=0`, CORS limited to our domains.
- Dependency scanning, audit logs and alerts on 401/403/429 spikes.

---

## 8. Microservices communication & resilience

### Q64. 🟢 Sync vs async communication: when to use which?
**A.** **Sync (REST)** when the caller needs the answer to continue, e.g. "is it in stock?" before adding to the cart. Simple, but it couples availability: if Django is down, add-to-cart fails. **Async (events)** when the caller just announces something, e.g. "payment succeeded". It's loosely coupled and the publisher doesn't wait or depend on subscribers being up, at the cost of eventual consistency.

### Q65. 🟡 Walk me through the checkout flow.
**A.**
1. The frontend POSTs `/api/shop/checkout/` with the address.
2. FastAPI verifies the JWT, validates the address and reads the cart.
3. It POSTs `/internal/orders/` to Django. Django locks rows, checks stock, computes totals with its own prices and creates a **PENDING** order.
4. FastAPI creates a PENDING payment and returns `{order, payment}`.
5. On confirm, FastAPI marks the payment SUCCESS, clears the cart, **publishes `payment.succeeded`** and queues a mock email.
6. `core_worker` receives the event, marks the order **PAID** and reduces stock.

### Q66. 🟡 What happens if the core service is down when a user adds to the cart?
**A.** `CoreClient` has a 3-second timeout and retries connection errors with backoff (0.2 s, 0.4 s). If all attempts fail, it raises `CoreServiceError(503, "Catalog service is unavailable…")`, which an exception handler returns as a clean 503. In my test it took ~10 s, because each DNS lookup of the stopped container times out. A **circuit breaker** would make it fail instantly after a few failures.

### Q67. 🔴 Why don't you retry the create-order POST after a timeout?
**A.** A timeout doesn't mean the request failed: Django may have created the order and the response got lost. Retrying could create a **duplicate order**. So POSTs are retried only on connection errors (request never sent). The proper fix is an **idempotency key**: the client sends a unique key and the server returns the same result for repeated requests.

### Q68. 🟡 What does "idempotent" mean, and where did you implement it?
**A.** Doing an operation twice has the same effect as doing it once. Examples:
- `mark_order_paid()` only acts if the order is still PENDING, so a duplicate event doesn't reduce stock twice.
- Confirming an already successful payment returns it unchanged without publishing again.

This is essential because message systems usually deliver **at least once**.

### Q69. 🔴 What are the weaknesses of Redis Pub/Sub, and how would you fix them?
**A.** Pub/Sub is fire-and-forget: if no subscriber is listening (worker down), the message is **lost** and the order stays PENDING. Also, if Redis is down when publishing, the event is lost after the payment commit. Fixes:
- **Redis Streams/RabbitMQ/Kafka**, which keep messages until acknowledged (consumer groups, XACK).
- The **transactional outbox**: write the event to an outbox table in the same DB transaction as the payment, and have a relay publish it.
- A **reconciliation job** for orders that are paid but still PENDING.

### Q70. 🟡 What is a circuit breaker?
**A.** A wrapper around remote calls with three states:
- **Closed:** calls pass through normally.
- **Open:** after N failures, calls fail immediately without contacting the service, which protects both sides and gives instant errors.
- **Half-open:** after a cool-down, one trial call is allowed; on success it closes again.

Libraries: `pybreaker` (Python), `opossum` (Node).

### Q71. 🟡 What is an API gateway, and what does yours do?
**A.** A single entry point in front of services. My Nginx:
- routes by path (`/api/core` → Django, `/api/shop` → FastAPI, `/` → Next.js), so the browser sees **one origin** and there are no CORS issues
- blocks `/internal/`
- rate-limits login
- adds `X-Request-ID` for tracing.

### Q72. 🔴 What is a saga, and would you need one here?
**A.** A saga coordinates a business transaction across services as a sequence of local transactions, with **compensating actions** if a step fails (e.g. release reserved stock, cancel the order). I avoided needing one by keeping stock and orders in the same service, so a normal DB transaction works. If catalog and orders were split into separate services, checkout would need a saga.

---

## 9. Docker, Docker Compose & Nginx

### Q73. 🟢 What is a multi-stage Docker build and why use it?
**A.** Several `FROM` stages in one Dockerfile. My frontend has stages:
- `deps`: `npm ci`, cached
- `dev`: hot reload
- `builder`: `next build`
- `runner`: only the standalone output, as a non-root user.

The final image contains no dev dependencies or source, so it's **smaller and more secure**, and layers are cached between builds.

### Q74. 🟡 Why copy `package.json` / `requirements.txt` before the rest of the code?
**A.** Docker caches layers. Dependencies change rarely, code changes often. Copying the dependency files and installing first means code changes don't invalidate the expensive install layer, so rebuilds take seconds instead of minutes.

### Q75. 🟡 How does Docker Compose start services in the right order?
**A.** `depends_on` with `condition: service_healthy`, plus health checks: `pg_isready` for Postgres, `redis-cli ping`, and the services' `/health/` endpoints. For example, `shop_service` waits until its DB, Redis and the core service are healthy. `restart: unless-stopped` restarts crashed containers.

### Q76. 🟡 How do migrations run, and why does the worker skip them?
**A.** Each service's **entrypoint** runs migrations before the main command (Django `migrate` + seed; `alembic upgrade head`), then `exec "$@"`. `core_worker` uses the same image but sets `RUN_STARTUP_TASKS=0` so two containers don't run migrations **concurrently**. It also waits for `core_service` to be healthy.

### Q77. 🟡 How can two containers use the same image with different roles?
**A.** `core_service` and `core_worker` share `cloth-store/core-service`; the worker overrides `command: python manage.py run_event_consumer`. One codebase and one build: the web server and the background worker can be scaled independently.

### Q78. 🔴 You got 502 errors after rebuilding one service. Why, and how did you fix it?
**A.** Nginx resolves upstream hostnames **once at startup** and caches the IP. A rebuilt container gets a new IP, so Nginx kept sending traffic to the old one. Fix: `resolver 127.0.0.11 valid=10s` (Docker's DNS) plus variables in `proxy_pass` (`set $shop_upstream http://shop_service:8001;`), which forces Nginx to re-resolve.

### Q79. 🔴 Django returned 400 "Invalid HTTP_HOST header: 'core_service:8000'". Why?
**A.** The shop service called Django at `http://core_service:8000`. Hostnames with **underscores are invalid** per RFC 1034/1035, and Django validates the Host header even with `ALLOWED_HOSTS=["*"]`. Fix: a Docker network alias `core-service` (hyphen) used by other services.

### Q80. 🟢 What are Docker volumes for?
**A.** Persisting data outside the container's writable layer. `core_db_data` and `shop_db_data` keep PostgreSQL data across restarts and rebuilds. `docker compose down` keeps them; `down -v` deletes them.

### Q81. 🟡 Why do the Dockerfiles run `sed -i 's/\r$//' entrypoint.sh`?
**A.** On Windows, git may convert line endings to CRLF. A shell script with CRLF fails in Linux (`exec ./entrypoint.sh: no such file or directory`). The `sed` strips carriage returns. I also added `.gitattributes` with `eol=lf` so the repository enforces LF for everyone.

---

## 10. Testing

### Q82. 🟢 What testing did you do?
**A.**
- **Unit/integration:** 22 pytest tests in Django (against a real PostgreSQL test DB) and 11 in FastAPI (SQLite + a fake core service).
- **End-to-end:** a Postman collection with 31 requests and 61 assertions through the gateway, also runnable with **Newman** for CI.
- **Manual:** smoke tests and resilience checks, such as stopping containers.

### Q83. 🟡 How did you test FastAPI without the real core service?
**A.** `app.dependency_overrides[get_core_client] = lambda: fake_core`. `FakeCore` returns fixed variants and can simulate an outage (`fake_core.down = True` → 503). The DB dependency is overridden with an aiosqlite file DB, and `publish` is monkeypatched to record events, so I can assert that `payment.succeeded` was published with the right data.

### Q84. 🟡 What do the Postman tests verify?
**A.** Status codes and bodies for health; auth (register, duplicate, wrong password, me, refresh); catalog filters and sorting; cart stock limits; checkout validation; failed and successful payment. They also check that the **async event changed the order to PAID** (with a short delay) and that internal APIs are blocked or require the key. Requests chain values (token, ids) through environment variables.

### Q85. 🟡 Which tests would you add next?
**A.** Frontend unit tests (Jest + React Testing Library) for `ProductFilters`, `AddToCart` and the network `classify()` function; Playwright E2E for the full purchase in a browser; contract tests between services; load tests with k6/Locust; and a CI workflow running everything on each PR.

---

## 11. Performance, caching & scaling

### Q86. 🟡 How would you scale this to 1 million users?
**A.** First estimate: ~100k daily active users, ~5–10k concurrent, ~500–1,000 requests/s at peak, about 95% reads. Then:
- Stateless services (JWT, cart in DB), scaled horizontally on Kubernetes with autoscaling.
- A CDN for static files and images.
- Caching: Redis for the catalog, ISR/edge caching for pages.
- PgBouncer and read replicas.
- A search engine for products.
- Durable messaging, and observability.

Load test first to find the real bottleneck.

### Q87. 🟡 Which caching layers would you use?
**A.**
- Browser HTTP cache (hashed JS/CSS cached for a year, images 1 day + stale-while-revalidate).
- React Query/SWR on the client.
- Service worker.
- CDN.
- Next.js ISR/fetch cache with tags.
- Nginx micro-cache for public GET APIs.
- Redis application cache (Django `cache_page`) for categories and products.
- DB indexes.

**Never** cache carts, orders or `/me` in shared caches, and always re-check stock and price at checkout.

### Q88. 🔴 How do you invalidate cached catalog data when an admin changes a product?
**A.** Options:
- A short TTL (accept up to 60 s staleness).
- **Event-based:** on product save, publish `product.updated`; consumers delete the Redis keys and call Next.js `revalidateTag("products")`.
- stale-while-revalidate.

Display data can be slightly stale because the checkout re-validates with the source of truth.

### Q89. 🟡 How would you handle a flash sale?
**A.** Pre-scale and warm caches; a virtual waiting room in front of checkout; stock reservation in Redis with atomic `DECR` and a TTL instead of holding DB locks for every visitor; rate limits; queue order processing; idempotency keys to make retries safe.

### Q90. 🟢 How do you find performance problems?
**A.** Measure first: browser DevTools (Network, Lighthouse), Django query counts (debug toolbar, `assertNumQueries`), `EXPLAIN ANALYZE` in PostgreSQL, APM/tracing (OpenTelemetry), and load tests with k6/Locust to see p95 latency and throughput under load.

---

## 12. Scenario & debugging questions

### Q91. 🟡 A customer paid but their order still shows PENDING. How do you debug it?
**A.**
1. Check the payment in `shop_db`: is it SUCCESS?
2. Check the `shop_service` logs for "Published payment.succeeded" (or a Redis error).
3. Check `core_worker`: is it running (`docker compose ps`)? Do its logs show "Handling payment.succeeded"?
4. Most likely cause: the worker was down and **Pub/Sub dropped the message**.

Immediate fix: `mark_order_paid(order_id)` in the Django shell (safe because it's idempotent). Long-term fix: durable queue + outbox + reconciliation job.

### Q92. 🟡 Users see "Request failed (502)". What do you check?
**A.** 502 comes from Nginx: the upstream isn't reachable. Check `docker compose ps` (is the service healthy or still starting?), `docker compose logs nginx` and the service's own logs, then call the service directly on its port (`:8000`/`:8001`) to separate a gateway problem from a service problem. Use the `X-Request-ID` header to correlate logs.

### Q93. 🟡 Login works in Postman but the cart says "Please log in". Why?
**A.** Possible causes:
- The `Authorization` header isn't being sent (check DevTools).
- The token expired and the refresh failed.
- **`JWT_SECRET` differs** between Django and FastAPI, so FastAPI can't verify Django's signature.
- `token_type` is "refresh" instead of "access".

Decode the token on jwt.io and compare the env variables in both containers.

### Q94. 🟡 You changed Python code but nothing changed in the running app. Why?
**A.** The code is **copied into the image at build time**; containers don't see local edits. Rebuild: `docker compose up --build -d <service>`. For fast iteration use bind mounts (like the `frontend-dev` profile) or run the service locally.

### Q95. 🔴 Tests failed with "relation auth_group does not exist" even though migrations existed locally. What happened?
**A.** The Docker image had been built **before** I generated the migration files, so the container had no migrations. Django then tried to sync apps without migrations and failed. Rebuilding the image fixed it, and I used `--create-db` to drop the broken test database. Lesson: verify what's actually inside the image (`docker run --rm image ls ...`).

### Q96. 🟡 How would you add a "material" field to products end to end?
**A.**
1. Add the model field.
2. Generate the migration.
3. Add it to `ProductSerializer.fields`.
4. Add `material?: string` to the TypeScript `Product` type.
5. Display it in `AddToCart.tsx`.
6. Rebuild `core_service` and `frontend`.
7. Fill values in the admin.
8. Add a test.

The contract between backend serializer and frontend type must stay in sync.

---

## 13. Behavioural questions (STAR answers from this project)

### Q97. Tell me about a bug that was hard to find.
**A.** *Situation:* after wiring the shop service to Django, add-to-cart always failed with "Unexpected response from catalog service". *Task:* find why a working endpoint failed only when called service-to-service. *Action:* I read the shop logs (Django returned 400 with an HTML page), then the Django logs, which showed `DisallowedHost: 'core_service:8000'`. Django rejects underscores in hostnames per RFC 1034 even with `ALLOWED_HOSTS=*`. I added a Docker network alias `core-service` and documented why. *Result:* the end-to-end flow passed, and I added the case to the troubleshooting guide.

### Q98. Tell me about a time you made a trade-off.
**A.** For events I chose **Redis Pub/Sub** over Streams or Kafka to keep the learning project simple and avoid another component. I knew it can lose messages, so I made the handlers idempotent, **documented the limitation**, wrote the production alternative (Streams + outbox + reconciliation) in the architecture docs, and included the fix in the plan for the Node.js version.

### Q99. How did you make sure your work was correct?
**A.** Several layers of verification: typecheck and production build for the frontend; pytest suites for both services; a scripted end-to-end flow; the Postman collection run twice to confirm it's repeatable (61/61); resilience tests by stopping containers; screenshots of the UI in headless Edge for the image feature; and a fresh-clone build test before publishing the README.

### Q100. How did you help others understand the system?
**A.** I wrote role-specific documentation: a backend developer guide, a Postman testing guide, a UI architecture guide, a junior developer walkthrough of every user journey with hands-on exercises, a demo presentation script with Q&A, and an architecture Q&A on scaling, caching and security. I also structured git history into meaningful conventional commits.

---

## 14. Quick-fire round

| # | Question | Short answer |
| --- | --- | --- |
| 101 | Default page size? | 8 (must match frontend `PAGE_SIZE`) |
| 102 | Access / refresh token lifetime? | 30 minutes / 7 days |
| 103 | JWT algorithm? | HS256 with a shared secret (≥ 32 bytes) |
| 104 | Free shipping threshold? | ₹1,999 (else ₹99), enforced by Django |
| 105 | Event names? | `payment.succeeded`, `order.shipped` on channel `events` |
| 106 | How many containers? | 8: nginx, frontend, core_service, core_worker, shop_service, core_db, shop_db, redis |
| 107 | Status code for stock conflict at checkout? | 409 Conflict |
| 108 | Status code for FastAPI validation errors? | 422 Unprocessable Entity |
| 109 | Status when a dependency service is down? | 503 Service Unavailable |
| 110 | Status for too many logins? | 429 Too Many Requests (Nginx) |
| 111 | Another user's order id? | 404 (queryset filtered by user) |
| 112 | Where are internal APIs blocked? | Nginx `location /internal/ { return 404; }` |
| 113 | Header for service-to-service auth? | `X-Internal-Key` |
| 114 | Header for request tracing? | `X-Request-ID` (added by Nginx) |
| 115 | Password hashing in Django? | PBKDF2 with SHA256 (Django default) |
| 116 | Why `CONN_MAX_AGE=60`? | Reuse DB connections across requests |
| 117 | What does `--create-db` do in pytest-django? | Recreate the test DB from scratch |
| 118 | Django vs FastAPI migration tools? | Django migrations vs Alembic |
| 119 | What does `output: "standalone"` do? | Minimal Node server bundle for small Docker images |
| 120 | `connection()` in layout? | Opt into request-time rendering (real backend mode) |
| 121 | Image formats served? | WebP via `next/image`, qualities 30/45/80 |
| 122 | Network detection API? | `navigator.connection` (effectiveType, downlink, saveData) |
| 123 | Speed test file size? | 100 KB of random bytes, `Cache-Control: no-store` |
| 124 | Why random bytes? | Incompressible, so the measurement reflects real transfer |
| 125 | How do you watch events live? | `docker compose exec redis redis-cli SUBSCRIBE events` |

---

> 💡 **Final tip:** interviewers value *why* over *what*. For every feature, be ready to explain
> the problem it solves, the alternative you didn't choose, and what you'd change at larger scale.
