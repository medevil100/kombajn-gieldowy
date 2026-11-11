"""New intraday evidence through real detection/SQLite/queue; no external calls."""
import copy
from datetime import datetime,timedelta
import json
import unittest
from unittest.mock import patch

import KI
import final_company_review as review
import test_final_company_review_20261106 as fixtures


class IntradayReviewTests(unittest.TestCase):
    def setup_company(self,state='REVIEW_REQUIRED'):
        f=fixtures.FinalCompanyReviewTests();f.setUp();self.addCleanup(f.doCleanups)
        f.prepare(2)
        old=next(r for r in f.rows('events') if r['ticker']=='A1')
        with f.store.transaction() as c:
            c.execute('UPDATE analysis_jobs SET state=?,result=?,last_error=?',
                      (state,KI.json_text({'historical':'do not replay'}),'historical fixture'))
        if state in ('FAILED','REVIEW_REQUIRED','FILTERED'):review.finalize(KI,f.store,fixtures.NOW)
        return f,old,KI.load_payload(old['payload'])['snapshot']

    def clock(self,at):
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return at if tz else at.replace(tzinfo=None)
        self.enterContext(patch.object(KI,'datetime',Clock))

    def frame(self,old,minutes=15,price=None,volume=None):
        now=fixtures.NOW+timedelta(minutes=minutes)
        self.clock(now)
        s=copy.deepcopy(old);s.pop('price_matrix',None)
        price=old['price'] if price is None else price
        opening,closing=review.session_context.bounds('XNYS','2026-11-06')
        start=opening+timedelta(hours=int((now-opening).total_seconds()//3600))
        end=min(start+timedelta(hours=1),closing)
        s.update(price=price,acquired_at=now.isoformat(),candle_time=start.isoformat(),
            candle_end=end.isoformat(),candle_status='OPEN',
            volume=old['volume']+minutes*1000 if volume is None else volume,
            ohlc={'open':105.,'high':max(105.,price)+.1,'low':min(105.,price)-.1,'close':price},
            partial_interval=(end-start).total_seconds()<3600)
        s['rvol']=s['volume']/s['average_volume']
        history=[];bar=opening
        while bar<start:
            history.append({'time':bar.isoformat(),'end':(bar+timedelta(hours=1)).isoformat(),
                'status':'CLOSED','open':100.,'high':105.1,'low':99.9,'close':104.5,'volume':200000.})
            bar+=timedelta(hours=1)
        s['previous_closed']={**history[-1],'rvol':2.,'average_volume':100000.}
        s['chart_history']=history+[{**s['ohlc'],'time':start.isoformat(),'end':end.isoformat(),'status':'OPEN','volume':s['volume']}]
        return now,s

    def record(self,f,s,at):
        cid='cycle-'+at.isoformat()
        detected=KI.detect_market(f.store,s,{'price_matrix_enabled':True,'price_threshold_pct':2.,'auto_scan_interval':15})
        self.assertEqual(detected['price_matrix']['read_status'],'RECORDED')
        s={**s,'price_matrix':detected['price_matrix']}
        result=KI.record_opportunity(f.store,s,cid,at)
        return cid,s,result

    def gate(self,f,s,old,at):
        with f.store.connection() as c:return review.intraday_gate(KI,c,s,old['id'],at)

    def test_same_price_and_more_volume_without_new_signal_does_not_repeat_assessment(self):
        f,old,s=self.setup_company()
        at,new=self.frame(s,15)
        cid,new,result=self.record(f,new,at)
        self.assertEqual(result['state'],'SELECTED')
        self.assertEqual(self.gate(f,new,old,at)['reason'],'NO_MATERIAL_CHANGE')
        self.assertEqual(KI.reserve_opportunities(f.store,cid,at),[])
        self.assertEqual(len(f.rows('analysis_jobs')),2)

    def test_price_change_releases_selected_and_records_current_cycle(self):
        f,old,s=self.setup_company()
        at,new=self.frame(s,15,price=106.2)
        cid,new,result=self.record(f,new,at)
        self.assertEqual(result['state'],'CONFIRMED')
        selected=KI.reserve_opportunities(f.store,cid,at)
        self.assertEqual([r['ticker'] for r in selected],['A1'])
        self.assertEqual(self.gate(f,new,old,at)['reason'],'PRICE_CHANGED')

    def test_same_price_can_be_reassessed_after_next_complete_hour(self):
        f,old,s=self.setup_company()
        # Real scanner cadence supplies the new activity proofs through the hour.
        for minute in (15,30,45):
            at,intermediate=self.frame(s,minute)
            self.record(f,intermediate,at)
        at,new=self.frame(s,60)
        cid,new,result=self.record(f,new,at)
        self.assertEqual(result['state'],'CONFIRMED')
        self.assertEqual(self.gate(f,new,old,at)['reason'],'NEW_CLOSED_HOUR')
        self.assertEqual([r['ticker'] for r in KI.reserve_opportunities(f.store,cid,at)],['A1'])

    def test_pending_or_running_old_job_is_not_duplicated(self):
        for state in ('PENDING_CONTEXT','BUSY_CONTEXT','PENDING_AI','BUSY_AI'):
            with self.subTest(state=state):
                f,old,s=self.setup_company(state)
                at,new=self.frame(s,15,price=106.2)
                cid,new,result=self.record(f,new,at)
                self.assertEqual(result['state'],'SELECTED')
                self.assertEqual(self.gate(f,new,old,at)['reason'],'ASSESSMENT_IN_PROGRESS')

    def test_no_activity_or_no_new_acquisition_blocks_even_large_price_change(self):
        f,old,s=self.setup_company()
        at,new=self.frame(s,15,price=110.,volume=s['volume'])
        self.assertEqual(self.gate(f,new,old,at)['reason'],'NO_NEW_MARKET_ACTIVITY')
        self.assertEqual(self.gate(f,s,old,at)['reason'],'NO_NEW_MARKET_DATA')

    def test_fifteen_minute_minimum_and_changed_technical_state(self):
        f,old,s=self.setup_company()
        at,new=self.frame(s,1,price=106.2)
        self.assertEqual(self.gate(f,new,old,at)['reason'],'REVIEW_COOLDOWN')
        at,new=self.frame(s,15)
        new['indicators']['rsi']=75.
        self.assertEqual(self.gate(f,new,old,at)['reason'],'TECHNICAL_STATE_CHANGED')

    def test_crossing_measured_activity_threshold_is_new_material(self):
        f,old,s=self.setup_company()
        s['rvol']=.8
        with f.store.transaction() as c:
            ev=KI.load_payload(old['payload']);ev['snapshot']=s
            c.execute('UPDATE events SET payload=? WHERE id=?',(KI.json_text(ev),old['id']))
        at,new=self.frame(s,15)
        self.assertEqual(self.gate(f,new,old,at)['reason'],'ACTIVITY_THRESHOLD_REACHED')

    def test_failed_old_jobs_stay_unchanged_and_new_cycle_gets_distinct_event(self):
        for state in ('FAILED','REVIEW_REQUIRED'):
            with self.subTest(state=state):
                f,old,s=self.setup_company(state)
                original=next(r for r in f.rows('analysis_jobs') if r['event_id']==old['id'])
                at,new=self.frame(s,15,price=106.2)
                cid,new,result=self.record(f,new,at)
                selected=KI.reserve_opportunities(f.store,cid,at)
                with patch.object(KI,'fetch_opportunity_spread',return_value={}) as quote:
                    batch=review.prepare(KI,f.store,cid,selected,at)
                quote.assert_called_once()
                members=KI.load_payload(next(r for r in f.rows('company_review_batches') if r['id']==batch)['payload'])['members']
                self.assertEqual(len(members),1)
                self.assertNotEqual(members[0],old['id'])
                self.assertEqual(next(r for r in f.rows('analysis_jobs') if r['event_id']==old['id']),original)
                self.assertEqual(len(f.rows('company_review_seen')),2)
                self.assertIsNone(review.prepare(KI,f.store,cid,[],at))

    def test_new_assessment_and_digest_pass_full_mocked_delivery_without_old_job_replay(self):
        f,old,s=self.setup_company()
        at,new=self.frame(s,15,price=106.2)
        cid,new,result=self.record(f,new,at)
        selected=KI.reserve_opportunities(f.store,cid,at)
        with patch.object(KI,'fetch_opportunity_spread',return_value={}):
            batch=review.prepare(KI,f.store,cid,selected,at)
        with f.store.transaction() as c:
            eid=KI.load_payload(c.execute('SELECT payload FROM company_review_batches WHERE id=?',(batch,)).fetchone()[0])['members'][0]
            ev=KI.load_payload(c.execute('SELECT payload FROM events WHERE id=?',(eid,)).fetchone()[0])
            ctx={'sources':[],'cutoff':ev['snapshot']['acquired_at']}
            c.execute("UPDATE analysis_jobs SET state='PENDING_AI',context=? WHERE event_id=?",(KI.json_text(ctx),eid))
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(f.answer())}}],
                  'model':'offline-fixture','usage':{'total_tokens':1}}
        with patch.object(KI,'service_http',side_effect=fixtures.model_transport(response)) as model:
            self.assertTrue(KI.process_analysis_once(f.store,{'OPENAI_API_KEY':'fake'},eid))
            model.assert_called_once()
        self.assertEqual(next(r for r in f.rows('analysis_jobs') if r['event_id']==eid)['state'],'DONE')
        self.assertTrue(review.finalize(KI,f.store,at))
        self.assertEqual(len(f.rows('outbox')),1)
        receipt={'ok':True,'result':{'message_id':42,'chat':{'id':123}}}
        with patch.object(KI,'service_http',return_value=receipt) as telegram:
            self.assertTrue(KI.process_delivery_once(f.store,{'TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'123'}))
            telegram.assert_called_once()
        self.assertEqual(f.rows('outbox')[0]['status'],'DELIVERED')
        self.assertEqual(len(f.rows('delivery_receipts')),1)
        self.assertEqual(next(r for r in f.rows('analysis_jobs') if r['event_id']==old['id'])['state'],'REVIEW_REQUIRED')


if __name__=='__main__':unittest.main()
