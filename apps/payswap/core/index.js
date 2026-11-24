/* PaySwap shell: navigation and retailer session bootstrap.

   Live client: apps/payswap/js/session.js, role "retailer"
   (packages/contracts, apps/backend/auth/contract.py ROLE_RETAILER).
   ParkPe must not load that file, and this shell must not load apps/parkpe/js.
   App context for apps/backend/api/v1/deps.py is payswap, via packages/sdk-client.
*/

export const core = Object.freeze({ app: "payswap" });
