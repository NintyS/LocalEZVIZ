# PTZ Proxy for Home Assistant

[Polski](README.md) | **English**

PTZ Proxy is a custom integration for Home Assistant Core **2026.7 or newer**. It connects Home Assistant to a local HTTP server that knows how to control physical cameras. Version `0.3.0` supports movement up, down, left and right, zooming in and out, and emergency stopping.

## What you get

- server configuration entirely through the UI;
- a `GET /health` check before the configuration is saved;
- any number of cameras represented as config subentries;
- a separate `camera` entity and device for every camera;
- a card with a circular D-pad and separate zoom buttons;
- the `ptz_proxy.move` action with entity permission checks;
- an automatically loaded `custom:ptz-camera-card` card;
- mouse, touchscreen, and keyboard control;
- Polish and English translations;
- diagnostics without tokens, passwords, or complete RTSP addresses.

## Architecture

```mermaid
flowchart LR
    U[Browser / HA application] -->|entity_id + action + direction| HA[Home Assistant backend]
    HA -->|camera credentials remain in the backend| S[Local PTZ server]
    S -->|vendor protocol| C[Camera]
    HA -. never .->|password or token| U
```

The card does not connect directly to the PTZ server. It invokes a standard Home Assistant entity action. The backend reads the private camera configuration and sends one `POST` request.

## Required server contract

### Health check

```http
GET {base_url}/health
Accept: application/json
Authorization: Bearer <api_token>  # only when the token is not empty
```

The server must respond with HTTP `200` and JSON:

```json
{
  "status": "ok"
}
```

The HCNet backend format is also accepted:

```json
{
  "ok": true,
  "backend": "hcnet",
  "connected_sessions": 0
}
```

The response may contain additional fields. A redirect, another HTTP status, invalid JSON, or the absence of both `"status": "ok"` and `"ok": true` prevents the configuration from being saved.

### PTZ control

```http
POST {base_url}/ptz
Content-Type: application/json
Accept: application/json
```

Example start request:

```json
{
  "ip": "192.168.1.50",
  "login": "admin",
  "password": "secret_password",
  "action": "start",
  "direction": "left"
}
```

Releasing a movement or zoom button sends `stop` with the same direction. Zoom uses `zoom_in` and `zoom_out`. An emergency stop sends `{"action":"stop","direction":"all", ...}`. Any `2xx` response, including an empty `204`, is treated as success. The integration does not retry commands.

> **Important safety requirement:** the PTZ server must stop the camera itself after 5–10 seconds of uninterrupted movement. A browser may fail to deliver `pointerup`, and a `stop` command may be lost when the network connection fails.

## Manual installation

1. Copy the complete `custom_components/ptz_proxy` directory into the Home Assistant configuration directory so that this file exists:

   ```text
   /config/custom_components/ptz_proxy/manifest.json
   ```

2. Restart Home Assistant.
3. Clear the browser cache only if the updated card does not appear. A normal first-time installation does not require it.

Do not add anything to `configuration.yaml` or the Lovelace resources. The backend serves and loads the card automatically.

## Installation through HACS

1. Open the HACS menu and select **Custom repositories**.
2. Paste `https://github.com/NintyS/LocalEZVIZ`.
3. Select the **Integration** category and add the repository.
4. Find **PTZ Proxy**, install it, and restart Home Assistant.

## Adding a server

1. Open **Settings → Devices & services**.
2. Select **Add integration** and search for **PTZ Proxy**.
3. Enter:

   | Field | Meaning | Example |
   |---|---|---|
   | Server name | Friendly config entry name | `Camera server` |
   | Server address | Base HTTP/HTTPS address without `/health` | `http://192.168.1.20:8080` |
   | API token | Optional Bearer token | leave empty when unused |
   | Verify TLS | Verify an HTTPS certificate | enabled |
   | Timeout | 1–30 seconds | `3` |

4. Submit the form. The integration calls `/health`. If validation fails, the form stays open and retains the entered values so that only the incorrect field needs to be fixed.

An address without a scheme receives `http://`. A trailing slash and an accidentally included `/health` path are removed. User information in the URL, query strings, fragments, and schemes other than HTTP/HTTPS are rejected.

## Adding or editing a camera

1. Open the newly created PTZ Proxy entry.
2. In its subentries section, add a **Camera**.
3. Enter a name, camera IP/DNS address, username, password, and RTSP address. RTSP is optional for PTZ control and is needed only to display video.
4. Repeat for every additional camera.

Every camera receives a random UUID. Changing its name or address does not change the entity identity. During reconfiguration, leaving the password empty preserves the existing password. Removing a camera subentry removes only that camera, not the server entry.

## Adding the card to a dashboard

The card is registered after Home Assistant restarts. In the dashboard editor, select **Add card**, find **PTZ Camera**, and choose an entity. You may also use YAML:

```yaml
type: custom:ptz-camera-card
entity: camera.living_room_camera
```

The card displays a circular D-pad and two zoom buttons. Version `0.3.0` does not render RTSP video inside the PTZ card. The camera entity still supports RTSP, so video can be displayed in a separate standard Home Assistant camera card.

Controls:

| Gesture or key | Result |
|---|---|
| hold ▲ ▼ ◀ ▶ | send `start` for the selected direction |
| release or cancel a pointer | send `stop` for the active direction |
| hold `+` / `−` | send `start/zoom_in` or `start/zoom_out` |
| release `+` / `−` | stop the corresponding zoom operation |
| Escape | send `stop/all` |
| focus loss, hidden application, or card removal | emergency `stop/all` |
| arrow keys and keyboard `+` / `−` | start on key down and stop on key up |

## Using the action in an automation

Start movement:

```yaml
action: ptz_proxy.move
target:
  entity_id: camera.living_room_camera
data:
  action: start
  direction: left
```

Stop movement:

```yaml
action: ptz_proxy.move
target:
  entity_id: camera.living_room_camera
data:
  action: stop
  direction: all
```

Whenever an automation sends `start`, always schedule a matching `stop`. The `start/all` combination is intentionally rejected.

## Security

- JavaScript receives only `entity_id`, `action`, and `direction`.
- The camera password and API token remain in backend config entries and subentries.
- The entity does not expose the username, password, token, or RTSP URL.
- Logs contain only the name, host and port, error category, and an optional HTTP status.
- Diagnostics expose only set/not-set flags for private fields.
- The integration does not create an endpoint that bypasses Home Assistant permissions.
- The server URL cannot contain user information, a query string, or a fragment.

## Troubleshooting

| Code | Most common cause | What to check |
|---|---|---|
| `timeout` | the server did not respond | server process, firewall, or a longer timeout |
| `dns_error` | invalid DNS name | Home Assistant DNS or use an IP address |
| `connection_refused` | nothing listens on the port | port number and server process |
| `network_unreachable` | no network route | VLAN, routing, and firewall |
| `tls_verification_failed` | invalid or private certificate | certificate SAN or deliberately disable verification |
| `invalid_auth` | HTTP 401/403 | Bearer token |
| `http_error` | another HTTP status | the separately reported status, such as 404/503 |
| `invalid_json` | `/health` does not return JSON | server endpoint implementation |
| `invalid_health_response` | neither `status: ok` nor `ok: true` is present | health response structure |
| `redirect_error` | HTTP 3xx | use the final URL without a redirect |

If the card is missing, inspect the integration loading logs, restart Home Assistant, and perform a hard browser refresh. Do not manually add `/ptz_proxy_static/ptz-camera-card.js` to Lovelace resources.

## Diagnostic logs

Version `0.3.0` logs the integration version, HTTP requests without payloads, response statuses, health results, and PTZ commands in Home Assistant. Health logging contains only the safe fields `ok`, `status`, `backend`, `connected_sessions`, `version`, and `name`. Tokens, passwords, and unknown field values are not logged.

To enable debug-level entries, add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.ptz_proxy: debug
```

Restart Home Assistant and open **Settings → System → Logs**. The card logs command submission, success, and failure in the browser developer tools with the `[PTZ Proxy 0.3.0]` prefix. The integration setup screen belongs to the Home Assistant Core frontend, so its `/health` details are written to the form and Home Assistant logs rather than the custom card console.

## Development tests

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest --cov --cov-report=term-missing
node --check custom_components/ptz_proxy/frontend/ptz-camera-card.js
node --test tests/frontend/test_ptz_camera_card.mjs
```

Hassfest runs through `.github/workflows/hassfest.yaml` on GitHub.

## RTSP video

The entity still enables `CameraEntityFeature.STREAM`, and `stream_source` returns the private RTSP address only to the backend. Version `0.3.0` deliberately does not embed video in the PTZ card. To display live video, add a separate standard Home Assistant card:

```yaml
type: picture-glance
camera_image: camera.living_room_camera
camera_view: live
entities: []
```

The RTSP address must be reachable from the Home Assistant host, not only from the user's computer.
