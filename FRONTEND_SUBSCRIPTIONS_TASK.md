# Frontend Task — SkuuMate Subscription Feature (Plans, Subscriptions, Payments)

## 1. Role & context

You are a senior frontend engineer on the **SkuuMate** project (React + TypeScript + Vite SPA running on `localhost:5173`). The backend is a Django REST API mounted at `/api/v1`. Your job is to **build the UI pages and integrate the API endpoints** for the subscription feature, matching the project's existing conventions (routing, design system, HTTP client, auth helpers, state management).

Hard constraints:

- **Do not modify the backend.** All required data comes from the endpoints below.
- **Do not invent endpoints or fields.** Use only the exact paths, methods, query params, and JSON shapes documented here.
- **Reuse** the existing axios/fetch wrapper, JWT interceptors (access + refresh), protected-route guards, and toast/notification component already in the project. Add a Vite dev proxy `"/api" -> "http://localhost:8000"` if one is not already configured.
- If the frontend repo already has subscription-related pages, refactor them to consume these exact shapes rather than build duplicates.

## 2. Backend conventions you must handle

### 2.1 Response envelope
- Success: `{ "success": true, "message": string, "data": <payload> }`
- App errors (404, some 400s/500s): `{ "success": false, "message": string }`
- **Field-validation errors may be un-wrapped** (raised by the backend's serializer) and look like `{ "plan_id": ["Package not found or inactive."], "payment_mode": ["..."] }` with status `400`.
- Auth: `401` = missing/expired token (trigger refresh flow), `403` = authenticated but wrong role.

Write one HTTP helper that unwraps all three shapes consistently (e.g., normalize to `{ ok, status, data, message, errors }`) and use it everywhere.

### 2.2 Roles
- `school admin` — user object has a `school`; can subscribe, initiate payments, read own subscriptions/current.
- `school staff` (any authenticated school user) — can read own subscriptions and current.
- `superadmin` — `role === "superadmin"` with no school (or Django superuser); full cross-school management.

Gate routes and hide nav items accordingly.

### 2.3 Pagination
Paginated lists return `data: { "count": int, "next": str|null, "previous": str|null, "results": [ ... ] }`, page size **10**. Navigate with `?page=<n>`. The two public `plans` endpoints are **not** paginated (`data` is a plain array).

### 2.4 Filtering / search / ordering
Lists accept query params: `?<filter>=<value>` for exact filters, `?search=<v>` (free text), `?ordering=<field>` / `?ordering=-<field>` (desc). Apply filters on submit/change, reset back to page 1.

Common subscription/payment enums:
- subscription `status`: `trial | pending_payment | active | past_due | expired | grace | locked | cancelled`
- payment `status`: `pending | successful | failed`
- payment `payment_mode`: `cash | virtual`
- gateways: `paystack | stripe | momo | simulate`

## 3. Endpoint reference

Base: `/api/v1`

### 3.1 Public (no auth)

| Method | Path | Notes |
|---|---|---|
| GET | `/plans/` | Active public packages. **Unpaginated array.** Filters: `plan_type`, `billing_period`, `is_active`, `is_public`, `currency`, `min_price`, `max_price`, `more_students_than`. |
| GET | `/plans/features/` | Comparison data: `{ packages: PlanCompare[], feature_categories: [{ key, label }] }`. |

`data` shapes:

```
Package: {
  id: string, name: string, code: string, plan_type: "lite"|"advantage"|"enterprise"|"",
  tagline: string, description: string,
  price: "500.00" (decimal string!), setup_fee: "100.00",
  billing_period: "TERM"|"MONTH"|"YEAR", currency: "GHS",
  minimum_students: number, maximum_students: number|null,
  is_active: boolean, is_public: boolean, display_order: number,
  features: [{ code, name, enabled }],
  limits: [{ key, name, value: "25" (string), description }],
  created_at, updated_at
}

PlanCompare: {
  id, name, code, plan_type, tagline, description,
  pricing: { price, setup_fee, currency, billing_period },
  limits: { minimum_students, maximum_students,
            student_range: "0–250 Students", package_limits: [{ key, name, value, description }] },
  features: [{ code, name, enabled }],
  is_popular: boolean   // true for the Advantage/medium tier we want people to choose
}
```

### 3.2 School-facing (auth: any authenticated school user; POST = school admin)

| Method | Path | Notes |
|---|---|---|
| GET | `/subscriptions/` | Paginated my subscriptions. Filters: `plan`, `plan_code`, `status`, `is_paid` (bool), `is_current` (bool), `term`, `start_date_from`, `start_date_to`, `end_date_from`, `end_date_to`. Supports `search`, `ordering`. |
| GET | `/subscriptions/current/` | Current subscription (single object) or `404 {success:false}` if none. |
| POST | `/subscriptions/payments/initiate/` | Start a gateway payment. Body below. Returns payment intent. |
| POST | `/subscriptions/subscribe/` | Complete subscription. Free trial if eligible; otherwise requires `payment_reference`. |

```
InitializePayment body:     { "plan_id": "<uuid>", "term_id": "<uuid>|null(opt)", "provider": "paystack|stripe|momo|simulate", "include_setup_fee": true|false }
InitializePayment response data:
  { "payment_id": "<uuid>", "payment_url": string, "reference": string,
    "provider": string, "amount": "250.00", "currency": "GHS", "plan": "Advantage" }

Subscribe body:  { "plan_id": "<uuid>", "term_id": "<uuid>|null(opt)", "payment_reference": string, "payment_provider": "paystack|stripe|momo|simulate" }
Subscribe response: 201 → Subscription object
```

`Subscription` (school view):

```
{
  id, plan: PackageSummary|null, plan_name: string|null,
  status, status_label, term: uuid|null, term_name: string|null,
  start_date, end_date, grace_end_date: string|null,
  days_remaining: number,
  is_paid, is_current, is_read_only, is_locked, is_accessible, is_on_trial: boolean,
  payments: [{
    id, amount, currency, payment_reference, provider,
    payment_mode: "cash"|"virtual", payment_mode_label, status, status_label, created_at
  }],
  notes, created_at
}

PackageSummary: { id, name, code, plan_type, tagline, description, price, setup_fee,
                  billing_period, currency, minimum_students, maximum_students }
```

### 3.3 Superadmin (auth: superadmin)

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/subscriptions/` | All schools' subscriptions. Paginated. Filters: `school`, `school_name`, `school_code`, `plan`, `plan_code`, `status`, `is_paid` (bool), `is_current` (bool), `term`, `start_date_from`, `start_date_to`, `end_date_from`, `end_date_to`, `created_from`, `created_to`. Supports `search`, `ordering`. |
| GET | `/admin/subscriptions/<uuid:pk>/` | Single admin subscription. |
| POST | `/admin/subscriptions/subscribe/` | Subscribe a school on behalf. Body below. |
| GET | `/admin/payments/` | All payments ledger. Paginated. Filters: `school`, `school_name`, `subscription`, `plan`, `status`, `payment_mode`, `provider`, `min_amount`, `max_amount`, `created_from`, `created_to`. |
| GET | `/schools/` | (Existing, superadmin) list of schools — use to pick the target school in the subscribe form. |

```
Admin subscribe body:
  { "school_id": "<uuid>", "plan_id": "<uuid>", "term_id": "<uuid>|null(opt)",
    "status": "trial" | "active",
    "payment_mode": "cash" | "virtual",        // REQUIRED when status=active
    "payment_reference": "<gateway-ref>",       // REQUIRED when payment_mode=virtual
    "payment_provider": "paystack|stripe|momo|cash", // REQUIRED (non-cash) when payment_mode=virtual
    "notes": "string" }                          // optional

Validation rules enforced by the API:
  - status=trial → free trial, payment fields unnecessary and ignored.
  - status=active → payment_mode must be cash or virtual.
  - payment_mode=virtual → payment_reference + non-cash payment_provider required.
  - response: 201 → AdminSubscription
```

`AdminSubscription` = `Subscription` **plus**:

```
{ school: { id, name, email, phone, school_code, status, city }, activated_by_name: string|null }
```

`AdminPayment` = school-side payment shape **plus**:

```
{ subscription: uuid|null, recorded_by_name: string|null }
```

## 4. Pages & flows to build

### 4.1 School-side

**A. Public pricing page (`/pricing`)** — no login required.
- Load `/plans/features/` and/or `/plans/`.
- Render 3 package cards (order by `display_order`); highlight the `is_popular` tier.
- Show student range, price (format `setup_fee` + `price` for the period), and features grouped under the returned `feature_categories`.
- "Choose <tier>" → school admins land on the subscribe flow; anonymous users get the login screen first.

**B. My subscription page (`/subscription` or `/billing`)** — school user.
- Show current subscription from `/subscriptions/current/`:
  - Trial banner with `days_remaining` + CTA "Choose a plan" (or "Upgrade" when a paid plan exists).
  - Status badges for `trial`, `active`, `grace` (warn + countdown, `is_read_only`), `locked` / `expired` (blocker CTA), `pending_payment` (resume payment).
  - Plan details: `plan_name`, `term_name`, `start_date`/`end_date`, `payments` history table.
- Subscription history table: `/subscriptions/` with pagination + status filter dropdown (and `search`).
- If no current subscription: empty state with CTA to pricing.

**C. Subscribe / choose-a-plan flow**.
- From the pricing cards, a logged-in school admin continues to checkout.
- Trial-eligible schools (no current/past paid plan): POST `/subscriptions/subscribe/` with `{ plan_id }` — no payment fields. Success → celebration screen showing `days_remaining`.
- Everyone else (paid): **two-step flow**:
  1. POST `/subscriptions/payments/initiate/` → get `payment_id`, `reference`, `payment_url`.
     - Real gateway (`payment_url` non-empty): show a "Complete payment" button that opens `payment_url` (Paystack/Stripe checkout). Provider `simulate` returns an empty `payment_url` — add a dev-only notice and a "I've paid / simulate completion" button.
  2. After gateway returns (or dev button), POST `/subscriptions/subscribe/` with `plan_id` + `payment_reference` (+ `payment_provider`).
     - The reference is verified server-side; `400` with `payment_reference` message → show error and let them retry.
     - Backend is idempotent: re-submitting an already-successful reference returns the existing subscription.
- **Polling/variance:** the endpoint may complete synchronously or via webhook. After a successful subscribe (201) refresh `/subscriptions/current/`. If a school returns 400 stating "A payment reference is required" (school is not trial-eligible), automatically fall back to the initiate→complete path.
- Optional: `term_id` from the current academic term if the UI exposes term selection; otherwise omit it (backend defaults to current term).

### 4.2 Superadmin-side (protected, superadmin only)

**A. All subscriptions page (`/admin/subscriptions`)**.
- Load `/admin/subscriptions/` with a filter bar: `status`, `is_paid`, `is_current`, `school_name` (search), `start_date_from/to`. Show school name/code, tier (`plan_name`), `status` badge, `is_current`, dates, `activated_by_name`.
- Row click → detail (`/admin/subscriptions/<id>/`) showing full subscription + payment history.
- Pagination controls (page size 10) + result count (from `count`).

**B. Subscribe a school (modal page, `/admin/subscriptions/new` or drawer from list)**.
- School selector → `GET /schools/` (pick by name).
- Plan selector → `GET /plans/` (active public tiers).
- Toggle `status`: 
  - `trial` → show only plan + optional term.
  - `active` → reveal payment section:
    - `payment_mode` = `cash`: show note "offline receipt, recorded as cash" — no reference required.
    - `payment_mode` = `virtual`: require `payment_reference` + gateway `payment_provider` (paystack/stripe/momo).
  - Submit to `/admin/subscriptions/subscribe/`; surface field errors from the un-wrapped shape.
- Success → toast + navigate to `/admin/subscriptions/<new-id>`.

**C. Payments ledger (`/admin/payments`)**.
- Load `/admin/payments/` with filters `status`, `payment_mode`, `provider`, `school_name`, `min_amount`/`max_amount`, `created_from/to`.
- Table: school, tier, amount+currency, `provider`, `payment_mode` (+label), `status` badge, `payment_reference`, date, `recorded_by_name`.
- Paginated.

**D. (If not already built) Package & feature admin** — `/packages/`, `/packages/<id>/` (GET/POST/PATCH), activate/deactivate endpooints, and `/features/` equivalents. Follow the existing list/form patterns; package `features`/`limits` are write payloads of `[{code, enabled}]` and `[{key, name, value, description}]` and come back expanded on GET.

## 5. UX / state requirements

- Every screen: explicit **loading**, **empty**, and **error** states — never a blank page.
- Use the app's existing date/time formatters and toast system.
- Map subscription statuses to the brand's existing badge colors (e.g., grace=amber, locked/expired=red, trial/active=green, pending=blue).
- Format money with `currency` (GHS default) and 2 decimals; `price`/`amount` arrive as decimal strings.
- After any create/update, refresh the relevant list/current view (avoid stale `is_current`/status).
- Keep filters in URL query params so states survive refresh/share (optional but preferred).

## 6. Definition of done

- All endpoints above are consumed only through the single HTTP helper; token refresh works on 401.
- Pricing page renders only active+public tiers with accurate student ranges and features.
- A trial-eligible school can subscribe with one click.
- A returning (paid) school can complete the initiate → gateway → verify → activate flow; simulated provider works end-to-end in dev.
- Superadmin can filter all subscriptions/payments, open a subscription detail, and subscribe any school via trial/cash/virtual paths with correct inline validation.
- No console errors; pages handle loading/empty/error; TypeScript compiles; project lint passes.
- Hand the finished work back as a concise summary listing each page, the endpoints used per page, and anything you couldn't build because the API did not support it.