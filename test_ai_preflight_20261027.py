"""Pakiet i decyzja przed AI: prawdziwe funkcje/SQLite, bez API i podmian."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
import KI
from test_repair_20261024 import NOW


class AIPreflightTests(unittest.TestCase):
    def sample(self,ticker='AAA.WA'):
        snap=KI.opportunity_test_snapshot(NOW,ticker,105.)
        snap['price_matrix']={'change_pct':5.,'anchor_price':100.,'anchor_at':'2026-10-09T15:00:00Z'}
        snap['spread']={}
        return {'kind':'CONFIRMED_OPPORTUNITY','manual_analysis':True,'snapshot':snap}, {'sources':[],'cutoff':snap['acquired_at']}

    def test_aligned_simple_move_is_local_with_or_without_quotes(self):
        for ticker in ('AAA.WA','XYZ','BRK.B'):
            ev,ctx=self.sample(ticker)
            for spread in ({},{'bid':104.,'ask':106.,'freshness_confirmed':False}):
                ev['snapshot']['spread']=spread
                decision=KI.automatic_ai_preflight(ev,ctx)
                self.assertFalse(decision['allowed'])
                self.assertTrue(decision['skip_reasons'])

    def test_conflicting_move_without_quotes_has_limited_scope_and_question(self):
        ev,ctx=self.sample();ev['snapshot']['indicators']['last_macd_hist']=-.1
        decision=KI.automatic_ai_preflight(ev,ctx)
        self.assertTrue(decision['allowed'])
        self.assertFalse(decision['quotes_available'])
        self.assertTrue(decision['questions'])
        self.assertIn('BEZ OCENY WYKONALNOŚCI',decision['scope'])
        self.assertTrue(any('bid/ask' in x for x in decision['limitations']))

    def test_wrong_identity_time_and_future_source_block_paid_request(self):
        ev,ctx=self.sample();ev['snapshot']['indicators']['last_macd_hist']=-.1
        for change in ({'issuer_identity':{'ticker':'OTHER'}},
                       {'cutoff':'2026-10-12T15:00:00Z'},
                       {'sources':[{'published_at':'2026-10-13T12:00:00Z'}]}):
            self.assertFalse(KI.automatic_ai_preflight(ev,{**ctx,**change})['allowed'])
        ev['previous_snapshot']={**ev['snapshot'],'ticker':'OTHER'}
        self.assertFalse(KI.automatic_ai_preflight(ev,ctx)['allowed'])

    def test_previous_relation_and_later_quote_timestamp_are_explicit(self):
        ev,ctx=self.sample();ev['snapshot']['indicators']['last_macd_hist']=-.1
        ev['snapshot']['spread']={'bid':104.,'ask':106.,'acquired_at':'2026-10-12T14:31:00Z','freshness_confirmed':False}
        ev['previous_snapshot']={**ev['snapshot'],'acquired_at':'2026-10-12T14:15:00Z'}
        decision=KI.automatic_ai_preflight(ev,ctx)
        self.assertTrue(decision['allowed'])
        self.assertEqual(decision['previous_relation'],'TA SAMA ŚWIECA')
        self.assertTrue(any('później' in x for x in decision['limitations']))

    def test_actual_worker_skips_ai_without_keys_and_creates_no_delivery(self):
        ev,ctx=self.sample()
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite3')
            with store.transaction() as c:
                c.execute('INSERT INTO events VALUES(?,?,?,?,?)',('e','AAA.WA','1h',NOW.isoformat(),KI.json_text(ev)))
                c.execute('INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)',('e','PENDING_AI',KI.json_text(ctx),NOW.isoformat()))
            self.assertTrue(KI.process_analysis_once(store,{},'e'))
            with store.connection() as c:
                row=c.execute('SELECT state,result FROM analysis_jobs').fetchone()
                self.assertEqual(row['state'],'FILTERED')
                self.assertTrue(json.loads(row['result'])['provider']['not_called'])
                self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM research_requests').fetchone()[0],0)

    def test_compact_request_keeps_single_identity_and_local_assessment(self):
        ev,ctx=self.sample();ev['snapshot']['indicators']['last_macd_hist']=-.1
        ev['snapshot']['chart_history']=[{'test':'bulk'}]*500
        ctx['ai_preflight']=KI.automatic_ai_preflight(ev,ctx)
        original=copy.deepcopy(ev)
        request=KI.event_analysis_request(ev,ctx)
        data=json.loads(request['messages'][-1]['content'])
        self.assertEqual(data['proved_event']['snapshot']['ticker'],'AAA.WA')
        self.assertTrue(data['proved_event']['local_assessment']['questions'])
        self.assertNotIn('chart_history',request['messages'][-1]['content'])
        self.assertNotIn('manual_analysis',request['messages'][-1]['content'])
        self.assertLess(len(request['messages'][0]['content']),2600)
        self.assertEqual(ev,original)

    def test_local_decision_invalidates_old_preview_without_deleting_history(self):
        ev,ctx=self.sample();decision=KI.automatic_ai_preflight(ev,ctx)
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite3')
            with store.transaction() as c:
                c.execute('INSERT INTO events VALUES(?,?,?,?,?)',('e','AAA.WA','1h',NOW.isoformat(),KI.json_text(ev)))
                c.execute('INSERT INTO analysis_jobs(event_id,state,context,updated_at) VALUES(?,?,?,?)',('e','BUSY_AI',KI.json_text(ctx),NOW.isoformat()))
                c.execute('INSERT INTO outbox(id,event_id,kind,message,status,created_at) VALUES(?,?,?,?,?,?)',('old','e','ANALYSIS','Stary podgląd','PREVIEW',NOW.isoformat()))
            KI.save_ai_preflight(store,'e',ctx,decision)
            with store.connection() as c:
                self.assertEqual(tuple(c.execute('SELECT status,message FROM outbox').fetchone()),('FILTERED','Stary podgląd'))


if __name__=='__main__':unittest.main()
