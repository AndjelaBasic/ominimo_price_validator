from __future__ import annotations

from abc import ABC, abstractmethod
from statistics import median
from typing import Dict, List

from src.core import (
    PricingItem,
    FixReport,
    Product,
    Variant,
    Deductible,
    REFERENCE_AVG_PRICE,
    RATIO_LC_OVER_MTPL,
    RATIO_C_OVER_MTPL,
    RATIO_C_OVER_LC,
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
    def __init__(self, tau_outlier: float = 5.0, eps: float = 1e-6, enable_mtpl_anchor: bool = True):
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
        Set MTPL as the anchor reference unless it is an outlier relative to
        the implied scaling level of the other product groups.

        We compute per-group scaling multipliers:
            k_mtpl = mtpl / avg_mtpl
            k_lc   = mean(lc_prices) / avg_lc
            k_c    = mean(casco_prices) / avg_casco

        Let k_ref = median([k_mtpl, k_lc, k_c] among groups present).
        If k_mtpl deviates from k_ref by more than tau_outlier multiplicatively,
        replace mtpl with:
            mtpl := avg_mtpl * k_ref
        """
        by_product = keys_by_product(items)

        mtpl_key = Product.MTPL.key
        mtpl = float(prices[mtpl_key])

        k_mtpl = mtpl / REFERENCE_AVG_PRICE[Product.MTPL]
        ks = [k_mtpl]

        lc_keys = by_product.get(Product.LIMITED_CASCO, [])
        if lc_keys:
            lc_mean = sum(float(prices[k]) for k in lc_keys) / len(lc_keys)
            ks.append(lc_mean / REFERENCE_AVG_PRICE[Product.LIMITED_CASCO])

        c_keys = by_product.get(Product.CASCO, [])
        if c_keys:
            c_mean = sum(float(prices[k]) for k in c_keys) / len(c_keys)
            ks.append(c_mean / REFERENCE_AVG_PRICE[Product.CASCO])

        k_ref = median(ks)
        ratio = max(k_mtpl / k_ref, k_ref / k_mtpl)  # prices assumed positive

        if ratio > self.tau_outlier:
            new_mtpl = REFERENCE_AVG_PRICE[Product.MTPL] * k_ref
            if abs(new_mtpl - mtpl) > 1e-12:
                prices[mtpl_key] = float(new_mtpl)
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

        Rule:
            mtpl < min(limited_casco) and mtpl < min(casco)

        Fix (only if violated for a given group):
            - If min(group) <= mtpl, set target minimum using reference ratios:
                target_min(limited_casco) = RATIO_LC_OVER_MTPL * mtpl
                target_min(casco)         = RATIO_C_OVER_MTPL  * mtpl
            - Scale the entire group by:
                scale = target_min / current_min
              so the group's minimum becomes target_min while preserving
              relative price differences within that product group.
        """
        changed = False
        mtpl = float(prices[Product.MTPL.key])
        by_product = keys_by_product(items)

        for product, ratio in (
            (Product.LIMITED_CASCO, RATIO_LC_OVER_MTPL),
            (Product.CASCO, RATIO_C_OVER_MTPL),
        ):
            keys = by_product.get(product, [])
            if not keys:
                continue

            current_min = min(float(prices[k]) for k in keys)
            if current_min > mtpl:
                continue  # ordering ok => do nothing

            target_min = ratio * mtpl
            scale = target_min / current_min

            for k in keys:
                prices[k] = float(prices[k]) * scale

            report.log(
                f"[product-min] scaled {product.key} by {scale:.6f} "
                f"(min {current_min:.6f} -> {target_min:.6f})"
            )
            changed = True

        return changed

    def enforce_limited_casco_less_than_casco(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        """
        Enforce product ordering between Limited Casco and Casco for matching
        (variant, deductible) combinations.

        Rule:
            limited_casco(v, d) < casco(v, d)

        Fix (only if violated):
            If casco(v, d) <= limited_casco(v, d), rebase Casco using the
            reference average tier ratio:
                casco(v, d) := RATIO_C_OVER_LC * limited_casco(v, d)
        """
        changed = False
        grouped = group_by_variant_and_deductible(items)

        for (_variant, _deductible), m in grouped.items():
            if Product.LIMITED_CASCO not in m or Product.CASCO not in m:
                continue

            lc_key = m[Product.LIMITED_CASCO]
            c_key = m[Product.CASCO]

            lc_price = float(prices[lc_key])
            c_price = float(prices[c_key])

            if c_price > lc_price:
                continue  # ordering ok => do nothing

            target = RATIO_C_OVER_LC * lc_price
            prices[c_key] = float(target)
            report.log(f"[product] {c_key}: {c_price:.6f} -> {target:.6f} (rebase vs {lc_key})")
            changed = True

        return changed

    def enforce_deductible_order(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        """
        Enforce deductible monotonicity within each (product, variant).

        Rule:
            price(100) > price(200) > price(500)

        Fix (only if violated):
            Rebuild the deductible ladder from the price(100) base using:
                price(200) := DEDUCTIBLE_FACTOR[D200] * price(100)
                price(500) := DEDUCTIBLE_FACTOR[D500] * price(100)
        """
        changed = False
        grouped = group_by_product_and_variant(items)

        for (_product, _variant), m in grouped.items():
            if Deductible.D100 not in m:
                continue

            p100 = float(prices[m[Deductible.D100]])

            violates = False
            if Deductible.D200 in m and not (p100 > float(prices[m[Deductible.D200]])):
                violates = True
            if (
                Deductible.D200 in m
                and Deductible.D500 in m
                and (float(prices[m[Deductible.D200]]) <= float(prices[m[Deductible.D500]]))
            ):
                violates = True

            if not violates:
                continue

            # Fix by rebasing from 100
            for d in (Deductible.D200, Deductible.D500):
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
            Rebuild the entire variant ladder from base using:
                comfort := VARIANT_FACTOR[COMFORT] * base
                premium := VARIANT_FACTOR[PREMIUM] * base
        """
        changed = False
        grouped = group_by_product_and_deductible(items)

        for (_product, _deductible), m in grouped.items():
            base_keys = [m[v] for v in (Variant.COMPACT, Variant.BASIC) if v in m]
            if not base_keys:
                continue

            base = max(float(prices[k]) for k in base_keys)

            violates = False
            if Variant.COMFORT in m and (float(prices[m[Variant.COMFORT]]) <= base):
                violates = True

            if Variant.PREMIUM in m:
                lower = float(prices[m[Variant.COMFORT]]) if Variant.COMFORT in m else base
                if (float(prices[m[Variant.PREMIUM]]) <= lower):
                    violates = True

            if not violates:
                continue

            # Fix entire ladder from base
            if Variant.COMFORT in m:
                old = float(prices[m[Variant.COMFORT]])
                target = VARIANT_FACTOR[Variant.COMFORT] * base
                prices[m[Variant.COMFORT]] = float(target)
                report.log(f"[variant] {m[Variant.COMFORT]}: {old:.6f} -> {target:.6f}")
                changed = True

            if Variant.PREMIUM in m:
                old = float(prices[m[Variant.PREMIUM]])
                target = VARIANT_FACTOR[Variant.PREMIUM] * base
                prices[m[Variant.PREMIUM]] = float(target)
                report.log(f"[variant] {m[Variant.PREMIUM]}: {old:.6f} -> {target:.6f}")
                changed = True

        return changed
