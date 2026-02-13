"""Comprehensive tests for P24Client."""

import hashlib
import json
from decimal import Decimal

import pytest
from getpaid_core.exceptions import CommunicationError
from getpaid_core.exceptions import CredentialsError
from getpaid_core.exceptions import LockFailure
from getpaid_core.exceptions import RefundFailure

from getpaid_przelewy24.client import P24Client


SANDBOX_URL = "https://sandbox.przelewy24.pl"
REGISTER_URL = f"{SANDBOX_URL}/api/v1/transaction/register"
VERIFY_URL = f"{SANDBOX_URL}/api/v1/transaction/verify"
TEST_ACCESS_URL = f"{SANDBOX_URL}/api/v1/testAccess"


def _make_client(
    *,
    merchant_id: int = 12345,
    pos_id: int = 12345,
    api_key: str = "test-api-key",
    crc_key: str = "test-crc-key",
    sandbox: bool = True,
) -> P24Client:
    return P24Client(
        merchant_id=merchant_id,
        pos_id=pos_id,
        api_key=api_key,
        crc_key=crc_key,
        sandbox=sandbox,
    )


class TestSign:
    """Tests for P24Client._calculate_sign."""

    def test_register_sign(self):
        """Sign for registration uses sessionId, merchantId,
        amount, currency, crc."""
        client = _make_client(crc_key="my-crc")
        sign = client._calculate_sign(
            {
                "sessionId": "sess-1",
                "merchantId": 12345,
                "amount": 100,
                "currency": "PLN",
            }
        )
        payload = json.dumps(
            {
                "sessionId": "sess-1",
                "merchantId": 12345,
                "amount": 100,
                "currency": "PLN",
                "crc": "my-crc",
            },
            separators=(",", ":"),
        )
        expected = hashlib.sha384(payload.encode()).hexdigest()
        assert sign == expected

    def test_verify_sign(self):
        """Sign for verification uses sessionId, orderId,
        amount, currency, crc."""
        client = _make_client(crc_key="my-crc")
        sign = client._calculate_sign(
            {
                "sessionId": "sess-1",
                "orderId": 999,
                "amount": 100,
                "currency": "PLN",
            }
        )
        payload = json.dumps(
            {
                "sessionId": "sess-1",
                "orderId": 999,
                "amount": 100,
                "currency": "PLN",
                "crc": "my-crc",
            },
            separators=(",", ":"),
        )
        expected = hashlib.sha384(payload.encode()).hexdigest()
        assert sign == expected

    def test_notification_sign(self):
        """Sign for notification verification uses many fields + crc."""
        client = _make_client(crc_key="my-crc")
        fields = {
            "merchantId": 12345,
            "posId": 12345,
            "sessionId": "sess-1",
            "amount": 100,
            "originAmount": 100,
            "currency": "PLN",
            "orderId": 999,
            "methodId": 25,
            "statement": "payment",
        }
        sign = client._calculate_sign(fields)
        payload = json.dumps(
            {**fields, "crc": "my-crc"},
            separators=(",", ":"),
        )
        expected = hashlib.sha384(payload.encode()).hexdigest()
        assert sign == expected


class TestAmountConversion:
    """Tests for _to_lowest_unit and _from_lowest_unit."""

    def test_to_lowest_unit_decimal(self):
        assert P24Client._to_lowest_unit(Decimal("1.23")) == 123

    def test_to_lowest_unit_integer(self):
        assert P24Client._to_lowest_unit(Decimal("100")) == 10000

    def test_to_lowest_unit_small(self):
        assert P24Client._to_lowest_unit(Decimal("0.01")) == 1

    def test_from_lowest_unit(self):
        assert P24Client._from_lowest_unit(123) == Decimal("1.23")

    def test_from_lowest_unit_large(self):
        assert P24Client._from_lowest_unit(10000) == Decimal("100.00")


class TestTestAccess:
    """Tests for test_access (connection check)."""

    async def test_test_access_success(self, respx_mock):
        respx_mock.get(TEST_ACCESS_URL).respond(
            json={"data": True}, status_code=200
        )
        client = _make_client()
        result = await client.test_access()
        assert result is True

    async def test_test_access_failure(self, respx_mock):
        respx_mock.get(TEST_ACCESS_URL).respond(status_code=401)
        client = _make_client()
        with pytest.raises(CredentialsError):
            await client.test_access()


class TestRegisterTransaction:
    """Tests for register_transaction."""

    async def test_register_success(self, respx_mock):
        respx_mock.post(REGISTER_URL).respond(
            json={"data": {"token": "TKN-ABC123"}},
            status_code=200,
        )
        client = _make_client()
        result = await client.register_transaction(
            session_id="sess-1",
            amount=Decimal("10.00"),
            currency="PLN",
            description="Test payment",
            email="john@example.com",
            url_return="https://shop.example.com/return",
            url_status="https://shop.example.com/callback",
        )
        assert result["data"]["token"] == "TKN-ABC123"

    async def test_register_sends_correct_body(self, respx_mock):
        route = respx_mock.post(REGISTER_URL).respond(
            json={"data": {"token": "TKN-ABC123"}},
            status_code=200,
        )
        client = _make_client()
        await client.register_transaction(
            session_id="sess-1",
            amount=Decimal("10.00"),
            currency="PLN",
            description="Test payment",
            email="john@example.com",
            url_return="https://shop.example.com/return",
            url_status="https://shop.example.com/callback",
        )
        body = json.loads(route.calls.last.request.content)
        assert body["sessionId"] == "sess-1"
        assert body["amount"] == 1000
        assert body["currency"] == "PLN"
        assert body["description"] == "Test payment"
        assert body["email"] == "john@example.com"
        assert body["merchantId"] == 12345
        assert body["posId"] == 12345
        assert "sign" in body

    async def test_register_uses_basic_auth(self, respx_mock):
        route = respx_mock.post(REGISTER_URL).respond(
            json={"data": {"token": "TKN-ABC123"}},
            status_code=200,
        )
        client = _make_client()
        await client.register_transaction(
            session_id="sess-1",
            amount=Decimal("10.00"),
            currency="PLN",
            description="Test",
            email="test@example.com",
            url_return="https://shop.example.com/return",
            url_status="https://shop.example.com/callback",
        )
        request = route.calls.last.request
        auth_header = request.headers.get("authorization", "")
        assert auth_header.startswith("Basic ")

    async def test_register_failure(self, respx_mock):
        respx_mock.post(REGISTER_URL).respond(
            json={"error": "Invalid data"},
            status_code=400,
        )
        client = _make_client()
        with pytest.raises(LockFailure):
            await client.register_transaction(
                session_id="sess-1",
                amount=Decimal("10.00"),
                currency="PLN",
                description="Test",
                email="test@example.com",
                url_return="https://shop.example.com/return",
                url_status="https://shop.example.com/callback",
            )

    async def test_register_with_optional_params(self, respx_mock):
        route = respx_mock.post(REGISTER_URL).respond(
            json={"data": {"token": "TKN-ABC123"}},
            status_code=200,
        )
        client = _make_client()
        await client.register_transaction(
            session_id="sess-1",
            amount=Decimal("10.00"),
            currency="PLN",
            description="Test",
            email="test@example.com",
            url_return="https://shop.example.com/return",
            url_status="https://shop.example.com/callback",
            language="pl",
            country="PL",
            time_limit=15,
            channel=1,
            transfer_label="ORDER-123",
        )
        body = json.loads(route.calls.last.request.content)
        assert body["language"] == "pl"
        assert body["country"] == "PL"
        assert body["timeLimit"] == 15
        assert body["channel"] == 1
        assert body["transferLabel"] == "ORDER-123"


class TestVerifyTransaction:
    """Tests for verify_transaction."""

    async def test_verify_success(self, respx_mock):
        respx_mock.put(VERIFY_URL).respond(
            json={"data": {"status": "success"}},
            status_code=200,
        )
        client = _make_client()
        result = await client.verify_transaction(
            session_id="sess-1",
            order_id=999,
            amount=Decimal("10.00"),
            currency="PLN",
        )
        assert result["data"]["status"] == "success"

    async def test_verify_sends_correct_body(self, respx_mock):
        route = respx_mock.put(VERIFY_URL).respond(
            json={"data": {"status": "success"}},
            status_code=200,
        )
        client = _make_client()
        await client.verify_transaction(
            session_id="sess-1",
            order_id=999,
            amount=Decimal("10.00"),
            currency="PLN",
        )
        body = json.loads(route.calls.last.request.content)
        assert body["merchantId"] == 12345
        assert body["posId"] == 12345
        assert body["sessionId"] == "sess-1"
        assert body["orderId"] == 999
        assert body["amount"] == 1000
        assert body["currency"] == "PLN"
        assert "sign" in body

    async def test_verify_failure(self, respx_mock):
        respx_mock.put(VERIFY_URL).respond(
            json={"error": "Verification failed"},
            status_code=400,
        )
        client = _make_client()
        with pytest.raises(CommunicationError):
            await client.verify_transaction(
                session_id="sess-1",
                order_id=999,
                amount=Decimal("10.00"),
                currency="PLN",
            )


class TestRefund:
    """Tests for refund."""

    async def test_refund_success(self, respx_mock):
        refund_url = f"{SANDBOX_URL}/api/v1/transaction/refund"
        respx_mock.post(refund_url).respond(
            json={
                "data": [
                    {
                        "orderId": 999,
                        "sessionId": "sess-1",
                        "amount": 1000,
                        "status": 0,
                    }
                ],
                "responseCode": 0,
            },
            status_code=200,
        )
        client = _make_client()
        result = await client.refund(
            request_id="req-1",
            refunds_uuid="uuid-1",
            url_status="https://shop.example.com/refund-callback",
            refunds=[
                {
                    "orderId": 999,
                    "sessionId": "sess-1",
                    "amount": 1000,
                }
            ],
        )
        assert result["responseCode"] == 0

    async def test_refund_sends_correct_body(self, respx_mock):
        refund_url = f"{SANDBOX_URL}/api/v1/transaction/refund"
        route = respx_mock.post(refund_url).respond(
            json={"data": [], "responseCode": 0},
            status_code=200,
        )
        client = _make_client()
        await client.refund(
            request_id="req-1",
            refunds_uuid="uuid-1",
            url_status="https://shop.example.com/refund-callback",
            refunds=[
                {
                    "orderId": 999,
                    "sessionId": "sess-1",
                    "amount": 1000,
                }
            ],
        )
        body = json.loads(route.calls.last.request.content)
        assert body["requestId"] == "req-1"
        assert body["refundsUuid"] == "uuid-1"
        assert body["urlStatus"] == "https://shop.example.com/refund-callback"
        assert len(body["refunds"]) == 1
        assert body["refunds"][0]["orderId"] == 999

    async def test_refund_failure(self, respx_mock):
        refund_url = f"{SANDBOX_URL}/api/v1/transaction/refund"
        respx_mock.post(refund_url).respond(
            json={"error": "Refund failed"},
            status_code=400,
        )
        client = _make_client()
        with pytest.raises(RefundFailure):
            await client.refund(
                request_id="req-1",
                refunds_uuid="uuid-1",
                url_status="https://shop.example.com/refund-callback",
                refunds=[
                    {
                        "orderId": 999,
                        "sessionId": "sess-1",
                        "amount": 1000,
                    }
                ],
            )


class TestGetTransactionBySessionId:
    """Tests for get_transaction_by_session_id."""

    async def test_get_transaction_success(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/transaction/by/sessionId/sess-1"
        respx_mock.get(url).respond(
            json={"data": {"status": 2, "amount": 1000}},
            status_code=200,
        )
        client = _make_client()
        result = await client.get_transaction_by_session_id("sess-1")
        assert result["data"]["status"] == 2

    async def test_get_transaction_failure(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/transaction/by/sessionId/sess-1"
        respx_mock.get(url).respond(
            status_code=404, json={"error": "Not found"}
        )
        client = _make_client()
        with pytest.raises(CommunicationError):
            await client.get_transaction_by_session_id("sess-1")


class TestGetRefundByOrderId:
    """Tests for get_refund_by_order_id."""

    async def test_get_refund_success(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/refund/by/orderId/999"
        respx_mock.get(url).respond(
            json={"data": [{"orderId": 999, "amount": 1000, "status": 0}]},
            status_code=200,
        )
        client = _make_client()
        result = await client.get_refund_by_order_id(999)
        assert len(result["data"]) == 1

    async def test_get_refund_failure(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/refund/by/orderId/999"
        respx_mock.get(url).respond(
            status_code=404, json={"error": "Not found"}
        )
        client = _make_client()
        with pytest.raises(CommunicationError):
            await client.get_refund_by_order_id(999)


class TestGetPaymentMethods:
    """Tests for get_payment_methods."""

    async def test_get_methods_success(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/payment/methods/pl"
        respx_mock.get(url).respond(
            json={"data": [{"id": 25, "name": "BLIK", "status": True}]},
            status_code=200,
        )
        client = _make_client()
        result = await client.get_payment_methods("pl")
        assert len(result["data"]) == 1

    async def test_get_methods_with_amount(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/payment/methods/pl"
        route = respx_mock.get(url).respond(
            json={"data": []},
            status_code=200,
        )
        client = _make_client()
        await client.get_payment_methods("pl", amount=1000, currency="PLN")
        request_url = str(route.calls.last.request.url)
        assert "amount=1000" in request_url
        assert "currency=PLN" in request_url

    async def test_get_methods_failure(self, respx_mock):
        url = f"{SANDBOX_URL}/api/v1/payment/methods/pl"
        respx_mock.get(url).respond(
            status_code=401, json={"error": "Unauthorized"}
        )
        client = _make_client()
        with pytest.raises(CommunicationError):
            await client.get_payment_methods("pl")


class TestAsyncContextManager:
    """Tests for async context manager protocol."""

    async def test_context_manager(self, respx_mock):
        respx_mock.get(TEST_ACCESS_URL).respond(
            json={"data": True}, status_code=200
        )
        async with _make_client() as client:
            result = await client.test_access()
            assert result is True
