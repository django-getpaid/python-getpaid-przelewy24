"""Przelewy24 API types and enums."""

from enum import IntEnum
from enum import StrEnum
from enum import auto
from enum import unique
from typing import TypedDict


class AutoName(StrEnum):
    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        return name.strip("_")


@unique
class Currency(AutoName):
    """Currencies supported by Przelewy24."""

    PLN = auto()
    EUR = auto()
    GBP = auto()
    CZK = auto()
    USD = auto()
    BGN = auto()
    DKK = auto()
    HUF = auto()
    NOK = auto()
    SEK = auto()
    CHF = auto()
    RON = auto()
    HRK = auto()


@unique
class Language(StrEnum):
    """Languages supported by Przelewy24."""

    pl = auto()
    en = auto()
    de = auto()
    es = auto()
    it = auto()
    cs = auto()
    sk = auto()
    fr = auto()
    pt = auto()
    hu = auto()
    bg = auto()
    ro = auto()
    hr = auto()


@unique
class TransactionStatus(IntEnum):
    """Transaction status from GET /transaction/by/sessionId.

    These are integer codes, not string enums.
    """

    NO_PAYMENT = 0
    ADVANCE_PAYMENT = 1
    PAYMENT_MADE = 2
    PAYMENT_RETURNED = 3


@unique
class RefundStatus(IntEnum):
    """Refund status codes from P24 refund notification."""

    COMPLETED = 0
    REJECTED = 1


# --- TypedDicts for API requests ---


class RegisterTransactionData(TypedDict, total=False):
    """Data for POST /api/v1/transaction/register."""

    merchantId: int
    posId: int
    sessionId: str
    amount: int
    currency: str
    description: str
    email: str
    country: str
    language: str
    urlReturn: str
    urlStatus: str
    timeLimit: int
    channel: int
    waitForResult: bool
    regulationAccept: bool
    shipping: int
    transferLabel: str
    methodRefId: str
    encoding: str
    sign: str


class VerifyTransactionData(TypedDict):
    """Data for PUT /api/v1/transaction/verify."""

    merchantId: int
    posId: int
    sessionId: str
    amount: int
    currency: str
    orderId: int
    sign: str


class RegisterResponse(TypedDict):
    """Response from POST /api/v1/transaction/register."""

    data: dict  # {"token": "..."}


class VerifyResponse(TypedDict):
    """Response from PUT /api/v1/transaction/verify."""

    data: dict  # {"status": "success"}


class NotificationPayload(TypedDict):
    """Notification POST data sent by P24 to urlStatus."""

    merchantId: int
    posId: int
    sessionId: str
    amount: int
    originAmount: int
    currency: str
    orderId: int
    methodId: int
    statement: str
    sign: str


class RefundRequestItem(TypedDict):
    """Single refund item in a batch refund request."""

    orderId: int
    sessionId: str
    amount: int


class RefundRequest(TypedDict):
    """Data for POST /api/v1/transaction/refund."""

    requestId: str
    refundsUuid: str
    urlStatus: str
    refunds: list[RefundRequestItem]


class RefundNotificationPayload(TypedDict, total=False):
    """Refund notification POST data sent by P24."""

    orderId: int
    sessionId: str
    merchantId: int
    requestId: str
    refundsUuid: str
    amount: int
    currency: str
    timestamp: int
    status: int  # 0 = completed, 1 = rejected
    sign: str


class TransactionInfoResponse(TypedDict):
    """Response from GET /transaction/by/sessionId/{sessionId}."""

    data: dict


class RefundInfoResponse(TypedDict):
    """Response from GET /refund/by/orderId/{orderId}."""

    data: list[dict]


class PaymentMethodsResponse(TypedDict):
    """Response from GET /payment/methods/{lang}."""

    data: list[dict]


class TestAccessResponse(TypedDict):
    """Response from GET /testAccess."""

    data: bool
