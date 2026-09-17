# Coupons and promotions

The API is available at `/api/coupons/` and the existing versioned prefix
`/api/v1/coupons/`. It includes list/create, retrieve/PUT/PATCH/delete,
`validate/` (POST), and `stats/` (GET). Management, including stats and read-only
requests, requires **both** `billing.view` and `billing.manage` platform
permissions. Validation requires an authenticated school account; an expired
school can validate a code while checking out a renewal.

`Package` is this application's Plan model; `accounts.User` represents the
platform actor in `created_by`. Coupon codes are normalized to uppercase before
saving. List responses use `{success: true, data: {count, results}}`; individual
responses use `{success: true, data: {...}}`. Checkout policy errors use
`{success: false, error: "..."}` with HTTP 400. Invalid fields use the existing
platform error envelope with an `errors` field. Redeemed coupons cannot be
deleted (409); payment-intent references also prevent deletion for auditability.

List filters: `search`, `status`, `discount_type`, `target`, `page`, `page_size`.
The default page size is 20, capped at 100. Status responses, filtering and active
stats all use effective expiry (past expiry date or exhausted usage limit),
even if the stored status is disabled. A coupon remains valid throughout its
expiry date. New/changed expiry dates must be later than today. An unrelated
PATCH may modify an already-expired coupon without changing its expiry date.

## Checkout

Add `coupon_code` to the existing payment-initiation request:

```json
{"plan_id": "<package UUID>", "coupon_code": "WELCOME20", "provider": "paystack"}
```

The server computes the discount, caps it at the charge amount, rounds to two
decimal places, and persists the coupon and actual discount on the payment
intent. Discounts cover the quoted total, including an optional setup fee.
Coupons currently apply only to GHS plans so aggregate financial stats have a
single currency. Client-provided discount amounts are never accepted. Fully discounted intents
return an empty `payment_url` and a reference: call the existing subscribe
endpoint with that reference directly. The server skips the gateway only for a
persisted zero-amount coupon intent, then revalidates and redeems normally.

Successful payment completion, including the webhook path, locks and reloads
the payment, revalidates the coupon, and atomically creates the subscription,
redemption and database-level usage increment. Retried completion returns the
same subscription. Each subscription can have only one redemption. The final
allowed redemption marks the stored coupon status expired. Invalid coupons
roll back activation and redemption. Validation/intent creation consume no uses.

`once` allows one redeemed payment per school. `recurring` and `forever` carry
forward from the current subscription to subsequent payment initiations when
no new code is supplied. Both are unbounded because the supplied contract has
no recurring-cycle count. Every renewal revalidates status, expiry, plan and
usage limit; a no-longer-valid inherited coupon returns an error rather than
silently charging the undiscounted amount. A different explicit code replaces
it. There is no automatic gateway renewal scheduler in this feature.

An intent does not reserve a use. A coupon can expire or become exhausted
between initiation and payment confirmation. In that case activation fails
atomically; a gateway charge that already settled requires payment support to
reconcile/refund. No external gateway refund is attempted automatically.

## Dashboard and operations

`revenue_impact` is the negative sum of recorded redemption discounts in GHS.
`total_claims` sums usage counts; `active_codes` uses effective status.
`conversion_lift_percent` is **null (placeholder)**: no conversion attribution
analytics exist, so no fabricated lift is returned.

Apply the schema using `python manage.py migrate`. Run
`python manage.py expire_coupons` daily with your deployment scheduler (for
example, at 00:05 in the application's timezone). This command updates only
active coupons with an expiry date earlier than today; API validity never
relies on the scheduler running. Creation, updates (including disabling) and
deletion write the existing platform AuditLog.

Run `python manage.py test subscriptions.test_coupons subscriptions.tests
integrations.tests --settings=skuumate.settings.testing`. Row-lock concurrency
tests skip on SQLite. Run them against MySQL using `skuumate.settings.ci` and
the isolated test database credentials; CI already uses that engine.
