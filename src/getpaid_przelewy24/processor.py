"""Przelewy24 payment processor."""

import logging
import uuid
from decimal import Decimal
from typing import ClassVar

from getpaid_core.processor import BaseProcessor
from getpaid_core.types import ChargeResponse
from getpaid_core.types import PaymentStatusResponse
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
    accepted_currencies: ClassVar[list[str]] = [c.value for c in Currency]
    sandbox_url: ClassVar[str] = "https://sandbox.przelewy24.pl"
    production_url: ClassVar[str] = "https://secure.przelewy24.pl"

    def _get_client(self) -> P24Client:
        """Create a P24Client from processor config."""
        return P24Client(
            merchant_id=self.get_setting("merchant_id"),
            pos_id=self.get_setting("pos_id"),
            api_key=self.get_setting("api_key"),
            crc_key=self.get_setting("crc_key"),
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
            redirect_url=redirect_url,
            form_data=None,
            method="GET",
            headers={},
        )

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        """Verify P24 notification signature.

        Expects data to contain the notification fields including
        'sign'. Computes the expected sign from the notification
        fields + CRC key and compares.
        """
        import hmac as hmac_mod

        from getpaid_core.exceptions import InvalidCallbackError

        client = self._get_client()
        sign_fields = {
            "merchantId": data.get("merchantId"),
            "posId": data.get("posId"),
            "sessionId": data.get("sessionId"),
            "amount": data.get("amount"),
            "originAmount": data.get("originAmount"),
            "currency": data.get("currency"),
            "orderId": data.get("orderId"),
            "methodId": data.get("methodId"),
            "statement": data.get("statement"),
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
    ) -> None:
        """Handle P24 notification and verify the transaction.

        After receiving a notification from P24, this method:
        1. Extracts orderId from the notification
        2. Stores orderId as external_id on the payment
        3. Calls verify_transaction to confirm the payment
        4. Updates FSM state based on verification result

        The verify step is MANDATORY — without it, P24 treats
        the payment as an advance payment only.
        """
        import contextlib

        from transitions.core import MachineError

        order_id: int = data.get("orderId", 0)
        session_id: str = data.get("sessionId", self.payment.id)
        amount: int = data.get("amount", 0)
        currency: str = data.get("currency", self.payment.currency)

        if order_id:
            self.payment.external_id = str(order_id)

        client = self._get_client()
        amount_decimal = P24Client._from_lowest_unit(amount)

        try:
            await client.verify_transaction(
                session_id=session_id,
                order_id=order_id,
                amount=amount_decimal,
                currency=currency,
            )
        except Exception:
            logger.exception(
                "P24 verification failed for payment %s",
                self.payment.id,
            )
            if hasattr(self.payment, "fail"):
                self.payment.fail()
            return

        # Verification succeeded — move to paid
        if self.payment.may_trigger("confirm_payment"):
            self.payment.confirm_payment()
            with contextlib.suppress(MachineError):
                self.payment.mark_as_paid()
        else:
            logger.debug(
                "Cannot confirm payment %s (status: %s)",
                self.payment.id,
                self.payment.status,
            )

    async def fetch_payment_status(self, **kwargs) -> PaymentStatusResponse:
        """PULL flow: fetch transaction status from P24 API."""
        client = self._get_client()
        response = await client.get_transaction_by_session_id(
            self.payment.id,
        )
        tx_data = response.get("data", {})
        status = tx_data.get("status")

        status_map = {
            TransactionStatus.NO_PAYMENT: None,
            TransactionStatus.ADVANCE_PAYMENT: "confirm_prepared",
            TransactionStatus.PAYMENT_MADE: "confirm_payment",
            TransactionStatus.PAYMENT_RETURNED: "confirm_refund",
        }

        return PaymentStatusResponse(
            status=status_map.get(status),
        )

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
    ) -> Decimal:
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

        await client.refund(
            request_id=str(uuid.uuid4()),
            refunds_uuid=str(uuid.uuid4()),
            url_status=refund_url_status,
            refunds=[
                {
                    "orderId": int(self.payment.external_id),
                    "sessionId": self.payment.id,
                    "amount": amount_int,
                }
            ],
        )
        return refund_amount
