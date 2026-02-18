# python-getpaid-przelewy24

[![PyPI version](https://img.shields.io/pypi/v/python-getpaid-przelewy24.svg)](https://pypi.org/project/python-getpaid-przelewy24/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python versions](https://img.shields.io/pypi/pyversions/python-getpaid-przelewy24.svg)](https://pypi.org/project/python-getpaid-przelewy24/)

**Przelewy24 payment processor for the [python-getpaid](https://github.com/django-getpaid/python-getpaid-core) ecosystem.**

[Przelewy24](https://www.przelewy24.pl/) is a leading Polish payment service provider that supports a wide range of payment methods, including bank transfers (pay-by-link), credit cards, and e-wallets (BLIK, Google Pay, Apple Pay).

This package provides a clean, async-first integration with the Przelewy24 REST API v1.1, implementing the standard `python-getpaid` processor interface.

## Features

- **Direct Payment Flow**: Full implementation of the `register -> redirect -> notification -> verify` flow.
- **Secure by Default**: Automatic signature verification (SHA-384) for all incoming notifications from Przelewy24.
- **Async-First**: Built on top of `httpx` for efficient, non-blocking I/O.
- **Multi-Currency Support**: PLN, EUR, GBP, USD, CZK, BGN, DKK, HUF, NOK, SEK, CHF, RON, HRK.
- **Sandbox Support**: Easy switching between Sandbox and Production environments.
- **Payment Status Polling**: Support for the PULL flow to check transaction status via API.
- **Refunds**: Full support for processing refunds through the Przelewy24 API.
- **FSM Integration**: Seamlessly integrates with the `python-getpaid-core` finite state machine for robust payment state management.

## Installation

Install the package using `pip`:

```bash
pip install python-getpaid-przelewy24
```

Or using `uv`:

```bash
uv add python-getpaid-przelewy24
```

## Quick Start

### Configuration

Add `przelewy24` to your `python-getpaid` configuration. For example, in a Django project using `django-getpaid`:

```python
GETPAID_BACKEND_SETTINGS = {
    "przelewy24": {
        "merchant_id": 12345,
        "pos_id": 12345,  # Usually the same as merchant_id
        "api_key": "your_api_key_here",
        "crc_key": "your_crc_key_here",
        "sandbox": True,  # Use True for testing, False for production
        "url_status": "https://your-domain.com/payments/p24/status/{payment_id}/",
        "url_return": "https://your-domain.com/payments/p24/return/{payment_id}/",
    }
}
```

### Configuration Parameters

| Key | Type | Description |
|-----|------|-------------|
| `merchant_id` | `int` | Your Przelewy24 Merchant ID. |
| `pos_id` | `int` | Your Przelewy24 POS ID (defaults to `merchant_id`). |
| `api_key` | `str` | REST API Key from the Przelewy24 panel. |
| `crc_key` | `str` | CRC Key from the Przelewy24 panel (used for signing). |
| `sandbox` | `bool` | If `True` (default), uses the P24 Sandbox environment. |
| `url_status` | `str` | Callback URL for asynchronous notifications. Supports `{payment_id}`. |
| `url_return` | `str` | Return URL after payment completion. Supports `{payment_id}`. |
| `refund_url_status` | `str` | (Optional) Callback URL for refund status notifications. |

Both `url_status`, `url_return`, and `refund_url_status` can include the `{payment_id}` placeholder, which will be automatically replaced with the actual payment ID.

## Standalone Usage

While designed to work with `python-getpaid` framework wrappers, you can also use the `P24Client` directly:

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
        # Register a transaction
        response = await client.register_transaction(
            session_id="order-001",
            amount=Decimal("49.99"),
            currency="PLN",
            description="Order #001",
            email="buyer@example.com",
            url_return="https://shop.example.com/return/",
            url_status="https://shop.example.com/callback/",
        )
        token = response["data"]["token"]
        print(f"Redirect URL: {client.get_transaction_redirect_url(token)}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Requirements

- Python 3.12 or 3.13
- `python-getpaid-core >= 3.0.0a2`
- `httpx >= 0.27.0`

## License

This project is licensed under the MIT License.

## Links

- [python-getpaid-core](https://github.com/django-getpaid/python-getpaid-core)
- [django-getpaid](https://github.com/django-getpaid/django-getpaid)
- [litestar-getpaid](https://github.com/django-getpaid/litestar-getpaid)
- [fastapi-getpaid](https://github.com/django-getpaid/fastapi-getpaid)
- [Przelewy24 API Documentation](https://developers.przelewy24.pl/)

---
Created by [Dominik Kozaczko](https://github.com/dekoza).
Part of the `python-getpaid` ecosystem.
