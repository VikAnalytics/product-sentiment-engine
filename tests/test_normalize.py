from normalize import guess_domain, normalize_target_name


class TestNormalizeTargetName:
    def test_word_order_invariant(self):
        assert normalize_target_name("M4 iPad Air") == normalize_target_name("iPad Air M4")

    def test_strips_parentheticals(self):
        assert normalize_target_name("Fire TV app (redesigned)") == normalize_target_name("Fire TV app")

    def test_lowercases(self):
        assert normalize_target_name("APPLE") == normalize_target_name("apple")

    def test_strips_punctuation(self):
        assert normalize_target_name("AT&T, Inc.") == normalize_target_name("at t inc")

    def test_empty_string(self):
        assert normalize_target_name("") == ""

    def test_none_input(self):
        assert normalize_target_name(None) == ""

    def test_non_string(self):
        assert normalize_target_name(123) == ""

    def test_collapses_whitespace(self):
        assert normalize_target_name("  Hello   World  ") == "hello world"


class TestGuessDomain:
    def test_basic(self):
        assert guess_domain("OpenAI") == "openai.com"

    def test_removes_punctuation_and_spaces(self):
        assert guess_domain("AT&T Inc.") == "attinc.com"

    def test_empty(self):
        assert guess_domain("") == ""

    def test_none(self):
        assert guess_domain(None) == ""

    def test_only_punctuation(self):
        assert guess_domain("!!!") == ""
