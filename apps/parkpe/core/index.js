/* ParkPe shell: navigation and session bootstrap.

   When a session client is added, it sends role "customer" (packages/contracts),
   matching apps/backend/auth/contract.py ROLE_CUSTOMER. PaySwap's retailer client
   stays in apps/payswap/js/session.js and must not be imported here.
   App context for apps/backend/api/v1/deps.py is parkpe, via apps/parkpe/js/hub.js.
*/

export const core = Object.freeze({ app: "parkpe" });
