/* ParkPe features. Each folder owns one product area and calls
   apps/backend/domain/parkpe through packages/sdk-client.
   Do not import apps/payswap/features.
*/

import { parking } from "./parking/index.js";
import { fastag } from "./fastag/index.js";
import { carpool } from "./carpool/index.js";
import { qrConnect } from "./qr-connect/index.js";

export { parking, fastag, carpool, qrConnect };

export const features = Object.freeze({ parking, fastag, carpool, qrConnect });
