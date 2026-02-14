# Concepts

## Payment Flow

The Przelewy24 payment flow follows a register-redirect-verify pattern:

```
┌──────────┐     register_transaction     ┌──────────┐
│  Your    │ ──────────────────────────►  │   P24    │
│  Server  │  ◄── token ──────────────── │   API    │
└────┬─────┘                              └──────────┘
     │
     │  redirect buyer to
     │  P24 payment page
     ▼
┌──────────┐     buyer pays               ┌──────────┐
│  Buyer   │ ──────────────────────────►  │   P24    │
│ Browser  │                              │ Payment  │
└──────────┘                              │  Page    │
                                          └────┬─────┘
                                               │
                          notification (POST)  │
┌──────────┐  ◄────────────────────────────────┘
│  Your    │
│  Server  │  1. verify_callback (check SHA-384 sign)
│          │  2. handle_callback (call verify_transaction)
│          │  3. FSM: confirm_payment → mark_as_paid
└──────────┘
```

### Step by Step

1. **Register transaction** — `P24Processor.prepare_transaction()` calls
   `P24Client.register_transaction()` with payment details. P24 returns a
   token.

2. **Redirect** — the buyer is redirected to
   `https://{base_url}/trnRequest/{token}` where they complete the payment.

3. **Notification** — P24 sends a POST request to `url_status` with the
   notification payload (including `orderId`, `amount`, `sign`).

4. **Verify callback** — `P24Processor.verify_callback()` recalculates the
   SHA-384 signature from the notification fields + CRC key and compares it
   with the received `sign`. Raises `InvalidCallbackError` on mismatch.

5. **Handle callback** — `P24Processor.handle_callback()` calls
   `P24Client.verify_transaction()` to confirm the payment with P24.

6. **FSM update** — on successful verification, the payment transitions
   through `confirm_payment` → `mark_as_paid`.

:::{warning}
The `verify_transaction` call in step 5 is **mandatory**. Without it,
Przelewy24 treats the payment as an advance payment only — the funds will
not be settled to your account.
:::

## No Pre-Authorization Flow

Przelewy24 only supports direct payments. There is no lock/charge/release
cycle. The `charge()` and `release_lock()` methods on `P24Processor` raise
`NotImplementedError`.

## Refund Flow

```
┌──────────┐     start_refund             ┌──────────┐
│  Your    │ ──────────────────────────►  │   P24    │
│  Server  │                              │   API    │
└──────────┘                              └────┬─────┘
                                               │
                    refund notification (POST)  │
┌──────────┐  ◄─────────────────────────────────┘
│  Your    │
│  Server  │  Process refund notification
└──────────┘
```

1. `P24Processor.start_refund(amount)` calls `P24Client.refund()` with the
   refund details. P24 supports batch refunds — multiple refunds in a single
   request.

2. P24 sends a refund notification to `refund_url_status` with the refund
   status (0 = completed, 1 = rejected).

## SHA-384 Signature Calculation

All requests that require a signature use the same algorithm:

1. Build a dict of the fields to sign.
2. Append `"crc": crc_key` to the dict.
3. Serialize as compact JSON (no spaces): `json.dumps(d, separators=(",", ":"))`.
4. Compute `hashlib.sha384(data.encode()).hexdigest()`.

For transaction registration, the signed fields are:
`sessionId`, `merchantId`, `amount`, `currency`.

For transaction verification, the signed fields are:
`sessionId`, `orderId`, `amount`, `currency`.

For callback verification, the signed fields are:
`merchantId`, `posId`, `sessionId`, `amount`, `originAmount`, `currency`,
`orderId`, `methodId`, `statement`.

## Amount Handling

Przelewy24 expects amounts as **integers in the lowest currency unit** (e.g.,
grosze for PLN, cents for EUR). The client handles conversion automatically:

- `P24Client._to_lowest_unit(Decimal("49.99"))` → `4999`
- `P24Client._from_lowest_unit(4999)` → `Decimal("49.99")`

## PUSH vs PULL Status Checking

The plugin supports both notification models:

- **PUSH** — P24 sends a POST to `url_status` after payment. The processor
  handles it via `verify_callback()` + `handle_callback()`. This is the
  primary flow.

- **PULL** — `P24Processor.fetch_payment_status()` calls
  `P24Client.get_transaction_by_session_id()` to poll the transaction status.
  Returns a `PaymentStatusResponse` with the mapped status.

| P24 Status | Value | Mapped FSM Trigger |
|------------|-------|--------------------|
| `NO_PAYMENT` | 0 | `None` |
| `ADVANCE_PAYMENT` | 1 | `confirm_prepared` |
| `PAYMENT_MADE` | 2 | `confirm_payment` |
| `PAYMENT_RETURNED` | 3 | `confirm_refund` |

## Supported Operations

| Operation | Client Method | Processor Method | HTTP |
|-----------|--------------|------------------|------|
| Test connection | `test_access()` | — | `GET /api/v1/testAccess` |
| Register transaction | `register_transaction()` | `prepare_transaction()` | `POST /api/v1/transaction/register` |
| Verify transaction | `verify_transaction()` | `handle_callback()` | `PUT /api/v1/transaction/verify` |
| Refund | `refund()` | `start_refund()` | `POST /api/v1/transaction/refund` |
| Get transaction | `get_transaction_by_session_id()` | `fetch_payment_status()` | `GET /api/v1/transaction/by/sessionId/{id}` |
| Get refund | `get_refund_by_order_id()` | — | `GET /api/v1/refund/by/orderId/{id}` |
| Payment methods | `get_payment_methods()` | — | `GET /api/v1/payment/methods/{lang}` |
| Redirect URL | `get_transaction_redirect_url()` | `prepare_transaction()` | — (builds URL) |

## Supported Currencies

Przelewy24 supports 13 currencies:

PLN, EUR, GBP, CZK, USD, BGN, DKK, HUF, NOK, SEK, CHF, RON, HRK.

## Supported Languages

The payment page and payment methods API accept 13 language codes:

pl, en, de, es, it, cs, sk, fr, pt, hu, bg, ro, hr.
