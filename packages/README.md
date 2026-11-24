# packages

Shared by `apps/parkpe`, `apps/payswap`, and `apps/backend`. App-specific code does not go here.

| Package | Responsibility |
| --- | --- |
| `contracts` | DTOs, enums, and error codes. One definition for a field. `apps/backend/schemas` matches it. The names that already ship (paths, cookies, roles, `X-Auth-Request`) are still `apps/backend/auth/contract.py`. |
| `sdk-client` | HTTP client both frontends use for Django on port 4610. Sets `X-App-Context` to `parkpe` or `payswap`, which `apps/backend/api/v1/deps.py` checks, and sends `Idempotency-Key` on POST, PUT, and PATCH. `apps/payswap/js/session.js` still talks to `apps/backend/auth/server.py` on port 4600. |
| `ui-tokens` | Shared design tokens. ParkPe color is still `apps/parkpe/css/dashboard.css`. PaySwap color is still `apps/payswap/css/app.css`. Those palettes are different and are not merged here. |

`apps/parkpe/packages` and `apps/payswap/packages` are symlinks here, so the static servers can load this client. `apps/backend/run.py` does not.
