# Operator dashboard

The admin is the operator console at `http://127.0.0.1:4600/`. Files live in `apps/backend/auth/console/`. ParkPe (`http://127.0.0.1:4310/`) and PaySwap (`http://127.0.0.1:4500/`) are the product apps. They are not the admin.

A customer session and a retailer session do not open this desk. The check is in `apps/backend/auth/server.py`, on a full admin session whose `Origin` is this console. Hiding a button in ParkPe or PaySwap is not the check.

## Console UI contract

The console is one product. Every current and future admin screen in `apps/backend/auth/console/` uses the control-desk system in `console.css`; ParkPe and PaySwap product pages do not import it.

- Use the existing canvas, surface, line, ink, muted, accent, status, and spacing tokens. Do not add a product-specific palette, font, shadow, or arbitrary card radius.
- A new room uses `room`, `room-head`, an eyebrow, a plain-language title, a short scope statement, then `card`-based content. Use `room-status` only for a meaningful state such as read-only or live checks.
- Use `panel-head` for a card title and one-sentence explanation. Use `rows` for server-backed lists, `activity` for audit tables, `service-grid` or `report-grid` for navigation/summary cards, and `empty-state` when there is no configured or stored data.
- Navigation must open a real room (`data-room`) or a real contextual action. Do not leave a new navigation item as a toast-only placeholder. A quick action uses `data-jump` and lands in the same room.
- UI copy distinguishes available data from planned capability. If no server-backed flow exists, say that clearly and use an empty state; never invent balances, settlement rows, outlets, or service health.
- Preserve keyboard focus, visible focus styles, responsive breakpoints, and status text alongside color. On narrow screens, cards stack before their content becomes cramped.
- New integration UI reads from a protected desk route, uses the shared `call` helper, renders loading/error/empty states without raw errors or sensitive values, and links to Logs when that is the appropriate source of detail.
- Keep protected values out of the DOM: no passwords, tokens, codes, raw bodies, provider secrets, PAN, Aadhaar, card, or bank data. The server remains the authorization boundary.

Before adding a console screen, check this section, `console.css`, and the relevant route contract together. Update the contract, handler, UI, and tests in the same change when a new data path is needed.

## Who runs it

| Role | App | How the account opens |
| --- | --- | --- |
| `admin` | This console | The first admin is the super admin, created once on this console. Every later admin is a sub-admin added from the desk by the super admin. |
| `customer` | ParkPe | An admin starts signup from the desk. The account exists only after the email code and the SMS code both match. |
| `retailer` | PaySwap | Same email and SMS check, then DigiLocker Aadhaar consent, then PAN. The account exists only after PAN passes. |

Nobody signs themselves up on ParkPe, PaySwap, or a second public admin form. `POST /api/auth/register` stays closed after the first admin. A ParkPe or PaySwap call to signup is refused with `An admin creates this account.`

One email can be both a customer and a retailer. It cannot also be an admin. The password and the authenticator stay on that person. The session stores the door they entered.

## Account hub model

The desk manages one person record, not separate customer and retailer people. The store `user_id` is the canonical identity. The console displays a stable, role-scoped reference derived from it: `CU00…` for a ParkPe customer and `R00…` for a PaySwap retailer. A pending signup is an application, not an account, and uses an application reference until its required checks complete.

- **Account Hub** is the one top-level account-management destination. It has Directory and Verification views, rather than two unrelated navigation pages. It is the operational source of truth for access state, sessions, product activity, and the roles a person holds.
- **Verification** is the role-specific Account Hub view. It shows the same account/application reference and opens the same account profile after completion.
- A person can gain the other product role through its own onboarding flow; do not create a second user merely because the person becomes both a customer and a retailer.
- Customer verification requires email and SMS. Retailer verification additionally requires DigiLocker and PAN. These checks belong to that role, while the password and authenticator remain on the one person record.
- Show the role-scoped account ID wherever an operator identifies, verifies, or reviews activity for a customer or retailer: the directory, account file, verification queue/profile, ParkPe/PaySwap activity, and money activity. Do not use it for admin-only records.
- Any new account, partner, or verification feature must link by `user_id`, show the role-specific reference, and lead back to the Account Hub instead of creating an unconnected directory or onboarding screen.

## What the desk does today

Signed-in home, from `GET /api/auth/desk`:

- Email, role, and whether this session is the super admin.
- Counts of customer, retailer, and admin memberships.
- The last 8 auth events: event name, time, email. No IP, no token, no payload.
- Whether admin signup is still open. The note does not claim the authenticator is on.

Users, from `GET /api/auth/desk/people`:

- One list for customers, retailers, and admins. Filters are All, Customers, Retailers, and Admins.
- Email, roles, authenticator on or off, sign-in open or closed, and a super-admin mark on the first admin.
- Close or open sign-in (`POST /api/auth/desk/people/sign-in`). Closing revokes that person's sessions. An admin cannot close their own sign-in, and cannot close the last open admin. A sub-admin cannot change another admin's sign-in.
- Remove one role (`POST /api/auth/desk/people/role`). An admin cannot remove their own admin role, and cannot remove the last open admin. Only the super admin can remove an admin role.
- Set a password (`POST /api/auth/desk/people/password`). The new password is checked by `password_problem`. Another person's sessions are revoked. The acting admin keeps their own session.
- Reset the authenticator (`POST /api/auth/desk/people/authenticator`). The secret and backup codes are cleared and that person's sessions are revoked. Resetting your own authenticator returns you to the sign-in gate.
- Open sessions (`GET /api/auth/desk/people/sessions?email=`). Each row is id, role, scope, expiry, and created time. No token hash.
- A file (`GET /api/auth/desk/users/file?email=`). It shows the account, verification checks, the **KYC record** on `account_profiles` (full mobile, PAN, name on PAN, PAN registry name from Cashfree, DigiLocker verification id, masked list fields), and open sessions. A customer file also lists that email's ParkPe session starts. A retailer file lists that email's PaySwap voucher orders. Parking, FASTag, challan, bills, vouchers, carpool, support, cards, recharge, wallet, transactions, AEPS, and DMT say there is no stored row. The Aadhaar number is not stored; DigiLocker session id is.

Add account is still on this room. Customer and retailer creation goes through `POST /api/auth/signup/start`, `/contact`, and for a retailer `/aadhaar`, `/aadhaar/confirm`, `/pan`. A new admin is `POST /api/auth/desk/accounts`, and only the super admin can call it. All of those require the admin session and the console origin. The DigiLocker URL is shown on the form so it can be copied, and the console also opens it. When the account opens, `account_profiles` keeps the role, mobile last four, and the pass flags. The signup intent is still deleted.

Verification, from `GET /api/auth/desk/signups`:

- Email, mobile last four, role, which checks passed, and whether the intent is still open. The signup id is included so Continue, Cancel, and Resend can name that intent.
- Resend (`POST /api/auth/signup/resend`) only before both contact checks pass. New codes are delivered. The response does not contain them.
- Cancel (`POST /api/auth/signup/cancel`) deletes the intent.
- Continue returns to the add-account step that is still open.

Processes, from `GET /api/auth/desk/processes`:

- Auth on 4600 is up, because this request reached it. ParkPe 4310 and PaySwap 4500 are a short TCP check. The API is up only when `GET http://127.0.0.1:4610/api/v1/health/` returns 200. Each row has a URL the console can open. The room does not embed the other apps.

API & Services, from `GET /api/auth/desk/services`:

- Lists Kaleyra SMS OTP, Email OTP, Cashfree Secure ID, the Shared Django API (`/api/v1/`), Mobikwik BBPS (`integrations/bbps.py`), and the local Parking stub with configuration or up/down state, safe route names, and the latest observed call without credentials or secrets.

Product rooms stay on this origin. The browser does not call port 4610, because the auth cookie is SameSite=Lax and would not be sent on that cross-origin fetch. `apps/backend/auth/server.py` copies the cookie onto a server-side call to `HUB_API_ORIGIN` (default `http://127.0.0.1:4610`). If that process is down, the desk answers 503.

- ParkPe: `GET /api/auth/desk/parkpe` reads done rows of `POST /api/v1/parkpe/sessions/initiate`. `?email=` limits that list to one customer. `POST /api/auth/desk/parkpe/close` marks one stored session `closed` and logs `parkpe.session.close`. FASTag, challan, and bills are not rows.
- PaySwap: `GET /api/auth/desk/payswap` reads done rows of `POST /api/v1/payswap/vouchers/order`. `?email=` limits that list to one retailer. The order has no outlet field. AEPS and DMT are not submitted from here.

A room does not show rows the server does not have.

## Rooms

The desk is one console. Each room reads one store. It does not import the other app's screens.

### Home

Shows membership counts and the latest auth events. This is the landing page after the authenticator matches.

### Users

Each row is email, roles, whether the authenticator is on, whether the account can sign in, and whether that admin is the super admin. The super admin can add another admin and can remove an admin role. A sub-admin can manage customers and retailers. The row does not show the password, the authenticator secret, backup codes, or a code from email or SMS.

Opening a row shows that person's file. A customer file has the ParkPe sections. A retailer file has the PaySwap sections. An admin file has neither. A person with both product roles sees both groups.

### ParkPe

ParkPe screens, from `apps/parkpe/js/dashboard.js`: bill payments, ParkPe voucher, brand voucher, Connect QR, FASTag, pay challan, CoPilot, transaction history, ParkPe Connect, parking desk, support, settings, profile, notifications.

Stored ParkPe work today is one route: `POST /api/v1/parkpe/sessions/initiate` (`apps/backend/api/v1/routes/parkpe.py`, `domain/parkpe/sessions.py`). It requires a customer session and `X-App-Context: parkpe`. The same key and body return the stored result. A different body with that key conflicts (`apps/backend/core/idempotency.py`).

`domain/parkpe/parking.py` can hold a bay, and it is not mounted on `/api/v1`. FASTag, challan, carpool, bills, vouchers, and support on the ParkPe screen are local screens. They are not rows an admin can open.

The ParkPe room shows the stored session: who, site, bay, vehicle, state, reference. The admin can mark that stored session closed. The admin does not type a card number or start a charge from this desk.

### PaySwap

PaySwap counter areas, from `apps/payswap/js/services.js`: vouchers, cards, bills, recharge, wallet, transactions. AEPS and DMT are on that counter as a retailer preview. They are not a live rail and they do not get an admin action that submits them.

Stored PaySwap work today includes brand vouchers (`POST /api/v1/payswap/vouchers/order`, `domain/payswap/vouchers.py`) and Mobikwik BBPS (`GET /api/v1/payswap/bbps/operators`, `POST /api/v1/payswap/bbps/fetch-bill`, `POST /api/v1/payswap/bbps/pay`, `GET /api/v1/payswap/bbps/status`, `domain/payswap/bbps.py`). Both require a retailer session and `X-App-Context: payswap`, and mutations share the idempotency rule. Cards, the transaction list, recharge, and wallet are local screens.

The PaySwap room shows the stored voucher order: retailer, brand, amount, state, and reference. There is no outlet on that row. AEPS and DMT stay off this list until a separate decision turns the preview into a stored flow. This document does not start that.

### Money

One list for both apps, fed by `HubAction` in `apps/backend/models/models.py` (`apps/backend/data/hub.sqlite`). `log_action` writes the redacted line. A line inside `transaction.atomic` is kept only after that transaction commits.

Each line is request id, idempotency key when the caller sent one, app (`parkpe` or `payswap`), actor, role, action, target, outcome, status, duration. The desk does not return the error reason.

Auth events do not move into this list. They stay in `apps/backend/auth/store.py` `audit`.

### Verification

Signup delivery is email through the PHP mailer and SMS through Kaleyra. Retailer Aadhaar is Cashfree DigiLocker consent. PAN is Cashfree `POST /verification/pan`. The code is `apps/backend/auth/verify.py`. If those are not configured, signup fails closed and no account is created.

The room shows, for a signup the admin started: email, mobile (last four digits), role, which checks passed, and whether the intent is open. It does not show the code, the Aadhaar number, the PAN, the DigiLocker document, or the provider secret. The store keeps a verification reference and the pass/fail flags. It does not keep the document.

### Processes

The hub is three processes. Django on 4610 is the fourth, and it is started on its own.

| Process | Port | Start | What the room shows |
| --- | --- | --- | --- |
| Auth and this console | 4600 | `make hub` or `python3 apps/backend/run.py` | Up, with a link to this console. `GET /api/auth/setup` answers whether the first admin can still be created. |
| ParkPe | 4310 | `make parkpe` | Up or down. The room links to the app. It does not embed it. |
| PaySwap | 4500 | `make payswap` | Up or down. Same rule. |
| Django `/api/v1/` | 4610 | `make api` or `python3 apps/backend/manage.py runserver --noreload 127.0.0.1:4610` | Up only when `GET /api/v1/health/` returns 200. The room links to that health URL. |

`python3 dev.py` starts auth, ParkPe, and PaySwap. It does not start Django.

## What a row is allowed to contain

Email, role, event name, time, app context, action, target id, amount, state, reference, status, duration.

## What a row never contains

Passwords, session cookies, refresh tokens, email codes, SMS codes, authenticator secrets, backup codes, Aadhaar numbers, PAN, card numbers, OTPs, raw request bodies, and the Kaleyra, Cashfree, or mail secrets. Those values stay in the environment named in `apps/backend/auth/server.py` and `apps/backend/auth/verify.py`. They are not copied into this document, the console, or a test.

The recent-auth list does not include the IP. The IP stays in the auth audit table for the server, not on the desk.

## How the admin manages the project

1. Sign in on `http://127.0.0.1:4600/` and finish the authenticator. Without that, the desk routes answer 401 or 403.
2. Add a person from Add account. Customer and retailer wait for the checks above. Only the super admin can add another admin. That admin gets email and password, then enrolls an authenticator on first sign-in.
3. Read Home for counts and the last auth events.
4. Read ParkPe, PaySwap, and Money for stored `/api/v1` rows. An empty room means that write has not happened. The desk does not invent parking sessions, bills, AEPS, or DMT to look complete.
5. Leave a product area alone while it is still a screen.

A new room is a small change, not a second admin app:

- The path goes in `apps/backend/auth/contract.py` if it is an auth or desk route, or in `apps/backend/api/v1/urls.py` if it is product data.
- The handler checks the admin session in `apps/backend/auth/server.py` for desk routes. Product reads on port 4610 check the admin cookie in `apps/backend/api/v1/routes/desk.py`. The console reaches those reads through the auth server proxy, not from the browser.
- A product write logs through `apps/backend/core/actions.py` in the same change. An auth event stays in `store.audit`.
- The console section is `apps/backend/auth/console/`. ParkPe and PaySwap do not get a copy of this screen.
- `python3 apps/backend/tests/test_auth.py` covers a desk or auth route. `python apps/backend/manage.py test tests` covers a Django route.

## Out of this desk

- Live bill pay, AEPS, and DMT. The PaySwap counter may preview them. The desk does not submit them.
- A button in the browser as the only lock. The server refuses the call.
- A second database pasted into the repo. `apps/backend/data/` stays local and ignored.
