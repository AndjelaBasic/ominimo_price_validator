from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

from src.core import (
    PricingItem,
    Violation,
    keys_by_product,
    group_by_product_and_variant,
    group_by_product_and_deductible,
)


class BasePriceValidator(ABC):
    @abstractmethod
    def validate(self, prices: Dict[str, float], items: List[PricingItem]) -> List[Violation]:
        raise NotImplementedError


class DefaultPriceVlidator(BasePriceValidator):
    """
    Validates monotonicity constraints. Does not modify prices.
    """

    def validate(self, prices: Dict[str, float], items: List[PricingItem]) -> List[Violation]:
        if "mtpl" not in prices:
            raise ValueError("Input must contain key 'mtpl'.")

        p = {k: float(v) for k, v in prices.items()}
        violations: List[Violation] = []

        # Product-level: MTPL must be cheaper than both groups' minima
        mtpl = p["mtpl"]
        by_product = keys_by_product(items)

        for prod in ("limited_casco", "casco"):
            keys = by_product.get(prod, [])
            if not keys:
                continue
            group_min = min(p[k] for k in keys)
            if not (mtpl < group_min):
                violations.append(Violation(
                    category="product",
                    rule=f"mtpl < min({prod})",
                    message="MTPL must be cheaper than the cheapest policy in this group.",
                    left_key="mtpl",
                    right_key=f"min({prod})",
                    left_value=mtpl,
                    right_value=group_min,
                ))

        # Product-level: limited_casco(v,d) < casco(v,d)
        lc_lookup = {}
        for it in items:
            if it.product == "limited_casco":
                lc_lookup[(it.variant, it.deductible)] = it.key

        for it in items:
            if it.product == "casco":
                lk = lc_lookup.get((it.variant, it.deductible))
                if lk is None:
                    continue
                if not (p[lk] < p[it.key]):
                    violations.append(Violation(
                        category="product",
                        rule="limited_casco < casco",
                        message="Limited Casco must be cheaper than Casco for same variant & deductible.",
                        left_key=lk,
                        right_key=it.key,
                        left_value=p[lk],
                        right_value=p[it.key],
                    ))

        # Deductible-level: within (product, variant): 100 > 200 > 500
        for (prod, var), m in group_by_product_and_variant(items).items():
            if 100 in m and 200 in m and not (p[m[100]] > p[m[200]]):
                violations.append(Violation("deductible", "100 > 200",
                    f"{prod}_{var}: 100 must be more expensive than 200.",
                    m[100], m[200], p[m[100]], p[m[200]]))
            if 200 in m and 500 in m and not (p[m[200]] > p[m[500]]):
                violations.append(Violation("deductible", "200 > 500",
                    f"{prod}_{var}: 200 must be more expensive than 500.",
                    m[200], m[500], p[m[200]], p[m[500]]))

        # Variant-level: within (product, deductible): base=max(compact,basic) < comfort < premium
        for (prod, ded), m in group_by_product_and_deductible(items).items():
            base_keys = [m[v] for v in ("compact", "basic") if v in m]
            if not base_keys:
                continue
            base = max(p[k] for k in base_keys)

            if "comfort" in m and not (base < p[m["comfort"]]):
                violations.append(Violation("variant", "base < comfort",
                    f"{prod}_{ded}: comfort must be above compact/basic base.",
                    "base(compact/basic)", m["comfort"], base, p[m["comfort"]]))

            if "premium" in m:
                lower = p[m["comfort"]] if "comfort" in m else base
                if not (lower < p[m["premium"]]):
                    violations.append(Violation("variant", "comfort/base < premium",
                        f"{prod}_{ded}: premium must be above comfort/base.",
                        ("comfort" if "comfort" in m else "base(compact/basic)"),
                        m["premium"], lower, p[m["premium"]]))

        return violations
