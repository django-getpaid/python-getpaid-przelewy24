"""Tests for P24Processor: prepare, fetch, refund."""

import json
from decimal import Decimal

import pytest
from getpaid_core.exceptions import LockFailure

from getpaid_przelewy24.processor import P24Processor

from .conftest import P24_CONFIG
from .conftest import make_mock_payment


SANDBOX_URL = "https://sandbox.przelewy24.pl"
REGISTER_URL = f"{SANDBOX_URL}/api/v1/transaction/register"
VERIFY_URL = f"{SANDBOX_URL}/api/v1/transaction/verify"
REFUND_URL = f"{SANDBOX_URL}/api/v1/transaction/refund"


def _make_processor(payment=None, config=None):
    """Create a P24Processor with defaults."""
    if payment is None:
        payment = make_mock_payment()
    if config is None:
        config = P24_CONFIG.copy()
    return P24Processor(payment=payment, config=config)


class TestPrepareTransaction:
    """Tests for prepare_transaction."""

    async def test_prepare_returns_redirect(self, respx_mock):
        respx_mock.post(REGISTER_URL).respond(
            json={"data": {"token": "TKN-ABC123"}},
            status_code=200,
        )
        processor = _make_processor()
        result = await processor.prepare_transaction()

        assert result["redirect_url"] == (
            f"{SANDBOX_URL}/trnRequest/TKN-ABC123"
        )
        assert result["method"] == "GET"
        assert result["form_data"] is None

    async def test_prepare_sends_correct_data(self, respx_mock):
        route = respx_mock.post(REGISTER_URL).respond(
            json={"data": {"token": "TKN-ABC123"}},
            status_code=200,
        )
        processor = _make_processor()
        await processor.prepare_transaction()

        body = json.loads(route.calls.last.request.content)
        assert body["sessionId"] == "test-payment-123"
        assert body["amount"] == 10000  # 100.00 * 100
        assert body["currency"] == "PLN"
        assert body["email"] == "john@example.com"
        assert body["description"] == "Test order"
        assert (
            body["urlStatus"]
            == "https://shop.example.com/payments/callback/test-payment-123"
        )
        assert (
            body["urlReturn"]
            == "https://shop.example.com/payments/success/test-payment-123"
        )

    async def test_prepare_failure_raises(self, respx_mock):
        respx_mock.post(REGISTER_URL).respond(
            json={"error": "Bad request"},
            status_code=400,
        )
        processor = _make_processor()
        with pytest.raises(LockFailure):
            await processor.prepare_transaction()

    async def test_custom_customer_ip_passed(self, respx_mock):
        route = respx_mock.post(REGISTER_URL).respond(
            json={"data": {"token": "TKN-ABC123"}},
            status_code=200,
        )
        processor = _make_processor()
        await processor.prepare_transaction(customer_ip="192.168.1.1")
        # customer_ip isn't a P24 field — just verify it doesn't crash
        assert route.call_count == 1


class TestFetchPaymentStatus:
    """Tests for fetch_payment_status (PULL flow)."""

    async def test_status_payment_made(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/transaction/by/sessionId/test-payment-123"
        respx_mock.get(url).respond(
            json={"data": {"status": 2, "amount": 10000}},
            status_code=200,
        )
        processor = _make_processor()
        result = await processor.fetch_payment_status()
        assert result["status"] == "confirm_payment"

    async def test_status_no_payment(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/transaction/by/sessionId/test-payment-123"
        respx_mock.get(url).respond(
            json={"data": {"status": 0}},
            status_code=200,
        )
        processor = _make_processor()
        result = await processor.fetch_payment_status()
        assert result["status"] is None

    async def test_status_advance_payment(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/transaction/by/sessionId/test-payment-123"
        respx_mock.get(url).respond(
            json={"data": {"status": 1}},
            status_code=200,
        )
        processor = _make_processor()
        result = await processor.fetch_payment_status()
        assert result["status"] == "confirm_prepared"

    async def test_status_returned(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/transaction/by/sessionId/test-payment-123"
        respx_mock.get(url).respond(
            json={"data": {"status": 3}},
            status_code=200,
        )
        processor = _make_processor()
        result = await processor.fetch_payment_status()
        assert result["status"] == "confirm_refund"


class TestCharge:
    """Tests that charge() raises NotImplementedError."""

    async def test_charge_not_supported(self):
        processor = _make_processor()
        with pytest.raises(NotImplementedError):
            await processor.charge()


class TestReleaseLock:
    """Tests that release_lock() raises NotImplementedError."""

    async def test_release_lock_not_supported(self):
        processor = _make_processor()
        with pytest.raises(NotImplementedError):
            await processor.release_lock()


class TestStartRefund:
    """Tests for start_refund method."""

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
        processor = _make_processor(payment=payment)
        result = await processor.start_refund(amount=Decimal("50.00"))
        assert result == Decimal("50.00")

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
        processor = _make_processor(payment=payment)
        result = await processor.start_refund()
        assert result == Decimal("100.00")


class TestBuildPaywallContext:
    """Tests for _build_paywall_context."""

    def test_builds_correct_structure(self):
        processor = _make_processor()
        context = processor._build_paywall_context()

        assert context["session_id"] == "test-payment-123"
        assert context["amount"] == Decimal("100.00")
        assert context["currency"] == "PLN"
        assert context["description"] == "Test order"
        assert context["email"] == "john@example.com"
        assert context["url_return"] == (
            "https://shop.example.com/payments/success/test-payment-123"
        )
        assert context["url_status"] == (
            "https://shop.example.com/payments/callback/test-payment-123"
        )

    def test_no_url_status_if_not_configured(self):
        config = P24_CONFIG.copy()
        del config["url_status"]
        processor = _make_processor(config=config)
        # Should not have url_status — will fall back to empty
        context = processor._build_paywall_context()
        assert context.get("url_status", "") == ""

    def test_no_url_return_if_not_configured(self):
        config = P24_CONFIG.copy()
        del config["url_return"]
        processor = _make_processor(config=config)
        context = processor._build_paywall_context()
        assert context.get("url_return", "") == ""


class TestGetClient:
    """Tests for _get_client helper."""

    def test_creates_client_with_sandbox(self):
        processor = _make_processor()
        client = processor._get_client()
        assert client.base_url == SANDBOX_URL
        assert client.merchant_id == 12345

    def test_creates_client_with_production(self):
        config = P24_CONFIG.copy()
        config["sandbox"] = False
        processor = _make_processor(config=config)
        client = processor._get_client()
        assert client.base_url == "https://secure.przelewy24.pl"
