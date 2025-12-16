from __future__ import annotations

import math
from src.main import PricingEngine
from src.core import DEDUCTIBLE_FACTOR, VARIANT_FACTOR, RATIO_LC_OVER_MTPL, RATIO_C_OVER_MTPL


def build_complete_consistent_prices(mtpl: float = 400.0) -> dict[str, float]:
    prices = {"mtpl": float(mtpl)}
    for product, base_100 in [("limited_casco", 700.0), ("casco", 900.0)]:
        for variant in ["compact", "basic", "comfort", "premium"]:
            for deductible in [100, 200, 500]:
                vf = 1.0 if variant in ("compact", "basic") else VARIANT_FACTOR[variant]
                df = DEDUCTIBLE_FACTOR[deductible]
                prices[f"{product}_{variant}_{deductible}"] = base_100 * vf * df
    return prices


def test_enforces_deductible_order_exact():
    engine = PricingEngine()
    prices = build_complete_consistent_prices()

    prices["casco_basic_200"] = prices["casco_basic_100"] * 2.0
    prices["casco_basic_500"] = prices["casco_basic_100"] * 3.0

    res = engine.validate_and_fix(prices)
    fixed = res.fixed_prices

    assert math.isclose(fixed["casco_basic_200"], DEDUCTIBLE_FACTOR[200] * fixed["casco_basic_100"], abs_tol=1e-9)
    assert math.isclose(fixed["casco_basic_500"], DEDUCTIBLE_FACTOR[500] * fixed["casco_basic_100"], abs_tol=1e-9)
    assert res.converged is True


def test_enforces_variant_order_by_raising():
    engine = PricingEngine()
    prices = build_complete_consistent_prices()

    prices["limited_casco_comfort_100"] = prices["limited_casco_basic_100"] * 0.5
    prices["limited_casco_premium_100"] = prices["limited_casco_basic_100"] * 0.6

    res = engine.validate_and_fix(prices)
    fixed = res.fixed_prices

    base = max(fixed["limited_casco_compact_100"], fixed["limited_casco_basic_100"])
    assert fixed["limited_casco_comfort_100"] >= VARIANT_FACTOR["comfort"] * base - 1e-9
    assert fixed["limited_casco_premium_100"] >= VARIANT_FACTOR["premium"] * base - 1e-9
    assert res.converged is True


def test_enforces_product_minima_ratios():
    engine = PricingEngine()
    prices = build_complete_consistent_prices()

    # Create an ordering violation WITHOUT triggering MTPL anchor:
    # Make MTPL larger than both LC and Casco minima.
    lc_min0 = min(v for k, v in prices.items() if k.startswith("limited_casco_"))
    c_min0  = min(v for k, v in prices.items() if k.startswith("casco_"))
    prices["mtpl"] = max(lc_min0, c_min0) + 100.0  # enough to violate both

    res = engine.validate_and_fix(prices)
    fixed = res.fixed_prices

    mtpl = fixed["mtpl"]
    lc_min = min(v for k, v in fixed.items() if k.startswith("limited_casco_"))
    c_min = min(v for k, v in fixed.items() if k.startswith("casco_"))

    assert lc_min >= RATIO_LC_OVER_MTPL * mtpl - 1e-6
    assert c_min >= RATIO_C_OVER_MTPL * mtpl - 1e-6
    assert res.converged is True


def test_enforces_limited_casco_less_than_casco_matched():
    engine = PricingEngine()
    prices = build_complete_consistent_prices()

    prices["limited_casco_basic_100"] = 2000.0
    prices["casco_basic_100"] = 1500.0

    res = engine.validate_and_fix(prices)
    fixed = res.fixed_prices

    assert fixed["limited_casco_basic_100"] < fixed["casco_basic_100"]
    assert res.converged is True
