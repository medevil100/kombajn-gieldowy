"""Measured activity in Telegram, including current/closed volume and real deltas."""
import copy
import unittest

import KI
from analysis_verdict import activity_summary
import test_analysis_verdict_20261031 as fixtures


class ActivityReportingTests(unittest.TestCase):
    def sample(self):
        return fixtures.AutonomousReviewTests().sample()

    def test_open_hour_has_measured_ratio_and_elapsed_time_without_stock_caveat(self):
        for ticker in ('AAA.WA', 'GOSS', 'BRK.B'):
            ev, ctx, result = self.sample()
            s = ev['snapshot']
            s.update(ticker=ticker, rvol=.7)
            text = activity_summary(s)
            self.assertIn('ostatnia zamknięta 1h: 2,00×', text)
            self.assertIn('bieżąca dotąd: 0,70× po 30 min', text)
            self.assertNotIn('za wcześnie', text)
            self.assertNotIn('świeca trwa', text)
            self.assertNotIn('poniżej średniej', text)

    def test_real_delta_uses_same_candle_and_elapsed_read_time(self):
        ev, ctx, result = self.sample()
        s = ev['snapshot']
        previous = {**s, 'acquired_at': '2026-10-12T14:15:00Z', 'volume': 170000.}
        before = copy.deepcopy((s, previous))
        text = activity_summary(s, previous)
        self.assertIn('+30 000 szt. w 15 min', text)
        self.assertEqual((s, previous), before)

    def test_reset_different_ticker_future_or_revised_volume_never_become_growth(self):
        ev, ctx, result = self.sample()
        s = ev['snapshot']
        previous = {**s, 'acquired_at': '2026-10-12T14:15:00Z', 'volume': 170000.}
        for changes in ({'candle_time': '2026-10-12T13:00:00Z'}, {'ticker': 'OTHER'},
                        {'interval': '1d'}, {'acquired_at': s['acquired_at']},
                        {'acquired_at': '2026-10-12T14:31:00Z'}, {'volume': 300000.}, {'volume': None}):
            self.assertNotIn('Od poprzedniego', activity_summary(s, {**previous, **changes}), str(changes))

    def test_zero_delta_is_reported_as_measured_instead_of_no_trades_claim(self):
        ev, ctx, result = self.sample()
        s = ev['snapshot']
        previous = {**s, 'acquired_at': '2026-10-12T14:29:30Z'}
        text = activity_summary(s, previous)
        self.assertIn('+0 szt. w 30 s', text)
        self.assertNotIn('brak transakcji', text)

    def test_missing_or_non_adjacent_closed_candle_is_not_presented_as_last_hour(self):
        ev, ctx, result = self.sample()
        s = ev['snapshot']
        for changes in ({'end': '2026-10-12T13:00:00Z'}, {'status': 'OPEN'}, {'rvol': None}):
            s['previous_closed'].update(changes)
            text = activity_summary(s)
            self.assertNotIn('ostatnia zamknięta', text)
            self.assertIn('średniej pełnej godziny', text)

    def test_closed_hour_is_compared_to_completed_hours(self):
        ev, ctx, result = self.sample()
        s = ev['snapshot']
        s.update(candle_status='CLOSED', rvol=.7)
        self.assertIn('zakończonej świecy poniżej średniej (0,70×)', activity_summary(s))
        s['rvol'] = 1.
        self.assertIn('równy średniej', activity_summary(s))
        s['rvol'] = 2.5
        self.assertIn('powyżej średniej (2,50×)', activity_summary(s))

    def test_missing_rvol_is_not_substituted_or_extrapolated(self):
        ev, ctx, result = self.sample()
        s = ev['snapshot']
        for value in (None, float('nan'), True, -1):
            s['rvol'] = value
            self.assertEqual(activity_summary(s), 'brak poprawnego pomiaru RVOL.')

    def test_telegram_uses_manifest_previous_read_and_keeps_all_axes_in_report(self):
        ev, ctx, result = self.sample()
        s = ev['snapshot']
        ev['previous_snapshot'] = {**s, 'acquired_at': '2026-10-12T14:15:00Z', 'volume': 170000.}
        ctx['analysis_manifest'] = KI.build_analysis_manifest(ev, ctx)
        before = copy.deepcopy(result)
        text = KI.opportunity_message('e', ev, ctx, result)
        self.assertIn('+30 000 szt. w 15 min', text)
        self.assertNotIn(result['assessment']['activity'], text)
        self.assertIn(result['assessment']['movement'], text)
        self.assertIn(result['assessment']['risk'], text)
        self.assertEqual(result, before)
        self.assertIn(result['assessment']['activity'], KI.analysis_assessment_text(result))


if __name__ == '__main__': unittest.main()
