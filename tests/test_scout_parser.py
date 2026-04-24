from scout import _parse_ai_extraction_line


class TestParseAiExtractionLine:
    def test_company_line(self):
        out = _parse_ai_extraction_line("COMPANY | Apple | New iPhone launched")
        assert out == ("COMPANY", "Apple", "New iPhone launched", "")

    def test_product_line_with_parent(self):
        out = _parse_ai_extraction_line(
            "PRODUCT | Pixel 9 | Announced at Google I/O | Google"
        )
        assert out == ("PRODUCT", "Pixel 9", "Announced at Google I/O", "Google")

    def test_macro_line(self):
        out = _parse_ai_extraction_line(
            "MACRO | US-China Trade Tensions | New chip export ban announced"
        )
        assert out is not None
        assert out[0] == "MACRO"
        assert out[1] == "US-China Trade Tensions"

    def test_lowercase_type_normalized(self):
        out = _parse_ai_extraction_line("company | Apple | event")
        assert out is not None
        assert out[0] == "COMPANY"

    def test_invalid_type_rejected(self):
        assert _parse_ai_extraction_line("UNKNOWN | foo | bar") is None

    def test_too_few_parts(self):
        assert _parse_ai_extraction_line("COMPANY | Apple") is None

    def test_empty_name(self):
        assert _parse_ai_extraction_line("COMPANY |  | event") is None

    def test_no_pipe(self):
        assert _parse_ai_extraction_line("Just some prose") is None

    def test_whitespace_trimmed(self):
        out = _parse_ai_extraction_line("  COMPANY | Apple | event  ")
        assert out == ("COMPANY", "Apple", "event", "")
