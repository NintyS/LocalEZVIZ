/** PL: Lekki test kontraktu źródła karty. EN: Lightweight card source-contract test. */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../../custom_components/ptz_proxy/frontend/ptz-camera-card.js", import.meta.url),
  "utf8",
);

// PL: Źródło musi zawierać wszystkie mechanizmy bezpieczeństwa ruchu.
// EN: The source must contain every movement safety mechanism.
for (const required of [
  "pointerdown",
  "pointerup",
  "pointercancel",
  "visibilitychange",
  '"blur"',
  '"stop", "all"',
  "event.repeat",
  "setPointerCapture",
]) {
  assert.ok(source.includes(required), `Missing frontend safety mechanism: ${required}`);
}
// PL: Frontend nie może zawierać pól sekretów ani własnego POST do serwera.
// EN: The frontend must not contain secret fields or direct server POST calls.
for (const forbidden of ["api_token", "camera_ip", '"password"', "fetch("]) {
  assert.equal(source.includes(forbidden), false, `Forbidden frontend value: ${forbidden}`);
}
