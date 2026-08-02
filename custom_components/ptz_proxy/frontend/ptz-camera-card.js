/*
 * PL: Samodzielna karta D-pad PTZ bez dostępu do sekretów.
 * EN: Standalone PTZ D-pad card with no access to secrets.
 */

const CARD_TAG = "ptz-camera-card";
const EDITOR_TAG = "ptz-camera-card-editor";
const DIRECTIONS = ["up", "left", "right", "down"];
const LOG_PREFIX = "[PTZ Proxy 0.1.2]";

class PtzCameraCard extends HTMLElement {
  /** PL: Utwórz bezpieczny stan karty. EN: Create the card's safe local state. */
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = undefined;
    this._hass = undefined;
    this._activeDirection = null;
    this._activePointerId = null;
    this._pending = false;
    this._error = "";
    this._built = false;
    this._onBlur = () => this._emergencyStop(false);
    this._onVisibility = () => {
      if (document.visibilityState === "hidden") this._emergencyStop(false);
    };
    this._onKeyDownBound = (event) => this._onKeyDown(event);
    this._onKeyUpBound = (event) => this._onKeyUp(event);
  }

  /** PL: Sprawdź minimalną konfigurację. EN: Validate the minimal card configuration. */
  setConfig(config) {
    if (!config || typeof config.entity !== "string" || !config.entity.startsWith("camera.")) {
      throw new Error("PTZ Camera Card requires a camera entity");
    }
    if (this._config?.entity && this._config.entity !== config.entity) {
      this._emergencyStop(false);
    }
    this._config = { entity: config.entity };
    this._build();
    this._updateView();
  }

  /** PL: Przyjmij aktualny obiekt Home Assistanta. EN: Receive the current Home Assistant object. */
  set hass(value) {
    this._hass = value;
    this._updateView();
  }

  /** PL: Zwróć przybliżoną wysokość karty. EN: Return the approximate card height. */
  getCardSize() {
    return 4;
  }

  /** PL: Utwórz graficzny edytor konfiguracji. EN: Create the graphical configuration editor. */
  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  /** PL: Wybierz pierwszą encję tej integracji. EN: Select the first entity from this integration. */
  static getStubConfig(hass) {
    const entity = Object.entries(hass?.entities ?? {}).find(
      ([entityId, registryEntry]) =>
        entityId.startsWith("camera.") && registryEntry?.platform === "ptz_proxy",
    )?.[0];
    return { entity: entity ?? "" };
  }

  /** PL: Podłącz zabezpieczenia utraty fokusu. EN: Attach focus-loss safety handlers. */
  connectedCallback() {
    this._build();
    window.addEventListener("blur", this._onBlur);
    document.addEventListener("visibilitychange", this._onVisibility);
    this.addEventListener("keydown", this._onKeyDownBound);
    this.addEventListener("keyup", this._onKeyUpBound);
  }

  /** PL: Zatrzymaj ruch przed usunięciem karty. EN: Stop motion before the card is detached. */
  disconnectedCallback() {
    this._emergencyStop(false);
    window.removeEventListener("blur", this._onBlur);
    document.removeEventListener("visibilitychange", this._onVisibility);
    this.removeEventListener("keydown", this._onKeyDownBound);
    this.removeEventListener("keyup", this._onKeyUpBound);
  }

  /** PL: Zbuduj nieruchomy DOM bez wstawiania danych użytkownika do HTML. EN: Build static DOM without injecting user data into HTML. */
  _build() {
    if (this._built || !this.shadowRoot) return;
    this._built = true;
    this.tabIndex = 0;
    this.setAttribute("role", "group");
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; outline: none; }
        ha-card {
          display: block; padding: 16px; color: var(--primary-text-color);
          background: var(--ha-card-background, var(--card-background-color));
          user-select: none; -webkit-user-select: none; touch-action: none;
        }
        .title { font-size: 1.15rem; font-weight: 500; margin-bottom: 12px; }
        .status { min-height: 20px; color: var(--secondary-text-color); font-size: .9rem; text-align: center; }
        .status.error { color: var(--error-color); }
        .pad { display: grid; grid-template: repeat(3, 56px) / repeat(3, 56px); gap: 8px; justify-content: center; }
        button {
          min-width: 48px; min-height: 48px; border: 1px solid var(--divider-color);
          border-radius: 50%; background: transparent; color: var(--primary-text-color);
          font: inherit; font-size: 24px; cursor: pointer; touch-action: none;
          -webkit-touch-callout: none; transition: background .12s, color .12s, transform .12s;
        }
        button:focus-visible { outline: 3px solid var(--primary-color); outline-offset: 2px; }
        button.active { background: var(--primary-color); color: var(--text-primary-color, white); transform: scale(.94); }
        button.pending { opacity: .55; }
        .up { grid-area: 1 / 2; } .left { grid-area: 2 / 1; }
        .stop { grid-area: 2 / 2; font-size: 12px; font-weight: 700; border-radius: 12px; }
        .right { grid-area: 2 / 3; } .down { grid-area: 3 / 2; }
      </style>
      <ha-card>
        <div class="title"></div>
        <div class="status" aria-live="polite"></div>
        <div class="pad" role="group" aria-label="PTZ controls">
          <button class="up" data-direction="up" aria-label="Move up">▲</button>
          <button class="left" data-direction="left" aria-label="Move left">◀</button>
          <button class="stop" aria-label="Emergency stop">STOP</button>
          <button class="right" data-direction="right" aria-label="Move right">▶</button>
          <button class="down" data-direction="down" aria-label="Move down">▼</button>
        </div>
      </ha-card>`;

    for (const button of this.shadowRoot.querySelectorAll("[data-direction]")) {
      button.addEventListener("pointerdown", (event) => this._onPointerDown(event));
      button.addEventListener("pointerup", (event) => this._finishPointer(event));
      button.addEventListener("pointercancel", (event) => this._finishPointer(event));
      button.addEventListener("contextmenu", (event) => event.preventDefault());
    }
    this.shadowRoot.querySelector(".stop").addEventListener("click", (event) => {
      event.preventDefault();
      this._emergencyStop(true);
    });
  }

  /** PL: Odśwież tylko bezpieczny tekst i klasy. EN: Update safe text and CSS classes only. */
  _updateView() {
    if (!this._built || !this.shadowRoot) return;
    const state = this._hass?.states?.[this._config?.entity];
    this.shadowRoot.querySelector(".title").textContent =
      state?.attributes?.friendly_name ?? this._config?.entity ?? "PTZ Camera";
    const status = this.shadowRoot.querySelector(".status");
    status.textContent = this._error || (this._pending ? this._message("sending") : "");
    status.classList.toggle("error", Boolean(this._error));
    for (const button of this.shadowRoot.querySelectorAll("[data-direction]")) {
      button.classList.toggle("active", button.dataset.direction === this._activeDirection);
      button.classList.toggle("pending", this._pending && button.dataset.direction === this._activeDirection);
    }
  }

  /** PL: Zwróć krótki komunikat w języku HA. EN: Return a short message in the HA language. */
  _message(kind) {
    const polish = (this._hass?.language ?? "en").toLowerCase().startsWith("pl");
    if (kind === "sending") return polish ? "Wysyłanie polecenia…" : "Sending command…";
    return polish ? "Nie udało się wysłać polecenia PTZ." : "Could not send the PTZ command.";
  }

  /** PL: Wyślij usługę wyłącznie z entity_id, action i direction. EN: Call the service with entity_id, action, and direction only. */
  async _callMove(action, direction) {
    if (!this._hass || !this._config?.entity) throw new Error("Card is not ready");
    const command = {
      entity_id: this._config.entity,
      action,
      direction,
    };
    console.info(LOG_PREFIX, "Sending command", command);
    try {
      await this._hass.callService("ptz_proxy", "move", command);
      console.info(LOG_PREFIX, "Command succeeded", command);
    } catch (error) {
      console.error(LOG_PREFIX, "Command failed", command, {
        name: error?.name ?? "Error",
        message: error?.message ?? String(error),
      });
      throw error;
    }
  }

  /** PL: Rozpocznij jeden ruch po pointerdown. EN: Start one movement on pointerdown. */
  async _onPointerDown(event) {
    event.preventDefault();
    const direction = event.currentTarget.dataset.direction;
    if (!DIRECTIONS.includes(direction) || this._activeDirection === direction) return;
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch (_error) {
      // PL: Brak capture nie może zablokować awaryjnego stopu. EN: Capture failure must not block emergency stop.
    }
    this._activePointerId = event.pointerId;
    await this._startDirection(direction);
  }

  /** PL: Rozpocznij kierunek, zatrzymując poprzedni. EN: Start a direction after stopping the previous one. */
  async _startDirection(direction) {
    if (this._activeDirection && this._activeDirection !== direction) {
      await this._stopDirection(this._activeDirection);
    }
    this._activeDirection = direction;
    this._pending = true;
    this._updateView();
    try {
      await this._callMove("start", direction);
      this._error = "";
    } catch (_error) {
      this._error = this._message("error");
      this._activeDirection = null;
      await this._emergencyStop(true, true);
    } finally {
      this._pending = false;
      this._updateView();
    }
  }

  /** PL: Obsłuż pointerup i pointercancel identycznie. EN: Handle pointerup and pointercancel identically. */
  async _finishPointer(event) {
    event.preventDefault();
    if (this._activePointerId !== null && event.pointerId !== this._activePointerId) return;
    const direction = event.currentTarget.dataset.direction;
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    } catch (_error) {
      // PL: Capture mógł już zostać zwolniony. EN: Pointer capture may already be released.
    }
    this._activePointerId = null;
    await this._stopDirection(direction);
  }

  /** PL: Idempotentnie zatrzymaj aktywny kierunek. EN: Idempotently stop the active direction. */
  async _stopDirection(direction) {
    if (!direction || this._activeDirection !== direction) return;
    this._activeDirection = null;
    this._updateView();
    try {
      await this._callMove("stop", direction);
      this._error = "";
    } catch (_error) {
      this._error = this._message("error");
    }
    this._updateView();
  }

  /** PL: Zatrzymaj wszystko przy utracie kontroli lub STOP. EN: Stop everything on control loss or STOP. */
  async _emergencyStop(force = false, suppressErrors = false) {
    if (!force && !this._activeDirection) return;
    this._activeDirection = null;
    this._activePointerId = null;
    this._pending = false;
    this._updateView();
    try {
      await this._callMove("stop", "all");
      if (!suppressErrors) this._error = "";
    } catch (_error) {
      if (!suppressErrors) this._error = this._message("error");
    }
    this._updateView();
  }

  /** PL: Uruchom kierunek klawiszem bez autorepeat. EN: Start a direction by keyboard without auto-repeat. */
  _onKeyDown(event) {
    if (event.repeat) return;
    const map = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
    if (event.key === "Escape") {
      event.preventDefault();
      this._emergencyStop(true);
      return;
    }
    const direction = map[event.key];
    if (!direction) return;
    event.preventDefault();
    this._startDirection(direction);
  }

  /** PL: Zatrzymaj kierunek po puszczeniu klawisza. EN: Stop the direction when the key is released. */
  _onKeyUp(event) {
    const map = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
    const direction = map[event.key];
    if (!direction) return;
    event.preventDefault();
    this._stopDirection(direction);
  }
}
class PtzCameraCardEditor extends HTMLElement {
  /** PL: Utwórz prosty edytor listy kamer PTZ Proxy. EN: Create a simple PTZ Proxy camera-list editor. */
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = undefined;
    this._config = {};
    this._entities = [];
    this._loadedRegistry = false;
  }

  /** PL: Zachowaj konfigurację edytora. EN: Store the editor configuration. */
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  /** PL: Pobierz registry i filtruj platformę ptz_proxy. EN: Fetch the registry and filter the ptz_proxy platform. */
  set hass(value) {
    this._hass = value;
    if (!this._loadedRegistry && value?.callWS) {
      this._loadedRegistry = true;
      value
        .callWS({ type: "config/entity_registry/list" })
        .then((entries) => {
          this._entities = entries
            .filter((entry) => entry.entity_id.startsWith("camera.") && entry.platform === "ptz_proxy")
            .map((entry) => entry.entity_id)
            .sort();
          this._render();
        })
        .catch((error) => {
          console.error(LOG_PREFIX, "Could not load the entity registry", {
            name: error?.name ?? "Error",
            message: error?.message ?? String(error),
          });
          this._entities = [];
          this._render();
        });
    }
    this._render();
  }

  /** PL: Wyrenderuj selektor albo czytelny komunikat. EN: Render a selector or a clear empty-state message. */
  _render() {
    if (!this.shadowRoot) return;
    this.shadowRoot.innerHTML = `
      <style>:host{display:block}.empty{color:var(--secondary-text-color);padding:12px 0}select{width:100%;padding:12px;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:6px}</style>
      <label></label><div class="content"></div>`;
    const polish = (this._hass?.language ?? "en").toLowerCase().startsWith("pl");
    this.shadowRoot.querySelector("label").textContent = polish ? "Encja kamery" : "Camera entity";
    const content = this.shadowRoot.querySelector(".content");
    if (!this._entities.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = polish
        ? "Brak encji camera z integracji PTZ Proxy. Najpierw dodaj kamerę."
        : "No PTZ Proxy camera entities exist. Add a camera first.";
      content.append(empty);
      return;
    }
    const select = document.createElement("select");
    for (const entityId of this._entities) {
      const option = document.createElement("option");
      option.value = entityId;
      option.textContent = this._hass?.states?.[entityId]?.attributes?.friendly_name ?? entityId;
      option.selected = entityId === this._config.entity;
      select.append(option);
    }
    select.addEventListener("change", () => this._valueChanged(select.value));
    content.append(select);
  }

  /** PL: Powiadom Lovelace o zmianie encji. EN: Notify Lovelace about an entity change. */
  _valueChanged(entity) {
    this._config = { ...this._config, entity };
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }),
    );
  }
}

if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, PtzCameraCard);
if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, PtzCameraCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "PTZ Camera",
    description: "Camera controls with press-and-hold PTZ D-pad.",
    preview: true,
  });
}
