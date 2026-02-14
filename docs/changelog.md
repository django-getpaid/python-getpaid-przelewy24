# Changelog

## v0.1.0 (2026-02-14)

Initial release.

### Features

- Full Przelewy24 REST API coverage
- Async HTTP client (`P24Client`) with HTTP Basic Auth
- Payment processor (`P24Processor`) implementing `BaseProcessor`
- Transaction registration and verification
- SHA-384 signature calculation and verification
- Batch refund support
- Transaction lookup by session ID
- Refund lookup by order ID
- Payment methods retrieval
- Connection testing (`testAccess`)
- PUSH callback handling with mandatory verify step
- PULL status polling
- Amount conversion (`Decimal` <-> integer lowest currency unit)
