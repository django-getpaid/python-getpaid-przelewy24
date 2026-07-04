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

    def test_to_lowest_unit_rounds_half_up(self):
        """10.005 must round to 1001, not truncate to 1000."""
        assert P24Client._to_lowest_unit(Decimal("10.005")) == 1001

    def test_to_lowest_unit_no_float_truncation(self):
        """19.99 stored as float is 19.9899...; int(a*100) gave 1998."""
        assert P24Client._to_lowest_unit(Decimal("19.99")) == 1999

    def test_to_lowest_unit_accepts_float_input(self):
        assert P24Client._to_lowest_unit(19.99) == 1999
        assert P24Client._to_lowest_unit(10.005) == 1001

    def test_to_lowest_unit_with_explicit_currency(self):
        assert P24Client._to_lowest_unit(Decimal("1.23"), "PLN") == 123
        assert P24Client._to_lowest_unit(Decimal("1.23"), "EUR") == 123

    def test_from_lowest_unit(self):
        assert P24Client._from_lowest_unit(123) == Decimal("1.23")

    def test_from_lowest_unit_with_currency(self):
        assert P24Client._from_lowest_unit(123, "PLN") == Decimal("1.23")

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


class TestErrorContextSanitization:
    """Exception context must never carry the raw httpx.Response —
    its request headers contain the Basic-auth Authorization header."""

    @staticmethod
    def _assert_sanitized(context: dict) -> None:
        import httpx

        assert not any(
            isinstance(value, httpx.Response) for value in context.values()
        )
        response = context["response"]
        assert isinstance(response, dict)
        assert "status_code" in response
        assert "body" in response
        dumped = repr(context)
        assert "Authorization" not in dumped
        assert "Basic " not in dumped

    async def test_register_failure_context_has_no_credentials(
        self, respx_mock
    ):
        respx_mock.post(REGISTER_URL).respond(
            json={"error": "Invalid data"}, status_code=400
        )
        client = _make_client()
        with pytest.raises(LockFailure) as excinfo:
            await client.register_transaction(
                session_id="sess-1",
                amount=Decimal("10.00"),
                currency="PLN",
                description="Test",
                email="test@example.com",
                url_return="https://shop.example.com/return",
                url_status="https://shop.example.com/callback",
            )
        self._assert_sanitized(excinfo.value.context)
        assert excinfo.value.context["response"]["status_code"] == 400

    async def test_verify_failure_context_has_no_credentials(self, respx_mock):
        respx_mock.put(VERIFY_URL).respond(
            json={"error": "nope"}, status_code=400
        )
        client = _make_client()
        with pytest.raises(CommunicationError) as excinfo:
            await client.verify_transaction(
                session_id="sess-1",
                order_id=999,
                amount=Decimal("10.00"),
                currency="PLN",
            )
        self._assert_sanitized(excinfo.value.context)

    async def test_test_access_failure_context_has_no_credentials(
        self, respx_mock
    ):
        respx_mock.get(TEST_ACCESS_URL).respond(status_code=401)
        client = _make_client()
        with pytest.raises(CredentialsError) as excinfo:
            await client.test_access()
        self._assert_sanitized(excinfo.value.context)

    async def test_long_body_is_truncated(self, respx_mock):
        respx_mock.get(TEST_ACCESS_URL).respond(
            status_code=500, text="x" * 100_000
        )
        client = _make_client()
        with pytest.raises(CredentialsError) as excinfo:
            await client.test_access()
        body = excinfo.value.context["response"]["body"]
        assert len(body) <= 2048


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


class TestTimeouts:
    """The client must use explicit, configurable HTTP timeouts."""

    async def test_default_timeout(self):
        import httpx

        client = _make_client()
        assert client.timeout == httpx.Timeout(10.0, connect=5.0)
        async with client:
            assert client._client.timeout == httpx.Timeout(10.0, connect=5.0)

    async def test_custom_timeout(self):
        import httpx

        custom = httpx.Timeout(2.0, connect=1.0)
        client = P24Client(
            merchant_id=1,
            pos_id=1,
            api_key="k",
            crc_key="c",
            timeout=custom,
        )
        assert client.timeout == custom
        async with client:
            assert client._client.timeout == custom


class TestVerifyRetry:
    """verify_transaction is idempotent and mandatory for funds
    settlement — transient transport failures are retried."""

    def _client(self) -> P24Client:
        client = _make_client()
        client.retry_backoff = 0  # no sleeping in tests
        return client

    async def test_retries_after_transient_failure(self, respx_mock):
        import httpx

        route = respx_mock.put(VERIFY_URL)
        route.side_effect = [
            httpx.ConnectError("boom"),
            httpx.Response(200, json={"data": {"status": "success"}}),
        ]
        result = await self._client().verify_transaction(
            session_id="sess-1",
            order_id=999,
            amount=Decimal("10.00"),
            currency="PLN",
        )
        assert result["data"]["status"] == "success"
        assert route.call_count == 2

    async def test_gives_up_after_two_retries(self, respx_mock):
        import httpx

        route = respx_mock.put(VERIFY_URL)
        route.side_effect = httpx.ConnectError("boom")
        with pytest.raises(CommunicationError):
            await self._client().verify_transaction(
                session_id="sess-1",
                order_id=999,
                amount=Decimal("10.00"),
                currency="PLN",
            )
        assert route.call_count == 3  # initial attempt + 2 retries

    async def test_register_does_not_retry(self, respx_mock):
        import httpx

        route = respx_mock.post(REGISTER_URL)
        route.side_effect = httpx.ConnectError("boom")
        with pytest.raises(httpx.ConnectError):
            await self._client().register_transaction(
                session_id="sess-1",
                amount=Decimal("10.00"),
                currency="PLN",
                description="Test",
                email="test@example.com",
                url_return="https://shop.example.com/return",
                url_status="https://shop.example.com/callback",
            )
        assert route.call_count == 1


class TestAsyncContextManager:
    """Tests for async context manager protocol."""

    async def test_context_manager(self, respx_mock):
        respx_mock.get(TEST_ACCESS_URL).respond(
            json={"data": True}, status_code=200
        )
        async with _make_client() as client:
            result = await client.test_access()
            assert result is True
