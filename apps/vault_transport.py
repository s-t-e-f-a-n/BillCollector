"""Connect the vault client only to a vetted local bw serve endpoint."""

import ipaddress
import os
import socket
import time
from urllib.parse import urlsplit

import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError

LOCAL_NETWORKS = tuple(ipaddress.ip_network(network) for network in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "fc00::/7", "::1/128",
))

TRANSIENT_DNS_ERRORS = {getattr(socket, name) for name in ("EAI_AGAIN", "EAI_NONAME", "EAI_FAIL", "EAI_NODATA")
                        if hasattr(socket, name)}


class VaultTransportError(ValueError):
    """Invalid API configuration or an unsafe response; do not retry it."""


def pinned_api_urls(url):
    """Return all vetted numeric local targets and the original Host header."""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment):
            raise ValueError("invalid API URL")
        port = parsed.port if parsed.port is not None else 80
        if port == 0:
            raise ValueError("invalid API port")
        addresses = {ipaddress.ip_address(info[4][0]) for info in
                     socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
        if not addresses or any(not any(address in network for network in LOCAL_NETWORKS)
                                for address in addresses):
            raise ValueError("non-local API address")
        targets = []
        for address in sorted(addresses, key=lambda ip: (ip.version, int(ip))):
            host = f"[{address}]" if address.version == 6 else str(address)
            targets.append(parsed._replace(netloc=f"{host}:{port}").geturl())
        return targets, parsed.netloc
    except socket.gaierror as error:
        # A name can be briefly unknown while a bw serve container is recreated.
        if error.errno in TRANSIENT_DNS_ERRORS:
            raise requests.exceptions.ConnectionError("Vault API DNS temporarily unavailable") from None
        raise VaultTransportError("BW_API_URL must resolve only to local HTTP addresses") from None
    except (OSError, TypeError, ValueError):
        raise VaultTransportError("BW_API_URL must resolve only to local HTTP addresses") from None


def pinned_api_url(url, attempts=3, backoff=2):
    """Validate preflight DNS with the caller's request retry policy."""
    for attempt in range(1, attempts + 1):
        try:
            targets, host = pinned_api_urls(url)
            return targets[0], host
        except requests.exceptions.ConnectionError:
            if attempt == attempts:
                raise VaultTransportError(f"Vault API DNS unavailable after {attempts} attempts") from None
            time.sleep(backoff * attempt)


def vault_http_request(method, url, payload, timeout):
    targets, original_host = pinned_api_urls(url)
    host = os.getenv("BW_API_HOST", "").strip() or original_host
    # Host is an ASCII authority, not a free-form HTTP header value.
    if not host.isascii() or any(ord(character) <= 32 or ord(character) == 127 for character in host):
        raise VaultTransportError("Invalid vault API Host header")
    try:
        with requests.Session() as session:
            session.trust_env = False
            for index, target in enumerate(targets):
                try:
                    response = session.request(method, target, json=payload,
                                               # Share only the connect budget across addresses.
                                               timeout=(timeout / len(targets), timeout),
                                               headers={"Host": host}, allow_redirects=False)
                    break
                except requests.exceptions.ConnectionError as error:
                    # A body read timeout/reset can also be a ConnectionError.
                    # Fall back only when connection setup failed before sending.
                    cause = error.args[0] if error.args else None
                    before_send = (isinstance(error, requests.exceptions.ConnectTimeout) or
                                   isinstance(cause, MaxRetryError) and
                                   isinstance(cause.reason, NewConnectionError))
                    if not before_send or index == len(targets) - 1:
                        raise
    except requests.exceptions.RequestException as error:
        # Requests exceptions may contain the target URL or credentials; keep the class only.
        message = f"Vault API network request failed ({type(error).__name__})"
        try:
            sanitized = type(error)(message)
        except TypeError:
            sanitized = requests.exceptions.RequestException(message)
        raise sanitized from None
    if 300 <= response.status_code < 400:
        raise VaultTransportError("Vault API redirects are refused")
    return response
