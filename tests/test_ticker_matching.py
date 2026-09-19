"""
Tests for the company-name guard in scripts/backfill_tickers.py.

The guard is what separates a real mapping from a confident hallucination, so it
has to accept the awkward-but-correct cases and still reject the plausible-looking
wrong ones.
"""
import os
import sys

import pytest

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "scripts"))

bt = pytest.importorskip("backfill_tickers")


class TestNamesMatch:
    @pytest.mark.parametrize("company,listed", [
        ("Alphabet", "Alphabet Inc."),
        ("Stryker", "Stryker Corporation"),
        ("Super Micro Computer", "Super Micro Computer, Inc."),
        ("Entergy Louisiana", "Entergy Corporation"),
        ("Snapchat", "Snap Inc."),
        ("Supermicro", "Super Micro Computer, Inc."),
        ("TSMC", "Taiwan Semiconductor Manufacturing Company"),
        ("TSMC", "Taiwan Semiconductor Manufacturing Company Limited"),
        ("IBM", "International Business Machines Corporation"),
        ("The New York Times", "New York Times Company"),
    ])
    def test_accepts_the_same_company(self, company, listed):
        assert bt._names_match(company, listed)

    @pytest.mark.parametrize("company,listed", [
        ("Arm", "NVIDIA Corporation"),
        ("Bandai Namco", "Nintendo Co., Ltd."),
        ("Standard Chartered", "State Street Corporation"),
        ("Paramount", "Banzai International, Inc."),
        ("Mojang Studios", "Roblox Corporation"),
    ])
    def test_rejects_a_different_company(self, company, listed):
        assert not bt._names_match(company, listed)

    def test_rejects_empty_input(self):
        assert not bt._names_match("", "Apple Inc.")
        assert not bt._names_match("Apple", "")

    def test_suffix_only_names_do_not_match_everything(self):
        assert not bt._names_match("Holdings Inc.", "Apple Inc.")


class TestCleanTicker:
    @pytest.mark.parametrize("raw,expected", [
        ("AAPL", "AAPL"),
        ("  aapl  ", "AAPL"),
        ("$TSLA", "TSLA"),
        ("NASDAQ: NVDA", "NVDA"),
        ("`MSFT`", "MSFT"),
        ("BRK.B", "BRK.B"),
    ])
    def test_normalizes(self, raw, expected):
        assert bt._clean_ticker(raw) == expected

    @pytest.mark.parametrize("raw", ["PRIVATE", "none", "N/A", "-", "", None,
                                     "a very long sentence instead of a ticker"])
    def test_rejects_non_tickers(self, raw):
        assert bt._clean_ticker(raw) is None
