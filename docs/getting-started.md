# Getting Started

## Installation

Install getpaid-przelewy24 from PyPI (distributed as `python-getpaid-przelewy24`):

```bash
pip install python-getpaid-przelewy24
```

Or add it as a dependency with uv:

```bash
uv add python-getpaid-przelewy24
```

This will also install `python-getpaid-core` and `httpx` as dependencies.

## About This Plugin

getpaid-przelewy24 is a **payment gateway plugin** for the python-getpaid
ecosystem. It can be used in two ways:

1. **Standalone** — use `P24Client` directly to interact with the Przelewy24
   REST API from any Python application.
2. **With django-getpaid** — register `P24Processor` as a payment backend and
   let the framework handle the payment lifecycle.

## Standalone Usage

The `P24Client` is an async HTTP client that wraps the Przelewy24 REST API.
Use it as an async context manager for connection reuse:

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
        # 1. Test connection
        ok = await client.test_access()
        print(f"Connection OK: {ok}")

        # 2. Register a transaction
        response = await client.register_transaction(
            session_id="order-001",
            amount=Decimal("49.99"),
            currency="PLN",
            description="Order #001",
            email="buyer@example.com",
            url_return="https://shop.example.com/return/order-001",
            url_status="https://shop.example.com/callback/order-001",
        )

        # 3. Get redirect URL
        token = response["data"]["token"]
        redirect_url = client.get_transaction_redirect_url(token)
        print(f"Redirect buyer to: {redirect_url}")

asyncio.run(main())
```

## Using with django-getpaid

### 1. Register the entry point

Add the processor to your plugin's or application's `pyproject.toml`:

```toml
[project.entry-points."getpaid.backends"]
przelewy24 = "getpaid_przelewy24.processor:P24Processor"
```

### 2. Configure backend settings

In your Django settings (or config dict passed to the processor):

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

The `{payment_id}` placeholder in URL templates is replaced with the actual
payment ID at runtime.

### 3. Process payments

The framework adapter handles the rest — creating payments, redirecting
buyers, receiving callbacks, and updating payment status via the FSM.

## Sandbox vs Production

By default, `sandbox=True`, which uses `https://sandbox.przelewy24.pl`.
Set `sandbox=False` for production, which uses `https://secure.przelewy24.pl`.

You can obtain sandbox credentials from the
[Przelewy24 sandbox panel](https://sandbox.przelewy24.pl/panel/).
Production credentials are available in the
[Przelewy24 merchant panel](https://secure.przelewy24.pl/panel/).
