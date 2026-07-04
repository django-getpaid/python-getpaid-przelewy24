# Changelog

## v3.2.0 (2026-07-04)

### Important

- **The published v3.1.0 is broken and does not import** (see below).
  It should be **yanked from PyPI** — any install of
  `python-getpaid-przelewy24==3.1.0` fails at import time.

### Fixed

- **Import failure**: restored the `from enum import StrEnum` import in
  `types.py` that was dropped in the "use core AutoName" refactor,
  leaving `Language(StrEnum)` referencing an undefined name.
- **Import failure**: `processor.py` imported `ChargeResponse` from
  `getpaid_core.types` — that symbol never existed in any released
  core. It now imports and uses `ChargeResult`.
- Core dependency floor raised to `python-getpaid-core>=3.1.0`
  (`ChargeResult` and `AutoName` are only exported from 3.1.0 on).

### Security

- Signature verification failures no longer log or embed the
  **expected** SHA-384 sign — doing so acted as a signature oracle
  letting an attacker iteratively forge valid notifications.
- Notifications are now **bound to the payment**: `verify_callback`
  and `handle_callback` reject payloads whose `sessionId`, `amount`
  or `currency` do not match the local payment record, and the
  mandatory verify call is made with the payment's own values, not
  attacker-postable payload values.
- Error contexts no longer attach the raw `httpx.Response` (whose
  request headers carry the Basic-auth `Authorization` header).
  They now carry a sanitized dict with only the status code and a
  truncated body.

### Changed

- Amount conversion now uses `Decimal` quantization with
  ROUND_HALF_UP and an explicit per-currency exponent map instead of
  truncating `int(amount * 100)` (10.005 now converts to 1001, not
  1000).
- Removed `HRK` from supported currencies — Croatia uses EUR since
  2023-01-01.
- HTTP requests use an explicit, configurable timeout
  (default `httpx.Timeout(10.0, connect=5.0)`).
- `verify_transaction` retries transient transport failures
  (2 retries with backoff) — it is idempotent and mandatory for
  funds settlement; terminal transport failures raise
  `CommunicationError`.
- `start_refund` raises `RefundFailure` instead of `TypeError`
  when the payment has no `external_id` (P24 orderId).
- `P24Client.last_response` is now an instance attribute instead of
  a shared mutable class attribute.
- Release workflow now runs only after the CI workflow succeeds on
  `main`.

## v3.1.0 (2026-06-20) — BROKEN, DO NOT USE

- **This release does not import** (`NameError: StrEnum` in
  `types.py` and `ImportError: ChargeResponse` in `processor.py`).
  It is recommended to yank it from PyPI. All fixes land in the next
  release (see Unreleased).
- Refactor: use core `AutoName` for `Currency`, lazy imports in
  `__init__` (this refactor introduced the import breakage).
- CI: added pip-audit dependency vulnerability scanning.

## v3.0.0 (2026-06-04)

Stable release of the Przelewy24 payment gateway integration.

### Breaking Changes

- Version bumped from `3.0.0a4` to `3.0.0` (stable).
- Development status changed from `Alpha` to `Production/Stable`.
- Core dependency floor raised to `>=3.0.0` (from `>=3.0.0a4`).

### Features

- Full Przelewy24 REST API v1.1 coverage with async HTTP client.
- SHA-384 signature calculation and verification for notifications.
- Transaction registration and verification flow.
- Batch refund support.
- Transaction lookup by session ID.
- Refund lookup by order ID.
- Payment methods retrieval.
- Connection testing (`testAccess`).
- PUSH callback handling with mandatory verify step.
- PULL status polling.
- Support for 13 currencies: PLN, EUR, GBP, USD, CZK, BGN, DKK, HUF, NOK, SEK, CHF, RON, HRK.

### Migration from alpha

- Update dependency from `python-getpaid-przelewy24>=3.0.0a4` to `python-getpaid-przelewy24>=3.0.0`.
- No API changes — all public interfaces remain stable.
