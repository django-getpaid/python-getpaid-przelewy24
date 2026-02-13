"""Przelewy24 payment gateway integration for python-getpaid ecosystem."""

# Lazy imports — client and processor are defined in later tasks.
# This avoids ImportError when only types.py is implemented so far.

__all__ = [
    "P24Client",
    "P24Processor",
]


def __getattr__(name: str):  # noqa: N807
    if name == "P24Client":
        from getpaid_przelewy24.client import P24Client

        return P24Client
    if name == "P24Processor":
        from getpaid_przelewy24.processor import P24Processor

        return P24Processor
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
