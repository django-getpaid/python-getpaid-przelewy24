"""Tests for P24Processor callback handling."""

import hashlib
import json
import logging

import pytest
from getpaid_core.enums import PaymentEvent
from getpaid_core.exceptions import CommunicationError
from getpaid_core.exceptions import InvalidCallbackError

from getpaid_przelewy24.processor import P24Processor

from .conftest import P24_CONFIG


CRC_KEY: str = str(P24_CONFIG["crc_key"])
SANDBOX_URL = "https://sandbox.przelewy24.pl"
VERIFY_URL = f"{SANDBOX_URL}/api/v1/transaction/verify"


def _make_processor(payment=None, config=None):
    from .conftest import make_mock_payment

    if payment is None:
        payment = make_mock_payment()
    if config is None:
        config = P24_CONFIG.copy()
    return P24Processor(payment=payment, config=config)


def _sign(fields: dict, crc: str = CRC_KEY) -> str:
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
    return {**fields, "sign": _sign(fields)}


class TestVerifyCallback:
    async def test_valid_signature(self):
        processor = _make_processor()
        await processor.verify_callback(data=_notification_data(), headers={})

    async def test_missing_sign_raises(self):
        processor = _make_processor()
        data = _notification_data()
        del data["sign"]

        with pytest.raises(InvalidCallbackError, match="Missing sign"):
            await processor.verify_callback(data=data, headers={})

    async def test_bad_signature_raises(self):
        processor = _make_processor()
        data = _notification_data()
        data["sign"] = "bad_signature"

        with pytest.raises(InvalidCallbackError, match=r"Invalid signature"):
            await processor.verify_callback(data=data, headers={})

    async def test_bad_signature_does_not_leak_expected_sign(self, caplog):
        """Neither exception nor logs may disclose the expected sign
        (signature oracle)."""
        processor = _make_processor()
        data = _notification_data()
        expected_sign = data["sign"]  # correct sign for these fields
        data["sign"] = "bad_signature"

        with (
            caplog.at_level(logging.DEBUG),
            pytest.raises(InvalidCallbackError) as excinfo,
        ):
            await processor.verify_callback(data=data, headers={})

        assert expected_sign not in str(excinfo.value)
        for record in caplog.records:
            assert expected_sign not in record.getMessage()


class TestCallbackBinding:
    """The notification must be bound to OUR payment — a valid
    signature over attacker-chosen fields is not enough."""

    async def test_verify_rejects_foreign_session_id(self):
        processor = _make_processor()
        data = _notification_data(session_id="someone-elses-payment")

        with pytest.raises(InvalidCallbackError, match="sessionId"):
            await processor.verify_callback(data=data, headers={})

    async def test_verify_rejects_wrong_amount(self):
        processor = _make_processor()
        # Payment requires 100.00 PLN == 10000; attacker posts 1 grosz.
        data = _notification_data(amount=1)

        with pytest.raises(InvalidCallbackError, match="amount"):
            await processor.verify_callback(data=data, headers={})

    async def test_verify_rejects_wrong_currency(self):
        processor = _make_processor()
        data = _notification_data(currency="HUF")

        with pytest.raises(InvalidCallbackError, match="currency"):
            await processor.verify_callback(data=data, headers={})

    async def test_handle_rejects_mismatch_without_calling_verify(
        self, respx_mock
    ):
        route = respx_mock.put(VERIFY_URL).respond(
            json={"data": {"status": "success"}},
            status_code=200,
        )
        processor = _make_processor()
        data = _notification_data(amount=1, origin_amount=1)

        with pytest.raises(InvalidCallbackError):
            await processor.handle_callback(data=data, headers={})

        assert not route.called

    async def test_handle_verifies_with_our_payment_values(self, respx_mock):
        route = respx_mock.put(VERIFY_URL).respond(
            json={"data": {"status": "success"}},
            status_code=200,
        )
        processor = _make_processor()

        await processor.handle_callback(
            data=_notification_data(),
            headers={},
        )

        body = json.loads(route.calls.last.request.content)
        assert body["sessionId"] == "test-payment-123"
        assert body["amount"] == 10000
        assert body["currency"] == "PLN"
        assert body["orderId"] == 999


class TestHandleCallback:
    async def test_successful_verification_returns_paid_update(
        self, respx_mock
    ):
        respx_mock.put(VERIFY_URL).respond(
            json={"data": {"status": "success"}},
            status_code=200,
        )
        processor = _make_processor()

        update = await processor.handle_callback(
            data=_notification_data(),
            headers={},
        )

        assert update is not None
        assert update.payment_event is PaymentEvent.PAYMENT_CAPTURED
        assert update.external_id == "999"

    async def test_failed_verification_raises_communication_error(
        self, respx_mock
    ):
        respx_mock.put(VERIFY_URL).respond(
            json={"error": "Verification failed"},
            status_code=400,
        )
        processor = _make_processor()

        with pytest.raises(CommunicationError):
            await processor.handle_callback(
                data=_notification_data(), headers={}
            )

    async def test_same_notification_generates_same_event_id(self, respx_mock):
        respx_mock.put(VERIFY_URL).respond(
            json={"data": {"status": "success"}},
            status_code=200,
        )
        processor = _make_processor()
        data = _notification_data()

        first = await processor.handle_callback(data=data, headers={})
        second = await processor.handle_callback(data=data, headers={})

        assert first is not None
        assert second is not None
        assert first.provider_event_id == second.provider_event_id
