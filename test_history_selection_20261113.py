import unittest,json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import market_intelligence as m
class HistorySelection(unittest.TestCase):
 def fixture(self):
  at=datetime(2026,11,13,20,tzinfo=timezone.utc);rows=[]
  for i in range(250):
   day=(at-timedelta(days=350-i)).date().isoformat()
   rows.append(dict(session_date=day,closed_at=day+'T17:00:00+00:00',open=4.,high=5.,low=3.,close=4.,volume=100,metadata=json.dumps({'acquired_at':at.isoformat()})))
  # Keep last session fresh without implying a full exchange calendar.
  for i,r in enumerate(rows[-4:]):
   day=(at-timedelta(days=4-i)).date().isoformat();r.update(session_date=day,closed_at=day+'T17:00:00+00:00')
  snap={'acquired_at':at.isoformat(),'price_matrix':{'reference_session':rows[-1]['session_date'],'anchor_price':4.}}
  cache={'acquired_at':at.isoformat(),'rows':[dict(time=r['session_date']+'T00:00:00+00:00',end=r['closed_at'],status='CLOSED',**{k:r[k] for k in ('open','high','low','close','volume')}) for r in rows[-4:]]}
  return rows,cache,snap
 def select(self,rows,cache,snap):return m.select_daily_history(SimpleNamespace(load_payload=json.loads),rows,cache,snap)
 def test_partial_cache_preserves_full_database(self):
  rows,c,s=self.fixture();self.assertEqual(len(self.select(rows,c,s)),250)
 def test_conflicting_units_do_not_merge(self):
  rows,c,s=self.fixture();c['rows'][0]['high']=50.;self.assertEqual(len(self.select(rows,c,s)),4)
 def test_future_acquisition_excluded(self):
  rows,c,s=self.fixture();rows[0]['metadata']=json.dumps({'acquired_at':'2026-11-14T00:00:00+00:00'});self.assertEqual(len(self.select(rows,c,s)),249)
 def test_pre_split_acquisition_excluded(self):
  rows,c,s=self.fixture();s['corporate_actions']=[{'effective_at':'2026-11-01T00:00:00+00:00'}];rows[0]['metadata']=json.dumps({'acquired_at':'2026-10-01T00:00:00+00:00'});self.assertEqual(len(self.select(rows,c,s)),249)
 def test_blocked_basis_no_history(self):
  rows,c,s=self.fixture();s['price_basis']={'blocked':True};self.assertEqual(self.select(rows,c,s),[])
 def test_reference_mismatch_no_history(self):
  rows,c,s=self.fixture();s['price_matrix']['anchor_price']=40.;self.assertEqual(self.select(rows,c,s),[])
if __name__=='__main__':unittest.main()
