from sec_scout import _filing_headline, _filing_published_at


class TestFilingHeadline:
    def test_names_the_item(self):
        filing = {"form_type": "8-K", "items": "2.02,9.01"}
        assert _filing_headline(filing, "ADOBE INC.") == "[8-K · Results of operations] ADOBE INC."

    def test_exhibits_alone_are_not_a_story(self):
        # 9.01 only ever means "exhibits attached", so it never stands as the label.
        filing = {"form_type": "8-K", "items": "9.01"}
        assert _filing_headline(filing, "NEWS CORP") == "[8-K] NEWS CORP"

    def test_routine_other_events_is_visible_as_routine(self):
        filing = {"form_type": "8-K", "items": "8.01,9.01"}
        assert _filing_headline(filing, "NEWS CORP") == "[8-K · Other events] NEWS CORP"

    def test_two_items_both_shown(self):
        filing = {"form_type": "8-K", "items": "2.02,5.02"}
        headline = _filing_headline(filing, "GE")
        assert "Results of operations" in headline and "Officer or director change" in headline

    def test_unknown_item_code_ignored(self):
        filing = {"form_type": "8-K", "items": "99.99"}
        assert _filing_headline(filing, "GE") == "[8-K] GE"

    def test_form_without_items(self):
        filing = {"form_type": "10-Q", "items": ""}
        assert _filing_headline(filing, "ADOBE INC.") == "[10-Q] ADOBE INC."


class TestFilingPublishedAt:
    def test_uses_acceptance_time(self):
        filing = {"filing_date": "2026-09-22", "accepted_at": "2026-09-21T20:23:10.000Z"}
        # The real News Corp 8-K: accepted the evening before its filing date.
        assert _filing_published_at(filing).startswith("2026-09-21T20:23:10")

    def test_falls_back_to_just_after_the_close(self):
        filing = {"filing_date": "2026-09-22", "accepted_at": ""}
        assert _filing_published_at(filing) == "2026-09-22T21:00:00+00:00"

    def test_unparseable_acceptance_falls_back(self):
        filing = {"filing_date": "2026-09-22", "accepted_at": "not a timestamp"}
        assert _filing_published_at(filing) == "2026-09-22T21:00:00+00:00"
