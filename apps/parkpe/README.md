# apps/parkpe

ParkPe customer app. `make parkpe` runs `serve.py` on port 4310 and serves this folder. Screens live in `js/screens.js`.

| Folder | Responsibility |
| --- | --- |
| `core/` | Shell, navigation, and the ParkPe session bootstrap. |
| `features/parking` | Parking desk. Current screen: `parkingScreen` in `apps/parkpe/js/screens.js`. |
| `features/fastag` | FASTag recharge. Current screen: `fastagScreen`. Issuer art stays in `apps/parkpe/assets/img/fastag-issuers/`. |
| `features/carpool` | Carpool. Current screen: `carpoolScreen`. |
| `features/qr-connect` | Connect QR. Current screen: `qrScreen`. |
| `shared/` | Helpers used by more than one ParkPe feature. Not for PaySwap. |

PaySwap code stays in `apps/payswap`. This app does not load `apps/payswap/js/session.js`.

API calls go through `packages/sdk-client` with `X-App-Context: parkpe`. Shared DTOs, enums, and error codes come from `packages/contracts`. Visual tokens come from `packages/ui-tokens`. ParkPe routes and domain rules live in `apps/backend` (`domain/parkpe`, `api/v1/routes`). The auth server that is actually listening is still `apps/backend/auth/server.py` (`role` `customer`).
