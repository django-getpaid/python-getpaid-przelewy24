"""Tests for P24Processor verify_callback and handle_callback."""

import hashlib
import json

import pytest
from getpaid_core.enums import PaymentStatus
from getpaid_core.exceptions import CommunicationError
from getpaid_core.exceptions import InvalidCallbackError
from getpaid_core.fsm import create_payment_machine

from getpaid_przelewy24.processor import P24Processor

from .conftest import P24_CONFIG
from .conftest import FakePayment
from .conftest import make_mock_payment


CRC_KEY: str = str(P24_CONFIG["crc_key"])


def _make_processor(payment=None, config=None):
    """Create a P24Processor with defaults."""
    if payment is None:
        payment = make_mock_payment()
    if config is None:
        config = P24_CONFIG.copy()
    return P24Processor(payment=payment, config=config)


def _sign(fields: dict, crc: str = CRC_KEY) -> str:
    """Compute SHA-384 sign for notification fields."""
    payload = {**fields, "crc": crc}
    data = json.dumps(payload, separators=(",", ":"))
    return hashlib.sha384(data.encode()).hexdigest()


def _notification_data(
    *,
    session_id: str = "test-payment-123",
    order_id: int = 999,
    amount: int = 10000,
    origin_amount: int = 10000,
    currency: str = "PLN",
    merchant_id: int = 12345,
    pos_id: int = 12345,
    method_id: int = 25,
    statement: str = "payment",
) -> dict:
    """Build a valid P24 notification payload with correct sign."""
    fields = {
        "merchantId": merchant_id,
        "posId": pos_id,
        "sessionId": session_id,
        "amount": amount,
        "originAmount": origin_amount,
        "currency": currency,
        "orderId": order_id,
        "methodId": method_id,
        "statement": statement,
    }
    return {
        **fields,
        "sign": _sign(fields),
    }


class TestVerifyCallback:
    """Tests for verify_callback signature verification."""

    async def test_valid_signature(self):
        data = _notification_data()
        processor = _make_processor()
        # Should not raise
        await processor.verify_callback(data=data, headers={})

    async def test_missing_sign_raises(self):
        data = _notification_data()
        del data["sign"]
        processor = _make_processor()
        with pytest.raises(InvalidCallbackError, match="Missing sign"):
            await processor.verify_callback(data=data, headers={})

    async def test_bad_signature_raises(self):
        data = _notification_data()
        data["sign"] = "bad_signature"
        processor = _make_processor()
        with pytest.raises(InvalidCallbackError, match="BAD SIGNATURE"):
            await processor.verify_callback(data=data, headers={})

    async def test_tampered_amount_raises(self):
        """If amount is changed after signing, verification fails."""
        data = _notification_data(amount=10000)
        data["amount"] = 99999  # tamper
        processor = _make_processor()
        with pytest.raises(InvalidCallbackError):
            await processor.verify_callback(data=data, headers={})

    async def test_missing_required_field_raises(self):
        data = _notification_data()
        del data["statement"]
        processor = _make_processor()
        with pytest.raises(
            InvalidCallbackError,
            match="Missing required callback fields",
        ):
            await processor.verify_callback(data=data, headers={})


SANDBOX_URL = "https://sandbox.przelewy24.pl"
VERIFY_URL = f"{SANDBOX_URL}/api/v1/transaction/verify"


class TestHandleCallback:
    """Tests for handle_callback with FSM transitions."""

    async def test_successful_verification_marks_paid(self, respx_mock):
        """Successful verify_transaction moves payment to PAID."""
        respx_mock.put(VERIFY_URL).respond(
            json={"data": {"status": "success"}},
            status_code=200,
        )
        payment = FakePayment(status=PaymentStatus.PREPARED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = _notification_data()
        await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.PAID

    async def test_failed_verification_raises_communication_error(
        self, respx_mock
    ):
        """Gateway verification failures should be retriable."""
        respx_mock.put(VERIFY_URL).respond(
            json={"error": "Verification failed"},
            status_code=400,
        )
        payment = FakePayment(status=PaymentStatus.PREPARED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = _notification_data()
        with pytest.raises(CommunicationError):
            await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.PREPARED

    async def test_stores_external_id(self, respx_mock):
        """handle_callback stores orderId as external_id."""
        respx_mock.put(VERIFY_URL).respond(
            json={"data": {"status": "success"}},
            status_code=200,
        )
        payment = FakePayment(status=PaymentStatus.PREPARED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = _notification_data(order_id=42)
        await processor.handle_callback(data=data, headers={})

        assert payment.external_id == "42"

    async def test_duplicate_callback_no_crash(self, respx_mock):
        """Duplicate callback on PAID payment does not crash."""
        respx_mock.put(VERIFY_URL).respond(
            json={"data": {"status": "success"}},
            status_code=200,
        )
        payment = FakePayment(status=PaymentStatus.PAID)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = _notification_data()
        # may_trigger returns False, no crash
        await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.PAID

    async def test_callback_from_new_status(self, respx_mock):
        """Callback on NEW payment — confirm_payment is available
        from PREPARED only, so it should log debug and not crash."""
        respx_mock.put(VERIFY_URL).respond(
            json={"data": {"status": "success"}},
            status_code=200,
        )
        payment = FakePayment(status=PaymentStatus.NEW)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = _notification_data()
        await processor.handle_callback(data=data, headers={})

        # confirm_payment not available from NEW
        assert payment.status == PaymentStatus.NEW
