from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

from src.core import (
    PricingItem,
    Violation,
    Product,
    Variant,
    Deductible,
    keys_by_product,
    group_by_product_and_variant,
    group_by_product_and_deductible,
    group_by_variant_and_deductible,
)


class BasePriceValidator(ABC):
    @abstractmethod
    def validate(self, prices: Dict[str, float], items: List[PricingItem]) -> List[Violation]:
        raise NotImplementedError


class DefaultPriceValidator(BasePriceValidator):
    """
    Validates monotonicity constraints by product type, variant and deductible.
    Does not modify prices.
    """

    def validate(self, prices: Dict[str, float], items: List[PricingItem]) -> List[Violation]:
        p = {k: float(v) for k, v in prices.items()}
        violations: List[Violation] = []

        # Product-level: MTPL must be cheaper than both groups' minima 
        mtpl_key = Product.MTPL.key
        if mtpl_key not in p:
            raise ValueError(f"Input must contain key '{mtpl_key}'.")

        mtpl = p[mtpl_key]
        by_product = keys_by_product(items)

        for prod in (Product.LIMITED_CASCO, Product.CASCO):
            keys = by_product.get(prod, [])
            if not keys:
                continue
            group_min = min(p[k] for k in keys)
            if not (mtpl < group_min):
                violations.append(
                    Violation(
                        category="product",
                        rule=f"{mtpl_key} < min({prod.key})",
                        message=f"{mtpl_key} must be cheaper than the cheapest policy in {prod.key}.",
                        left_key=mtpl_key,
                        right_key=f"min({prod.key})",
                        left_value=mtpl,
                        right_value=group_min,
                    )
                )

        # Product-level: LIMITED_CASCO(v,d) < CASCO(v,d) for matching (variant, deductible) ---
        for (_variant, _deductible), m in group_by_variant_and_deductible(items).items():
            if Product.LIMITED_CASCO not in m or Product.CASCO not in m:
                continue

            lc_key = m[Product.LIMITED_CASCO]
            c_key = m[Product.CASCO]

            if not (p[lc_key] < p[c_key]):
                violations.append(
                    Violation(
                        category="product",
                        rule="limited_casco < casco",
                        message="Limited Casco must be cheaper than Casco for same variant & deductible.",
                        left_key=lc_key,
                        right_key=c_key,
                        left_value=p[lc_key],
                        right_value=p[c_key],
                    )
                )

        # Deductible-level: within (product, variant): 100 > 200 > 500 ---
        for (prod, var), m in group_by_product_and_variant(items).items():
            if Deductible.D100 in m and Deductible.D200 in m:
                k100 = m[Deductible.D100]
                k200 = m[Deductible.D200]
                if not (p[k100] > p[k200]):
                    violations.append(
                        Violation(
                            category="deductible",
                            rule="100 > 200",
                            message=f"{prod.key}_{var.key}: 100 must be more expensive than 200.",
                            left_key=k100,
                            right_key=k200,
                            left_value=p[k100],
                            right_value=p[k200],
                        )
                    )

            if Deductible.D200 in m and Deductible.D500 in m:
                k200 = m[Deductible.D200]
                k500 = m[Deductible.D500]
                if not (p[k200] > p[k500]):
                    violations.append(
                        Violation(
                            category="deductible",
                            rule="200 > 500",
                            message=f"{prod.key}_{var.key}: 200 must be more expensive than 500.",
                            left_key=k200,
                            right_key=k500,
                            left_value=p[k200],
                            right_value=p[k500],
                        )
                    )

        # Variant-level: within (product, deductible): base=max(compact,basic) < comfort < premium ---
        for (prod, ded), m in group_by_product_and_deductible(items).items():
            base_keys = [m[v] for v in (Variant.COMPACT, Variant.BASIC) if v in m]
            if not base_keys:
                continue

            base = max(p[k] for k in base_keys)

            if Variant.COMFORT in m:
                comfort_key = m[Variant.COMFORT]
                if not (base < p[comfort_key]):
                    violations.append(
                        Violation(
                            category="variant",
                            rule="base < comfort",
                            message=f"{prod.key}_{ded.value}: comfort must be above compact/basic base.",
                            left_key="base(compact/basic)",
                            right_key=comfort_key,
                            left_value=base,
                            right_value=p[comfort_key],
                        )
                    )

            if Variant.PREMIUM in m:
                premium_key = m[Variant.PREMIUM]
                lower = p[m[Variant.COMFORT]] if Variant.COMFORT in m else base
                left_name = "comfort" if Variant.COMFORT in m else "base(compact/basic)"
                if not (lower < p[premium_key]):
                    violations.append(
                        Violation(
                            category="variant",
                            rule="comfort/base < premium",
                            message=f"{prod.key}_{ded.value}: premium must be above comfort/base.",
                            left_key=left_name,
                            right_key=premium_key,
                            left_value=lower,
                            right_value=p[premium_key],
                        )
                    )

        return violations
