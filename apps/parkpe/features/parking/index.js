/* Parking desk for apps/parkpe.

   Live UI: parkingScreen in apps/parkpe/js/screens.js, served by apps/parkpe/serve.py.
   Future API: apps/backend/domain/parkpe, reached with X-App-Context: parkpe
   (packages/sdk-client). Payswap bill-pay stays in apps/payswap/features/bbps.
*/

export const parking = Object.freeze({ id: "parking" });
