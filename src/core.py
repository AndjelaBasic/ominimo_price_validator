from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

class Product(Enum):
    MTPL = "mtpl"
    LIMITED_CASCO = "limited_casco"
    CASCO = "casco"

    @property
    def key(self) -> str:
        """Canonical string used in input dictionary keys."""
        return self.value


class Variant(Enum):
    COMPACT = "compact"
    BASIC = "basic"
    COMFORT = "comfort"
    PREMIUM = "premium"

    @property
    def key(self) -> str:
        return self.value


class Deductible(Enum):
    D100 = 100
    D200 = 200
    D500 = 500

    @property
    def amount(self) -> int:
        """Numeric deductible amount."""
        return int(self.value)

# Reference prices & factors
REFERENCE_AVG_PRICE: dict[Product, float] = {
    Product.MTPL: 400.0,
    Product.LIMITED_CASCO: 700.0,
    Product.CASCO: 900.0,
}

RATIO_LC_OVER_MTPL: float = REFERENCE_AVG_PRICE[Product.LIMITED_CASCO] / REFERENCE_AVG_PRICE[Product.MTPL]  # 1.75
RATIO_C_OVER_MTPL: float = REFERENCE_AVG_PRICE[Product.CASCO] / REFERENCE_AVG_PRICE[Product.MTPL]           # 2.25
RATIO_C_OVER_LC: float = REFERENCE_AVG_PRICE[Product.CASCO] / REFERENCE_AVG_PRICE[Product.LIMITED_CASCO]    # ~1.2857

# Deductible steps: 100 baseline, each step ~10% cheaper
DEDUCTIBLE_FACTOR: dict[Deductible, float] = {
    Deductible.D100: 1.00,
    Deductible.D200: 0.90,
    Deductible.D500: 0.80,
}

# Variant steps relative to base tier (compact/basic treated as same tier)
VARIANT_FACTOR: dict[Variant, float] = {
    Variant.COMPACT: 1.00,
    Variant.BASIC: 1.00,
    Variant.COMFORT: 1.07,
    Variant.PREMIUM: 1.14,
}

VALID_PRODUCTS: frozenset[Product] = frozenset(Product)
VALID_VARIANTS: frozenset[Variant] = frozenset(Variant)
VALID_DEDUCTIBLES: frozenset[Deductible] = frozenset(Deductible)


# Parsed representation

@dataclass(frozen=True)
class PricingItem:
    """
        Parsed representation of a key in the prices dict.
        - MTPL has variant=None and deductible=None.
        - Non-MTPL keys always have variant and deductible.
    """
    key: str
    product: Product
    variant: Optional[Variant]
    deductible: Optional[Deductible]


# Validation & fixing reports

@dataclass(frozen=True)
class Violation:
    category: str   # "product" | "deductible" | "variant"
    rule: str       # short rule id
    message: str    # human readable
    left_key: str
    right_key: str
    left_value: float
    right_value: float


@dataclass
class FixReport:
    violations_before: List[Violation] = field(default_factory=list)
    violations_after: List[Violation] = field(default_factory=list)
    fix_log: List[str] = field(default_factory=list)

    def log(self, msg: str) -> None:
        self.fix_log.append(msg)


@dataclass(frozen=True)
class FixResult:
    fixed_prices: Dict[str, float]
    converged: bool
    iterations: int
    report: FixReport


# Helpers

def keys_by_product(items: List[PricingItem]) -> Dict[Product, List[str]]:
    """
        Product -> list of original dict keys.
    """
    out: Dict[Product, List[str]] = {}
    for it in items:
        out.setdefault(it.product, []).append(it.key)
    return out


def group_by_product_and_variant(items: List[PricingItem]) -> Dict[Tuple[Product, Variant], Dict[Deductible, str]]:
    """
        (product, variant) -> {deductible -> key}
    """
    out: Dict[Tuple[Product, Variant], Dict[Deductible, str]] = {}
    for it in items:
        if it.product == Product.MTPL:
            continue
        # by spec, non-MTPL always has both
        assert it.variant is not None
        assert it.deductible is not None
        out.setdefault((it.product, it.variant), {})[it.deductible] = it.key
    return out


def group_by_product_and_deductible(items: List[PricingItem]) -> Dict[Tuple[Product, Deductible], Dict[Variant, str]]:
    """
        (product, deductible) -> {variant -> key}
    """
    out: Dict[Tuple[Product, Deductible], Dict[Variant, str]] = {}
    for it in items:
        if it.product == Product.MTPL:
            continue
        assert it.variant is not None
        assert it.deductible is not None
        out.setdefault((it.product, it.deductible), {})[it.variant] = it.key
    return out


def group_by_variant_and_deductible(items: List[PricingItem]) -> Dict[Tuple[Variant, Deductible], Dict[Product, str]]:
    """
        (variant, deductible) -> {product -> key}

        Example:
            (Variant.BASIC, Deductible.D100) -> {
                Product.LIMITED_CASCO: 'limited_casco_basic_100',
                Product.CASCO: 'casco_basic_100'
            }
    """
    out: Dict[Tuple[Variant, Deductible], Dict[Product, str]] = {}
    for it in items:
        if it.product == Product.MTPL:
            continue
        assert it.variant is not None
        assert it.deductible is not None
        out.setdefault((it.variant, it.deductible), {})[it.product] = it.key
    return out
