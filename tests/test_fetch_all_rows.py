"""
Tests for config.fetch_all_rows.

PostgREST caps a response at 1000 rows and does so silently, so the paging
helper is the only thing standing between us and quietly missing data.
"""
from config import fetch_all_rows


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """Minimal stand-in for a PostgREST query builder."""

    def __init__(self, rows, calls):
        self._rows = rows
        self._calls = calls
        self._start = 0
        self._end = 0

    def range(self, start, end):
        self._start, self._end = start, end
        self._calls.append((start, end))
        return self

    def execute(self):
        return FakeResponse(self._rows[self._start:self._end + 1])


def make_factory(total_rows, calls, page_size=1000):
    rows = [{"id": i} for i in range(total_rows)]
    return lambda: FakeQuery(rows, calls)


class TestFetchAllRows:
    def test_returns_every_row_past_the_first_page(self):
        calls = []
        out = fetch_all_rows(make_factory(2350, calls))
        assert len(out) == 2350
        assert out[0]["id"] == 0 and out[-1]["id"] == 2349

    def test_stops_after_a_short_page(self):
        calls = []
        fetch_all_rows(make_factory(1500, calls))
        assert calls == [(0, 999), (1000, 1999)]

    def test_single_short_page_makes_one_call(self):
        calls = []
        out = fetch_all_rows(make_factory(12, calls))
        assert len(out) == 12
        assert calls == [(0, 999)]

    def test_exactly_one_full_page_probes_once_more(self):
        """A full page is indistinguishable from a truncated one, so the helper
        must ask again rather than assume it is done."""
        calls = []
        out = fetch_all_rows(make_factory(1000, calls))
        assert len(out) == 1000
        assert calls == [(0, 999), (1000, 1999)]

    def test_empty_result(self):
        calls = []
        assert fetch_all_rows(make_factory(0, calls)) == []

    def test_respects_a_custom_page_size(self):
        calls = []
        out = fetch_all_rows(make_factory(250, calls), page_size=100)
        assert len(out) == 250
        assert calls == [(0, 99), (100, 199), (200, 299)]

    def test_calls_the_factory_fresh_each_page(self):
        """Reusing one builder would carry the previous range and loop forever."""
        seen = []

        def factory():
            q = FakeQuery([{"id": i} for i in range(1500)], [])
            seen.append(q)
            return q

        fetch_all_rows(factory)
        assert len(seen) == 2
        assert seen[0] is not seen[1]
