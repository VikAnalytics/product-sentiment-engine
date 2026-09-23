from scout import (
    _cites_its_article,
    _is_junk_name,
    _parse_ai_extraction_line,
    _strip_parent_possessive,
)


class TestParseAiExtractionLine:
    def test_company_line_with_article_number(self):
        out = _parse_ai_extraction_line("COMPANY | 3 | Apple | New iPhone launched")
        assert out == ("COMPANY", "Apple", "New iPhone launched", "", 3)

    def test_product_line_with_parent(self):
        out = _parse_ai_extraction_line(
            "PRODUCT | 7 | Pixel 9 | Announced at Google I/O | Google"
        )
        assert out == ("PRODUCT", "Pixel 9", "Announced at Google I/O", "Google", 7)

    def test_macro_line(self):
        out = _parse_ai_extraction_line(
            "MACRO | 2 | US-China Trade Tensions | New chip export ban announced"
        )
        assert out is not None
        assert out.target_type == "MACRO"
        assert out.name == "US-China Trade Tensions"
        assert out.article_idx == 2

    def test_bracketed_article_number(self):
        out = _parse_ai_extraction_line("COMPANY | [12] | Apple | event")
        assert out is not None
        assert out.article_idx == 12

    # The numberless format predates the article reference. A model that drops the
    # number still produces a usable line; it just loses its source.
    def test_legacy_company_line_without_number(self):
        out = _parse_ai_extraction_line("COMPANY | Apple | New iPhone launched")
        assert out == ("COMPANY", "Apple", "New iPhone launched", "", None)

    def test_legacy_product_line_without_number(self):
        out = _parse_ai_extraction_line("PRODUCT | Pixel 9 | Announced at I/O | Google")
        assert out == ("PRODUCT", "Pixel 9", "Announced at I/O", "Google", None)

    def test_lowercase_type_normalized(self):
        out = _parse_ai_extraction_line("company | 1 | Apple | event")
        assert out is not None
        assert out.target_type == "COMPANY"

    def test_invalid_type_rejected(self):
        assert _parse_ai_extraction_line("UNKNOWN | foo | bar") is None

    def test_too_few_parts(self):
        assert _parse_ai_extraction_line("COMPANY | Apple") is None

    def test_empty_name(self):
        assert _parse_ai_extraction_line("COMPANY | 3 |  | event") is None

    def test_no_pipe(self):
        assert _parse_ai_extraction_line("Just some prose") is None

    def test_whitespace_trimmed(self):
        out = _parse_ai_extraction_line("  COMPANY | 4 | Apple | event  ")
        assert out == ("COMPANY", "Apple", "event", "", 4)

    def test_numeric_company_name_is_not_read_as_article_number(self):
        # Without a fourth field there is no number to take: "3M" is the name.
        out = _parse_ai_extraction_line("COMPANY | 3M | Raised guidance")
        assert out == ("COMPANY", "3M", "Raised guidance", "", None)


class TestIsJunkName:
    # Real names the scout should keep accepting.
    def test_accepts_branded_products(self):
        for name in ["Snapdragon 8 Elite Gen 6", "Cadillac Vistiq", "GPT-6 Sol",
                     "Opus 5.5", "OS3", "Pixel 9", "iPhone 18 Pro"]:
            assert _is_junk_name(name, "PRODUCT") is None, name

    def test_accepts_real_companies(self):
        for name in ["Apple", "Novo Nordisk", "Samsung C&T", "Emirates", "Verizon"]:
            assert _is_junk_name(name, "COMPANY") is None, name

    # Names that created junk targets in production.
    def test_rejects_sentinels(self):
        assert _is_junk_name("None", "COMPANY")
        assert _is_junk_name("N/A", "PRODUCT")
        assert _is_junk_name("   ", "COMPANY")

    def test_rejects_descriptions_posing_as_products(self):
        assert _is_junk_name("New Fitness Tracker", "PRODUCT")
        assert _is_junk_name("New Treadmills", "PRODUCT")
        assert _is_junk_name("Texture and Grain Controls", "PRODUCT")
        assert _is_junk_name("Smart Circuit Breaker", "PRODUCT")

    def test_rejects_countries_and_groups_as_companies(self):
        for name in ["Germany", "Denmark", "NATO", "Houthis", "European Union",
                     "Federal Reserve", "United States"]:
            assert _is_junk_name(name, "COMPANY"), name

    def test_rejects_company_named_after_a_macro_theme(self):
        themes = ["US-China Trade Tensions", "AI Regulation"]
        assert _is_junk_name("AI Regulation", "COMPANY", themes)
        assert _is_junk_name("Anthropic", "COMPANY", themes) is None

    # A country is a plausible product name, and products are not geopolitics.
    def test_country_rule_applies_to_companies_only(self):
        assert _is_junk_name("Georgia", "PRODUCT") is None


class TestCitesItsArticle:
    QUALCOMM = {
        "title": "Qualcomm launches two new smartphone chips with emphasis on AI",
        "summary": "The chipmaker announced a standard and an Extreme version.",
    }
    IRAN = {
        "title": "Trump had a 'good meeting' with Iranian officials, warning he may annihilate the Islamic Republic",
        "summary": "Remarks at the UN General Assembly escalated tensions.",
    }

    def test_company_named_in_the_article(self):
        assert _cites_its_article("COMPANY", "Qualcomm", "Launched two chips.", self.QUALCOMM)

    def test_company_absent_from_the_article(self):
        # The drift this guards against: a real headline stapled to another story.
        assert not _cites_its_article("COMPANY", "Bose", "Bose returns with open earbuds.", self.QUALCOMM)

    def test_product_named_in_the_article(self):
        assert _cites_its_article("PRODUCT", "Snapdragon 8 Elite Extreme", "New chip.", self.QUALCOMM)

    def test_macro_matching_the_article(self):
        assert _cites_its_article(
            "MACRO", "Middle East Tensions",
            "Trump's posturing toward Iran raises Middle East tensions.", self.IRAN,
        )

    def test_macro_about_a_different_story(self):
        assert not _cites_its_article(
            "MACRO", "Climate & Clean Energy Policy",
            "The unveiling of new electric vehicles signals commitment to clean energy.",
            self.QUALCOMM,
        )

    def test_empty_article_never_matches(self):
        assert not _cites_its_article("COMPANY", "Qualcomm", "x", {"title": "", "summary": ""})


class TestStripParentPossessive:
    def test_strips_the_companys_possessive(self):
        assert _strip_parent_possessive("Qualcomm's Snapdragon 8 Elite Gen 6", "Qualcomm") == "Snapdragon 8 Elite Gen 6"

    def test_strips_curly_apostrophe(self):
        assert _strip_parent_possessive("Qualcomm’s Snapdragon 8 Elite", "Qualcomm") == "Snapdragon 8 Elite"

    def test_keeps_company_word_when_the_rest_is_generic(self):
        # "Watch" alone is not a product name, so the full name stands.
        assert _strip_parent_possessive("Apple's Watch", "Apple") == "Apple's Watch"

    def test_leaves_non_possessive_names_alone(self):
        assert _strip_parent_possessive("Apple Watch Series 10", "Apple") == "Apple Watch Series 10"

    def test_no_parent(self):
        assert _strip_parent_possessive("Snapdragon 8", "") == "Snapdragon 8"
