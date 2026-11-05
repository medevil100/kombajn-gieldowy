from datetime import date, datetime, timedelta, timezone
import io
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch

import KI
import portfolio_fundamentals as funds
from portfolio_view import fundamentals_html, market_context_html


NOW = datetime(2026, 11, 3, 15, tzinfo=timezone.utc)


def documents(ticker):
    periods = [{'fiscalDateEnding': d, 'reportedCurrency': 'USD'}
               for d in ('2026-06-30', '2026-03-31', '2025-12-31', '2025-09-30')]
    return {
        'INCOME_STATEMENT': {'symbol': ticker, 'quarterlyReports': [
            dict(period, netIncome='-7005000') for period in periods]},
        'BALANCE_SHEET': {'symbol': ticker, 'quarterlyReports': [
            dict(period, totalAssets='34714000', totalLiabilities='6062000',
                 totalShareholderEquity='28652000', cashAndCashEquivalentsAtCarryingValue='30118000',
                 commonStockSharesOutstanding='niezweryfikowana') for period in periods]},
        'CASH_FLOW': {'symbol': ticker, 'quarterlyReports': [
            dict(period, operatingCashflow='-6043000') for period in periods]},
    }


class PortfolioFundamentalsTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = KI.Store(self.root / 'KI.matrix.sqlite3')
        self.stop = Mock()
        self.stop.is_set.return_value = False
        self.stop.wait.return_value = False

    def test_reads_usa_and_publishes_polish_values_without_share_count(self):
        with patch.object(funds, 'fetch', side_effect=lambda t, f, k: documents(t)[f]) as fetch:
            self.assertTrue(funds.process_one(self.store, ['ASM.WA', 'MREO'], 'sample123456', self.stop, NOW))
            self.assertEqual(fetch.call_count, 3)
            self.assertTrue(all(call.args[0] == 'MREO' for call in fetch.call_args_list))
            self.assertFalse(funds.process_one(self.store, ['MREO'], 'sample123456', self.stop, NOW + timedelta(days=6)))
        with patch.object(funds, 'key_path', return_value=self.root / 'missing'):
            views = funds.views(self.store, ['MREO', 'ASM.WA'])
        html = fundamentals_html(views['MREO'])
        self.assertIn('30.06.2026', html)
        self.assertIn('30,12 mln USD', html)
        self.assertIn('-24,17 mln USD', html)
        self.assertIn('Wycena na akcję wymaga potwierdzenia liczby akcji.', html)
        self.assertIn('Brak zweryfikowanego źródła', fundamentals_html(views['ASM.WA']))

    def test_budget_persists_when_worker_reopens_database(self):
        tickers = ['MREO', 'PLRX', 'CATX', 'HUMA', 'ABC']
        with patch.object(funds, 'fetch', side_effect=lambda t, f, k: documents(t)[f]) as fetch:
            for _ in range(4):
                self.assertTrue(funds.process_one(self.store, tickers, 'sample123456', self.stop, NOW))
            reopened = KI.Store(self.root / 'KI.matrix.sqlite3')
            self.assertFalse(funds.process_one(reopened, tickers, 'sample123456', self.stop, NOW))
            self.assertEqual(fetch.call_count, 12)
            self.assertTrue(funds.process_one(reopened, tickers, 'sample123456', self.stop, NOW + timedelta(days=1, minutes=3)))
            self.assertEqual(fetch.call_count, 15)

    def test_refusal_stops_entire_queue_and_keeps_last_good_summary(self):
        with patch.object(funds, 'fetch', side_effect=lambda t, f, k: documents(t)[f]):
            funds.process_one(self.store, ['MREO'], 'sample123456', self.stop, NOW)
        later = NOW + funds.REFRESH
        with patch.object(funds, 'fetch', side_effect=funds.ProviderUnavailable) as fetch:
            self.assertTrue(funds.process_one(self.store, ['MREO'], 'sample123456', self.stop, later))
            self.assertFalse(funds.process_one(self.store, ['PLRX'], 'sample123456', self.stop, later))
            self.assertEqual(fetch.call_count, 1)
        with self.store.connection() as db:
            record = funds.load(db, funds.PREFIX + 'MREO')
        self.assertEqual(record['status'], 'provider')
        self.assertEqual(record['summary']['cash'], 30118000)

    def test_mismatched_quarter_or_broken_balance_blocks_publication(self):
        for field, value in [('fiscalDateEnding', '2026-03-31'), ('totalAssets', '1'), ('reportedCurrency', 'GBP')]:
            data = documents('MREO')
            data['BALANCE_SHEET']['quarterlyReports'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                funds.summarize('MREO', data, date(2026, 11, 3))

    def test_key_is_saved_atomically_without_printing_it(self):
        path = self.root / '.config' / 'ki2' / 'alpha-vantage.key'
        with patch.object(funds, 'key_path', return_value=path):
            with patch.object(funds.sys, 'stdin', io.StringIO('sample123456\r\n')), patch('builtins.print') as log:
                funds.save_key()
                self.assertNotIn('sample123456', repr(log.call_args_list))
            self.assertEqual(funds.read_key(), 'sample123456')
            with patch.object(funds.sys, 'stdin', io.StringIO('API key: sample123456\n')), self.assertRaises(SystemExit):
                funds.save_key()
            self.assertEqual(funds.read_key(), 'sample123456')

    def test_range_requires_matching_instrument_and_fresh_ordered_prices(self):
        data = {'symbol': 'ASM.WA', 'currency': 'PLN', 'fiftyTwoWeekLow': .14,
                'fiftyTwoWeekHigh': 1.05, 'regularMarketTime': NOW.timestamp()}
        result = KI.market_52_week_range(data, 'ASM.WA', NOW)
        self.assertIn('0,1400 – 1,0500 PLN', market_context_html({'_currency':'PLN', '_market_52_week_range':result}))
        self.assertIsNone(KI.market_52_week_range(data, 'STX.WA', NOW))
        self.assertIsNone(KI.market_52_week_range(data, 'ASM.WA', NOW + timedelta(days=8)))
        self.assertIsNone(KI.market_52_week_range(dict(data, fiftyTwoWeekLow=2), 'ASM.WA', NOW))

    def test_daily_change_requires_matching_session_and_accepted_price(self):
        stamp = NOW.isoformat()
        matrix = {'reference_status':'READY', 'reference_session':'2026-11-02', 'session_date':'2026-11-03',
                  'anchor_price':.2, 'last_acquired_at':stamp, 'last_price':.15}
        snap = {'ticker':'ASM.WA', 'acquired_at':stamp, 'price':.15, 'price_matrix':matrix}
        self.assertAlmostEqual(KI.portfolio_daily_move(snap)['percent'], -25)
        self.assertIsNone(KI.portfolio_daily_move(dict(snap, price=.16)))
        self.assertIsNone(KI.portfolio_daily_move(dict(snap, latest_price_origin='carried_previous_close')))
        matrix['reference_status'] = 'MISSING_PREVIOUS_SESSION'
        self.assertIsNone(KI.portfolio_daily_move(snap))

    def test_analyst_cache_distinguishes_reported_target_from_missing_data(self):
        now = datetime.now(timezone.utc)
        info = {'symbol':'MREO', 'currency':'USD', 'numberOfAnalystOpinions':5, 'targetMeanPrice':1.99}
        quote = Mock(side_effect=[info, {'symbol':'ASM.WA', 'currency':'PLN'}])
        tickers = ['MREO', 'ASM.WA']
        self.assertTrue(funds.process_analyst(self.store, tickers, quote, now))
        self.assertTrue(funds.process_analyst(self.store, tickers, quote, now))
        self.assertFalse(funds.process_analyst(self.store, tickers, quote, now))
        views = funds.analyst_views(self.store, tickers)
        self.assertIn('Liczba opinii: 5', market_context_html({'_currency':'USD', '_analyst':views['MREO']}))
        self.assertIn('Brak potwierdzonego celu', market_context_html({'_currency':'PLN', '_analyst':views['ASM.WA']}))
        self.assertIn('Waluta celu różni', market_context_html({'_currency':'PLN', '_analyst':views['MREO']}))
