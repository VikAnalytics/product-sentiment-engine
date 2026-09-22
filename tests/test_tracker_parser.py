"""
Tests for the tracker's JSON sentiment parser.

Importing tracker pulls in sentence_transformers, which is heavy but already a
runtime dependency; no network or DB access happens at import time.
"""
import json

import pytest

tracker = pytest.importorskip("tracker")


def _payload(**overrides):
    base = {
        "pros": "Strong demand for the new tier.",
        "cons": "Churn risk from the price increase.",
        "verbatim_quotes": "People will cancel over this.",
        "source_url": "https://example.com/a",
        "sentiment_score": 4,
        "implication_tag": "monitor",
    }
    base.update(overrides)
    return json.dumps(base)


class TestParseJsonSentiment:
    def test_parses_a_full_payload(self):
        out = tracker._parse_json_sentiment(_payload())
        assert out["pros"].startswith("Strong demand")
        assert out["sentiment_score"] == 4
        assert out["implication_tag"] == "monitor"

    def test_clamps_score_to_range(self):
        assert tracker._parse_json_sentiment(_payload(sentiment_score=99))["sentiment_score"] == 10
        assert tracker._parse_json_sentiment(_payload(sentiment_score=-99))["sentiment_score"] == -10

    def test_drops_an_invalid_tag(self):
        assert tracker._parse_json_sentiment(_payload(implication_tag="banana"))["implication_tag"] is None

    def test_keeps_a_score_only_reading(self):
        """Headline-only events have nothing to quote, but the score still drives
        the feed badge, the rankings and the simulator's sentiment factor."""
        out = tracker._parse_json_sentiment(
            _payload(pros="", cons="", verbatim_quotes="", source_url="", sentiment_score=-6)
        )
        assert out is not None
        assert out["sentiment_score"] == -6
        assert out["pros"] == "" and out["cons"] == ""

    def test_keeps_a_score_of_zero(self):
        out = tracker._parse_json_sentiment(
            _payload(pros="", cons="", verbatim_quotes="", sentiment_score=0)
        )
        assert out is not None
        assert out["sentiment_score"] == 0

    def test_rejects_a_reading_with_neither_prose_nor_score(self):
        assert tracker._parse_json_sentiment(
            _payload(pros="", cons="", verbatim_quotes="", sentiment_score=None)
        ) is None

    def test_keeps_prose_when_the_score_is_missing(self):
        out = tracker._parse_json_sentiment(_payload(sentiment_score=None))
        assert out is not None
        assert out["sentiment_score"] is None

    def test_rejects_malformed_json(self):
        assert tracker._parse_json_sentiment("not json at all") is None

    def test_rejects_a_json_list(self):
        assert tracker._parse_json_sentiment('["a", "b"]') is None


class TestBuildSourceType:
    def test_joins_active_sources_in_order(self):
        assert tracker._build_source_type(True, True, False, True, False, True) == (
            "hn|reddit|stocktwits|gnews_general"
        )

    def test_unknown_when_nothing_is_active(self):
        assert tracker._build_source_type(False, False, False) == "unknown"
