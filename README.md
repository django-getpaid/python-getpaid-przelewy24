# getpaid-przelewy24

[![PyPI](https://img.shields.io/pypi/v/python-getpaid-przelewy24.svg)](https://pypi.org/project/python-getpaid-przelewy24/)
[![Python Version](https://img.shields.io/pypi/pyversions/python-getpaid-przelewy24)](https://pypi.org/project/python-getpaid-przelewy24/)
[![License](https://img.shields.io/pypi/l/python-getpaid-przelewy24)](https://github.com/django-getpaid/python-getpaid-przelewy24/blob/main/LICENSE)

[Przelewy24](https://www.przelewy24.pl/) payment gateway plugin for the
[python-getpaid](https://github.com/django-getpaid) ecosystem. Provides an
async HTTP client (`P24Client`) and a payment processor (`P24Processor`) that
integrates with getpaid-core's `BaseProcessor` interface. Authentication uses
HTTP Basic Auth against the Przelewy24 REST API.

## Architecture

The plugin is split into two layers:

- **`P24Client`** — low-level async HTTP client wrapping the Przelewy24 REST
  API. Uses `httpx.AsyncClient` with HTTP Basic Auth (pos_id / api_key). Can be
  used standalone or as an async context manager for connection reuse.
- **`P24Processor`** — high-level payment processor implementing
  `BaseProcessor`. Orchestrates transaction registration, callback verification,
  payment confirmation, status polling, and refunds. Integrates with the
  getpaid-core FSM for state transitions.

## Key Features

- **Register transaction** — create a payment session and get a redirect URL
- **Verify transaction** — mandatory confirmation after P24 callback (without
  this, P24 treats the payment as advance only)
- **Refund** — batch refund support via P24 API
- **Get transaction info** — look up transaction by session ID
- **Get refund info** — look up refunds by P24 order ID
- **Get payment methods** — retrieve available payment methods for a language
- **Test access** — verify API credentials
- **PUSH and PULL** — callback-based notifications with optional status polling
- **SHA-384 signatures** — automatic sign calculation and verification

## Quick Usage

### Standalone Client

```python
import asyncio
from decimal import Decimal
from getpaid_przelewy24 import P24Client

async def main():
    async with P24Client(
        merchant_id=12345,
        pos_id=12345,
        api_key="your-api-key",
        crc_key="your-crc-key",
        sandbox=True,
    ) as client:
        # Test connection
        ok = await client.test_access()
        print(f"Connection OK: {ok}")

        # Register a transaction
        response = await client.register_transaction(
            session_id="order-001",
            amount=Decimal("49.99"),
            currency="PLN",
            description="Order #001",
            email="buyer@example.com",
            url_return="https://shop.example.com/return/order-001",
            url_status="https://shop.example.com/callback/order-001",
        )
        token = response["data"]["token"]
        redirect_url = client.get_transaction_redirect_url(token)
        print(f"Redirect buyer to: {redirect_url}")

asyncio.run(main())
```

### With django-getpaid

Register the plugin via entry point in `pyproject.toml`:

```toml
[project.entry-points."getpaid.backends"]
przelewy24 = "getpaid_przelewy24.processor:P24Processor"
```

Then configure in your Django settings (or config dict):

```python
GETPAID_BACKEND_SETTINGS = {
    "przelewy24": {
        "merchant_id": 12345,
        "pos_id": 12345,
        "api_key": "your-api-key",
        "crc_key": "your-crc-key",
        "sandbox": True,
        "url_status": "https://shop.example.com/payments/{payment_id}/callback/",
        "url_return": "https://shop.example.com/payments/{payment_id}/return/",
        "refund_url_status": "https://shop.example.com/payments/{payment_id}/refund-callback/",
    }
}
```

## Configuration Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `merchant_id` | `int` | *required* | Merchant ID from P24 panel |
| `pos_id` | `int` | *required* | POS ID (often same as merchant_id) |
| `api_key` | `str` | *required* | REST API key from P24 panel |
| `crc_key` | `str` | *required* | CRC key for signature calculation |
| `sandbox` | `bool` | `True` | Use sandbox (`sandbox.przelewy24.pl`) or production (`secure.przelewy24.pl`) |
| `url_status` | `str` | `""` | Callback URL template; use `{payment_id}` placeholder |
| `url_return` | `str` | `""` | Return URL template; use `{payment_id}` placeholder |
| `refund_url_status` | `str` | `""` | Refund callback URL template; use `{payment_id}` placeholder |

## Supported Currencies

PLN, EUR, GBP, CZK, USD, BGN, DKK, HUF, NOK, SEK, CHF, RON, HRK (13 total).

## Limitations

Przelewy24 does not support pre-authorization. The `charge()` and
`release_lock()` methods raise `NotImplementedError`.

## Requirements

- Python 3.12+
- `python-getpaid-core >= 0.1.0`
- `httpx >= 0.27.0`

## Related Projects

- [python-getpaid-core](https://github.com/django-getpaid/python-getpaid-core) — core abstractions (protocols, FSM, processor base class)
- [django-getpaid](https://github.com/django-getpaid/django-getpaid) — Django adapter (models, views, admin)

## License

MIT

## Disclaimer

This project has nothing in common with the
[getpaid](http://code.google.com/p/getpaid/) plone project.
It is part of the `django-getpaid` / `python-getpaid` ecosystem.

## Credits

Created by [Dominik Kozaczko](https://github.com/dekoza).
