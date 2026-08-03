# Raport implementacji PTZ Proxy

## 1. Cel i wynik

Na podstawie dwóch dokumentów z katalogu `Wskazania` powstało kompletne repozytorium niestandardowej integracji Home Assistant o domenie `ptz_proxy`. Implementacja realizuje MVP sterowania kamerami PTZ przez lokalny serwer pośredniczący. Obejmuje backend, UI konfiguracji, encje, urządzenia, akcję, kartę Lovelace, diagnostykę, tłumaczenia, testy, HACS i CI.

Najważniejsza decyzja: przeglądarka **nigdy nie otrzymuje danych logowania kamery ani tokenu API**. Frontend wskazuje tylko encję i zamiar ruchu. Wszystkie dane prywatne są dołączane dopiero w backendzie Home Assistanta.

## 2. Źródła wymagań

| Dokument | Zakres wykorzystany w implementacji |
|---|---|
| `PTZ Proxy dla Home Assistant.pdf` | architektura, config entry/subentry, klient HTTP, encja camera, akcja, karta, diagnostyka, testy, HACS i CI |
| `Obsługa błędów i formularza konfiguracji Home Assistanta.pdf` | pozostawanie w formularzu po błędzie, suggested values, szczegółowe kategorie, sanityzacja, bezpieczne logi, scenariusz poprawienia jednego pola |

Kod jest przeznaczony dla Home Assistant Core 2026.7+. Zastosowano aktualne API: `ConfigEntry.runtime_data`, `ConfigSubentryFlow`, `AddConfigEntryEntitiesCallback` z `config_subentry_id`, `async_register_platform_entity_service`, `StaticPathConfig` i bezpośredni `frontend.add_extra_js_url`.

## 3. Architektura rozwiązania

```mermaid
sequenceDiagram
    participant User as Użytkownik
    participant Card as Karta PTZ
    participant HA as Home Assistant
    participant Client as PtzProxyClient
    participant Server as Serwer PTZ
    participant Camera as Kamera

    User->>Card: pointerdown left
    Card->>HA: ptz_proxy.move(entity_id, start, left)
    HA->>HA: sprawdzenie uprawnień i encji
    HA->>Client: async_move(prywatny CameraConfig)
    Client->>Server: POST /ptz + ip/login/password
    Server->>Camera: protokół urządzenia
    User->>Card: pointerup
    Card->>HA: ptz_proxy.move(entity_id, stop, left)
    HA->>Client: async_move(... stop, left)
    Client->>Server: pojedynczy POST stop
```

### Podział odpowiedzialności

| Warstwa | Odpowiedzialność | Czego celowo nie robi |
|---|---|---|
| config flow | waliduje URL i `/health`, zapisuje dopiero po sukcesie | nie tworzy encji i nie loguje sekretów |
| config subentry flow | dodaje/zmienia/usuwa prywatną konfigurację kamery | nie łączy się bezpośrednio z kamerą |
| klient HTTP | buduje żądania, klasyfikuje błędy, nie wykonuje retry | nie zna Home Assistant UI |
| encja camera | łączy entity service z właściwą kamerą | nie publikuje obrazu ani credentials |
| karta JS | zamienia gest/klawisz na akcję encji | nie zna adresu serwera i nie wykonuje `fetch` |
| diagnostyka | pokazuje bezpieczne fakty i flagi | nie zwraca tokenu, hasła, username ani RTSP |

## 4. Model konfiguracji

### Parent config entry — jeden serwer

| Pole | Typ | Domyślne | Walidacja | Poufne |
|---|---:|---:|---|---|
| `name` | tekst | — | wymagane | nie |
| `base_url` | URL | — | tylko HTTP/HTTPS, bez userinfo/query/fragment | nie, ale redagowane defensywnie |
| `api_token` | tekst | pusty | opcjonalny Bearer | **tak** |
| `verify_ssl` | bool | `true` | selektor logiczny | nie |
| `request_timeout` | liczba | `3` | 1–30 sekund | nie |

Znormalizowany `base_url` jest unique ID wpisu. Dzięki temu `host:8080/`, `http://HOST:8080` i `http://host:8080/` prowadzą do tej samej tożsamości. Duplikat jest blokowany.

### Camera config subentry — jedna kamera

| Pole | Cel | Zachowanie przy rekonfiguracji |
|---|---|---|
| `camera_id` | stabilny UUID | nigdy się nie zmienia |
| `name` | nazwa urządzenia i encji | może się zmienić |
| `camera_ip` | cel dla serwera PTZ | może się zmienić |
| `username` | login przekazywany backend → serwer | wymagany |
| `password` | hasło przekazywane backend → serwer | puste pole zachowuje stare |
| `rtsp_url` | prywatne źródło obrazu dla komponentu `stream` | może się zmienić; puste wyłącza tylko obraz |

UUID, a nie nazwa ani IP, buduje unique ID encji. Zmiana nazwy, adresu kamery lub hasła nie tworzy nowej encji.

## 5. Normalizacja URL

Funkcja `normalize_base_url` wykonuje następujący, deterministyczny proces:

1. usuwa białe znaki z obu końców;
2. dodaje `http://`, jeżeli nie podano schematu;
3. akceptuje wyłącznie `http` i `https`;
4. wymaga hosta i poprawnego portu;
5. odrzuca username/password w URL;
6. odrzuca query string i fragment, aby nie dopuścić sekretów lub niejednoznaczności;
7. normalizuje schemat i host do małych liter;
8. zachowuje ścieżkę bazową;
9. usuwa końcowe ukośniki;
10. usuwa przypadkowo dopisany końcowy endpoint `/health`.

| Wejście | Wynik |
|---|---|
| `192.168.1.20:8080/` | `http://192.168.1.20:8080` |
| `http://HOST:8080/` | `http://host:8080` |
| `https://host/api/` | `https://host/api` |
| `https://host/api/health` | `https://host/api` |
| `https://admin:secret@host` | błąd `invalid_url` |
| `https://host?token=x` | błąd `invalid_url` |

## 6. Test `/health` i zapis konfiguracji

Konfiguracja jest zapisywana wyłącznie po spełnieniu wszystkich warunków:

| Warunek | Wymagana wartość |
|---|---|
| metoda | `GET` |
| endpoint | `{base_url}/health` |
| przekierowania | niedozwolone |
| status | dokładnie `200` |
| format | poprawny dokument JSON |
| główny typ JSON | obiekt |
| sygnał gotowości | `"status": "ok"` albo `"ok": true` (format HCNet) |

Token jest dołączany jako `Authorization: Bearer …` tylko wtedy, gdy nie jest pusty. Nie jest umieszczany w URL. Sesja `aiohttp` pochodzi z `async_get_clientsession(hass)`, więc integracja nie tworzy sesji na każde żądanie.

## 7. Zachowanie formularza po błędzie

Po błędzie funkcja zwraca `async_show_form`, a nie abort. Schemat jest odtwarzany przez `add_suggested_values_to_schema`. Dlatego nazwa, URL, token w ramach bieżącego flow, TLS i timeout pozostają na ekranie.

```mermaid
stateDiagram-v2
    [*] --> Formularz
    Formularz --> HealthCheck: Zatwierdź
    HealthCheck --> Formularz: błąd + te same wartości
    Formularz --> HealthCheck: popraw jedno pole
    HealthCheck --> ConfigEntry: HTTP 200 + status ok lub ok=true
    ConfigEntry --> [*]
```

W reconfigure pusty token oznacza „zachowaj stary”. Nowy token trafia do config entry dopiero po poprawnym health check. Błąd nowego tokenu nie narusza działającej konfiguracji.

## 8. Kategorie błędów

| Kod formularza | Przykładowa przyczyna | Dodatkowy status |
|---|---|---|
| `timeout` | przekroczony `ClientTimeout` | nie |
| `dns_error` | `socket.gaierror` | nie |
| `connection_refused` | `ECONNREFUSED` | nie |
| `network_unreachable` | `ENETUNREACH`, `EHOSTUNREACH`, inny transport | nie |
| `tls_verification_failed` | błąd certyfikatu/SSL | nie |
| `invalid_auth` | HTTP 401 lub 403 | tak |
| `http_error` | np. 404, 429, 500, 503 | tak |
| `invalid_json` | odpowiedzi nie da się zdekodować | nie |
| `invalid_health_response` | brak obiektu albo brak `status=ok` i `ok=true` | nie |
| `redirect_error` | HTTP 3xx | tak |
| `unknown` | nieoczekiwany wyjątek | nie |

`ErrorDetails` jest zamrożonym dataclass ze slots. UI otrzymuje tylko stały klucz tłumaczenia, stały kod, kontrolowany opis i opcjonalny status. Nigdy nie przekazuje się surowego `str(exception)`.

## 9. Kontrakt komendy PTZ

`PtzProxyClient.async_move` wysyła dokładnie jedno żądanie. Nie ma pętli retry ani automatycznego powtórzenia start/stop.

| Action | Direction | Dozwolone |
|---|---|---|
| `start` | `up/down/left/right` | tak |
| `stop` | `up/down/left/right` | tak |
| `start/stop` | `zoom_in/zoom_out` | tak |
| `stop` | `all` | tak, awaryjny STOP |
| `start` | `all` | **nie** |

Każdy status 2xx jest sukcesem. 401/403 stają się błędem uwierzytelnienia, pozostałe statusy błędem HTTP. Payload zawiera credentials, dlatego nie jest nigdzie logowany.

## 10. Encja i Device Registry

Każda camera subentry tworzy dokładnie jedną `PtzProxyCamera`. Wersja `0.2.0` dodatkowo naprawia pełną inicjalizację klasy bazowej `Camera`, bez której encja mogła zostać oznaczona jako niedostępna. Encja:

- ma `has_entity_name = True`;
- ma `should_poll = False`;
- ma funkcję STREAM, gdy skonfigurowano RTSP;
- przekazuje RTSP tylko do backendowego komponentu `stream`; własna karta PTZ tymczasowo nie renderuje obrazu;
- posiada stabilny unique ID `parent_entry_id + camera_uuid`;
- jest przypisana do właściwego config subentry;
- tworzy urządzenie `Generic / PTZ Proxy Camera`;
- publikuje tylko standardowy stan kamery, bez prywatnych atrybutów.

Urządzenie ma identifier `(ptz_proxy, camera_uuid)` i `configuration_url` prowadzący do bazowego serwera. Usunięcie subentry powoduje czyszczenie powiązanych encji/urządzenia przez mechanizm config entries HA, a update listener przeładowuje parent entry.

## 11. Akcja `ptz_proxy.move`

Akcja jest rejestrowana globalnie raz w `async_setup`. Użyty helper platform entity service:

- wymaga targetu encji;
- ogranicza domenę do `camera`;
- wybiera encje platformy `ptz_proxy`;
- korzysta ze standardowego mechanizmu uprawnień encji;
- wywołuje metodę `async_ptz_move` konkretnej encji.

Nie ma osobnej usługi dla każdego serwera i nie ma własnego endpointu HTTP omijającego HA.

## 12. Karta frontendowa

Karta jest modułem bez zewnętrznego frameworka. Backend serwuje ją jako statyczny plik i dopisuje jako extra JS module. Nie modyfikuje `.storage/lovelace_resources` i nie wymaga `/config/www`.

Karta pokazuje okrągły, czterokierunkowy D-pad z pustym środkiem oraz dwa okrągłe przyciski zoomu. Nie ma widocznego przycisku STOP ani podglądu RTSP. Adres RTSP i dane logowania nadal nie trafiają do JavaScriptu. Przyciski zoomu używają tego samego bezpiecznego cyklu `pointerdown → start` i `pointerup/pointercancel → stop` co kierunki ruchu.

### Maszyna bezpieczeństwa ruchu

| Zdarzenie | Działanie |
|---|---|
| `pointerdown` | capture, aktywny stan, jeden `start/direction` |
| drugi kierunek | najpierw stop poprzedniego |
| `pointerup` | `stop` dla aktywnego kierunku |
| `pointercancel` | identycznie jak pointerup |
| `blur` | `stop/all`, jeśli trwa ruch |
| `visibilitychange → hidden` | `stop/all` |
| `disconnectedCallback` | `stop/all` |
| zmiana encji | stop starej encji przed zmianą |
| błąd start | usuń aktywny stan, spróbuj `stop/all`, pokaż krótki błąd |
| Escape | zawsze `stop/all` |

Pierścień D-pada ma 190×190 px, przyciski zoomu 56×56 px, a wszystkie kontrolki mają `touch-action: none`, blokadę menu kontekstowego, stany active/pending, `aria-label` i obsługę klawiatury. `event.repeat` jest ignorowane.

Edytor pobiera entity registry i filtruje wyłącznie encje `camera` z platformą `ptz_proxy`. Brak kamery daje czytelny komunikat.

## 13. Analiza bezpieczeństwa

| Ryzyko | Zabezpieczenie |
|---|---|
| hasło w JavaScripcie | frontend wysyła tylko trzy jawne pola sterujące |
| token w logu | logowane są stałe kody, host/port, status i wyłącznie dozwolone pola health; reszta jest pomijana |
| sekret w wyjątku aiohttp | wyjątek jest mapowany na `ErrorDetails`; brak `str(exception)` |
| sekret w URL | zakaz userinfo, query i fragmentu |
| sekret w stanie encji | brak prywatnych extra state attributes |
| sekret w diagnostyce | wartości zastąpione booleanami „configured” |
| podwójny start | aktywny kierunek blokuje ponowne `pointerdown`; repeat klawiatury ignorowany |
| ruch po utracie strony | stop na blur/hidden/disconnect; obowiązkowy watchdog serwera |
| nieautoryzowane wywołanie | platform entity service i target encji HA |
| niekontrolowane powtórzenie POST | brak retry w kliencie |

Watchdog po stronie serwera jest konieczny, ponieważ żadne zabezpieczenie aplikacyjne nie gwarantuje dostarczenia pakietu `stop` po fizycznym zerwaniu sieci.

## 14. Diagnostyka

Diagnostyka parent entry zawiera:

- wersję integracji;
- nazwę;
- oczyszczony base URL;
- TLS i timeout;
- flagę obecności tokenu;
- liczbę kamer;
- bezpieczny opis każdej kamery.

Diagnostyka urządzenia zawiera nazwę, camera IP i trzy flagi obecności username/password/RTSP. Nie zawiera wartości tych pól.

## 15. Inwentarz plików

| Plik | Rola |
|---|---|
| `__init__.py` | globalna usługa, karta, setup/unload/runtime |
| `api.py` | normalizacja URL, klient aiohttp, wyjątki i sanityzacja |
| `camera.py` | platforma camera i wykonanie entity action |
| `config_flow.py` | server flow i camera subentry flow |
| `const.py` | niezmienne klucze i wartości domeny |
| `diagnostics.py` | diagnostyka parent entry oraz urządzenia |
| `entity.py` | wspólna tożsamość encji i DeviceInfo |
| `models.py` | enumy, dataclasses i typed ConfigEntry |
| `frontend/ptz-camera-card.js` | kołowy D-pad, zoom i graficzny edytor karty |
| `services.yaml` | opis targetu i pól akcji |
| `strings.json` | źródłowe napisy integracji |
| `translations/en.json`, `pl.json` | kompletne tłumaczenia |
| `manifest.json` | metadane custom integration |
| `icons.json` | ikona akcji |
| `tests/` | testy API, flow, subentries, encji, usługi, diagnostyki, setupu i JS |
| `hacs.json` | zgodność z HACS i minimalna wersja HA |
| `.github/workflows/` | Hassfest i testy CI |
| `README.md`, `README_EN.md` | pełna instrukcja użytkownika po polsku i angielsku |

## 16. Dwujęzyczna dokumentacja kodu

Każdy moduł, klasa, dataclass, enum, metoda i funkcja ma docstring albo komentarz w formacie `PL: … / EN: …`. Struktury stałych i schematów mają dwujęzyczne komentarze blokowe. Ta zasada obejmuje również metody JavaScriptu i funkcje testowe. Instrukcja użytkownika jest dostępna jako polski `README.md` oraz angielski `README_EN.md`, z przełącznikiem języka w obu plikach.

## 17. Zakres testów

| Grupa | Sprawdzane przypadki |
|---|---|
| URL | schemat domyślny, ścieżka, `/health`, credentials, query, fragment |
| health | 200, 401, 403, 404, 500, 503, invalid JSON, zła struktura |
| formularz | timeout, DNS, refused, unreachable, TLS, auth, HTTP, JSON, unknown |
| zachowanie flow | typ FORM, ten sam step, suggested values, brak config entry, retry w tym samym flow |
| sekrety flow | token nie występuje w placeholders; stary token przetrwa blank reconfigure |
| subentries | dodanie UUID, rekonfiguracja, zachowanie hasła |
| PTZ | dokładny JSON, ruch, zoom, 200, 204, stop/all, odrzucenie start/all, brak retry |
| encja | unique ID, DeviceInfo, inicjalizacja Camera, RTSP/STREAM, tryb bez RTSP, prywatny CameraConfig |
| diagnostyka | brak tokenu, hasła, username i RTSP |
| frontend | kołowy D-pad, zoom, brak obrazu i STOP, pointer safety, blur/visibility, keyboard repeat i logi; brak sekretów i fetch |

Pełny zestaw uruchomiono z `pytest-homeassistant-custom-component` przeciwko Home Assistant `2026.8.0b3`, czyli wersji nowszej od minimalnej `2026.7`. Wynik: **58 testów zaliczonych, 0 błędów**. Niezależnie wykonano kompilację wszystkich modułów Python, lint i formatowanie Ruff, walidację wszystkich plików JSON i YAML, kontrolę parytetu kluczy tłumaczeń, kontrolę składni JavaScriptu, test kontraktu karty oraz audyt dwujęzycznych docstringów.

## 18. Kryteria ukończenia

| Kryterium | Status | Implementacja |
|---|---|---|
| konfiguracja przez UI | gotowe | `PtzProxyConfigFlow` |
| health przed zapisem | gotowe | `_async_validate_server` |
| wiele kamer | gotowe | config subentries |
| osobna encja i urządzenie | gotowe | `camera.py`, `entity.py` |
| automatyczna karta | gotowe | static path + extra JS |
| pointerdown/start | gotowe | `_onPointerDown` |
| pointerup/cancel/stop | gotowe | `_finishPointer` |
| blur/hidden/disconnect stop | gotowe | lifecycle JS |
| awaryjne stop/all | gotowe | Escape i lifecycle JS |
| przybliżanie i oddalanie | gotowe | `zoom_in`, `zoom_out` |
| brak sekretów frontend/state | gotowe | rozdział backend/frontend |
| błędy formularza z zachowaniem pól | gotowe | suggested values |
| reload/unload | gotowe | update listener + platform unload |
| PL/EN | gotowe | strings i translations |
| ręczna instalacja/HACS | gotowe | README + hacs.json |
| RTSP w backendzie, bez obrazu w karcie | gotowe | `stream_source`, STREAM; frontend bez `picture-entity` |

## 19. Znane ograniczenia MVP

1. Karta PTZ tymczasowo nie renderuje obrazu RTSP; obraz można dodać jako osobną standardową kartę HA.
2. Brak focusu, presetów, patrolu i kierunków diagonalnych.
3. Brak automatycznego wykrywania kamer.
4. Sterowanie nie komunikuje się bezpośrednio z kamerą — wymagany jest zgodny serwer PTZ.
5. Komunikaty techniczne w placeholders są kontrolowane i obecnie angielskie; przyjazna warstwa błędu jest tłumaczona przez HA.
6. Watchdog ruchu musi być zaimplementowany po stronie serwera.

Ograniczenia są zamierzone i nie są atrapami. Wszystkie funkcje należące do MVP mają działającą implementację.

## 20. Instrukcja odbioru

1. Zainstaluj zależności testowe z `pyproject.toml`.
2. Uruchom `pytest --cov --cov-report=term-missing`.
3. Uruchom kontrolę JS podaną w README.
4. Uruchom Hassfest przez workflow lub w checkout Home Assistant Core.
5. Skopiuj integrację do testowej instancji HA 2026.7+.
6. Skonfiguruj mock/realny serwer z `/health` i `/ptz`.
7. W DevTools potwierdź, że wywołanie z karty zawiera tylko `entity_id`, `action`, `direction`.
8. Pobierz diagnostykę i wyszukaj token, hasło oraz fragment RTSP — nie mogą wystąpić.
9. Wykonaj manualną macierz pointer/keyboard z README.

Po pozytywnym odbiorze repozytorium jest gotowe do publikacji jako custom repository HACS.
