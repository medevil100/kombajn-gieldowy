import unittest
import sqlite3
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import session_context
import early_company_review
import KI


class SessionActivityFollowTests(unittest.TestCase):
    def snapshot(self):
        zone=timezone(timedelta(hours=1))
        start=datetime(2026,11,20,8,tzinfo=zone)
        history=[]
        for index in range(20):
            at=start+timedelta(hours=index)
            history.append({'time':at.isoformat(),'end':(at+timedelta(hours=1)).isoformat(),
                            'status':'CLOSED','open':.18,'high':.19,'low':.17,
                            'close':.18,'volume':1000})
        active=datetime(2026,11,23,11,tzinfo=zone)
        history.append({'time':active.isoformat(),'end':(active+timedelta(hours=1)).isoformat(),
                        'status':'CLOSED','open':.19,'high':.205,'low':.19,
                        'close':.202,'volume':5000})
        return {'ticker':'SZR.WA','acquired_at':datetime(2026,11,23,12,36,tzinfo=timezone.utc).isoformat(),
                'price':.21,'volume':144,'rvol':.00046,
                'price_matrix':{'anchor_price':.168,'change_pct':25.},
                'chart_history':history}

    def test_quiet_new_hour_does_not_erase_confirmed_same_session_activity(self):
        proof=session_context.strong_closed_hour_activity(self.snapshot(),1.5,1000,2.)
        self.assertIsNotNone(proof)
        self.assertEqual(proof['volume'],5000)
        self.assertAlmostEqual(proof['rvol'],5.)
        self.assertGreater(proof['change_pct'],20.)

    def test_previous_session_activity_is_not_reused(self):
        snapshot=self.snapshot()
        snapshot['acquired_at']=datetime(2026,11,24,12,36,tzinfo=timezone.utc).isoformat()
        self.assertIsNone(session_context.strong_closed_hour_activity(snapshot,1.5,1000,2.))

    def test_early_review_uses_earlier_closed_hour_with_live_small_volume(self):
        snapshot=self.snapshot()
        snapshot.update(currency='PLN',price_matrix={**snapshot['price_matrix'],
            'state':'CANDIDATE','activity_tracking_version':'E05','consecutive_reads':1,
            'activity_evidence':'NEW_CANDLE_VOLUME','last_activity_at':snapshot['acquired_at']})
        api=Mock()
        api.finite_number=KI.finite_number
        api.accepted_matrix_snapshot.return_value=True
        api.open_hour_fresh.return_value=True
        api.market_session_open.return_value=True
        api.material_issues.return_value=[]
        api.company_review=SimpleNamespace(session_context=SimpleNamespace(
            strong_closed_hour_activity=session_context.strong_closed_hour_activity,
            build=lambda _: {'status':'COMPLETE_TO_ASOF'}))
        result=early_company_review.gate(api,snapshot,
            datetime.fromisoformat(snapshot['acquired_at']),{'price_threshold_pct':2.})
        self.assertTrue(result['allowed'])
        self.assertEqual(result['activity_hour']['volume'],5000)

    def test_scan_drift_does_not_restart_three_activity_proofs(self):
        previous='2026-11-23T12:11:52+00:00'
        current='2026-11-23T12:36:11+00:00'
        old={'ticker':'SZR.WA','anchor_price':.168,'anchor_at':'2026-11-20T16:05:00+00:00',
             'reference_session':'2026-11-20','session_date':'2026-11-23','reference_status':'READY',
             'last_price':.202,'last_acquired_at':previous,'last_candle_time':'2026-11-23T12:00:00+01:00',
             'last_volume':88721,'change_pct':20.24,'state':'CANDIDATE','consecutive_reads':2,
             'candidate_started_at':'2026-11-23T11:57:21+00:00','confirmed_at':None,
             'activity_tracking_version':'E05','activity_verified':False}
        snapshot={'ticker':'SZR.WA','price':.21,'acquired_at':current,
                  'candle_time':'2026-11-23T13:00:00+01:00','volume':144}
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        self.addCleanup(db.close)
        db.execute('CREATE TABLE price_matrix(ticker TEXT PRIMARY KEY,payload TEXT,updated_at TEXT)')
        db.execute('INSERT INTO price_matrix VALUES(?,?,?)',('SZR.WA',json.dumps(old),previous))
        reference={'session_date':'2026-11-20','close':.168,'closed_at':old['anchor_at']}
        with patch.object(KI,'market_session_open',return_value=True), \
             patch.object(KI,'required_daily_session',return_value='2026-11-20'), \
             patch.object(KI,'_daily_reference',return_value=reference), \
             patch.object(KI.market_intelligence,'price_basis',return_value={'blocked':False}):
            result=KI._record_price_matrix_read(db,snapshot,2.,15)
        self.assertEqual(result['state'],'CONFIRMED')
        self.assertEqual(result['consecutive_reads'],3)


if __name__=='__main__':
    unittest.main()
