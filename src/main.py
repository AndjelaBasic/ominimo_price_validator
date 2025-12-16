from __future__ import annotations

from typing import Dict

from src.core import FixResult, FixReport
from src.parser import DefaultPriceParser, BasePriceParser
from src.validator import DefaultPriceValidator, BasePriceValidator
from src.fixer import DefaultPriceFixer, BasePriceFixer


class PricingEngine:
    def __init__(
        self,
        parser: BasePriceParser = DefaultPriceParser(),
        validator: BasePriceValidator = DefaultPriceValidator(),
        fixer: BasePriceFixer = DefaultPriceFixer(),
        *,
        max_iterations: int = 10,
    ):
        self.parser = parser 
        self.validator = validator 
        self.fixer = fixer 
        self.max_iterations = max_iterations

    def validate_and_fix(self, prices: Dict[str, float]) -> FixResult:
        prices = {k: float(v) for k, v in prices.items()}
        items = self.parser.parse_all(prices)

        report = FixReport()
        report.violations_before = self.validator.validate(prices, items)

        converged = False
        iterations_used = 0

        for iteration in range(1, self.max_iterations + 1):
            iterations_used = iteration
            current = self.validator.validate(prices, items)
            # nothing to validate
            if not current:
                converged = True
                break
            # nothing to fix
            if not self.fixer.fix_pass(prices, items, report):
                break

        report.violations_after = self.validator.validate(prices, items)
        return FixResult(prices, converged, iterations_used, report)


if __name__ == "__main__":
    example_prices_to_correct = {
        "mtpl": 400,
        "limited_casco_compact_100": 820,
        "limited_casco_compact_200": 760,
        "limited_casco_compact_500": 650,
        "limited_casco_basic_100": 900,
        "limited_casco_basic_200": 780,
        "limited_casco_basic_500": 600,
        "limited_casco_comfort_100": 950,
        "limited_casco_comfort_200": 870,
        "limited_casco_comfort_500": 720,
        "limited_casco_premium_100": 1100,
        "limited_casco_premium_200": 980,
        "limited_casco_premium_500": 800,
        "casco_compact_100": 750,
        "casco_compact_200": 700,
        "casco_compact_500": 620,
        "casco_basic_100": 830,
        "casco_basic_200": 760,
        "casco_basic_500": 650,
        "casco_comfort_100": 900,
        "casco_comfort_200": 820,
        "casco_comfort_500": 720,
        "casco_premium_100": 1050,
        "casco_premium_200": 950,
        "casco_premium_500": 780,
    }

    engine = PricingEngine(max_iterations=10)
    result = engine.validate_and_fix(example_prices_to_correct)

    print("Converged:", result.converged, "Iterations:", result.iterations)

    print("\nViolations before:", len(result.report.violations_before))
    for v in result.report.violations_before:
        print(f"  [{v.category}] {v.rule}: {v.message} ({v.left_key}={v.left_value:.2f}, {v.right_key}={v.right_value:.2f})")

    print("\nFixed prices:")
    for k in sorted(result.fixed_prices.keys()):
        print(f"  {k}: {result.fixed_prices[k]:.6f}")

    if result.report.fix_log:
        print("\nFix log:")
        for line in result.report.fix_log:
            print(" ", line)

    print("\nViolations after:", len(result.report.violations_after))
    for v in result.report.violations_after:
        print(f"  [{v.category}] {v.rule}: {v.message} ({v.left_key}={v.left_value:.2f}, {v.right_key}={v.right_value:.2f})")
