# tests/test_engine.py
from __future__ import annotations

import math

import pytest

from src.main import PricingEngine
from src.core import (
    DEDUCTIBLE_FACTOR,
    VARIANT_FACTOR,
    RATIO_LC_OVER_MTPL,
    RATIO_C_OVER_MTPL,
    RATIO_C_OVER_LC,
)

# Optional enums (depending on your current core.py)
try:
    from src.core import Deductible, Variant
except Exception:  # pragma: no cover
    Deductible = None  # type: ignore
    Variant = None  # type: ignore


def deductible_factor(d: int) -> float:
    """
    Supports either:
      - DEDUCTIBLE_FACTOR keyed by ints (100/200/500), or
      - DEDUCTIBLE_FACTOR keyed by Deductible Enum.
    """
    if d in DEDUCTIBLE_FACTOR:  # type: ignore[operator]
        return float(DEDUCTIBLE_FACTOR[d])  # type: ignore[index]
    if Deductible is None:
        raise KeyError(f"Missing deductible factor for {d} and no Deductible enum available.")
    enum_map = {100: Deductible.D100, 200: Deductible.D200, 500: Deductible.D500}
    return float(DEDUCTIBLE_FACTOR[enum_map[d]])  # type: ignore[index]


def variant_factor(v: str) -> float:
    """
    Supports either:
      - VARIANT_FACTOR keyed by strings, or
      - VARIANT_FACTOR keyed by Variant Enum.
    """
    if v in VARIANT_FACTOR:  # type: ignore[operator]
        return float(VARIANT_FACTOR[v])  # type: ignore[index]
    if Variant is None:
        raise KeyError(f"Missing variant factor for '{v}' and no Variant enum available.")
    enum_map = {
        "compact": Variant.COMPACT,
        "basic": Variant.BASIC,
        "comfort": Variant.COMFORT,
        "premium": Variant.PREMIUM,
    }
    return float(VARIANT_FACTOR[enum_map[v]])  # type: ignore[index]


def build_complete_consistent_prices(mtpl: float = 400.0) -> dict[str, float]:
    prices: dict[str, float] = {"mtpl": float(mtpl)}
    for product, base_100 in [("limited_casco", 700.0), ("casco", 900.0)]:
        for variant in ["compact", "basic", "comfort", "premium"]:
            for deductible in [100, 200, 500]:
                vf = variant_factor(variant)
                df = deductible_factor(deductible)
                prices[f"{product}_{variant}_{deductible}"] = float(base_100 * vf * df)
    return prices


def test_enforces_deductible_order_exact():
    engine = PricingEngine()
    prices = build_complete_consistent_prices()

    # Break ladder: make 200 and 500 more expensive than 100
    prices["casco_basic_200"] = prices["casco_basic_100"] * 2.0
    prices["casco_basic_500"] = prices["casco_basic_100"] * 3.0

    res = engine.validate_and_fix(prices)
    fixed = res.fixed_prices

    assert math.isclose(
        fixed["casco_basic_200"],
        deductible_factor(200) * fixed["casco_basic_100"],
        abs_tol=1e-9,
    )
    assert math.isclose(
        fixed["casco_basic_500"],
        deductible_factor(500) * fixed["casco_basic_100"],
        abs_tol=1e-9,
    )
    assert res.converged is True


def test_enforces_variant_order_rebuilds_ladder_when_violated():
    engine = PricingEngine()
    prices = build_complete_consistent_prices()

    # Break variant ordering: comfort/premium below base(compact/basic)
    prices["limited_casco_comfort_100"] = prices["limited_casco_basic_100"] * 0.5
    prices["limited_casco_premium_100"] = prices["limited_casco_basic_100"] * 0.6

    res = engine.validate_and_fix(prices)
    fixed = res.fixed_prices

    base = max(fixed["limited_casco_compact_100"], fixed["limited_casco_basic_100"])
    assert fixed["limited_casco_comfort_100"] >= variant_factor("comfort") * base - 1e-9
    assert fixed["limited_casco_premium_100"] >= variant_factor("premium") * base - 1e-9
    assert fixed["limited_casco_comfort_100"] < fixed["limited_casco_premium_100"]
    assert res.converged is True


def test_product_minima_ratios_no_change_when_order_ok():
    engine = PricingEngine()
    prices = build_complete_consistent_prices()

    res = engine.validate_and_fix(prices)
    fixed = res.fixed_prices

    # If already consistent, nothing should change (use approx for float stability)
    for k, v in prices.items():
        assert fixed[k] == pytest.approx(v, rel=0.0, abs=1e-12)

    assert res.converged is True


def test_enforces_product_minima_ratios_when_group_min_below_mtpl():
    engine = PricingEngine()
    prices = build_complete_consistent_prices(mtpl=400.0)

    # Create an ordering violation WITHOUT touching MTPL (avoid anchor interactions):
    # scale down both groups so their minima fall below MTPL.
    for k in list(prices.keys()):
        if k.startswith("limited_casco_") or k.startswith("casco_"):
            prices[k] *= 0.25  # minima now below 400 -> triggers product-min fix

    res = engine.validate_and_fix(prices)
    fixed = res.fixed_prices

    mtpl = fixed["mtpl"]
    lc_min = min(v for k, v in fixed.items() if k.startswith("limited_casco_"))
    c_min = min(v for k, v in fixed.items() if k.startswith("casco_"))

    # After fixing, minima are set to ratio * MTPL (via group scaling)
    assert lc_min >= RATIO_LC_OVER_MTPL * mtpl - 1e-9
    assert c_min >= RATIO_C_OVER_MTPL * mtpl - 1e-9
    assert res.converged is True


def test_enforces_limited_casco_less_than_casco_matched():
    engine = PricingEngine()
    prices = build_complete_consistent_prices()

    # Break matched ordering for (basic, 100)
    prices["limited_casco_basic_100"] = 2000.0
    prices["casco_basic_100"] = 1500.0

    res = engine.validate_and_fix(prices)
    fixed = res.fixed_prices

    assert fixed["limited_casco_basic_100"] < fixed["casco_basic_100"]

    # With your current fixer, casco is set to RATIO_C_OVER_LC * lc (only if violated)
    assert fixed["casco_basic_100"] == pytest.approx(RATIO_C_OVER_LC * fixed["limited_casco_basic_100"], abs=1e-9)

    assert res.converged is True
