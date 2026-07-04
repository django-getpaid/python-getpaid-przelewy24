"""Async HTTP client for Przelewy24 REST API."""

import hashlib
import json
from decimal import ROUND_HALF_UP
from decimal import Decimal

import anyio
import httpx
from getpaid_core.exceptions import CommunicationError
from getpaid_core.exceptions import CredentialsError
from getpaid_core.exceptions import LockFailure
from getpaid_core.exceptions import RefundFailure

from .types import RegisterResponse
from .types import VerifyResponse


SANDBOX_URL = "https://sandbox.przelewy24.pl"
PRODUCTION_URL = "https://secure.przelewy24.pl"

# P24 expresses amounts in the lowest currency unit. All currencies
# currently supported by P24 have an ISO 4217 exponent of 2
# (amount x 100), but the mapping is explicit so a future currency
# with a different exponent cannot be silently mis-scaled.
CURRENCY_EXPONENTS: dict[str, int] = {
    "PLN": 2,
    "EUR": 2,
    "GBP": 2,
    "CZK": 2,
    "USD": 2,
    "BGN": 2,
    "DKK": 2,
    "HUF": 2,
    "NOK": 2,
    "SEK": 2,
    "CHF": 2,
    "RON": 2,
}
DEFAULT_CURRENCY_EXPONENT = 2

MAX_ERROR_BODY_LENGTH = 2048

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

#: Retries for the (idempotent, settlement-critical) verify call.
VERIFY_RETRIES = 2


def _sanitize_response(response: httpx.Response) -> dict:
    """Build a safe error-context dict from an httpx.Response.

    The raw Response must never be attached to exceptions: its
    ``request.headers`` carry the Basic-auth Authorization header,
    which would leak credentials into logs and error trackers.
    """
    return {
        "status_code": response.status_code,
        "body": response.text[:MAX_ERROR_BODY_LENGTH],
    }


class P24Client:
    """Async client for Przelewy24 REST API.

    Uses ``httpx.AsyncClient`` with HTTP Basic Auth for all API
    calls. Can be used as an async context manager for connection
    reuse::

        async with P24Client(...) as client:
            await client.register_transaction(...)
    """

    def __init__(
        self,
        *,
        merchant_id: int,
        pos_id: int,
        api_key: str,
        crc_key: str,
        sandbox: bool = True,
        timeout: httpx.Timeout | float | None = None,
    ) -> None:
        self.merchant_id = merchant_id
        self.pos_id = pos_id
        self.api_key = api_key
        self.crc_key = crc_key
        self.base_url = SANDBOX_URL if sandbox else PRODUCTION_URL
        self.timeout: httpx.Timeout | float = (
            DEFAULT_TIMEOUT if timeout is None else timeout
        )
        self.retry_backoff: float = 0.5
        # Instance attribute — a class-level Response would be shared
        # (and leak) across all client instances.
        self.last_response: httpx.Response | None = None
        self._client: httpx.AsyncClient | None = None
        self._owns_client: bool = False

    async def __aenter__(self) -> "P24Client":
        self._client = httpx.AsyncClient(
            auth=(str(self.pos_id), self.api_key),
            timeout=self.timeout,
        )
        self._owns_client = True
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None
            self._owns_client = False

    def _get_auth(self) -> httpx.BasicAuth:
        """Build HTTP Basic Auth credentials."""
        return httpx.BasicAuth(
            username=str(self.pos_id),
            password=self.api_key,
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        content: str | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        """Execute an authenticated HTTP request."""
        headers = {"Content-Type": "application/json"} if content else {}
        if self._client is not None:
            return await self._client.request(
                method,
                url,
                headers=headers,
                content=content,
                params=params,
            )
        async with httpx.AsyncClient(
            auth=self._get_auth(),
            timeout=self.timeout,
        ) as client:
            return await client.request(
                method,
                url,
                headers=headers,
                content=content,
                params=params,
            )

    def _calculate_sign(self, fields: dict) -> str:
        """Calculate SHA-384 sign for P24 API.

        Appends the CRC key to the fields dict, serializes as
        compact JSON, and returns the SHA-384 hex digest.
        """
        payload = {**fields, "crc": self.crc_key}
        data = json.dumps(payload, separators=(",", ":"))
        return hashlib.sha384(data.encode()).hexdigest()

    @staticmethod
    def _currency_exponent(currency: str | None) -> int:
        return CURRENCY_EXPONENTS.get(
            (currency or "").upper(),
            DEFAULT_CURRENCY_EXPONENT,
        )

    @staticmethod
    def _to_lowest_unit(
        amount: Decimal | float | str,
        currency: str | None = None,
    ) -> int:
        """Convert an amount to the integer lowest currency unit.

        Uses ``Decimal`` quantization with ROUND_HALF_UP — never
        binary-float truncation. Floats are converted through
        ``str()`` so 10.005 means 10.005, not 10.00499...
        """
        exponent = P24Client._currency_exponent(currency)
        if isinstance(amount, float):
            amount = str(amount)
        value = Decimal(amount).quantize(
            Decimal(1).scaleb(-exponent),
            rounding=ROUND_HALF_UP,
        )
        return int(value.scaleb(exponent))

    @staticmethod
    def _from_lowest_unit(
        amount: int,
        currency: str | None = None,
    ) -> Decimal:
        """Convert integer lowest currency unit to Decimal."""
        exponent = P24Client._currency_exponent(currency)
        return Decimal(amount).scaleb(-exponent)

    async def test_access(self) -> bool:
        """Test API connection (GET /api/v1/testAccess).

        :return: True if connection is valid.
        :raises CredentialsError: If credentials are invalid.
        """
        url = f"{self.base_url}/api/v1/testAccess"
        self.last_response = await self._request("GET", url)
        if self.last_response.status_code == 200:
            return self.last_response.json().get("data", False)
        raise CredentialsError(
            "Cannot connect to Przelewy24 API.",
            context={"response": _sanitize_response(self.last_response)},
        )

    async def register_transaction(
        self,
        *,
        session_id: str,
        amount: Decimal,
        currency: str,
        description: str,
        email: str,
        url_return: str,
        url_status: str,
        country: str | None = None,
        language: str | None = None,
        time_limit: int | None = None,
        channel: int | None = None,
        wait_for_result: bool | None = None,
        transfer_label: str | None = None,
        method_ref_id: str | None = None,
    ) -> RegisterResponse:
        """Register a new transaction.

        POST /api/v1/transaction/register

        :param session_id: Unique session ID (maps to payment.id).
        :param amount: Payment amount.
        :param currency: ISO 4217 currency code.
        :param description: Payment description.
        :param email: Buyer email.
        :param url_return: URL to redirect buyer after payment.
        :param url_status: Callback URL for notifications.
        :return: Response with token for redirect.
        """
        url = f"{self.base_url}/api/v1/transaction/register"
        amount_int = self._to_lowest_unit(amount, currency)
        sign_fields = {
            "sessionId": session_id,
            "merchantId": self.merchant_id,
            "amount": amount_int,
            "currency": currency,
        }
        data: dict = {
            "merchantId": self.merchant_id,
            "posId": self.pos_id,
            "sessionId": session_id,
            "amount": amount_int,
            "currency": currency,
            "description": description,
            "email": email,
            "urlReturn": url_return,
            "urlStatus": url_status,
            "sign": self._calculate_sign(sign_fields),
        }
        optional = {
            "country": country,
            "language": language,
            "timeLimit": time_limit,
            "channel": channel,
            "waitForResult": wait_for_result,
            "transferLabel": transfer_label,
            "methodRefId": method_ref_id,
        }
        for key, value in optional.items():
            if value is not None:
                data[key] = value

        encoded = json.dumps(data, default=str)
        self.last_response = await self._request(
            "POST",
            url,
            content=encoded,
        )
        if self.last_response.status_code in (200, 201):
            return self.last_response.json()
        raise LockFailure(
            "Error registering P24 transaction",
            context={"response": _sanitize_response(self.last_response)},
        )

    async def verify_transaction(
        self,
        *,
        session_id: str,
        order_id: int,
        amount: Decimal,
        currency: str,
    ) -> VerifyResponse:
        """Verify a transaction after callback.

        PUT /api/v1/transaction/verify

        This MUST be called after receiving a notification to confirm
        the payment. Without verification, funds stay as advance
        payment.

        :param session_id: Session ID from original registration.
        :param order_id: P24 order ID from the notification.
        :param amount: Original payment amount.
        :param currency: ISO 4217 currency code.
        :return: Verification response.
        """
        url = f"{self.base_url}/api/v1/transaction/verify"
        amount_int = self._to_lowest_unit(amount, currency)
        sign_fields = {
            "sessionId": session_id,
            "orderId": order_id,
            "amount": amount_int,
            "currency": currency,
        }
        data = {
            "merchantId": self.merchant_id,
            "posId": self.pos_id,
            "sessionId": session_id,
            "orderId": order_id,
            "amount": amount_int,
            "currency": currency,
            "sign": self._calculate_sign(sign_fields),
        }
        encoded = json.dumps(data, default=str)
        # Verify is idempotent and mandatory for funds settlement:
        # retry transient transport failures with backoff before
        # giving up.
        attempts = VERIFY_RETRIES + 1
        response: httpx.Response | None = None
        for attempt in range(attempts):
            try:
                response = await self._request(
                    "PUT",
                    url,
                    content=encoded,
                )
                break
            except httpx.TransportError as exc:
                if attempt == attempts - 1:
                    raise CommunicationError(
                        "Transport error verifying P24 transaction "
                        f"after {attempts} attempts: {exc}",
                    ) from exc
                await anyio.sleep(self.retry_backoff * 2**attempt)
        assert response is not None  # loop either broke or raised
        self.last_response = response
        if response.status_code == 200:
            return response.json()
        raise CommunicationError(
            "Error verifying P24 transaction",
            context={"response": _sanitize_response(response)},
        )

    async def refund(
        self,
        *,
        request_id: str,
        refunds_uuid: str,
        url_status: str,
        refunds: list[dict],
    ) -> dict:
        """Request refund(s).

        POST /api/v1/transaction/refund

        P24 supports batch refunds — multiple refunds in one request.

        :param request_id: Unique request identifier.
        :param refunds_uuid: Unique UUID for this refund batch.
        :param url_status: Callback URL for refund notifications.
        :param refunds: List of refund items (orderId, sessionId,
            amount).
        :return: Refund response.
        """
        url = f"{self.base_url}/api/v1/transaction/refund"
        data = {
            "requestId": request_id,
            "refundsUuid": refunds_uuid,
            "urlStatus": url_status,
            "refunds": refunds,
        }
        encoded = json.dumps(data, default=str)
        self.last_response = await self._request(
            "POST",
            url,
            content=encoded,
        )
        if self.last_response.status_code == 200:
            return self.last_response.json()
        raise RefundFailure(
            "Error requesting P24 refund",
            context={"response": _sanitize_response(self.last_response)},
        )

    async def get_transaction_by_session_id(
        self,
        session_id: str,
    ) -> dict:
        """Look up transaction by session ID.

        GET /api/v1/transaction/by/sessionId/{sessionId}

        :param session_id: Session ID to look up.
        :return: Transaction info response.
        """
        url = f"{self.base_url}/api/v1/transaction/by/sessionId/{session_id}"
        self.last_response = await self._request("GET", url)
        if self.last_response.status_code == 200:
            return self.last_response.json()
        raise CommunicationError(
            "Error fetching P24 transaction",
            context={"response": _sanitize_response(self.last_response)},
        )

    async def get_refund_by_order_id(
        self,
        order_id: int,
    ) -> dict:
        """Look up refunds by P24 order ID.

        GET /api/v1/refund/by/orderId/{orderId}

        :param order_id: P24 order ID.
        :return: Refund info response.
        """
        url = f"{self.base_url}/api/v1/refund/by/orderId/{order_id}"
        self.last_response = await self._request("GET", url)
        if self.last_response.status_code == 200:
            return self.last_response.json()
        raise CommunicationError(
            "Error fetching P24 refunds",
            context={"response": _sanitize_response(self.last_response)},
        )

    async def get_payment_methods(
        self,
        lang: str,
        *,
        amount: int | None = None,
        currency: str | None = None,
    ) -> dict:
        """Get available payment methods.

        GET /api/v1/payment/methods/{lang}

        :param lang: ISO 639-1 language code.
        :param amount: Optional amount filter (lowest currency unit).
        :param currency: Optional currency filter.
        :return: Payment methods response.
        """
        url = f"{self.base_url}/api/v1/payment/methods/{lang}"
        params: dict = {}
        if amount is not None:
            params["amount"] = amount
        if currency is not None:
            params["currency"] = currency
        self.last_response = await self._request(
            "GET",
            url,
            params=params,
        )
        if self.last_response.status_code == 200:
            return self.last_response.json()
        raise CommunicationError(
            "Error fetching P24 payment methods",
            context={"response": _sanitize_response(self.last_response)},
        )

    def get_transaction_redirect_url(self, token: str) -> str:
        """Build the redirect URL for a registered transaction.

        :param token: Token from register_transaction response.
        :return: Full URL to redirect the buyer to.
        """
        return f"{self.base_url}/trnRequest/{token}"
