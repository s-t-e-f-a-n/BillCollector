# Files

- [Recipe System](recipes.md) - How BillCollector recipes work as a contract: the YAML structure (services/steps/methods) validated by recipe-pw-schema.yaml, locator and page-level Playwright method chains, {{USERNAME}}/{{PASSWORD}}/{{OTP}} substitution (including the runner's fresh-TOTP re-fetch), expect_download nesting, graceful steps, and the validation, saving, and repair paths in the CLI and the UI editor.
- [Vault Transport and Security](vault-transport.md) - How BillCollector connects to the local vault API: BW_API_URL must be plain HTTP resolving only to loopback/private addresses, per-attempt DNS vetting with pinned numeric targets, proxy bypass and redirect refusal, and the VaultAPIError timeout/retry/4xx semantics in billcollector/vault.py.
