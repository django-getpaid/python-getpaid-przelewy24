# Changelog

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
