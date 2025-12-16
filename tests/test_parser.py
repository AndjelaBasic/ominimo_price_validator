import pytest
from src.parser import DefaultPriceParser

def test_parse_mtpl():
    p = DefaultPriceParser()
    item = p.parse_key("mtpl")
    assert item.product == "mtpl"
    assert item.variant is None
    assert item.deductible is None


def test_parse_regular_key():
    p = DefaultPriceParser()
    item = p.parse_key("casco_basic_200")
    assert item.product == "casco"
    assert item.variant == "basic"
    assert item.deductible == 200


def test_invalid_key_raises():
    p = DefaultPriceParser()
    with pytest.raises(ValueError):
        p.parse_key("limitedcasco_basic_100")
    with pytest.raises(ValueError):
        p.parse_key("casco_basic_300")
