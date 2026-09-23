import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

from check_pipeline_health import assess

STEPS = ['scout', 'tracker']


def row(step, status, **kw):
    return {'step_name': step, 'status': status, 'started_at': kw.pop('at', '2026-09-23T21:00:00Z'),
            'error_message': kw.pop('error', None), 'rows_processed': kw.pop('rows', None)}


class TestAssess:
    def test_all_success_is_quiet(self):
        code, lines = assess([row('scout', 'success'), row('tracker', 'success')], STEPS)
        assert code == 0
        assert 'Every step reported success.' in lines[-1]

    # The June failure: the run finishes, reports success, and writes nothing.
    def test_degraded_step_alerts(self):
        code, lines = assess(
            [row('scout', 'degraded', error='extraction call failed, no targets or events created'),
             row('tracker', 'success')], STEPS)
        assert code == 1
        assert any('extraction call failed' in l for l in lines)

    def test_failed_step_alerts(self):
        code, _ = assess([row('scout', 'failed'), row('tracker', 'success')], STEPS)
        assert code == 1

    # A step that never starts writes no row, so absence has to be looked for.
    def test_missing_step_alerts(self):
        code, lines = assess([row('scout', 'success')], STEPS)
        assert code == 1
        assert any('did not run' in l for l in lines)

    def test_step_left_running_alerts(self):
        code, lines = assess([row('scout', 'running'), row('tracker', 'success')], STEPS)
        assert code == 1
        assert any('never finished' in l for l in lines)

    # A retry that succeeds should clear the earlier attempt, not alert on it.
    def test_later_success_supersedes_earlier_degraded(self):
        code, _ = assess([
            row('scout', 'degraded', at='2026-09-23T04:32:00Z', error='nothing extracted'),
            row('scout', 'success', at='2026-09-23T21:00:00Z'),
            row('tracker', 'success', at='2026-09-23T21:05:00Z'),
        ], STEPS)
        assert code == 0

    def test_no_rows_at_all_alerts(self):
        code, lines = assess([], STEPS, hours=6)
        assert code == 1
        assert 'no steps recorded' in lines[0]

    def test_extra_steps_are_reported_too(self):
        code, lines = assess(
            [row('scout', 'success'), row('tracker', 'success'), row('weekly_brief', 'degraded')], STEPS)
        assert code == 1
        assert any('weekly_brief' in l for l in lines)
