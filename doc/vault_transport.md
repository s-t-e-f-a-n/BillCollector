# Vault HTTP transport

`BW_API_URL` must point to a local `bw serve` HTTP endpoint, not the remote
Bitwarden Cloud or Vaultwarden server. Loopback, RFC1918 IPv4 and IPv6 ULA
addresses are accepted. Every DNS answer must be in those ranges; DNS is checked
for each attempt and the connection uses a vetted numeric address. HTTP defaults
to port 80 when no port is specified. URL credentials, fragments, HTTPS and
public targets are refused before a request is made, and the configured
`BW_API_URL` base refuses query strings. Request URLs may carry an endpoint
query string (the exact-item search query), which is preserved in every pinned
target.

Requests ignore ambient proxy configuration and refuse redirects. The HTTP Host
header defaults to the configured API host/port; `BW_API_HOST` optionally overrides
it for a `bw serve` host check. `bw serve` accepts only `Host: 127.0.0.1:<port>`
(DNS-rebinding protection), so a client in another container sets
`BW_API_HOST=127.0.0.1:8087`. The upstream timeout,
retry/backoff, final 4xx and optional-TOTP behavior remain in the existing client.
`VAULT_HOST` is no longer used; the backend vault may be Cloud-hosted while its
CLI API remains local. HTTPS is refused because `bw serve` itself speaks HTTP;
a TLS proxy in front of it is not supported by this client.

This is target enforcement, not API authentication. `bw serve` must remain on a
trusted private network. Credential retrieval searches the item list for the
configured name, requires exactly one exact (case-sensitive) match, and fetches
the item and its optional TOTP by that validated item id; missing, ambiguous or
changed identities fail with a sanitized error that retains no names, queries,
credentials or response bodies.

Verification uses `python -m unittest tests.test_vault_transport -v`, with mocked
DNS/HTTP and a synthetic loopback partial-response server. To roll back, revert
this contribution; no vault state is migrated.

DNS answers "temporarily unavailable", "name unknown", "no data" and "server
failure" are retried with the request policy (`VAULT_MAX_ATTEMPTS`, backoff
`VAULT_RETRY_BACKOFF`) in preflight and in the request loop, so a `bw serve`
container that is being recreated is waited for. Policy failures (non-local or
mixed answers, invalid URL) remain final.
All local answers are vetted before any connection; connection failures try
remaining vetted addresses in deterministic order only after connection-setup
failures before sending the request. Each address receives an
equal share of the per-attempt connect timeout; the read timeout stays the full
`VAULT_TIMEOUT`. A read timeout does not trigger address fallback.
Host overrides must be ASCII without whitespace/control characters.
