# Backend Testing with Postman: Local Validation Guide

This guide shows how to validate every backend API of the Threads store with
**Postman** on your machine. You can run the ready-made collection (31 requests,
61 automatic checks) or test requests one by one by hand.

Files used:

| File | What it is |
| --- | --- |
| `postman/Threads-Backend.postman_collection.json` | All requests, grouped in folders, with test scripts |
| `postman/Threads-Local.postman_environment.json` | URLs, demo login and variables that requests fill in automatically |

---

## 1. Before you start

1. Start the backend (see `BACKEND_DEVELOPER_GUIDE.md`):
   ```bash
   docker compose up --build -d
   docker compose ps          # wait until core_service and shop_service are (healthy)
   ```
2. Quick check in a browser: http://localhost/api/core/health/ should show
   `{"status":"ok","service":"core","database":"ok"}`.
3. Install Postman (desktop app) from https://www.postman.com/downloads/.
   A free account is enough. The web version can't reach `localhost` without the desktop agent.

---

## 2. Import the collection and environment

1. Open Postman and click **Import** (top left).
2. Drag in **both** files from the `postman/` folder, or click *files* and select them.
3. In the top-right environment dropdown, select **"Threads - Local (Docker)"**.
   If no environment is selected, `{{base_url}}` stays unresolved and requests fail.

You should now see the collection **"Threads Backend (Local)"** with these folders:

```
Threads Backend (Local)
├── 0. Health                                  is everything running?
├── 1. Auth (Django core)                      register, login, JWT, refresh
├── 2. Catalog (Django core)                   categories, products, filters, search
├── 3. Cart (FastAPI shop)                     add / update / view cart
├── 4. Checkout & payment (FastAPI → Django → Redis)
├── 5. Orders (Django core)
└── 6. Internal APIs (service-to-service)      security of internal endpoints
```

### Environment variables

| Variable | Default | Filled by |
| --- | --- | --- |
| `base_url` | `http://localhost` (Nginx gateway) | you |
| `core_url` | `http://localhost:8000` (Django directly) | you |
| `shop_url` | `http://localhost:8001` (FastAPI directly) | you |
| `internal_api_key` | `dev-internal-key-change-me` | you (must match `.env`) |
| `email` / `password` | demo customer | you |
| `access_token`, `refresh_token` | – | **Login** request |
| `product_slug`, `variant_id`, `variant_stock` | – | **List products** request |
| `cart_item_id` | – | **Add item to cart** |
| `order_id`, `payment_id` | – | **Checkout** |

Requests save these values in their **Tests** tab scripts (`pm.environment.set(...)`),
so run the folders **in order** the first time.

---

## 3. Run everything automatically (Collection Runner)

1. Hover the collection, click **⋯ → Run collection**.
2. Keep all requests ticked, **Iterations: 1**, environment **Threads - Local (Docker)**.
3. Click **Run Threads Backend (Local)**.

Expected result: **all tests passed** (61 assertions). Each request shows its
checks, e.g. `✓ 201 Created`, `✓ order is PENDING`.

You can run it again and again: it registers a new random user each time and
picks the variant with the most stock. When stock runs low, reset the demo data
(see section 7).

### Same thing from the command line (Newman)

Newman is Postman's command-line runner and is handy for CI pipelines. Needs Node.js.

```bash
npx newman run postman/Threads-Backend.postman_collection.json \
  -e postman/Threads-Local.postman_environment.json
```

Ends with a summary table: `requests 31 / failed 0`, `assertions 61 / failed 0`.

---

## 4. Manual walkthrough (learn what each API does)

Open each request, click **Send**, and look at the **Body**, **Status** and
**Test Results** tabs at the bottom.

### Step 0: Health
| Request | Expect |
| --- | --- |
| Core service health | `200`, `"database": "ok"` |
| Shop service health | `200`, `"database": "ok"`, `"redis": "ok"` |

### Step 1: Authentication (Django issues JWT tokens)

**Login (saves tokens)**
```http
POST {{base_url}}/api/core/auth/login/
Content-Type: application/json

{ "email": "demo@clothstore.com", "password": "demo1234" }
```
Response:
```json
{ "refresh": "eyJhbGciOiJIUzI1NiIs...", "access": "eyJhbGciOiJIUzI1NiIs..." }
```
The test script stores both tokens. Every later request uses
**Authorization → Bearer `{{access_token}}`**, configured once at collection level.
Requests that must work *without* a token have Auth set to **No Auth**.

💡 Paste the access token into https://jwt.io to see its payload: `user_id`,
`email`, `first_name`, `token_type: "access"`, `exp`. The FastAPI service reads
exactly these claims.

| Request | What it proves | Expect |
| --- | --- | --- |
| Register new user | Sign-up works, password not returned | `201` |
| Register duplicate email | Validation and readable errors | `400`, `detail: "Email: A user with this email already exists."` |
| Login wrong password | Bad credentials rejected | `401`, `"Invalid email or password."` |
| Me (needs token) | Token authentication | `200`, your profile |
| Me without token | Endpoint is protected | `401` |
| Refresh access token | Get a new access token without the password | `200`, new `access` |

### Step 2: Catalog (public, no token)

| Request | URL | Check |
| --- | --- | --- |
| List categories | `/api/core/categories/` | 12 categories, `parent` links children to Men/Women/Kids |
| List products | `/api/core/products/` | `{count, next, previous, results}`, 8 per page |
| Filter | `/api/core/products/?category=men&size=M&ordering=price` | only men's products with size M, cheapest first |
| Search | `/api/core/products/?search=linen` | only linen products |
| Product detail | `/api/core/products/{{product_slug}}/` | nested `category`, `variants` with `stock` and `price` |
| Unknown product | `/api/core/products/does-not-exist/` | `404` |

Try changing query parameters yourself in the **Params** tab:
`featured=true`, `color=Black`, `min_price=1000&max_price=2500`, `ordering=-price`, `page=2`.

### Step 3: Cart (FastAPI checks the token and asks Django for stock)

| Request | Body | Expect |
| --- | --- | --- |
| Cart without token | – | `401`, `"Please log in to continue."` |
| Add item to cart | `{"variant_id": {{variant_id}}, "quantity": 1}` | `200`, cart with the item, `subtotal` |
| Add more than stock | `quantity` = stock + 1 | `400`, `"Only N left in stock for Black / M."` |
| Update quantity | `PATCH .../items/{{cart_item_id}}/` `{"quantity": 2}` | quantity 2 |
| Get my cart | – | items and subtotal |

🔍 **See the service-to-service call:** while sending *Add item to cart*, run
`docker compose logs -f core_service`. You'll see `GET /internal/variants/<id>/`
from `python-httpx`: FastAPI asking Django for price and stock.

### Step 4: Checkout and payment (sync and async communication)

**Checkout**
```http
POST {{base_url}}/api/shop/checkout/
Authorization: Bearer {{access_token}}
Content-Type: application/json

{
  "address": {
    "full_name": "Demo User", "phone": "9876543210", "line1": "12 MG Road",
    "city": "Pune", "state": "Maharashtra", "postal_code": "411001"
  }
}
```
Response (shortened):
```json
{
  "order":   { "id": 1005, "status": "PENDING", "subtotal": 1198, "shipping_fee": 99, "total": 1297, "items": [ ... ] },
  "payment": { "id": 3, "order_id": 1005, "amount": 1297, "status": "PENDING" }
}
```

| Request | Expect | What happens behind the scenes |
| --- | --- | --- |
| Checkout with invalid address | `422`, `"Phone: Enter a valid 10-digit mobile number"` | Pydantic validation in FastAPI |
| Checkout | `201`, order `PENDING` | FastAPI → `POST /internal/orders/` → Django locks stock rows, uses its own prices, creates the order |
| Pay - simulate failure | `status: FAILED` | Nothing else changes; you can retry |
| Pay - success | `status: SUCCESS` | Cart cleared, **`payment.succeeded` published to Redis**, mock email in a background task |
| Order is now PAID | `status: PAID` | **core_worker** received the event and updated the order and stock |
| Cart is empty after payment | `items: []` | |

🔍 **Watch the asynchronous event:** before clicking *Pay - success*, run
```bash
docker compose logs -f core_worker shop_service
```
You'll see:
```
shop_service | Published payment.succeeded (2 receiver(s)): {'order_id': 1005, ...}
shop_service | [mock email] To: demo@clothstore.com | Order #1005 confirmed | Amount paid: Rs.1297
core_worker  | Handling payment.succeeded {'order_id': 1005, ...}
core_worker  | Order #1005 marked PAID and stock reduced
```
You can also listen to Redis directly: `docker compose exec redis redis-cli SUBSCRIBE events`.

> The "Order is now PAID" request waits 1.5 s first (pre-request script)
> because the event is processed **asynchronously**. That small delay is
> exactly the difference between sync and async communication.

### Step 5: Orders
| Request | Expect |
| --- | --- |
| My orders | `200`, list including the new order first |
| Order without token | `401` |

Try: log in as `admin@clothstore.com` / `admin1234` (change the environment
variables), then request the demo user's order id. You get **404**, because users
can only see their own orders.

### Step 6: Internal APIs (security)
| Request | URL | Expect | Lesson |
| --- | --- | --- | --- |
| Blocked at gateway | `{{base_url}}/internal/variants/{{variant_id}}/` | `404` | Nginx hides internal APIs from the internet |
| Without key | `{{core_url}}/internal/variants/...` | `403` | Even inside the network, a key is required |
| With key | header `X-Internal-Key: {{internal_api_key}}` | `200` | What the shop service sees |

---

## 5. Bonus: test the "order shipped" event (admin → FastAPI)

1. Open http://localhost/admin/ and log in as `admin@clothstore.com` / `admin1234`.
2. **Orders**: tick the order you just paid (status PAID).
3. Action **"Mark selected PAID orders as SHIPPED"**, then **Go**.
4. In Postman, send **My orders**: the status is now `SHIPPED`.
5. `docker compose logs shop_service` shows:
   `[mock email] To: demo@clothstore.com | Good news! Order #1005 has been shipped.`

This time **Django published** the event and **FastAPI consumed** it, the reverse direction.

---

## 6. Testing services directly (bypassing the gateway)

Replace `{{base_url}}` with:
- `{{core_url}}` (http://localhost:8000) for Django,
- `{{shop_url}}` (http://localhost:8001) for FastAPI.

The paths stay the same (`/api/core/...`, `/api/shop/...`). Useful to find out
whether a problem is in Nginx or in the service itself.

FastAPI also has its own built-in tester: **http://localhost/api/shop/docs**.
1. Click **Authorize**, paste the access token (without the word "Bearer"), click Authorize.
2. Open any endpoint, **Try it out**, **Execute**.

---

## 7. Resetting test data

| Goal | Command |
| --- | --- |
| Restore demo stock and catalog (keeps users/orders) | `docker compose exec core_service python manage.py seed_demo --force` |
| Empty all carts and payments | `docker compose exec shop_db psql -U shop -d shop_db -c "TRUNCATE cart_items, carts, payments;"` |
| Wipe everything and start fresh | `docker compose down -v && docker compose up --build -d` |

---

## 8. Writing your own Postman tests

Each request has a **Scripts → Post-response** (older Postman: **Tests**) tab with JavaScript:

```javascript
// Check the status code
pm.test("200 OK", () => pm.response.to.have.status(200));

// Check the body
const body = pm.response.json();
pm.test("order is PAID", () => pm.expect(body.status).to.eql("PAID"));

// Save a value for later requests
pm.environment.set("order_id", body.id);
```

Use a variable anywhere with double braces: `{{order_id}}` in URLs, headers or bodies.
**Pre-request** scripts run *before* sending (e.g. to generate a unique email).

---

## 9. Troubleshooting

| Problem | Fix |
| --- | --- |
| `Error: connect ECONNREFUSED 127.0.0.1:80` | Backend not running: `docker compose up -d`, then check `docker compose ps` |
| URLs show `{{base_url}}` literally / "Invalid URL" | Select the **Threads - Local (Docker)** environment (top right) |
| `401` on cart/orders | Token missing or expired (30 min). Run **1. Auth → Login** again |
| `403` on internal API *with* key | `internal_api_key` in the environment doesn't match `INTERNAL_API_KEY` in `.env` |
| `429 Too Many Requests` | Login rate limit (30/min). Wait a minute |
| `400 Only N left in stock` on Add item | Stock used up by earlier runs: reset with `seed_demo --force` |
| Order still `PENDING` after payment | Is `core_worker` running? `docker compose ps core_worker`, `docker compose logs core_worker` |
| `502 Bad Gateway` | A service is (re)starting. Wait for `(healthy)` |
| `503 Catalog service is unavailable` from the shop | The core service is down; FastAPI handled it gracefully. `docker compose start core_service` |
