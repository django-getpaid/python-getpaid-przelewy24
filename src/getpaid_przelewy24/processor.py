"""Przelewy24 payment processor."""

import hmac as hmac_mod
import logging
import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import ClassVar

from getpaid_core.enums import PaymentEvent
from getpaid_core.exceptions import InvalidCallbackError
from getpaid_core.processor import BaseProcessor
from getpaid_core.types import ChargeResponse
from getpaid_core.types import PaymentUpdate
from getpaid_core.types import RefundResult
from getpaid_core.types import TransactionResult

from .client import P24Client
from .types import Currency
from .types import TransactionStatus


logger = logging.getLogger(__name__)


class P24Processor(BaseProcessor):
    """Przelewy24 payment gateway processor.

    P24 has no pre-authorization flow — only direct payment:
    register -> redirect -> notification -> verify.
    Therefore ``charge()`` and ``release_lock()`` raise
    ``NotImplementedError``.
    """

    slug: ClassVar[str] = "przelewy24"
    display_name: ClassVar[str] = "Przelewy24"
    accepted_currencies: ClassVar[Sequence[str]] = [c.value for c in Currency]
    sandbox_url: ClassVar[str] = "https://sandbox.przelewy24.pl"
    production_url: ClassVar[str] = "https://secure.przelewy24.pl"

    def _get_client(self) -> P24Client:
        """Create a P24Client from processor config."""
        return P24Client(
            merchant_id=int(self.get_setting("merchant_id", 0)),
            pos_id=int(self.get_setting("pos_id", 0)),
            api_key=str(self.get_setting("api_key", "")),
            crc_key=str(self.get_setting("crc_key", "")),
            sandbox=self.get_setting("sandbox", True),
        )

    def _resolve_url(self, url_template: str) -> str:
        """Replace {payment_id} placeholder."""
        return url_template.format(payment_id=self.payment.id)

    def _build_paywall_context(self, **kwargs) -> dict:
        """Build P24 registration data from payment object."""
        buyer = self.payment.order.get_buyer_info()

        url_status_template = self.get_setting("url_status", "")
        url_return_template = self.get_setting("url_return", "")

        context = {
            "session_id": self.payment.id,
            "amount": self.payment.amount_required,
            "currency": self.payment.currency,
            "description": self.payment.description,
            "email": buyer.get("email", ""),
        }
        if url_status_template:
            context["url_status"] = self._resolve_url(
                url_status_template,
            )
        if url_return_template:
            context["url_return"] = self._resolve_url(
                url_return_template,
            )

        return context

    async def prepare_transaction(self, **kwargs) -> TransactionResult:
        """Prepare a P24 payment — register and get redirect URL."""
        client = self._get_client()
        context = self._build_paywall_context(**kwargs)
        response = await client.register_transaction(**context)
        token = response.get("data", {}).get("token", "")
        redirect_url = client.get_transaction_redirect_url(token)
        return TransactionResult(
            method="GET",
            redirect_url=redirect_url,
            provider_data={"p24_token": token},
        )

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        """Verify P24 notification signature.

        Expects data to contain the notification fields including
        'sign'. Computes the expected sign from the notification
        fields + CRC key and compares.
        """
        client = self._get_client()
        required_fields = [
            "merchantId",
            "posId",
            "sessionId",
            "amount",
            "originAmount",
            "currency",
            "orderId",
            "methodId",
            "statement",
        ]
        missing = [
            field
            for field in required_fields
            if field not in data or data[field] in (None, "")
        ]
        if missing:
            raise InvalidCallbackError(
                "Missing required callback fields: "
                + ", ".join(sorted(missing))
            )
        sign_fields = {
            "merchantId": data["merchantId"],
            "posId": data["posId"],
            "sessionId": data["sessionId"],
            "amount": data["amount"],
            "originAmount": data["originAmount"],
            "currency": data["currency"],
            "orderId": data["orderId"],
            "methodId": data["methodId"],
            "statement": data["statement"],
        }
        expected_sign = client._calculate_sign(sign_fields)

        received_sign = data.get("sign", "")
        if not received_sign:
            raise InvalidCallbackError(
                "Missing sign in notification",
            )

        if not hmac_mod.compare_digest(expected_sign, received_sign):
            logger.error(
                "P24 notification bad signature for payment %s! "
                "Got '%s', expected '%s'",
                self.payment.id,
                received_sign,
                expected_sign,
            )
            raise InvalidCallbackError(
                f"BAD SIGNATURE: got '{received_sign}', "
                f"expected '{expected_sign}'"
            )

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> PaymentUpdate:
        """Handle P24 notification and return a semantic update."""
        order_id: int = data.get("orderId", 0)
        session_id: str = data.get("sessionId", self.payment.id)
        amount: int = data.get("amount", 0)
        currency: str = data.get("currency", self.payment.currency)

        client = self._get_client()
        amount_decimal = P24Client._from_lowest_unit(amount)

        await client.verify_transaction(
            session_id=session_id,
            order_id=order_id,
            amount=amount_decimal,
            currency=currency,
        )

        return PaymentUpdate(
            payment_event=PaymentEvent.PAYMENT_CAPTURED,
            paid_amount=amount_decimal,
            external_id=str(order_id) if order_id else self.payment.external_id,
            provider_event_id=(
                f"{session_id}:{order_id}:{amount}:{currency}"
                if order_id
                else None
            ),
            provider_data={"p24_verified": True},
        )

    async def fetch_payment_status(self, **kwargs) -> PaymentUpdate | None:
        """PULL flow: fetch transaction status from P24 API."""
        client = self._get_client()
        response = await client.get_transaction_by_session_id(
            self.payment.id,
        )
        tx_data = response.get("data", {})
        status = tx_data.get("status")
        amount = tx_data.get("amount")
        provider_event_id = f"poll:{self.payment.id}:{status}"

        if status == TransactionStatus.PAYMENT_MADE:
            return PaymentUpdate(
                payment_event=PaymentEvent.PAYMENT_CAPTURED,
                paid_amount=P24Client._from_lowest_unit(amount or 0),
                provider_event_id=provider_event_id,
                provider_data={"p24_status": status},
            )
        if status == TransactionStatus.PAYMENT_RETURNED:
            return PaymentUpdate(
                payment_event=PaymentEvent.REFUND_CONFIRMED,
                refunded_amount=P24Client._from_lowest_unit(amount or 0),
                provider_event_id=provider_event_id,
                provider_data={"p24_status": status},
            )
        return None

    async def charge(
        self, amount: Decimal | None = None, **kwargs
    ) -> ChargeResponse:
        """Not supported by P24 (no pre-auth flow)."""
        raise NotImplementedError(
            "Przelewy24 does not support pre-authorization/charge flow"
        )

    async def release_lock(self, **kwargs) -> Decimal:
        """Not supported by P24 (no pre-auth flow)."""
        raise NotImplementedError(
            "Przelewy24 does not support pre-authorization/release flow"
        )

    async def start_refund(
        self, amount: Decimal | None = None, **kwargs
    ) -> RefundResult:
        """Start a refund via P24 API."""
        client = self._get_client()
        refund_amount = amount or self.payment.amount_paid
        amount_int = P24Client._to_lowest_unit(refund_amount)

        refund_url_status = self.get_setting(
            "refund_url_status",
            "",
        )
        if refund_url_status:
            refund_url_status = self._resolve_url(refund_url_status)

        request_id = str(uuid.uuid4())
        refunds_uuid = str(uuid.uuid4())
        await client.refund(
            request_id=request_id,
            refunds_uuid=refunds_uuid,
            url_status=refund_url_status,
            refunds=[
                {
                    "orderId": int(self.payment.external_id),
                    "sessionId": self.payment.id,
                    "amount": amount_int,
                }
            ],
        )
        return RefundResult(
            amount=refund_amount,
            provider_data={
                "request_id": request_id,
                "refunds_uuid": refunds_uuid,
            },
        )
