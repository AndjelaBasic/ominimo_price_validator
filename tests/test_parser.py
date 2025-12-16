# tests/test_parser.py
from __future__ import annotations

import pytest

from src.parser import DefaultPriceParser
from src.core import Product, Variant, Deductible

def test_parse_mtpl():
    p = DefaultPriceParser()
    item = p.parse_key("mtpl")

    # product
    if Product is None:
        assert item.product == "mtpl"
    else:
        assert item.product == Product.MTPL  # type: ignore[attr-defined]

    assert item.variant is None
    assert item.deductible is None


def test_parse_regular_key():
    p = DefaultPriceParser()
    item = p.parse_key("casco_basic_200")

    if Product is None:
        assert item.product == "casco"
    else:
        assert item.product == Product.CASCO  # type: ignore[attr-defined]

    if Variant is None:
        assert item.variant == "basic"
    else:
        assert item.variant == Variant.BASIC  # type: ignore[attr-defined]

    if Deductible is None:
        assert item.deductible == 200
    else:
        assert item.deductible == Deductible.D200  # type: ignore[attr-defined]


def test_invalid_key_raises():
    p = DefaultPriceParser()

    with pytest.raises(ValueError):
        p.parse_key("limitedcasco_basic_100")  # missing underscore

    with pytest.raises(ValueError):
        p.parse_key("casco_basic_300")  # invalid deductible
