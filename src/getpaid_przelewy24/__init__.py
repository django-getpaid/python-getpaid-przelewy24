"""Przelewy24 payment gateway integration for python-getpaid ecosystem."""

from getpaid_przelewy24.client import P24Client
from getpaid_przelewy24.processor import P24Processor


__all__ = [
    "P24Client",
    "P24Processor",
]
