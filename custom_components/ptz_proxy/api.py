"""Asynchroniczny klient HTTP PTZ Proxy. / Asynchronous PTZ Proxy HTTP client."""

from __future__ import annotations

import errno
import json
import socket
import ssl
from http import HTTPStatus
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from aiohttp import (
    ClientConnectionError,
    ClientConnectorCertificateError,
    ClientConnectorError,
    ClientError,
    ClientResponse,
    ClientSession,
    ClientSSLError,
    ClientTimeout,
)

from .const import HEALTH_PATH, PTZ_PATH
from .models import CameraConfig, ErrorDetails, HealthResponse, PtzAction, PtzDirection


class PtzProxyError(Exception):
    """PL: Bazowy kontrolowany błąd klienta. EN: Base controlled client error."""

    def __init__(self, details: ErrorDetails) -> None:
        """PL: Zachowaj wyłącznie oczyszczone szczegóły. EN: Store sanitized details only."""

        super().__init__(details.error_code)
        self.details = details


class PtzProxyConnectionError(PtzProxyError):
    """PL: Błąd połączenia sieciowego. EN: Network connection failure."""


class PtzProxyAuthenticationError(PtzProxyError):
    """PL: Serwer odrzucił uwierzytelnienie. EN: The server rejected authentication."""


class PtzProxyInvalidResponseError(PtzProxyError):
    """PL: Serwer zwrócił niepoprawną odpowiedź. EN: The server returned an invalid response."""


class PtzProxyTimeoutError(PtzProxyConnectionError):
    """PL: Upłynął limit czasu żądania. EN: The request timed out."""


class PtzProxyHttpError(PtzProxyError):
    """PL: Serwer zwrócił niepoprawny status HTTP. EN: The server returned an unsuccessful HTTP status."""


class PtzProxyTlsError(PtzProxyConnectionError):
    """PL: Weryfikacja TLS nie powiodła się. EN: TLS verification failed."""


class PtzProxyRedirectError(PtzProxyConnectionError):
    """PL: Serwer próbował wykonać przekierowanie. EN: The server attempted a redirect."""


def normalize_base_url(raw_url: str) -> str:
    """PL: Sprawdź i znormalizuj bazowy URL. EN: Validate and normalize the base URL."""

    candidate = raw_url.strip()
    if not candidate:
        raise ValueError("empty_url")
    if "://" not in candidate:
        candidate = f"http://{candidate}"

    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("unsupported_scheme")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("credentials_in_url")
    if not parsed.hostname:
        raise ValueError("missing_host")
    if parsed.query or parsed.fragment:
        raise ValueError("query_or_fragment_not_allowed")

    try:
        port = parsed.port
    except ValueError as err:
        raise ValueError("invalid_port") from err

    host = parsed.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{host}:{port}" if port is not None else host

    path = parsed.path.rstrip("/")
    if path.lower().endswith(HEALTH_PATH):
        path = path[: -len(HEALTH_PATH)].rstrip("/")

    return urlunsplit(SplitResult(parsed.scheme.lower(), netloc, path, "", ""))


def _safe_host_port(base_url: str) -> tuple[str, int | None]:
    """PL: Pobierz host i port bez sekretów. EN: Extract host and port without secrets."""

    parsed = urlsplit(base_url)
    return parsed.hostname or "server", parsed.port


def _safe_http_detail(status: int) -> str:
    """PL: Zbuduj kontrolowany opis statusu HTTP. EN: Build a controlled HTTP status detail."""

    try:
        phrase = HTTPStatus(status).phrase
    except ValueError:
        phrase = "HTTP error"
    return f"HTTP {status}: {phrase}."


def get_safe_error_details(exception: Exception) -> ErrorDetails:
    """PL: Zamień wyjątek na bezpieczny opis bez sekretów. EN: Convert an exception into secret-free safe details."""

    if isinstance(exception, PtzProxyError):
        return exception.details
    if isinstance(exception, TimeoutError):
        return ErrorDetails("timeout", "timeout", "The request time limit was exceeded.")
    if isinstance(exception, (ssl.SSLError, ClientSSLError)):
        return ErrorDetails(
            "tls_verification_failed",
            "tls_verification_failed",
            "The TLS certificate could not be verified.",
        )
    if isinstance(exception, socket.gaierror):
        return ErrorDetails("dns_error", "dns_error", "The host name could not be resolved.")
    if isinstance(exception, ConnectionRefusedError):
        return ErrorDetails(
            "connection_refused", "connection_refused", "The server refused the TCP connection."
        )
    if isinstance(exception, OSError) and exception.errno in {
        errno.ENETUNREACH,
        errno.EHOSTUNREACH,
        errno.ENETDOWN,
    }:
        return ErrorDetails(
            "network_unreachable", "network_unreachable", "The network or host is unreachable."
        )
    return ErrorDetails("unknown", "unknown", "An unexpected internal error occurred.")


class PtzProxyClient:
    """PL: Bezpieczny klient endpointów health i PTZ. EN: Safe client for the health and PTZ endpoints."""

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        api_token: str,
        verify_ssl: bool,
        request_timeout: float,
    ) -> None:
        """PL: Skonfiguruj klient bez tworzenia nowej sesji. EN: Configure the client without creating a new session."""

        self._session = session
        self._base_url = normalize_base_url(base_url)
        self._api_token = api_token
        self._verify_ssl = verify_ssl
        self._timeout = ClientTimeout(total=request_timeout)
        self._timeout_seconds = request_timeout

    @property
    def base_url(self) -> str:
        """PL: Zwróć znormalizowany URL bez sekretów. EN: Return the normalized secret-free URL."""

        return self._base_url

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        """PL: Zbuduj nagłówki, opcjonalnie z Bearer. EN: Build headers, optionally with Bearer authentication."""

        headers = {"Accept": "application/json"}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> ClientResponse:
        """PL: Wykonaj jedno żądanie i sklasyfikuj błędy transportu. EN: Perform one request and classify transport failures."""

        host, port = _safe_host_port(self._base_url)
        try:
            response = await self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers(json_body="json" in kwargs),
                timeout=self._timeout,
                ssl=self._verify_ssl,
                allow_redirects=False,
                **kwargs,
            )
        except TimeoutError as err:
            raise PtzProxyTimeoutError(
                ErrorDetails(
                    "timeout",
                    "timeout",
                    f"The server did not respond within {self._timeout_seconds:g} seconds.",
                )
            ) from err
        except (ClientConnectorCertificateError, ClientSSLError, ssl.SSLError) as err:
            raise PtzProxyTlsError(
                ErrorDetails(
                    "tls_verification_failed",
                    "tls_verification_failed",
                    "The TLS certificate could not be verified.",
                )
            ) from err
        except ClientConnectorError as err:
            cause = err.os_error
            if isinstance(cause, socket.gaierror):
                details = ErrorDetails(
                    "dns_error", "dns_error", f"The host name {host} could not be resolved."
                )
            elif isinstance(cause, ConnectionRefusedError) or getattr(cause, "errno", None) in {
                errno.ECONNREFUSED
            }:
                target = f"port {port}" if port is not None else "the configured port"
                details = ErrorDetails(
                    "connection_refused",
                    "connection_refused",
                    f"The server refused the connection on {target}.",
                )
            elif getattr(cause, "errno", None) in {
                errno.ENETUNREACH,
                errno.EHOSTUNREACH,
                errno.ENETDOWN,
            }:
                details = ErrorDetails(
                    "network_unreachable",
                    "network_unreachable",
                    "The network or host is unreachable.",
                )
            else:
                details = ErrorDetails(
                    "network_unreachable",
                    "network_unreachable",
                    "A network connection could not be established.",
                )
            raise PtzProxyConnectionError(details) from err
        except (ClientConnectionError, ClientError, OSError) as err:
            details = get_safe_error_details(err)
            if details.error_code == "unknown":
                details = ErrorDetails(
                    "network_unreachable",
                    "network_unreachable",
                    "A network connection could not be established.",
                )
            raise PtzProxyConnectionError(details) from err

        if 300 <= response.status < 400:
            response.release()
            raise PtzProxyRedirectError(
                ErrorDetails(
                    "redirect_error",
                    "redirect_error",
                    "The endpoint returned a redirect, which is not allowed.",
                    response.status,
                )
            )
        return response

    @staticmethod
    def _raise_for_status(response: ClientResponse) -> None:
        """PL: Zamień błędny status HTTP na kontrolowany wyjątek. EN: Convert an unsuccessful HTTP status into a controlled exception."""

        if response.status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
            raise PtzProxyAuthenticationError(
                ErrorDetails(
                    "invalid_auth",
                    "invalid_auth",
                    "The server rejected the API token.",
                    response.status,
                )
            )
        raise PtzProxyHttpError(
            ErrorDetails(
                "http_error",
                "http_error",
                _safe_http_detail(response.status),
                response.status,
            )
        )

    async def async_health(self) -> HealthResponse:
        """PL: Sprawdź GET /health i strukturę JSON. EN: Validate GET /health and its JSON structure."""

        response = await self._request("GET", HEALTH_PATH)
        async with response:
            if response.status != HTTPStatus.OK:
                self._raise_for_status(response)
            try:
                payload = await response.json(content_type=None)
            except (json.JSONDecodeError, ValueError, TypeError) as err:
                raise PtzProxyInvalidResponseError(
                    ErrorDetails(
                        "invalid_json",
                        "invalid_json",
                        "The response is not a valid JSON document.",
                    )
                ) from err
            if not isinstance(payload, dict):
                raise PtzProxyInvalidResponseError(
                    ErrorDetails(
                        "invalid_health_response",
                        "invalid_health_response",
                        "The health response must be a JSON object.",
                    )
                )
            status_is_ok = payload.get("status") == "ok"
            boolean_is_ok = payload.get("ok") is True
            if not status_is_ok and not boolean_is_ok:
                detail = (
                    "The health response must contain status='ok' or ok=true."
                    if "status" not in payload and "ok" not in payload
                    else "The health response reports that the backend is not ready."
                )
                raise PtzProxyInvalidResponseError(
                    ErrorDetails("invalid_health_response", "invalid_health_response", detail)
                )
            return HealthResponse(
                status="ok",
                version=str(payload["version"]) if "version" in payload else None,
                name=str(payload["name"]) if "name" in payload else None,
            )

    async def async_move(
        self,
        camera: CameraConfig,
        action: PtzAction,
        direction: PtzDirection,
    ) -> None:
        """PL: Wyślij dokładnie jedną komendę PTZ bez retry. EN: Send exactly one PTZ command without retries."""

        if action is PtzAction.START and direction is PtzDirection.ALL:
            raise ValueError("start_all_not_allowed")

        response = await self._request(
            "POST", PTZ_PATH, json=camera.as_request_payload(action, direction)
        )
        async with response:
            if not 200 <= response.status < 300:
                self._raise_for_status(response)
