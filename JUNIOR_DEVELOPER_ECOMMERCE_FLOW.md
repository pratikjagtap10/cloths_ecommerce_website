# Junior Developer Guide: How the Threads Store Works, End to End

Welcome! 👋 This document follows a customer's actions **from the click in the
browser, through every service, down to the database, and back to the screen**.
After reading it you should be able to:

- explain what each part of the system does,
- open the right file when something breaks,
- trace any request yourself,
- make your first change across frontend and backend.

Read it with the project open in VS Code and the app running
(`docker compose up -d`, then open http://localhost).

Other docs, for later:
- `FRONTEND_DEVELOPER_GUIDE.md` / `UI_DEVELOPER_GUIDE.md`: UI details
- `BACKEND_DEVELOPER_GUIDE.md`: Docker commands, API list, configuration
- `BACKEND_POSTMAN_TESTING_GUIDE.md`: testing APIs by hand

---

## Contents

1. [The big picture (a real shop analogy)](#1-the-big-picture-a-real-shop-analogy)
2. [Words you need to know](#2-words-you-need-to-know)
3. [Where everything lives](#3-where-everything-lives)
4. [Anatomy of ONE request (the pattern behind everything)](#4-anatomy-of-one-request)
5. [Journey A: Browsing products](#journey-a-browsing-products)
6. [Journey B: Registering and logging in](#journey-b-registering-and-logging-in)
7. [Journey C: Adding to the cart](#journey-c-adding-to-the-cart)
8. [Journey D: Checkout](#journey-d-checkout)
9. [Journey E: Payment and the event](#journey-e-payment-and-the-event)
10. [Journey F: Viewing orders](#journey-f-viewing-orders)
11. [Journey G: The admin ships the order](#journey-g-the-admin-ships-the-order)
12. [Who owns which data](#12-who-owns-which-data)
13. [The JSON shapes (the contract)](#13-the-json-shapes-the-contract)
14. [How errors travel back to the screen](#14-how-errors-travel-back-to-the-screen)
15. [How to debug any problem](#15-how-to-debug-any-problem)
16. [Hands-on exercises](#16-hands-on-exercises)
17. [FAQ](#17-faq)

---

## 1. The big picture (a real shop analogy)

Imagine a real clothing shop:

| Real shop | Our system | Container |
| --- | --- | --- |
| The **shop window and floor** customers walk around | Next.js frontend | `frontend` |
| The **reception desk** at the entrance that sends you to the right counter | Nginx API gateway | `nginx` |
| The **back office**: staff records, the stock room, the order book | Django **core service** | `core_service` |
| The **till**: your basket, paying | FastAPI **shop service** | `shop_service` |
| The **notice board** where staff pin messages for each other | Redis | `redis` |
| A **clerk** who reads the notice board and updates the order book | Django **worker** | `core_worker` |
| Two separate **filing cabinets** | PostgreSQL databases | `core_db`, `shop_db` |

The till doesn't walk into the stock room itself. It **asks** the back office:
*"Do we have this T-shirt in M? What's the price?"* That is a **synchronous** call
(the till waits for the answer).

After a customer pays, the till **pins a note** on the board: *"Order 1003 is paid."*
It doesn't wait. The clerk sees the note and updates the order book. That is an
**asynchronous** event.

```
                              Browser
                                 │  every request goes to http://localhost
                                 ▼
                         ┌───────────────┐
                         │     NGINX     │  reception desk
                         └─┬─────┬─────┬─┘
                  /        │     │     │      /api/shop/*
       ┌───────────────────┘     │     └────────────────────┐
       ▼                         ▼ /api/core/*, /admin/      ▼
┌─────────────┐        ┌──────────────────┐  asks (REST) ┌──────────────────┐
│  FRONTEND   │        │  CORE (Django)   │◄─────────────│  SHOP (FastAPI)  │
│  Next.js    │        │ users, products, │              │ cart, checkout,  │
│  pages, UI  │        │ orders, admin    │              │ payments         │
└─────────────┘        └───┬──────────────┘              └──────┬───────────┘
                           │        ▲                           │
                       core_db      │ updates order      publishes "payment.succeeded"
                                ┌───┴─────────┐                 │
                                │ CORE WORKER │◄──── REDIS ◄────┘
                                └─────────────┘   (notice board)
                                                              shop_db
```

---

## 2. Words you need to know

| Term | Meaning in this project |
| --- | --- |
| **Microservice** | A small, separately deployable app with its own job and its own database. We have two backend ones: core and shop. |
| **API** | A set of URLs a program can call to get or change data, e.g. `GET /api/core/products/`. |
| **REST** | A style of API: resources as URLs, actions as HTTP methods (GET read, POST create, PATCH update, DELETE remove). |
| **JSON** | The text format all our APIs send and receive. |
| **Gateway** | Nginx: a single entry point that forwards requests to the right service. |
| **JWT** | "JSON Web Token": a signed string proving who you are. Sent as `Authorization: Bearer <token>`. |
| **Access / refresh token** | Access token: short-lived (30 min), used on every request. Refresh token: long-lived (7 days), used only to get a new access token. |
| **Variant** | A product in one size + colour, e.g. *Classic Tee, Black, M*. Stock and price are per variant. |
| **ORM** | Code that maps database tables to classes (Django models, SQLAlchemy models), so we rarely write SQL. |
| **Migration** | A versioned script that changes the database structure (Django migrations, Alembic). |
| **Serializer / schema** | Converts objects ↔ JSON and validates input (DRF serializers in Django, Pydantic schemas in FastAPI). |
| **Synchronous call** | Caller sends a request and **waits** for the answer (HTTP). |
| **Asynchronous event** | Publisher sends a message and **doesn't wait**; subscribers react later (Redis Pub/Sub). |
| **Idempotent** | Doing it twice has the same effect as doing it once (important for events that may repeat). |
| **SSR** | Server-Side Rendering: Next.js builds the HTML on the server before sending it. |
| **Context (React)** | Global state shared by many components (who is logged in, what's in the cart). |

---

## 3. Where everything lives

```
ecommerce_demo/
├── frontend/          Next.js app: what the user SEES
│   └── src/
│       ├── app/           pages, one folder = one URL (app/cart/page.tsx = /cart)
│       ├── components/    reusable UI pieces (Navbar, ProductCard, AddToCart…)
│       ├── context/       AuthContext (user), CartContext (cart)
│       ├── lib/api.ts     ★ the ONLY door to data. Picks mockApi or httpApi
│       ├── lib/httpApi.ts real HTTP calls to the backend (adds the JWT)
│       └── types/index.ts ★ shapes of Product, Cart, Order… (the contract)
│
├── core_service/      Django: users, catalog, orders
│   ├── users/             register, login (JWT), me
│   ├── catalog/           Category, Product, ProductVariant + filters
│   ├── orders/            Order, OrderItem, ★ services.py (business rules)
│   ├── events/            Redis publish + the worker's event handlers
│   └── core/              settings, URL map, error format, internal-key check
│
├── shop_service/      FastAPI: cart, checkout, payments
│   └── app/
│       ├── routers/       cart.py, checkout.py, payments.py (the endpoints)
│       ├── services/      ★ core_client.py (calls Django), events.py (Redis)
│       ├── security.py    verifies the JWT
│       └── models.py      Cart, CartItem, Payment tables
│
├── nginx/default.conf ★ which URL goes to which service
└── docker-compose.yml ★ all 8 containers and how they connect
```

**Rule of thumb for "where's the code for X?"**

| If it's about… | Look in… |
| --- | --- |
| How something looks or a button's behaviour | `frontend/src/components/` or `frontend/src/app/<page>/` |
| Which API the UI calls | `frontend/src/lib/httpApi.ts` |
| Users, products, stock, orders, prices | `core_service/` |
| Cart, checkout, payment | `shop_service/app/routers/` |
| One service calling another | `shop_service/app/services/core_client.py` |
| Events | `core_service/events/`, `shop_service/app/services/events.py` |
| A URL returning 404 at the gateway | `nginx/default.conf` |

---

## 4. Anatomy of ONE request

**Every** feature follows the same round trip. Learn it once and you can follow any feature.

```
 ① User clicks a button
        │
 ② React component calls a function     e.g. useCart().add(variantId, 2)
        │                                     (frontend/src/context/CartContext.tsx)
 ③ Context calls the API layer           api.addToCart(...)   (frontend/src/lib/api.ts)
        │
 ④ httpApi builds the HTTP request       POST http://localhost/api/shop/cart/items/
        │                                 Authorization: Bearer eyJ...   (lib/httpApi.ts)
        ▼
 ⑤ NGINX looks at the path               /api/shop/* → shop_service:8001
        │                                 (nginx/default.conf)
        ▼
 ⑥ Backend framework finds the endpoint  @router.post("/items/")  (routers/cart.py)
        │
 ⑦ Authentication                        who is this? → verify JWT (security.py)
        │
 ⑧ Validation                            is the body valid? → Pydantic / DRF serializer
        │
 ⑨ Business logic                        rules: enough stock? correct price?
        │                                 (may call ANOTHER service here)
 ⑩ Database                              read/write through the ORM
        │
 ⑪ Response JSON                         {"items":[...], "subtotal": 1198}
        │
        ▼  (back through Nginx)
 ⑫ httpApi parses JSON or throws ApiError(status, detail)
        │
 ⑬ Context updates state                 setCart(newCart)
        │
 ⑭ React re-renders everything using that state → the cart badge shows "2" ✅
```

> 💡 Open the browser **DevTools → Network** tab and click around the shop. Every
> line you see there is step ④→⑪ happening.

---

## Journey A: Browsing products

**User action:** opens http://localhost/products?category=men&size=M

```
Browser ──GET /products?category=men&size=M──► Nginx ──► frontend (Next.js server)
                                                            │
             app/products/page.tsx (a SERVER component) reads searchParams
                                                            │
             api.getProducts({category:"men", size:"M"})
                                                            │  server-side fetch
                         GET http://nginx/api/core/products/?category=men&size=M
                                                            ▼
                                      Nginx ──► core_service (Django)
                                                            │
     catalog/views.py  ProductViewSet.list()
        ├─ get_queryset(): only active products, load category + variants efficiently
        ├─ ProductFilter (catalog/filters.py):
        │     category=men → products in "men" OR its children (men-tshirts, men-jeans…)
        │     size=M       → products having a variant with size M
        ├─ ordering, search
        ├─ pagination: 8 per page → {count, next, previous, results}
        └─ ProductSerializer → JSON (product + category + variants)
                                                            │
             Next.js renders ProductCard × N into HTML ◄────┘
                                                            │
Browser ◄────────────── finished HTML page ─────────────────┘
```

**Things to notice**
- The **Next.js server** called the API, not your browser. That's SSR: the HTML arrives
  complete. (Inside Docker it uses `http://nginx/api` because "localhost" inside a
  container means the container itself.)
- Filters live in the **URL**. Clicking a filter (`components/ProductFilters.tsx`)
  just changes the URL, and the page re-runs on the server.
- Public endpoint: **no login needed** (`permission_classes = [AllowAny]`).

**Try it:** open http://localhost/api/core/products/?category=men&size=M in your
browser to see the raw JSON in Django's browsable API.

---

## Journey B: Registering and logging in

### Register
```
/register form (app/register/page.tsx)
   Zod checks: email format, password ≥ 8 chars, passwords match   ← instant feedback
        │ api.register({...})
        ▼
POST /api/core/auth/register/  →  users/views.py RegisterView
   RegisterSerializer (users/serializers.py):
     • email lower-cased, duplicate check  → 400 "A user with this email already exists."
     • Django password validators (too common, too short, all numbers…)
     • User.objects.create_user() → password is HASHED before saving
   → 201 {id, email, first_name, last_name}       (never the password)
        │
AuthContext then logs in automatically ↓
```

### Login
```
AuthContext.login(email, password)            (frontend/src/context/AuthContext.tsx)
   │
   ├─ POST /api/core/auth/login/  {email, password}
   │      LoginSerializer: checks password, creates two signed JWTs:
   │        access  = {user_id: 1, email, first_name, token_type:"access",  exp: +30 min}
   │        refresh = {user_id: 1, token_type:"refresh", exp: +7 days}
   │      ← {access, refresh}
   │
   ├─ setTokens() (lib/storage.ts)
   │      • localStorage: access_token, refresh_token  (read by httpApi)
   │      • cookie: access_token                       (read by middleware.ts)
   │
   ├─ GET /api/core/auth/me/   with  Authorization: Bearer <access>
   │      ← {id, email, first_name, last_name}
   │
   └─ setUser(user)  → Navbar shows "Hi, Demo" + "My Orders"
                      → CartContext sees a user → loads the cart from FastAPI
```

### Why the token works in BOTH backends
```
Django signs the token with JWT_SECRET  ─────────┐
                                                 │ same secret (from .env)
FastAPI verifies the signature with JWT_SECRET ◄─┘   (shop_service/app/security.py)
```
FastAPI never calls Django to ask "who is this?". It checks the signature
mathematically and reads `user_id` from the token. Fast and independent.

### Protected pages
`frontend/src/middleware.ts` runs **before** `/checkout` and `/orders` render. If there's no
`access_token` cookie it redirects to `/login?next=/checkout`. After login the user is
sent back to `next`.

### Token expiry (after 30 minutes)
```
any API call → 401 → httpApi automatically: POST /auth/refresh/ {refresh}
             → new access token saved → original request retried once ✅
             (if the refresh also fails → logged out)
```

---

## Journey C: Adding to the cart

**User action:** on a product page, chooses Black / M, quantity 2, clicks **Add to cart**.

```
AddToCart.tsx (component)
   finds the variant for colour+size → variant.id = 2
   useCart().add(2, 2)
        │
CartContext → api.addToCart(2, 2) → httpApi
        │
POST /api/shop/cart/items/   {"variant_id": 2, "quantity": 2}
Authorization: Bearer <access>
        │
        ▼ Nginx: /api/shop/* → shop_service
shop_service/app/routers/cart.py  add_item()
   ① get_current_user()      verify JWT → user_id = 1         (no JWT → 401)
   ② AddItemIn (Pydantic)    variant_id > 0, 1 ≤ quantity ≤ 20 (bad → 422)
   ③ core.get_variant(2)  ═══ SYNCHRONOUS CALL TO DJANGO ═══════════════════╗
                                                                            ║
        GET http://core-service:8000/internal/variants/2/                   ║
        X-Internal-Key: <secret>                                            ║
              │                                                             ║
        core_service: catalog/views.py InternalVariantView                  ║
           HasInternalApiKey checks the header (wrong → 403)                ║
           ← {"id":2,"price":599,"stock":3,"size":"M","color":"Black",      ║
              "product_name":"Classic Crew Neck Tee", "is_active":true, …}  ║
   ◄════════════════════════════════════════════════════════════════════════╝
   ④ rule: quantity already in cart + 2 ≤ stock 3?   no → 400 "Only 3 left…"
   ⑤ save CartItem in shop_db, with a SNAPSHOT of name, size, colour, price
   ⑥ ← {"items":[{...,"quantity":2,"unit_price":599}], "subtotal":1198}
        │
CartContext: setCart(newCart)
   → Navbar badge (uses useCart().count) re-renders to 2
   → AddToCart shows "Added 2 × Classic Crew Neck Tee… View cart"
```

**Key lessons**
- **Django is the source of truth** for price and stock, so the shop asks it every time.
- The **internal API** is protected twice: Nginx returns 404 for `/internal/` from outside,
  and Django requires the secret `X-Internal-Key`.
- The cart stores a **snapshot** (name, colour, price) so showing the cart doesn't need
  one call to Django per item.
- `core_client.py` has a **timeout and retries**. If Django is down you get a clean
  **503 "Catalog service is unavailable"** instead of a hang or crash.
- `user_id` and `variant_id` are just numbers in shop_db. There are **no foreign keys
  between the two databases**.

---

## Journey D: Checkout

**User action:** on `/checkout` fills in the address and clicks **Place order**.

```
app/checkout/page.tsx
   React Hook Form + Zod validate: mobile ^[6-9]\d{9}$, PIN ^\d{6}$ ...
   api.checkout(address)
        │
POST /api/shop/checkout/  {"address": {...}}          → shop_service
shop_service/app/routers/checkout.py
   ① verify JWT → user 1
   ② validate address again (AddressIn in schemas.py)   ← never trust the browser
   ③ read my cart from shop_db → empty? 400 "Your cart is empty."
   ④ core.create_order({...}) ═══ SYNCHRONOUS CALL TO DJANGO ════════════════╗
                                                                             ║
        POST http://core-service:8000/internal/orders/                       ║
        {"user_id":1, "address":{...}, "items":[{"variant_id":2,"quantity":2}]}
              │                                                              ║
        core_service/orders/services.py  create_order()   (ONE DB TRANSACTION)
           • SELECT … FOR UPDATE on the variants   ← locks the rows so two
             customers can't both buy the last T-shirt                       ║
           • stock still enough? no → 409 "…Only N left."                    ║
           • prices from DJANGO's database (not from the cart!)              ║
           • subtotal 1198, shipping 99 (free over ₹1,999), total 1297       ║
           • save Order(status=PENDING) + OrderItems                         ║
           ← 201 {id:1003, status:"PENDING", total:1297, items:[...]}        ║
   ◄═════════════════════════════════════════════════════════════════════════╝
   ⑤ save Payment(order_id=1003, amount=1297, status=PENDING) in shop_db
   ⑥ ← 201 {"order": {...}, "payment": {"id": 7, "status": "PENDING", ...}}
        │
Checkout page switches to step 2: "Mock payment"
```

**Key lessons**
- Business rules (stock, prices, shipping) live in **one place**: `orders/services.py`.
  Views stay thin.
- **Transactions + row locks** prevent overselling.
- The POST to create the order is **not retried on timeout**. The first attempt may have
  succeeded, and retrying could create a duplicate order (see `core_client.py`).

---

## Journey E: Payment and the event

**User action:** clicks **Pay now (success)**.

```
api.confirmPayment(7, true)
        │
POST /api/shop/payments/7/confirm/  {"success": true}   → shop_service
shop_service/app/routers/payments.py  confirm_payment()
   ① JWT → user 1; payment 7 belongs to user 1? (else 404)
   ② already SUCCESS? → return it (idempotent, no double processing)
   ③ success=false → status FAILED, return (user can retry)
   ④ status=SUCCESS, provider_ref="MOCK-…", DELETE my cart items, COMMIT
   ⑤ publish("payment.succeeded", {order_id:1003, payment_id:7, user_id:1, amount:1297})
        │                                          ═══ ASYNCHRONOUS EVENT ═══
        │                    Redis channel "events":
        │                    {"type":"payment.succeeded","data":{"order_id":1003,...}}
        │                                │
   ⑥ background task: mock confirmation email (runs AFTER the response is sent)
   ⑦ ← {"id":7, "status":"SUCCESS", ...}       ← the browser gets this immediately
        │                                │
Frontend:                                ▼
   refresh cart (now empty)      core_worker  (python manage.py run_event_consumer)
   go to /orders/1003?placed=1     events/management/commands/run_event_consumer.py
                                      receives the message
                                   events/handlers.py → handle_payment_succeeded()
                                   orders/services.py → mark_order_paid(1003)
                                      • lock the order row
                                      • status still PENDING? (else do nothing: idempotent)
                                      • stock = stock − quantity for each item
                                      • status = PAID
```

**Watch it live:** run `docker compose logs -f core_worker shop_service`, then pay:
```
shop_service | Published payment.succeeded (2 receiver(s)): {'order_id': 1003, ...}
shop_service | [mock email] To: demo@clothstore.com | Order #1003 confirmed | Amount paid: Rs.1297
core_worker  | Handling payment.succeeded {'order_id': 1003, ...}
core_worker  | Order #1003 marked PAID and stock reduced
```

**Sync vs async: why both?**

| | Synchronous (REST) | Asynchronous (event) |
| --- | --- | --- |
| Used for | "Is it in stock?", "create the order" | "the payment happened" |
| Caller waits? | Yes, it needs the answer to continue | No, it just announces |
| If the other service is down | Request fails (we return 503) | Publisher still succeeds; subscriber reacts later* |
| Coupling | Tighter | Looser |

\* With Redis **Pub/Sub**, a message sent while the worker is down is **lost**. That's
a known simplification. Production systems use Redis Streams/RabbitMQ/Kafka, which
keep messages until processed.

---

## Journey F: Viewing orders

```
/orders  (app/orders/page.tsx, client component)
   middleware.ts: cookie present? else → /login?next=/orders
   useEffect → api.getOrders()
        │
GET /api/core/orders/  Authorization: Bearer <access>   → core_service
orders/views.py OrderViewSet
   IsAuthenticated (no token → 401)
   get_queryset(): Order.objects.filter(user=request.user)   ← ONLY my orders
   OrderSerializer → [{id, status, total, address:{...}, items:[...]}, ...]
        │
React renders the list with OrderStatusBadge (PENDING / PAID / SHIPPED)
```

**Security lesson:** asking for someone else's order (`/api/core/orders/1001/` as
another user) returns **404**, not 403, because the queryset only contains your own
orders. We don't even reveal that the order exists.

---

## Journey G: The admin ships the order

```
http://localhost/admin/  (Django admin, staff only)
Orders → tick order 1003 (PAID) → action "Mark selected PAID orders as SHIPPED"
   orders/admin.py mark_shipped()
      status = SHIPPED, save
      publish("order.shipped", {order_id:1003, user_id:1, email:"demo@…"})
              │                                  ═══ EVENT, other direction ═══
              ▼  Redis "events"
shop_service: services/events.py listen_for_events()  (started in main.py lifespan)
      → notifications.notify_order_shipped() → logs a mock "shipped" email
```

Status changes in the admin are only allowed through these **actions**: the status field
is read-only. This guarantees the event is always published.

---

## 12. Who owns which data

| Data | Owner service | Database | Others get it via |
| --- | --- | --- | --- |
| Users, passwords | core | core_db | JWT claims (`user_id`, `email`) |
| Categories, products, variants, **stock**, **prices** | core | core_db | `GET /api/core/products/`, `GET /internal/variants/{id}/` |
| Orders and order items | core | core_db | `GET /api/core/orders/`, `POST /internal/orders/` |
| Carts and cart items | shop | shop_db | `GET /api/shop/cart/` |
| Payments | shop | shop_db | `GET /api/shop/payments/{id}/` |
| Logged-in user and cart on screen | frontend | browser memory (React Context) | – |
| Tokens | frontend | localStorage + cookie | – |

**Golden rule:** a service may only read/write **its own** database. Need data from
another service? Call its API or listen to its events.

---

## 13. The JSON shapes (the contract)

The frontend's `src/types/index.ts` and the backend serializers/schemas must agree.
If you change one, change the other.

**Product** (`GET /api/core/products/{slug}/`)
```json
{
  "id": 1, "name": "Classic Crew Neck Tee", "slug": "classic-crew-neck-tee",
  "description": "Soft 100% combed cotton tee...",
  "category": { "id": 4, "name": "T-Shirts", "slug": "men-tshirts" },
  "base_price": 599, "is_active": true, "is_featured": true,
  "created_at": "2026-10-30T00:00:00Z", "images": [],
  "variants": [
    { "id": 2, "size": "M", "color": "Black", "color_hex": "#1f2937",
      "sku": "CLT-001-BLA-M", "stock": 3, "price": 599 }
  ]
}
```

**Cart** (`GET /api/shop/cart/`)
```json
{
  "items": [
    { "id": 5, "variant_id": 2, "product_name": "Classic Crew Neck Tee",
      "product_slug": "classic-crew-neck-tee", "size": "M", "color": "Black",
      "color_hex": "#1f2937", "quantity": 2, "unit_price": 599 }
  ],
  "subtotal": 1198
}
```

**Order** (`GET /api/core/orders/{id}/`)
```json
{
  "id": 1003, "user_id": 1, "status": "PAID",
  "subtotal": 1198, "shipping_fee": 99, "total": 1297,
  "address": { "full_name": "Demo User", "phone": "9876543210", "line1": "12 MG Road",
               "city": "Pune", "state": "Maharashtra", "postal_code": "411001" },
  "created_at": "2026-11-07T07:33:52Z",
  "items": [ { "id": 7, "variant_id": 2, "product_name": "Classic Crew Neck Tee",
               "size": "M", "color": "Black", "quantity": 2, "unit_price": 599, "...": "..." } ]
}
```

**Error** (every service, every failure)
```json
{ "detail": "Only 3 left in stock for Black / M." }
```

Prices are **whole rupees as integers** (599, not 599.00), so there are no rounding problems.

---

## 14. How errors travel back to the screen

```
Backend raises an error
   Django:  ValidationError / OutOfStock / NotAuthenticated …
            → core/exceptions.py turns it into {"detail": "Readable message"}
   FastAPI: HTTPException / CoreServiceError / validation error
            → app/errors.py turns it into {"detail": "Readable message"}
        │  HTTP status 400 / 401 / 404 / 409 / 422 / 503
        ▼
frontend/src/lib/httpApi.ts
   401 → try refresh token once → retry
   otherwise → throw new ApiError(status, body.detail)
        │
Context function (e.g. CartContext.add) does NOT catch, it re-throws
        │
The component that started the action catches it:
   try { await add(...) } catch (e) { setStatus({type:"error", text: errorMessage(e)}) }
        │
User sees a red message: "Only 3 left in stock for Black / M."
```

Rule: **the component that started an action decides how to show its error.**

---

## 15. How to debug any problem

Work from the outside in:

1. **Browser DevTools → Network tab.** Find the failing request.
   - What URL? What status code? What does the response `detail` say?
   - Every response has an **`X-Request-ID`** header added by Nginx.
2. **Is everything running?** `docker compose ps`. Look for `(healthy)`; `Exited` means trouble.
3. **Read the logs of the service that owns the URL:**
   - `/api/core/...` → `docker compose logs -f core_service`
   - `/api/shop/...` → `docker compose logs -f shop_service`
   - events → `docker compose logs -f core_worker`
   - 502/404 at the gateway → `docker compose logs -f nginx`
4. **Reproduce without the UI** in Postman or Swagger (http://localhost/api/shop/docs).
   If Postman works but the UI doesn't, the bug is in the frontend.
5. **Bypass the gateway:** call `http://localhost:8000/...` (core) or `:8001` (shop)
   directly to tell an Nginx problem from a service problem.
6. **Look at the data:**
   `docker compose exec core_db psql -U core -d core_db` → `SELECT id, status FROM orders_order ORDER BY id DESC LIMIT 5;`
7. **Watch events:** `docker compose exec redis redis-cli SUBSCRIBE events`

Common symptoms → first place to look:

| Symptom | Look at |
| --- | --- |
| Product list empty / page error | core_service logs; was demo data seeded? |
| "Please log in" when you are logged in | Token expired + refresh failed → log in again; check `JWT_SECRET` is the same for both services |
| Add to cart → 503 | core_service is down or unreachable from shop_service |
| Order stuck on PENDING | core_worker not running when you paid |
| Code change not visible | You must rebuild: `docker compose up --build -d <service>` |

---

## 16. Hands-on exercises

Do these in order. Each one touches more of the system. Ask a senior to review your change.

### Exercise 1: Follow a request (no code, 20 min)
Open DevTools → Network, add an item to the cart, and find:
the URL, the method, the `Authorization` header, the request body, the response.
Then find the matching lines in `docker compose logs core_service shop_service`
(you should see FastAPI's call to `/internal/variants/…`).

### Exercise 2: Change a business rule (30 min)
Make shipping free from **₹2,499** instead of ₹1,999.
- Backend: `FREE_SHIPPING_OVER` in `core_service/core/settings.py`
- Frontend: `FREE_SHIPPING_OVER` in `frontend/src/lib/config.ts` (the cart page shows the hint)
- Update the test in `core_service/tests/test_orders.py` if needed, then run the tests.

❓ *Why does the same number exist in two places, and which one decides the real
price?* (Answer: Django decides. The frontend value is only for display. In a bigger
system the frontend would get it from an API.)

### Exercise 3: Add a field end to end (1-2 h)
Add **`material`** (e.g. "100% cotton") to products and show it on the product page.
1. `core_service/catalog/models.py`: add `material = models.CharField(max_length=100, blank=True)`
2. Generate the migration (command in `BACKEND_DEVELOPER_GUIDE.md` §11)
3. `catalog/serializers.py`: add `"material"` to `ProductSerializer.Meta.fields`
4. `frontend/src/types/index.ts`: add `material?: string` to `Product`
5. `frontend/src/components/AddToCart.tsx`: display it under the description
6. Rebuild `core_service` and `frontend`, fill the value in the Django admin, and check the page
7. Add a check in `tests/test_catalog.py`

### Exercise 4: Add a new event (2 h)
When an admin **cancels** an order, publish `order.cancelled`; the shop service should
log *"[mock email] Your order #X was cancelled"*.
- Publish in `orders/admin.py` → `mark_cancelled` (look at how `mark_shipped` does it)
- Handle it in `shop_service/app/services/events.py` → `_handle()` and `notifications.py`
- Test: cancel a PENDING order in the admin and watch `docker compose logs -f shop_service`

### Exercise 5: Write tests (1 h)
- FastAPI: a test that `PATCH /api/shop/cart/items/{id}/` with `quantity: 0` returns 422
  (`shop_service/tests/test_shop.py`)
- Django: a test that `?max_price=600` returns only cheap products (`tests/test_catalog.py`)
- Run them (commands in `BACKEND_DEVELOPER_GUIDE.md` §6)

---

## 17. FAQ

**Why is the cart in FastAPI but orders in Django?**
Different responsibilities. The cart changes constantly and is temporary (shop service).
Orders are permanent business records tied to stock and the admin panel (core service).

**Why does checkout call Django instead of writing the order itself?**
Django owns orders and stock. Only the owner may change them, so it can enforce the
rules (locking, prices) in one place.

**Why store product name and price in the cart and order items?**
They're **snapshots**. If the price changes tomorrow, your past order must still show
what you paid.

**How does the UI work when the backend is off?**
Set `NEXT_PUBLIC_USE_MOCK=true`. `lib/api.ts` then uses `mockApi.ts` (JSON files +
localStorage) with the same interface. That's how the UI was built first.

**Where do the demo products come from?**
`core_service/catalog/seed_data/*.json`, the same files as the frontend mocks.
Loaded by `python manage.py seed_demo` on first start.

**What's `core_worker`?**
The same Django code and image as `core_service`, started with a different command
(`run_event_consumer`). It doesn't serve HTTP; it only listens to Redis.

**Can I run only the frontend?**
Yes, in mock mode. See `FRONTEND_DEVELOPER_GUIDE.md` §1.

**I changed Python code and nothing happened.**
The code is copied into the image at build time. Run `docker compose up --build -d <service>`.

---

### One-page summary

```
Browse     : Next.js server → Django catalog API → HTML                      (SSR, public)
Login      : Django checks password → JWT access + refresh → stored in browser
Add to cart: FastAPI verifies JWT → asks Django price/stock (SYNC) → saves cart
Checkout   : FastAPI → Django creates order with row locks + own prices (SYNC) → payment PENDING
Pay        : FastAPI marks payment SUCCESS → publishes payment.succeeded (ASYNC)
             → core_worker marks order PAID + reduces stock
Orders     : Django returns only the logged-in user's orders
Ship       : Django admin action → publishes order.shipped (ASYNC) → FastAPI notifies
Gateway    : Nginx routes /api/core → Django, /api/shop → FastAPI, / → Next.js, blocks /internal
```

Happy coding! 🚀 If something in this guide is unclear, that's a bug in the guide. Please improve it.
