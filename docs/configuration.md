# Configuration

## Configuration Keys

All settings are passed as a dictionary to the processor (via
`BaseProcessor.get_setting()`) or directly to `P24Client.__init__()`.

| Key | Type | Default | Required | Description |
|-----|------|---------|----------|-------------|
| `merchant_id` | `int` | — | Yes | Merchant ID assigned by Przelewy24 |
| `pos_id` | `int` | — | Yes | POS (Point of Sale) ID; often the same as `merchant_id` |
| `api_key` | `str` | — | Yes | REST API key for HTTP Basic Auth |
| `crc_key` | `str` | — | Yes | CRC key used for SHA-384 signature calculation |
| `sandbox` | `bool` | `True` | No | Use sandbox environment (`True`) or production (`False`) |
| `url_status` | `str` | `""` | No | Callback URL template for payment notifications |
| `url_return` | `str` | `""` | No | URL template to redirect buyer after payment |
| `refund_url_status` | `str` | `""` | No | Callback URL template for refund notifications |

### URL Templates

The `url_status`, `url_return`, and `refund_url_status` settings support a
`{payment_id}` placeholder that is replaced with the actual payment ID at
runtime:

```python
"url_status": "https://shop.example.com/payments/{payment_id}/callback/"
# becomes: https://shop.example.com/payments/abc123/callback/
```

## Example Configuration

```python
GETPAID_BACKEND_SETTINGS = {
    "przelewy24": {
        "merchant_id": 12345,
        "pos_id": 12345,
        "api_key": "a1b2c3d4e5f6",
        "crc_key": "f6e5d4c3b2a1",
        "sandbox": False,
        "url_status": "https://shop.example.com/payments/{payment_id}/callback/",
        "url_return": "https://shop.example.com/payments/{payment_id}/return/",
        "refund_url_status": "https://shop.example.com/payments/{payment_id}/refund-callback/",
    }
}
```

## Where to Find Credentials

All four required credentials are available in the Przelewy24 merchant panel:

1. **merchant_id** — displayed on the main dashboard after login
2. **pos_id** — found under *My shops* (Moje sklepy); for most merchants this
   is the same value as `merchant_id`
3. **api_key** — generated under *My shops → Shop configuration → API key*
4. **crc_key** — generated under *My shops → Shop configuration → CRC key*

:::{important}
The `api_key` and `crc_key` are secrets. Never commit them to version control.
Use environment variables or a secrets manager.
:::

## Sandbox vs Production

| Setting | Sandbox | Production |
|---------|---------|------------|
| `sandbox` | `True` | `False` |
| Base URL | `https://sandbox.przelewy24.pl` | `https://secure.przelewy24.pl` |
| Panel | [sandbox.przelewy24.pl/panel](https://sandbox.przelewy24.pl/panel/) | [secure.przelewy24.pl/panel](https://secure.przelewy24.pl/panel/) |

:::{note}
The default value of `sandbox` is `True`. Always set it explicitly to `False`
for production deployments.
:::
