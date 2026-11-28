# apps/backend

One API folder for ParkPe and PaySwap. `make hub` runs `run.py`, the auth server on port 4600 (`auth/`). `make api` runs Django `/api/v1/` on port 4610.

```
python apps/backend/manage.py check
python apps/backend/manage.py test tests
make api
```

`/api/v1` calls `GET /api/auth/me` on port 4600 (`AUTH_BASE_URL`, default `http://127.0.0.1:4600`) with the `auth_access` cookie. That server has to be up for a real sign-in. Tests stub that call.

| Folder | Responsibility |
| --- | --- |
| `config/` | Django settings, `/api/v1/` mount, CORS for ports 4310, 4500, and 4610. |
| `api/v1/routes` | `health/`, `parkpe/sessions/initiate`, `payswap/vouchers/order`. ParkPe and PaySwap handlers stay in separate modules. |
| `api/v1/deps.py` | Reads `X-App-Context` from `packages/sdk-client` and rejects the wrong app. |
| `core/security.py` | Request scope checks for `/api/v1`. Password and token primitives stay in `auth/security.py`. |
| `core/idempotency.py` | Same `Idempotency-Key` returns the stored money-movement result and does not post twice. |
| `domain/common` | Rules both apps share. No ParkPe screen copy and no PaySwap counter copy. |
| `domain/parkpe` | Parking, FASTag, carpool, QR. Callers: `apps/parkpe/features/*`. |
| `domain/payswap` | Cards, vouchers, BBPS, transactions. Callers: `apps/payswap/features/*`. |
| `models` | Persistence shapes. The live database is `apps/backend/auth/store.py` (`apps/backend/data/auth.sqlite`, gitignored). |
| `schemas` | Request and response bodies. Field names match `packages/contracts`. |
| `integrations` | Outbound calls (issuers, billers). Apps do not call those hosts themselves. |
| `tests` | Tests for this package. The suite that runs today is `apps/backend/tests/test_auth.py`. |

`domain/parkpe` does not import `domain/payswap`. A ParkPe caller (`customer`, context `parkpe`) does not enter a PaySwap use case, and the reverse. Hiding a button in `apps/parkpe` or `apps/payswap` is not the check.

## PayU troubleshooting

Hosted Checkout lives in `integrations/payu.py` and `domain/payswap/payu_checkout.py`. Routes: `POST /api/payu/initiate`, `POST /api/payu/success`, `POST /api/payu/failure`, `GET /api/payu/verify/<order_id>`.

Set in `apps/backend/.env` (never commit): `PAYU_MERCHANT_KEY`, `PAYU_MERCHANT_SALT` (Salt-32), optional `PAYU_MERCHANT_SALT_V2` (Salt-256 for dual), `PAYU_HASH_MODE` (`v1` or `dual`; empty auto-dual when SALT_V2 is set), `PAYU_ENV=test|production`, `APP_BASE_URL=http://127.0.0.1:4610`. Admin default policy `pg_provider` is `cashfree` | `payu` | `both`.

| Symptom | Check |
| --- | --- |
| Invalid / incorrectly calculated hash | Key + Salt-32 must be the pair from the same PayU env; amount `x.xx`; udf pipes. If PayU shows `{"v1","v2"}`, set Salt-256 as `PAYU_MERCHANT_SALT_V2` and use dual mode |
| Duplicate txnid | Each attempt gets a new txnid from initiate |
| surl/furl never hits | `APP_BASE_URL` must reach Django :4610; callbacks are CSRF-exempt form POSTs |
| Order stuck pending | `GET /api/payu/verify/<order_id>` or Verify on the counter |
| Works in test, fails in prod | Switch `PAYU_ENV` and credentials together |

Never log key, salt, hash inputs, or raw callback bodies with PII.
