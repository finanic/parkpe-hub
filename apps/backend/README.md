# apps/backend

One API folder for ParkPe and PaySwap. `make hub` runs `run.py`, the auth server on port 4600 (`auth/`). Django and Django REST Framework serve `/api/v1/` when you start `manage.py` on port 4610.

```
python apps/backend/manage.py check
python apps/backend/manage.py test tests
python apps/backend/manage.py runserver 127.0.0.1:4610
```

`/api/v1` calls `GET /api/auth/me` on port 4600 (`AUTH_BASE_URL`, default `http://127.0.0.1:4600`) with the `auth_access` cookie. That server has to be up for a real sign-in. Tests stub that call.

| Folder | Responsibility |
| --- | --- |
| `config/` | Django settings, `/api/v1/` mount, CORS for ports 4310, 4500, and 4610. |
| `api/v1/routes` | `health/`, `parkpe/parking/holds/`, `payswap/bbps/payments/`. ParkPe and PaySwap handlers stay in separate modules. |
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
