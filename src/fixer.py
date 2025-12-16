from __future__ import annotations

from abc import ABC, abstractmethod
from statistics import median
from typing import Dict, List

from src.core import (
    PricingItem,
    FixReport,
    REFERENCE_AVG_PRICE,
    RATIO_LC_OVER_MTPL,
    RATIO_C_OVER_MTPL,
    DEDUCTIBLE_FACTOR,
    VARIANT_FACTOR,
    keys_by_product,
    group_by_product_and_variant,
    group_by_product_and_deductible,
    group_by_variant_and_deductible,
)


class BasePriceFixer(ABC):
    @abstractmethod
    def fix_pass(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        raise NotImplementedError


class DefaultPriceFixer(BasePriceFixer):
    def __init__(self, tau_outlier: float = 3.0, eps: float = 1e-6, enable_mtpl_anchor: bool = True):
        self.tau_outlier = tau_outlier
        self.eps = eps
        self.enable_mtpl_anchor = enable_mtpl_anchor

    def fix_pass(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        changed = False
        if self.enable_mtpl_anchor:
            changed |= self.set_mtpl_anchor(prices, items, report)
        changed |= self.enforce_product_type_order(prices, items, report)
        changed |= self.enforce_deductible_order(prices, items, report)
        changed |= self.enforce_variant_order(prices, items, report)
        return changed

    def set_mtpl_anchor(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        """
        We need to set an MTPL anchor as an reference to validate and fix other prices.
        We can just take MTPL from price input dictionary
        This could fail if MTPL is too large relative to its average compared to other products.
        Therefore, we take MTPL as an anchor unless it is an outlier, otherwsie we scale it based on its average of 400.
        """
        
        by_product = keys_by_product(items)

        mtpl = float(prices["mtpl"])
        k_mtpl = mtpl / REFERENCE_AVG_PRICE["mtpl"]
        ks = [k_mtpl]

        lc_keys = by_product.get("limited_casco", [])
        if lc_keys:
            lc_mean = sum(float(prices[k]) for k in lc_keys) / len(lc_keys)
            ks.append(lc_mean / REFERENCE_AVG_PRICE["limited_casco"])

        c_keys = by_product.get("casco", [])
        if c_keys:
            c_mean = sum(float(prices[k]) for k in c_keys) / len(c_keys)
            ks.append(c_mean / REFERENCE_AVG_PRICE["casco"])

        k_ref = median(ks)
        ratio = float("inf") if k_ref <= 0 or k_mtpl <= 0 else max(k_mtpl / k_ref, k_ref / k_mtpl)

        if ratio > self.tau_outlier:
            new_mtpl = REFERENCE_AVG_PRICE["mtpl"] * k_ref
            if abs(new_mtpl - mtpl) > 1e-12:
                prices["mtpl"] = float(new_mtpl)
                report.log(f"[anchor] mtpl {mtpl:.6f} -> {new_mtpl:.6f} (ratio={ratio:.3f})")
                return True

        return False

    def enforce_product_type_order(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        changed = False
        changed |= self.enforce_product_minima_ratios(prices, items, report)
        changed |= self.enforce_limited_casco_less_than_casco(prices, items, report)
        return changed

    def enforce_product_minima_ratios(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        """
        Enforce product-type ordering relative to MTPL.

        Rule: MTPL must be cheaper than all Limited Casco and Casco products
        (i.e., mtpl < min(limited_casco) and mtpl < min(casco)).

        Fix (only if the rule is violated for a given product group):
        - Define the target minimum using reference average ratios:
            target_min(limited_casco) = (700/400) * mtpl
            target_min(casco)         = (900/400) * mtpl
        - Let current_min be the current minimum price in that group.
        Scale the entire group by:
            scale = target_min / current_min
        so the group's minimum becomes target_min while preserving relative
        price differences within the group.
        """

        changed = False
        mtpl = float(prices["mtpl"])
        by_product = keys_by_product(items)

        for product, ratio in (("limited_casco", RATIO_LC_OVER_MTPL), ("casco", RATIO_C_OVER_MTPL)):
            keys = by_product.get(product, [])
            if not keys:
                continue

            current_min = min(float(prices[k]) for k in keys)
            if current_min > mtpl:
                continue

            target_min = ratio * mtpl
            scale = target_min / current_min

            for k in keys:
                prices[k] = float(prices[k]) * scale

            report.log(f"[product-min] scaled {product} by {scale:.6f} (min {current_min:.6f} -> {target_min:.6f})")
            changed = True

        return changed


    def enforce_limited_casco_less_than_casco(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        """
            Enforce product-type ordering between Limited Casco and Casco for matching
            (variant, deductible) combinations.

            Rule: limited_casco(v, d) < casco(v, d).

            Fix (only if the rule is violated):
            - If casco(v, d) <= limited_casco(v, d), raise casco(v, d) using the
            reference average tier ratio:
                casco(v, d) := (900 / 700) * limited_casco(v, d)

            No adjustment is applied when the ordering is already satisfied.
        """
        changed = False
        ratio = REFERENCE_AVG_PRICE["casco"] / REFERENCE_AVG_PRICE["limited_casco"]

        grouped = group_by_variant_and_deductible(items)

        for (_variant, _deductible), m in grouped.items():
            if "limited_casco" not in m or "casco" not in m:
                continue

            lc_key = m["limited_casco"]
            c_key = m["casco"]

            lc_price = float(prices[lc_key])
            c_price = float(prices[c_key])

            if c_price > lc_price:
                continue

            target = ratio * lc_price
            prices[c_key] = float(target)
            report.log(
                f"[product] {c_key}: {c_price:.6f} -> {target:.6f} (rebase vs {lc_key})"
            )
            changed = True

        return changed

    def enforce_deductible_order(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        """
            Enforce deductible monotonicity within each (product, variant).

            Rule:
                price(100) > price(200) > price(500)

            Fix (only if violated):
            Rebuild the entire deductible ladder from the price(100) base using
            reference percentage factors:
                price(200) := DEDUCTIBLE_FACTOR[200] * price(100)
                price(500) := DEDUCTIBLE_FACTOR[500] * price(100)

            If the ordering is already satisfied, no changes are applied.
        """
        changed = False
        grouped = group_by_product_and_variant(items)

        for (_product, _variant), m in grouped.items():
            if 100 not in m:
                continue

            p100 = float(prices[m[100]])

            # Check for violations
            violates = False
            if 200 in m and not (p100 > float(prices[m[200]])):
                violates = True
            if 500 in m and 200 in m and not (float(prices[m[200]]) > float(prices[m[500]])):
                violates = True

            if not violates:
                continue

            # Fix by rebasing from 100
            for d in (200, 500):
                if d not in m:
                    continue
                target = DEDUCTIBLE_FACTOR[d] * p100
                old = float(prices[m[d]])
                prices[m[d]] = float(target)
                report.log(f"[deductible] {m[d]}: {old:.6f} -> {target:.6f}")
                changed = True

        return changed
    

    def enforce_variant_order(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        """
    Enforce variant monotonicity within each (product, deductible).

    Rule:
        base := max(price(compact), price(basic))
        base < comfort < premium

    Fix (only if violated):
        Rebuild the entire variant ladder from the base using
        reference percentage factors:
            comfort := VARIANT_FACTOR["comfort"] * base
            premium := VARIANT_FACTOR["premium"] * base

    If no violation is detected, no changes are applied.
    """
        changed = False
        grouped = group_by_product_and_deductible(items)

        for (_product, _deductible), m in grouped.items():
            base_keys = [m[v] for v in ("compact", "basic") if v in m]
            if not base_keys:
                continue

            base = max(float(prices[k]) for k in base_keys)

            # --- detect violations ---
            violates = False

            if "comfort" in m:
                if float(prices[m["comfort"]]) <= base:
                    violates = True

            if "premium" in m:
                lower = float(prices[m["comfort"]]) if "comfort" in m else base
                if float(prices[m["premium"]]) <= lower:
                    violates = True

            if not violates:
                continue

            # --- fix entire ladder ---
            if "comfort" in m:
                old = float(prices[m["comfort"]])
                target = VARIANT_FACTOR["comfort"] * base
                prices[m["comfort"]] = float(target)
                report.log(f"[variant] {m['comfort']}: {old:.6f} -> {target:.6f}")
                changed = True

            if "premium" in m:
                old = float(prices[m["premium"]])
                target = VARIANT_FACTOR["premium"] * base
                prices[m["premium"]] = float(target)
                report.log(f"[variant] {m['premium']}: {old:.6f} -> {target:.6f}")
                changed = True

        return changed