# Operator dashboard

The admin is the operator console at `http://127.0.0.1:4600/`. Files live in `apps/backend/auth/console/`. ParkPe (`http://127.0.0.1:4310/`) and PaySwap (`http://127.0.0.1:4500/`) are the product apps. They are not the admin.

A customer session and a retailer session do not open this desk. The check is in `apps/backend/auth/server.py`, on a full operator session whose `Origin` is this console. Hiding a button in ParkPe or PaySwap is not the check.

## Who runs it

| Role | App | How the account opens |
| --- | --- | --- |
| `operator` | This console | The first operator is created once on this console. Every later operator is added from the desk. |
| `customer` | ParkPe | An operator starts signup from the desk. The account exists only after the email code and the SMS code both match. |
| `retailer` | PaySwap | Same email and SMS check, then DigiLocker Aadhaar consent, then PAN. The account exists only after PAN passes. |

Nobody signs themselves up on ParkPe, PaySwap, or a second public operator form. `POST /api/auth/register` stays closed after the first operator. A ParkPe or PaySwap call to signup is refused with `An operator creates this account.`

One email can be both a customer and a retailer. It cannot also be an operator. The password and the authenticator stay on that person. The session stores the door they entered.

## What the desk does today

Signed-in home, from `GET /api/auth/desk`:

- Email and role of the operator.
- Counts of customer, retailer, and operator memberships.
- The last 8 auth events: event name, time, email. No IP, no token, no payload.
- Add account: customer, retailer, or operator.

Customer and retailer creation still goes through `POST /api/auth/signup/start`, `/contact`, and for a retailer `/aadhaar`, `/aadhaar/confirm`, `/pan`. A new operator is `POST /api/auth/desk/accounts`. All of those require the operator session and the console origin.

That is the whole admin that is stored and enforced today. The rest of this document is the desk those rooms grow into. A room does not show rows the server does not have.

## Rooms

The desk is one console with these rooms. Each room reads one store. It does not import the other app's screens.

### Home

Already open.

Shows membership counts and the latest auth events. This is the landing page after the authenticator matches.

### People

Partly open. Add account works. A list of people does not, because no list route exists yet.

When the list exists, each row is email, roles, whether the authenticator is on, and whether the account can sign in. The operator can add a role the person does not have yet, and can turn sign-in off. Turning sign-in off revokes that person's sessions. It does not delete the audit row.

The row does not show the password, the authenticator secret, backup codes, or a code from email or SMS.

### ParkPe

ParkPe screens, from `apps/parkpe/js/dashboard.js`: bill payments, ParkPe voucher, brand voucher, Connect QR, FASTag, pay challan, CoPilot, transaction history, ParkPe Connect, parking desk, support, settings, profile, notifications.

Stored ParkPe work today is one route: `POST /api/v1/parkpe/sessions/initiate` (`apps/backend/api/v1/routes/parkpe.py`, `domain/parkpe/sessions.py`). It requires a customer session and `X-App-Context: parkpe`. The same key and body return the stored result. A different body with that key conflicts (`apps/backend/core/idempotency.py`).

`domain/parkpe/parking.py` can hold a bay, and it is not mounted on `/api/v1`. FASTag, challan, carpool, bills, vouchers, and support on the ParkPe screen are local screens. They are not rows an operator can open.

The ParkPe room, once those writes are stored, shows the session or the order: who, vehicle or site, amount, state, reference, time. The operator can read it and can mark a stored session closed. The operator does not type a card number or start a charge from this desk.

### PaySwap

PaySwap counter areas, from `apps/payswap/js/services.js`: vouchers, cards, bills, recharge, wallet, transactions. AEPS and DMT are on that counter as a retailer preview. They are not a live rail and they do not get an admin action that submits them.

Stored PaySwap work today is one route: `POST /api/v1/payswap/vouchers/order` (`apps/backend/api/v1/routes/payswap.py`, `domain/payswap/vouchers.py`). It requires a retailer session and `X-App-Context: payswap`. Idempotency is the same rule as the ParkPe session route.

`domain/payswap/bbps.py` can record a collection, and it is not mounted. Cards, the transaction list, recharge, and wallet are local screens.

The PaySwap room, once those writes are stored, shows the outlet, the retailer, the kind of order, the amount, the state, and the reference. AEPS and DMT stay off this list until a separate decision turns the preview into a stored flow. This document does not start that.

### Money

One list for both apps, fed by `apps/backend/core/actions.py` and `IdempotencyRecord` in `apps/backend/models/models.py` (`apps/backend/data/hub.sqlite`).

Each line is request id, idempotency key when the caller sent one, app (`parkpe` or `payswap`), actor, role, action, target, outcome, status, duration. The same key replay shows the stored result. A conflict shows the conflict, not a second charge.

Auth events do not move into this list. They stay in `apps/backend/auth/store.py` `audit`.

### Verification

Signup delivery is email through the PHP mailer and SMS through Kaleyra. Retailer Aadhaar is Cashfree DigiLocker consent. PAN is Cashfree `POST /verification/pan`. The code is `apps/backend/auth/verify.py`. If those are not configured, signup fails closed and no account is created.

The room shows, for a signup the operator started: email, mobile (last four digits), role, which checks passed, and whether delivery failed. It does not show the code, the Aadhaar number, the PAN, the DigiLocker document, or the provider secret. The store keeps a verification reference and the pass/fail flags. It does not keep the document.

### Processes

The hub is three processes. Django on 4610 is the fourth, and it is started on its own.

| Process | Port | Start | What the room shows |
| --- | --- | --- | --- |
| Auth and this console | 4600 | `make hub` or `python3 apps/backend/run.py` | Up or down. `GET /api/auth/setup` answers whether the first operator can still be created. |
| ParkPe | 4310 | `make parkpe` | Up or down. The room links to the app. It does not embed it. |
| PaySwap | 4500 | `make payswap` | Up or down. Same rule. |
| Django `/api/v1/` | 4610 | `python apps/backend/manage.py runserver 127.0.0.1:4610` | Up or down, plus `GET /api/v1/health/`. |

`python3 dev.py` starts auth, ParkPe, and PaySwap. It does not start Django.

## What a row is allowed to contain

Email, role, event name, time, app context, action, target id, amount, state, reference, status, duration.

## What a row never contains

Passwords, session cookies, refresh tokens, email codes, SMS codes, authenticator secrets, backup codes, Aadhaar numbers, PAN, card numbers, OTPs, raw request bodies, and the Kaleyra, Cashfree, or mail secrets. Those values stay in the environment named in `apps/backend/auth/server.py` and `apps/backend/auth/verify.py`. They are not copied into this document, the console, or a test.

The recent-auth list does not include the IP. The IP stays in the auth audit table for the server, not on the desk.

## How the operator manages the project

1. Sign in on `http://127.0.0.1:4600/` and finish the authenticator. Without that, the desk routes answer 401 or 403.
2. Add a person from Add account. Customer and retailer wait for the checks above. Operator gets email and password, then enrolls an authenticator on first sign-in.
3. Read Home for counts and the last auth events.
4. Read Money only after a `/api/v1` write has been logged. There is no money list route yet, so this room is not on the console.
5. Leave a product area alone while it is still a screen. The desk does not invent parking sessions, bills, AEPS, or DMT to look complete.

A new room is a small change, not a second admin app:

- The path goes in `apps/backend/auth/contract.py` if it is an auth or desk route, or in `apps/backend/api/v1/urls.py` if it is product data.
- The handler checks the operator session in `apps/backend/auth/server.py` for desk routes. Product reads on port 4610 check the operator through `GET /api/auth/me` the same way `apps/backend/api/v1/deps.py` already checks a customer or a retailer.
- A product write logs through `apps/backend/core/actions.py` in the same change. An auth event stays in `store.audit`.
- The console section is `apps/backend/auth/console/`. ParkPe and PaySwap do not get a copy of this screen.
- `python3 apps/backend/tests/test_auth.py` covers a desk or auth route. `python apps/backend/manage.py test tests` covers a Django route.

## Out of this desk

- Live bill pay, AEPS, and DMT. The PaySwap counter may preview them. The desk does not submit them.
- A button in the browser as the only lock. The server refuses the call.
- A second database pasted into the repo. `apps/backend/data/` stays local and ignored.
