from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Reference prices & factors
REFERENCE_AVG_PRICE: dict[str, float] = {
    "mtpl": 400.0,
    "limited_casco": 700.0,
    "casco": 900.0,
}
 
RATIO_LC_OVER_MTPL: float = REFERENCE_AVG_PRICE["limited_casco"] / REFERENCE_AVG_PRICE["mtpl"]  # 1.75
RATIO_C_OVER_MTPL: float = REFERENCE_AVG_PRICE["casco"] / REFERENCE_AVG_PRICE["mtpl"]          # 2.25
RATIO_C_OVER_LC: float = REFERENCE_AVG_PRICE["casco"] / REFERENCE_AVG_PRICE["limited_casco"] # 1.29

# Deductible steps: 100 baseline, each step ~10% cheaper
DEDUCTIBLE_FACTOR: dict[int, float] = {100: 1.00, 200: 0.90, 500: 0.80}

# Variant steps relative to base tier (compact/basic treated as same tier)
VARIANT_FACTOR: dict[str, float] = {"compact": 1.00, "basic": 1.00, "comfort": 1.07, "premium": 1.14}

VALID_PRODUCTS = {"mtpl", "limited_casco", "casco"}
VALID_VARIANTS = {"compact", "basic", "comfort", "premium"}
VALID_DEDUCTIBLES = {100, 200, 500}


# Parsed representation
@dataclass(frozen=True)
class PricingItem:
    """
    Parsed representation of a key in the prices dict.
    - MTPL has variant=None and deductible=None.
    - Non-MTPL keys always have variant and deductible.
    """
    key: str
    product: str
    variant: Optional[str]
    deductible: Optional[int]


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
def keys_by_product(items: List[PricingItem]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for it in items:
        out.setdefault(it.product, []).append(it.key)
    return out

def group_by_product_and_variant(items: List[PricingItem]) -> Dict[Tuple[str, str], Dict[int, str]]:
    """
    (product, variant) -> {deductible -> key}
    """
    out: Dict[Tuple[str, str], Dict[int, str]] = {}
    for it in items:
        if it.product == "mtpl":
            continue
        out.setdefault((it.product, it.variant), {})[it.deductible] = it.key
    return out

def group_by_product_and_deductible(items: List[PricingItem]) -> Dict[Tuple[str, int], Dict[str, str]]:
    """
    (product, deductible) -> {variant -> key}
    """
    out: Dict[Tuple[str, int], Dict[str, str]] = {}
    for it in items:
        if it.product == "mtpl":
            continue
        out.setdefault((it.product, it.deductible), {})[it.variant] = it.key
    return out

def group_by_variant_and_deductible(items: List[PricingItem]) -> Dict[Tuple[str, int], Dict[str, str]]:
    """
    (variant, deductible) -> {product -> key}

    Example:
        ('basic', 100) -> {
            'limited_casco': 'limited_casco_basic_100',
            'casco': 'casco_basic_100'
        }
    """
    out: Dict[Tuple[str, int], Dict[str, str]] = {}
    for it in items:
        if it.product == "mtpl":
            continue
        out.setdefault((it.variant, it.deductible), {})[it.product] = it.key
    return out
