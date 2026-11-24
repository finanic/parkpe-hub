# packages

Shared by `apps/parkpe`, `apps/payswap`, and `apps/backend`. App-specific code does not go here.

| Package | Responsibility |
| --- | --- |
| `contracts` | DTOs, enums, and error codes. One definition for a field. `apps/backend/schemas` matches it. The names that already ship (paths, cookies, roles, `X-Auth-Request`) are still `apps/backend/auth/contract.py`. |
| `sdk-client` | HTTP client both frontends use. Sets `X-App-Context` to `parkpe` or `payswap`, which `apps/backend/api/v1/deps.py` checks. The client that runs today is `apps/payswap/js/session.js` against `apps/backend/auth/server.py` on port 4600. ParkPe (`apps/parkpe/`) has no auth client yet. |
| `ui-tokens` | Shared design tokens. ParkPe color is still `apps/parkpe/css/dashboard.css`. PaySwap color is still `apps/payswap/css/app.css`. Those palettes are different and are not merged here. |

These files are not loaded by `apps/parkpe/serve.py`, `apps/payswap/serve.py`, or `apps/backend/run.py`.
