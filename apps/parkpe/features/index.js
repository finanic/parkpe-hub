/* ParkPe features. Each folder owns one product area.
   qr-connect calls packages/sdk-client (X-App-Context: parkpe).
   Parking, FASTag, and carpool are still local screens.
   Do not import apps/payswap/features.
*/

import { parking } from "./parking/index.js";
import { fastag } from "./fastag/index.js";
import { carpool } from "./carpool/index.js";
import { initiateSession, qrConnect } from "./qr-connect/index.js";

export { parking, fastag, carpool, qrConnect, initiateSession };

export const features = Object.freeze({ parking, fastag, carpool, qrConnect, initiateSession });
