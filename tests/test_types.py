"""Tests for P24-specific types and enums."""

from getpaid_przelewy24.types import Currency
from getpaid_przelewy24.types import Language
from getpaid_przelewy24.types import TransactionStatus


def test_currency_values():
    assert Currency.PLN == "PLN"
    assert Currency.EUR == "EUR"
    assert Currency.GBP == "GBP"
    assert Currency.CZK == "CZK"
    assert Currency.USD == "USD"
    assert Currency.BGN == "BGN"
    assert Currency.DKK == "DKK"
    assert Currency.HUF == "HUF"
    assert Currency.NOK == "NOK"
    assert Currency.SEK == "SEK"
    assert Currency.CHF == "CHF"
    assert Currency.RON == "RON"
    assert Currency.HRK == "HRK"
    assert len(Currency) == 13


def test_language_values():
    assert Language.pl == "pl"
    assert Language.en == "en"
    assert Language.de == "de"
    assert Language.es == "es"
    assert Language.it == "it"
    assert Language.cs == "cs"
    assert Language.sk == "sk"
    assert Language.fr == "fr"
    assert Language.pt == "pt"
    assert Language.hu == "hu"
    assert Language.bg == "bg"
    assert Language.ro == "ro"
    assert Language.hr == "hr"
    assert len(Language) == 13


def test_transaction_status_values():
    """P24 transaction statuses from GET /transaction/by/sessionId."""
    assert TransactionStatus.NO_PAYMENT == 0
    assert TransactionStatus.ADVANCE_PAYMENT == 1
    assert TransactionStatus.PAYMENT_MADE == 2
    assert TransactionStatus.PAYMENT_RETURNED == 3
