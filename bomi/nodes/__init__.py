"""The four Bomi task nodes, one per API task controller."""

from .ai_suite import BomiAiSuite
from .background import BomiBackground
from .ecommerce_white_background import BomiEcommerceWhiteBackground
from .wear_ring_plus import BomiWearRingPlus

NODES = (
    BomiBackground,
    BomiAiSuite,
    BomiEcommerceWhiteBackground,
    BomiWearRingPlus,
)

__all__ = [cls.__name__ for cls in NODES] + ["NODES"]
