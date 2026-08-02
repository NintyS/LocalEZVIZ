# PTZ Proxy dla Home Assistant

PTZ Proxy to niestandardowa integracja dla Home Assistant Core **2026.7 lub nowszego**. Łączy Home Assistanta z lokalnym serwerem HTTP, który zna sposób sterowania fizycznymi kamerami. Wersja `0.1.0` jest świadomie małym MVP: obsługuje ruch góra, dół, lewo, prawo oraz awaryjne zatrzymanie. Nie wyświetla jeszcze obrazu RTSP.

## Co dostajesz

- konfigurację serwera wyłącznie przez UI;
- kontrolę `GET /health` przed zapisaniem konfiguracji;
- dowolną liczbę kamer jako config subentries;
- osobną encję `camera` i urządzenie dla każdej kamery;
- akcję `ptz_proxy.move` z kontrolą uprawnień encji;
- automatycznie ładowaną kartę `custom:ptz-camera-card`;
- D-pad działający na myszce, ekranie dotykowym i klawiaturze;
- polskie i angielskie tłumaczenia;
- diagnostykę bez tokenów, haseł i pełnych adresów RTSP.

## Architektura

```mermaid
flowchart LR
    U[Przeglądarka / aplikacja HA] -->|entity_id + action + direction| HA[Backend Home Assistant]
    HA -->|dane kamery tylko w backendzie| S[Lokalny serwer PTZ]
    S -->|protokół producenta| C[Kamera]
    HA -. nigdy .->|hasło lub token| U
```

Karta nie łączy się bezpośrednio z serwerem PTZ. Wywołuje standardową akcję encji Home Assistanta, a backend odczytuje prywatne dane kamery i wysyła pojedynczy `POST`.

## Wymagany kontrakt serwera

### Sprawdzenie działania

```http
GET {base_url}/health
Accept: application/json
Authorization: Bearer <api_token>  # tylko gdy token nie jest pusty
```

Serwer musi odpowiedzieć statusem `200` i JSON-em:

```json
{
  "status": "ok"
}
```

Może dodać np. `version` i `name`. Przekierowania, inny status, niepoprawny JSON albo brak `status: ok` blokują zapis konfiguracji.

### Sterowanie PTZ

```http
POST {base_url}/api/v1/ptz
Content-Type: application/json
Accept: application/json
```

Przykładowy start:

```json
{
  "camera_ip": "192.168.1.50",
  "username": "admin",
  "password": "tajne_haslo",
  "action": "start",
  "direction": "left"
}
```

Puszczenie kierunku wysyła `stop` z tym samym kierunkiem. Centralny STOP wysyła `{"action":"stop","direction":"all", ...}`. Sukcesem jest dowolny status `2xx`, w tym puste `204`. Integracja nie wykonuje retry.

> **Ważny bezpiecznik:** serwer PTZ musi sam zatrzymać kamerę po 5–10 sekundach ciągłego ruchu. Nie wolno zakładać, że przeglądarka zawsze dostarczy `pointerup` lub że komenda `stop` dotrze przez uszkodzoną sieć.

## Instalacja ręczna

1. Skopiuj cały katalog `custom_components/ptz_proxy` do katalogu konfiguracyjnego Home Assistanta tak, aby istniał plik:

   ```text
   /config/custom_components/ptz_proxy/manifest.json
   ```

2. Uruchom ponownie Home Assistant.
3. Wyczyść cache przeglądarki tylko wtedy, gdy po aktualizacji nie widzisz nowej wersji karty. Zwykła pierwsza instalacja tego nie wymaga.

Nie dodawaj niczego do `configuration.yaml` ani do zasobów Lovelace. Backend udostępnia i ładuje kartę automatycznie.

## Instalacja przez HACS

1. W HACS otwórz menu i wybierz **Niestandardowe repozytoria**.
2. Wklej adres repozytorium zawierającego ten projekt.
3. Wybierz kategorię **Integration** i dodaj repozytorium.
4. Wyszukaj **PTZ Proxy**, zainstaluj i uruchom ponownie Home Assistant.

## Dodanie serwera

1. Otwórz **Ustawienia → Urządzenia i usługi**.
2. Kliknij **Dodaj integrację** i wyszukaj **PTZ Proxy**.
3. Podaj:

   | Pole | Znaczenie | Przykład |
   |---|---|---|
   | Nazwa serwera | Przyjazna nazwa wpisu | `Serwer kamer` |
   | Adres serwera | Bazowy HTTP/HTTPS, bez `/health` | `http://192.168.1.20:8080` |
   | Token API | Opcjonalny Bearer | pozostaw puste, jeśli brak |
   | Sprawdź TLS | Weryfikacja certyfikatu HTTPS | włączone |
   | Limit czasu | 1–30 sekund | `3` |

4. Zatwierdź. Integracja wywoła `/health`. Gdy test nie przejdzie, formularz pozostanie otwarty i zachowa wpisane wartości; popraw tylko błędne pole.

Adres bez schematu dostanie `http://`. Końcowy ukośnik i przypadkowo podane `/health` zostaną usunięte. Dane logowania w URL, query string, fragment oraz schemat inny niż HTTP/HTTPS są odrzucane.

## Dodanie lub zmiana kamery

1. Otwórz utworzony wpis PTZ Proxy.
2. W sekcji wpisów podrzędnych wybierz dodanie **Kamery**.
3. Podaj nazwę, adres IP/DNS kamery, username i password. Pole RTSP jest opcjonalne i w tej wersji nie jest używane.
4. Powtórz operację dla następnych kamer.

Każda kamera otrzymuje losowy UUID. Zmiana nazwy lub adresu nie zmienia tożsamości encji. Podczas rekonfiguracji puste pole hasła zachowuje dotychczasowe hasło. Usunięcie camera subentry usuwa tylko tę kamerę, nie serwer.

## Dodanie karty do dashboardu

Po restarcie karta jest już zarejestrowana. W edytorze dashboardu wybierz **Dodaj kartę**, znajdź **PTZ Camera** i wybierz encję. Możesz też użyć YAML:

```yaml
type: custom:ptz-camera-card
entity: camera.kamera_salon
```

Sterowanie:

| Gest/klawisz | Efekt |
|---|---|
| przytrzymanie ▲ ▼ ◀ ▶ | `start` w odpowiednim kierunku |
| puszczenie lub anulowanie dotyku | `stop` dla aktywnego kierunku |
| centralny STOP lub Escape | `stop/all` |
| utrata fokusu, ukrycie aplikacji, usunięcie karty | awaryjne `stop/all` |
| strzałki klawiatury | start przy wciśnięciu, stop przy puszczeniu |

## Użycie w automatyzacji

Rozpoczęcie ruchu:

```yaml
action: ptz_proxy.move
target:
  entity_id: camera.kamera_salon
data:
  action: start
  direction: left
```

Zatrzymanie:

```yaml
action: ptz_proxy.move
target:
  entity_id: camera.kamera_salon
data:
  action: stop
  direction: all
```

Jeżeli automatyzacja wysyła `start`, zawsze zaplanuj odpowiadający `stop`. Kombinacja `start/all` jest celowo odrzucana.

## Bezpieczeństwo

- JavaScript dostaje wyłącznie `entity_id`, `action` i `direction`.
- Hasło kamery i token API pozostają w config entry/subentry backendu.
- Encja nie publikuje username, password, tokenu ani RTSP.
- Logi zawierają wyłącznie nazwę, host/port, kategorię i ewentualny status HTTP.
- Diagnostyka pokazuje tylko flagi „ustawiono/nie ustawiono”.
- Nie istnieje własny endpoint omijający uprawnienia Home Assistanta.
- URL serwera nie może zawierać userinfo, query ani fragmentu.

## Rozwiązywanie problemów

| Kod | Najczęstsza przyczyna | Co sprawdzić |
|---|---|---|
| `timeout` | serwer nie odpowiedział | proces serwera, firewall, zwiększenie timeoutu |
| `dns_error` | błędna nazwa DNS | DNS Home Assistanta lub użycie adresu IP |
| `connection_refused` | nic nie słucha na porcie | port i uruchomienie serwera |
| `network_unreachable` | brak trasy | VLAN, routing, firewall |
| `tls_verification_failed` | zły/własny certyfikat | SAN certyfikatu lub świadome wyłączenie weryfikacji |
| `invalid_auth` | HTTP 401/403 | token Bearer |
| `http_error` | inny status HTTP | pokazany osobno status, np. 404/503 |
| `invalid_json` | endpoint nie oddaje JSON | implementację `/health` |
| `invalid_health_response` | brak dokładnego `status: ok` | strukturę odpowiedzi |
| `redirect_error` | 3xx | podaj końcowy adres bez przekierowania |

Jeżeli nie widzisz karty, sprawdź log ładowania integracji, zrestartuj HA i wykonaj twarde odświeżenie przeglądarki. Nie dodawaj ręcznie `/ptz_proxy_static/ptz-camera-card.js` do zasobów.

## Testy deweloperskie

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest --cov --cov-report=term-missing
node --check custom_components/ptz_proxy/frontend/ptz-camera-card.js
node --test tests/frontend/test_ptz_camera_card.mjs
```

Hassfest uruchamia workflow `.github/workflows/hassfest.yaml` na GitHubie.

## Plan RTSP

Pole `rtsp_url` jest już zachowywane prywatnie, ale wersja `0.1.0` nie ustawia `CameraEntityFeature.STREAM`. Następny etap powinien użyć standardowego `stream_source` Home Assistanta, bez dekodera RTSP w JavaScripcie i bez ujawniania danych logowania. Własny D-pad może wtedy znaleźć się pod standardowym podglądem HA.
