"""Test that Przelewy24 processor is discoverable via entry_points."""

from importlib.metadata import entry_points


def test_przelewy24_entry_point_registered():
    """Verify Przelewy24 processor is discoverable via entry_points."""
    eps = [
        e
        for e in entry_points(group="getpaid.backends")
        if e.name == "przelewy24"
    ]
    assert len(eps) == 1, (
        "Przelewy24 entry_point not found or duplicate registered"
    )
    assert eps[0].value == "getpaid_przelewy24.processor:P24Processor"
