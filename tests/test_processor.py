"""Tests for P24Processor prepare, polling, and refunds."""

import json
from decimal import Decimal

import pytest
from getpaid_core.enums import BackendMethod
from getpaid_core.enums import PaymentEvent
from getpaid_core.exceptions import LockFailure
from getpaid_core.exceptions import RefundFailure

from getpaid_przelewy24.processor import P24Processor

from .conftest import P24_CONFIG
from .conftest import make_mock_payment


SANDBOX_URL = "https://sandbox.przelewy24.pl"
REGISTER_URL = f"{SANDBOX_URL}/api/v1/transaction/register"
REFUND_URL = f"{SANDBOX_URL}/api/v1/transaction/refund"


def _make_processor(payment=None, config=None):
    if payment is None:
        payment = make_mock_payment()
    if config is None:
        config = P24_CONFIG.copy()
    return P24Processor(payment=payment, config=config)


class TestPrepareTransaction:
    async def test_prepare_returns_redirect(self, respx_mock):
        respx_mock.post(REGISTER_URL).respond(
            json={"data": {"token": "TKN-ABC123"}},
            status_code=200,
        )
        result = await _make_processor().prepare_transaction()

        assert result.redirect_url == f"{SANDBOX_URL}/trnRequest/TKN-ABC123"
        assert result.method is BackendMethod.GET

    async def test_prepare_sends_correct_data(self, respx_mock):
        route = respx_mock.post(REGISTER_URL).respond(
            json={"data": {"token": "TKN-ABC123"}},
            status_code=200,
        )

        await _make_processor().prepare_transaction()

        body = json.loads(route.calls.last.request.content)
        assert body["sessionId"] == "test-payment-123"
        assert body["amount"] == 10000
        assert body["currency"] == "PLN"
        assert body["email"] == "john@example.com"

    async def test_prepare_failure_raises(self, respx_mock):
        respx_mock.post(REGISTER_URL).respond(
            json={"error": "Bad request"},
            status_code=400,
        )

        with pytest.raises(LockFailure):
            await _make_processor().prepare_transaction()


class TestFetchPaymentStatus:
    async def test_status_payment_made_returns_capture_update(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/transaction/by/sessionId/test-payment-123"
        respx_mock.get(url).respond(
            json={"data": {"status": 2, "amount": 10000}},
            status_code=200,
        )

        result = await _make_processor().fetch_payment_status()

        assert result is not None
        assert result.payment_event is PaymentEvent.PAYMENT_CAPTURED
        assert result.paid_amount == Decimal("100.00")

    async def test_status_no_payment_returns_none(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/transaction/by/sessionId/test-payment-123"
        respx_mock.get(url).respond(
            json={"data": {"status": 0}},
            status_code=200,
        )

        result = await _make_processor().fetch_payment_status()

        assert result is None

    async def test_status_returned_returns_refund_update(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/transaction/by/sessionId/test-payment-123"
        respx_mock.get(url).respond(
            json={"data": {"status": 3, "amount": 10000}},
            status_code=200,
        )

        result = await _make_processor().fetch_payment_status()

        assert result is not None
        assert result.payment_event is PaymentEvent.REFUND_CONFIRMED
        assert result.refunded_amount == Decimal("100.00")


class TestUnsupportedOperations:
    async def test_charge_not_supported(self):
        with pytest.raises(NotImplementedError):
            await _make_processor().charge()

    async def test_release_lock_not_supported(self):
        with pytest.raises(NotImplementedError):
            await _make_processor().release_lock()


class TestRefunds:
    async def test_start_refund_with_amount(self, respx_mock):
        respx_mock.post(REFUND_URL).respond(
            json={
                "data": [
                    {
                        "orderId": 999,
                        "sessionId": "test-payment-123",
                        "amount": 5000,
                        "status": 0,
                    }
                ],
                "responseCode": 0,
            },
            status_code=200,
        )
        payment = make_mock_payment(external_id="999")
        payment.amount_paid = Decimal("100.00")

        result = await _make_processor(payment=payment).start_refund(
            amount=Decimal("50.00")
        )

        assert result.amount == Decimal("50.00")

    async def test_start_refund_full_amount(self, respx_mock):
        respx_mock.post(REFUND_URL).respond(
            json={
                "data": [
                    {
                        "orderId": 999,
                        "sessionId": "test-payment-123",
                        "amount": 10000,
                        "status": 0,
                    }
                ],
                "responseCode": 0,
            },
            status_code=200,
        )
        payment = make_mock_payment(external_id="999")
        payment.amount_paid = Decimal("100.00")

        result = await _make_processor(payment=payment).start_refund()

        assert result.amount == Decimal("100.00")

    async def test_start_refund_without_external_id_raises(self, respx_mock):
        """A payment that was never captured has no P24 orderId —
        refuse with a domain error instead of TypeError."""
        route = respx_mock.post(REFUND_URL)
        payment = make_mock_payment(external_id=None)
        payment.amount_paid = Decimal("100.00")

        with pytest.raises(RefundFailure, match="external_id"):
            await _make_processor(payment=payment).start_refund()

        assert not route.called
