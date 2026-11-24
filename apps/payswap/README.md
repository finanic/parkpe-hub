# apps/payswap

PaySwap retailer app. `make payswap` runs `serve.py` on port 4500 and serves this folder. The counter UI is `js/app.js` and `js/services.js`. Sign-in is `js/session.js` (`role` `retailer`).

| Folder | Responsibility |
| --- | --- |
| `core/` | Shell, navigation, and the retailer session bootstrap. |
| `features/cards` | Card products. No separate screen in the running app yet. |
| `features/vouchers` | Vouchers. No separate screen in the running app yet. |
| `features/bbps` | Bill collection. Closest running screen: `bills` in `apps/payswap/js/services.js`. |
| `features/transactions` | Counter history. Running screen: `transactions` in `apps/payswap/js/services.js`. |
| `shared/` | Helpers used by more than one PaySwap feature. Not for ParkPe. |

The running counter also has AEPS, DMT, recharge, and wallet views in `apps/payswap/js/services.js`. Those stay there until a feature is moved on purpose.

ParkPe code stays in `apps/parkpe`. Do not import `apps/parkpe/js/screens.js`.

API calls go through `packages/sdk-client` with `X-App-Context: payswap`. Shared DTOs come from `packages/contracts`. Tokens come from `packages/ui-tokens`. PaySwap routes and domain rules live in `apps/backend` (`domain/payswap`, `api/v1/routes`). The auth server that is actually listening is still `apps/backend/auth/server.py`.
