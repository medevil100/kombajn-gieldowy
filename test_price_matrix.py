import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import KI


class PriceMatrixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = KI.Store(Path(self.temp.name) / 'matrix.sqlite3')
        self.anchor_time = datetime(2026, 10, 8, 8, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self, price, minutes, ticker='STX.WA'):
        acquired = self.anchor_time + timedelta(minutes=minutes)
        candle = acquired.replace(minute=0, second=0, microsecond=0)
        previous = candle - timedelta(hours=1)
        return {
            'ticker': ticker, 'interval': '1h', 'candle_time': candle.isoformat(),
            'candle_end': (candle + timedelta(hours=1)).isoformat(),
            'acquired_at': acquired.isoformat(), 'candle_status': 'OPEN',
            'price': price, 'rvol': 1.0, 'volume': 100 + minutes % 60, 'average_volume': 100,
            'ohlc': {'open': 1.00, 'high': max(price, 1.00), 'low': min(price, 1.00), 'close': price},
            'previous_closed': {'time': previous.isoformat(), 'end': candle.isoformat(), 'status': 'CLOSED',
                                'open': 1.00, 'high': 1.00, 'low': 1.00, 'close': 1.00,
                                'volume': 100, 'rvol': 1.0, 'average_volume': 100},
            'indicators': {'last_macd_hist': 0.1, 'ma_fast': 1.0, 'plus_di': 20.0, 'minus_di': 10.0},
            'currency': 'PLN',
        }

    def test_first_successful_price_is_immutable_anchor_across_days(self):
        first = KI.record_price_matrix_read(self.store, self.snapshot(1.00, 0), 2.0, 15)
        later = KI.record_price_matrix_read(self.store, self.snapshot(1.30, 15), 2.0, 15)
        next_day = KI.record_price_matrix_read(self.store, self.snapshot(1.25, 24 * 60), 2.0, 15)
        self.assertEqual(first['state'], 'BASELINE_CREATED')
        self.assertEqual(later['anchor_price'], 1.00)
        self.assertAlmostEqual(later['change_pct'], 30.0)
        self.assertEqual(next_day['anchor_price'], 1.00)
        self.assertAlmostEqual(next_day['change_pct'], 25.0)
        self.assertEqual(next_day['state'], 'CANDIDATE')
        self.assertEqual(KI.Store(self.store.path).get_price_matrix('STX.WA')['anchor_price'], 1.00)

    def test_three_consecutive_above_threshold_reads_confirm_candidate(self):
        KI.record_price_matrix_read(self.store, self.snapshot(1.00, 0), 2.0, 15)
        first = KI.record_price_matrix_read(self.store, self.snapshot(1.30, 15), 2.0, 15)
        second = KI.record_price_matrix_read(self.store, self.snapshot(1.25, 30), 2.0, 15)
        third = KI.record_price_matrix_read(self.store, self.snapshot(1.24, 45), 2.0, 15)
        self.assertEqual([first['state'], second['state'], third['state']],
                         ['CANDIDATE', 'CANDIDATE', 'CONFIRMED'])
        self.assertEqual([first['consecutive_reads'], second['consecutive_reads'], third['consecutive_reads']], [1, 2, 3])
        self.assertAlmostEqual(third['change_pct'], 24.0)

    def test_dropping_below_anchor_threshold_rearms_without_changing_anchor(self):
        KI.record_price_matrix_read(self.store, self.snapshot(1.00, 0), 2.0, 15)
        KI.record_price_matrix_read(self.store, self.snapshot(1.03, 15), 2.0, 15)
        reset = KI.record_price_matrix_read(self.store, self.snapshot(1.01, 30), 2.0, 15)
        self.assertEqual(reset['state'], 'MONITORING')
        self.assertEqual(reset['consecutive_reads'], 0)
        self.assertEqual(reset['anchor_price'], 1.00)

    def test_late_read_does_not_confirm_expired_one_hour_candidate(self):
        KI.record_price_matrix_read(self.store, self.snapshot(1.00, 0), 2.0, 15)
        KI.record_price_matrix_read(self.store, self.snapshot(1.30, 15), 2.0, 15)
        expired = KI.record_price_matrix_read(self.store, self.snapshot(1.25, 75), 2.0, 15)
        self.assertEqual(expired['state'], 'CANDIDATE')
        self.assertEqual(expired['consecutive_reads'], 1)

    def test_reads_too_close_together_do_not_count_as_confirmations(self):
        KI.record_price_matrix_read(self.store, self.snapshot(1.00, 0), 2.0, 15)
        first = KI.record_price_matrix_read(self.store, self.snapshot(1.30, 15), 2.0, 15)
        too_soon = KI.record_price_matrix_read(self.store, self.snapshot(1.29, 16), 2.0, 15)
        self.assertEqual(first['consecutive_reads'], 1)
        self.assertEqual(too_soon['read_status'], 'TOO_SOON')
        self.assertEqual(too_soon['consecutive_reads'], 1)

    def test_market_scanner_creates_event_after_three_15_minute_reads(self):
        config = {'price_threshold_pct': 2.0, 'auto_scan_interval': 15,
                  'pipeline_enabled': False, 'telegram_enabled': False,
                  'price_matrix_enabled': True}
        self.store.save_section('tickers', ['STX.WA'])
        results = [KI.detect_market(self.store, self.snapshot(price, minute), config)
                   for price, minute in ((1.00, 0), (1.30, 15), (1.25, 30), (1.24, 45))]
        self.assertEqual([x['status'] for x in results],
                         ['BASELINE_CREATED', 'PRICE_CANDIDATE', 'PRICE_CANDIDATE', 'PRICE_CONFIRMED'])
        opportunities=[]
        for price, minute, result in zip((1.00, 1.30, 1.25, 1.24), (0,15,30,45), results):
            snapshot={**self.snapshot(price,minute),'price_matrix':result['price_matrix']}
            opportunities.append(KI.record_opportunity(self.store,snapshot,'cycle-'+str(minute),
                                                        now=self.anchor_time+timedelta(minutes=minute)))
        self.assertEqual([x['state'] for x in opportunities], ['NOT_QUALIFIED','CANDIDATE','CANDIDATE','CONFIRMED'])
        self.assertAlmostEqual(self.store.get_price_matrix('STX.WA')['change_pct'],24.0)
        ranking=KI.load_growth_ranking(self.store,self.anchor_time+timedelta(minutes=45))
        self.assertEqual(ranking['top_count'],1)
        self.assertEqual(ranking['top'][0]['reference']['price'],1.00)
        selected=KI.reserve_opportunities(self.store,'cycle-45',self.anchor_time+timedelta(minutes=45))
        self.assertEqual(len(selected),1)
        self.assertTrue(KI.queue_opportunity(self.store,selected[0]['sequence_id'],
                         {'bid':1.23,'ask':1.24,'spread_pct':0.81,'acquired_at':self.snapshot(1.24,45)['acquired_at']},
                         False,self.anchor_time+timedelta(minutes=45)))
        with self.store.connection() as connection:
            evidence=__import__('json').loads(connection.execute('SELECT payload FROM events').fetchone()[0])
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM analysis_jobs').fetchone()[0],1)
        self.assertEqual(evidence['reference']['price'],1.00)
        self.assertEqual(evidence['reasons'],['PRICE_MATRIX_3_READS'])

    def test_ticker_matrices_are_independent(self):
        KI.record_price_matrix_read(self.store, self.snapshot(1.00, 0, 'AAA.WA'), 2.0, 15)
        other = KI.record_price_matrix_read(self.store, self.snapshot(2.00, 0, 'BBB.WA'), 2.0, 15)
        self.assertEqual(other['anchor_price'], 2.00)
        self.assertEqual(self.store.get_price_matrix('AAA.WA')['anchor_price'], 1.00)

    def test_new_database_keeps_scanner_list_and_settings_but_starts_empty(self):
        old = Path(self.temp.name) / 'old.sqlite3'
        new = Path(self.temp.name) / 'new.sqlite3'
        source = KI.Store(old)
        source.save_section('tickers', ['STX.WA', 'AAT.WA'])
        source.save_section('settings', {'market_interval': '1h', 'auto_scan_interval': 15,
                                         'price_threshold_pct': 2.0, 'rvol_threshold_pct': 2.0,
                                         'observation_retention_days': 90})
        KI.record_price_matrix_read(source, self.snapshot(1.00, 0), 2.0, 15)
        with source.transaction() as connection:
            connection.execute('INSERT INTO events VALUES(?,?,?,?,?)',
                               ('old-event', 'STX.WA', '1h', self.anchor_time.isoformat(), '{}'))
        result = KI.initialize_matrix_database(old, new)
        fresh = KI.Store(new)
        self.assertEqual(result['tickers_copied'], 2)
        self.assertEqual(fresh.load_section('tickers', []), ['STX.WA', 'AAT.WA'])
        self.assertEqual(fresh.load_section('settings', {})['auto_scan_interval'], 15)
        self.assertIsNone(fresh.get_price_matrix('STX.WA'))
        with fresh.connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 0)
        with source.connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM events').fetchone()[0], 1)

    def test_new_database_never_overwrites_existing_target(self):
        old = Path(self.temp.name) / 'old.sqlite3'
        target = Path(self.temp.name) / 'existing.sqlite3'
        KI.Store(old)
        target.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            KI.initialize_matrix_database(old, target)
        self.assertEqual(target.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
