from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Dict, List

from src.core import PricingItem, VALID_PRODUCTS, VALID_VARIANTS, VALID_DEDUCTIBLES


class BasePriceParser(ABC):
    @abstractmethod
    def parse_all(self, prices: Dict[str, float]) -> List[PricingItem]:
        raise NotImplementedError


class DefaultPriceParser(BasePriceParser):
    """
    Parses:
      - mtpl
      - {limited_casco|casco}_{variant}_{deductible}
    """

    pattern = re.compile(
        r"^(limited_casco|casco)_(compact|basic|comfort|premium)_(\d+)$",
        re.IGNORECASE,
    )

    def parse_key(self, key: str) -> PricingItem:
        k = key.lower().strip()
        if k == "mtpl":
            return PricingItem(key=key, product="mtpl", variant=None, deductible=None)

        m = self.pattern.match(k)
        if not m:
            raise ValueError(f"Invalid key format: {key}")

        product, variant, ded_str = m.groups()
        deductible = int(ded_str)

        if product not in VALID_PRODUCTS:
            raise ValueError(f"Invalid product in key {key}: {product}")
        if variant not in VALID_VARIANTS:
            raise ValueError(f"Invalid variant in key {key}: {variant}")
        if deductible not in VALID_DEDUCTIBLES:
            raise ValueError(f"Invalid deductible in key {key}: {deductible}")

        return PricingItem(key=key, product=product, variant=variant, deductible=deductible)

    def parse_all(self, prices: Dict[str, float]) -> List[PricingItem]:
        return [self.parse_key(k) for k in prices.keys()]
