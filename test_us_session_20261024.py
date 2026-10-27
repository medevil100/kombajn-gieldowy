import unittest
from datetime import datetime,timezone
import KI


class USSessionTests(unittest.TestCase):
    def check_bounds(self,day,opening,closing):
        def stamp(hour,minute):return datetime.fromisoformat(day+f'T{hour:02}:{minute:02}:00+00:00')
        self.assertFalse(KI.market_session_open('AAA',stamp(opening[0],opening[1]-1)))
        self.assertTrue(KI.market_session_open('AAA',stamp(*opening)))
        self.assertTrue(KI.market_session_open('AAA',stamp(closing[0]-1,59)))
        self.assertFalse(KI.market_session_open('AAA',stamp(*closing)))

    def test_regular_winter_hours(self):self.check_bounds('2026-01-12',(14,30),(21,0))
    def test_regular_summer_hours(self):self.check_bounds('2026-07-13',(13,30),(20,0))
    def test_europe_changed_time_before_us(self):self.check_bounds('2026-10-26',(13,30),(20,0))
    def test_us_changed_time_before_europe(self):self.check_bounds('2026-03-09',(13,30),(20,0))

    def test_gpw_bounds_and_weekend(self):
        self.assertTrue(KI.market_session_open('STX.WA','2026-10-26T08:00:00Z'))
        self.assertFalse(KI.market_session_open('STX.WA','2026-10-26T16:00:00Z'))
        self.assertTrue(KI.market_session_open('STX.WA','2026-07-13T07:00:00Z'))
        self.assertFalse(KI.market_session_open('STX.WA','2026-07-13T15:00:00Z'))
        for ticker in ('AAA','STX.WA'):
            self.assertFalse(KI.market_session_open(ticker,'2026-10-24T14:30:00Z'))

    def test_unknown_ticker_and_future_open_candle_do_not_bypass_session(self):
        self.assertFalse(KI.market_session_open(None,'2026-10-26T14:30:00Z'))
        now=datetime(2026,10,26,13,29,tzinfo=timezone.utc)
        snap=KI.opportunity_test_snapshot(now)
        self.assertFalse(KI.telegram_movement_confirmed({'kind':'CONFIRMED_OPPORTUNITY','snapshot':snap},now))

    def test_prompt_does_not_invent_activity_from_missing_carry_markers(self):
        import json
        snap=KI.opportunity_test_snapshot(datetime(2026,10,24,14,30,tzinfo=timezone.utc))
        request=KI.event_analysis_request({'snapshot':snap},{'sources':[]})
        market=json.loads(request['messages'][-1]['content'])['proved_event']['snapshot']
        self.assertIn('spoza regularnej sesji',market['market_activity'])
        self.assertNotIn('Ceny zmieniaja sie',market['market_activity'])

    def test_unexpected_analysis_error_retains_stage_and_safe_reason(self):
        import tempfile,json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            store=KI.Store(Path(d)/'diagnostics.sqlite3')
            evidence={'historical_test':True,'snapshot':{'ticker':'AAA'}}
            with store.transaction() as c:
                c.execute('INSERT INTO events VALUES(?,?,?,?,?)',('bad-context','AAA','1h','2026-10-24T14:00:00Z',KI.json_text(evidence)))
                c.execute('INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)',
                    ('bad-context','PENDING_AI','{invalid','2026-10-24T14:00:00Z'))
            self.assertTrue(KI.process_analysis_once(store,{},'bad-context'))
            with store.connection() as c:
                row=c.execute('SELECT state,last_error FROM analysis_jobs').fetchone()
            self.assertEqual(row['state'],'REVIEW_REQUIRED')
            self.assertIn('AI_PREFLIGHT',row['last_error'])
            self.assertIn('JSONDecodeError',row['last_error'])


if __name__=='__main__':unittest.main(verbosity=2)
