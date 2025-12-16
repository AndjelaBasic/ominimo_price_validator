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
        changed = False
        mtpl = float(prices["mtpl"])
        by_product = keys_by_product(items)

        for product, ratio in (("limited_casco", RATIO_LC_OVER_MTPL), ("casco", RATIO_C_OVER_MTPL)):
            keys = by_product.get(product, [])
            if not keys:
                continue
            current_min = min(float(prices[k]) for k in keys)
            target_min = ratio * mtpl
            if current_min < target_min:
                scale = target_min / current_min
                for k in keys:
                    prices[k] = float(prices[k]) * scale
                report.log(f"[product-min] scaled {product} by {scale:.6f}")
                changed = True

        return changed

    def enforce_limited_casco_less_than_casco(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        changed = False
        lc_lookup = {}
        for it in items:
            if it.product == "limited_casco":
                lc_lookup[(it.variant, it.deductible)] = it.key

        for it in items:
            if it.product == "casco":
                lk = lc_lookup.get((it.variant, it.deductible))
                if lk is None:
                    continue
                if float(prices[it.key]) <= float(prices[lk]):
                    old = float(prices[it.key])
                    new = float(prices[lk]) + self.eps
                    prices[it.key] = float(new)
                    report.log(f"[product] {it.key}: {old:.6f} -> {new:.6f} (>{lk})")
                    changed = True

        return changed

    def enforce_deductible_order(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        changed = False
        grouped = group_by_product_and_variant(items)

        for (_product, _variant), m in grouped.items():
            if 100 not in m:
                continue
            base = float(prices[m[100]])

            for d in (200, 500):
                if d not in m:
                    continue
                target = DEDUCTIBLE_FACTOR[d] * base
                old = float(prices[m[d]])
                if abs(old - target) > 1e-12:
                    prices[m[d]] = float(target)
                    report.log(f"[deductible] {m[d]}: {old:.6f} -> {target:.6f}")
                    changed = True

        return changed

    def enforce_variant_order(self, prices: Dict[str, float], items: List[PricingItem], report: FixReport) -> bool:
        changed = False
        grouped = group_by_product_and_deductible(items)

        for (_product, _deductible), m in grouped.items():
            base_keys = [m[v] for v in ("compact", "basic") if v in m]
            if not base_keys:
                continue
            base = max(float(prices[k]) for k in base_keys)

            for v in ("comfort", "premium"):
                if v not in m:
                    continue
                target = VARIANT_FACTOR[v] * base
                old = float(prices[m[v]])
                if old < target - 1e-12:
                    prices[m[v]] = float(target)
                    report.log(f"[variant] {m[v]}: {old:.6f} -> {target:.6f}")
                    changed = True

        return changed
