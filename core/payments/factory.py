

from core.payments.base import BasePaymentGateway


GATEWAY_MAP = {
    "simulator": "core.payments.simulator.SimulatorPaymentGateway",
}

_cache: BasePaymentGateway | None = None


def get_payment_gateway() -> BasePaymentGateway:
    """Return the configured payment gateway instance.

    The gateway is determined by the ``PAYMENT_GATEWAY`` Django setting
    (e.g. ``PAYMENT_GATEWAY=simulator``). The instance is cached so the
    same gateway object is reused throughout the process.

    To add a new gateway:
      1. Create ``apps/sms/payments/<name>.py`` with a class that
         inherits from ``BasePaymentGateway``.
      2. Register the dotted path in ``GATEWAY_MAP`` above.
    """
    global _cache

    if _cache is not None:
        return _cache

    from django.conf import settings

    gateway_key = getattr(settings, "PAYMENT_GATEWAY", "simulator")

    if gateway_key not in GATEWAY_MAP:
        available = ", ".join(sorted(GATEWAY_MAP.keys()))
        raise ValueError(
            f"Unknown payment gateway '{gateway_key}'. "
            f"Available gateways: {available}"
        )

    dotted_path = GATEWAY_MAP[gateway_key]
    module_path, class_name = dotted_path.rsplit(".", 1)

    import importlib

    module = importlib.import_module(module_path)
    gateway_cls = getattr(module, class_name)
    _cache = gateway_cls()

    return _cache


def clear_gateway_cache() -> None:
    """Reset the cached gateway. Useful for testing."""
    global _cache
    _cache = None