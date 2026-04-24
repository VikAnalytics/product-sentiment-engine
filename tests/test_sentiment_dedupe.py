from sentiment_dedupe import (
    dedupe_lines,
    dedupe_pros_cons_text,
    line_similarity,
    normalize_for_dedupe,
    significant_words,
    to_bullet_lines,
)


class TestNormalizeForDedupe:
    def test_lowercases_and_strips_punctuation(self):
        assert normalize_for_dedupe("Hello, World!") == "hello world"

    def test_collapses_whitespace(self):
        assert normalize_for_dedupe("a  b   c") == "a b c"

    def test_empty(self):
        assert normalize_for_dedupe("") == ""
        assert normalize_for_dedupe(None) == ""


class TestSignificantWords:
    def test_drops_stopwords(self):
        words = significant_words("the quick brown fox")
        assert words == {"quick", "brown", "fox"}

    def test_empty(self):
        assert significant_words("") == set()


class TestLineSimilarity:
    def test_identical(self):
        assert line_similarity("Fast loading speed", "Fast loading speed")

    def test_near_duplicate(self):
        assert line_similarity(
            "The product has fast loading speeds",
            "Fast loading speeds are great",
        )

    def test_unrelated(self):
        assert not line_similarity(
            "Fast loading speed",
            "Customer support is poor",
        )

    def test_empty_lines(self):
        assert not line_similarity("", "anything")
        assert not line_similarity("anything", "")


class TestDedupeLines:
    def test_removes_exact_duplicates(self):
        out = dedupe_lines(["A", "A", "B"])
        assert len(out) == 2
        assert set(out) == {"A", "B"}

    def test_keeps_longer_version(self):
        out = dedupe_lines([
            "Fast loading",
            "Fast loading speeds on all pages",
        ])
        assert out == ["Fast loading speeds on all pages"]

    def test_empty_and_whitespace_dropped(self):
        assert dedupe_lines(["", "   ", "A"]) == ["A"]

    def test_empty_input(self):
        assert dedupe_lines([]) == []


class TestToBulletLines:
    def test_bullet_prefixes_stripped(self):
        out = to_bullet_lines("- first\n* second\n• third")
        assert out == ["first", "second", "third"]

    def test_pipe_separator(self):
        out = to_bullet_lines("a | b | c")
        assert out == ["a", "b", "c"]

    def test_ignores_none_placeholders(self):
        out = to_bullet_lines("real thing\nNone\nn/a")
        assert out == ["real thing"]

    def test_empty(self):
        assert to_bullet_lines("") == []
        assert to_bullet_lines(None) == []


class TestDedupeProsConsText:
    def test_full_pipeline(self):
        pros_in = "Fast loading\nFast loading speeds on all pages\nGood UX"
        cons_in = "Expensive\nExpensive pricing"
        pros_out, cons_out = dedupe_pros_cons_text(pros_in, cons_in)
        assert "Fast loading speeds on all pages" in pros_out
        assert "Good UX" in pros_out
        assert "Expensive" in cons_out
