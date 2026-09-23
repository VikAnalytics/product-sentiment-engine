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

    def test_strips_corporate_suffix(self):
        assert normalize_target_name("Meta Platforms") == normalize_target_name("Meta")
        assert normalize_target_name("Alphabet Inc.") == normalize_target_name("Alphabet")
        assert normalize_target_name("Cisco Systems") == normalize_target_name("Cisco")

    def test_strips_stacked_suffixes(self):
        assert normalize_target_name("Prosus Holdings Group") == "prosus"

    def test_keeps_suffix_when_it_is_the_whole_name(self):
        assert normalize_target_name("Group") == "group"

    def test_only_trailing_suffixes_are_stripped(self):
        # "Group 1 Automotive" is a real dealership chain, not "1 Automotive".
        assert normalize_target_name("Group 1 Automotive") == "1 automotive group"


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
