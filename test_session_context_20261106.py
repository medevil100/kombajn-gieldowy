"""Whole-day context and structurally shortened session tails; no providers."""
import copy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import KI
import session_context as session
from analysis_verdict import material_issues,shortened_activity_ready,activity_summary


NOW=datetime(2026,11,6,20,32,tzinfo=timezone.utc)


def snapshot():
    opening,closing=session.bounds('XNYS','2026-11-06')
    rows=[];start=opening;n=0
    while start<=NOW and start<closing:
        end=min(start+timedelta(hours=1),closing);price=1.02+n*.1
        rows.append({'time':start.isoformat(),'end':end.isoformat(),'status':'CLOSED' if end<=NOW else 'OPEN',
                     'open':1.+n*.1,'high':price+.03,'low':.99+n*.1,'close':price,
                     'volume':200000. if end<=NOW else 21544.})
        start=end;n+=1
    last=rows[-1];price=last['close']
    return {'ticker':'SVRA','interval':'1h','currency':'USD','acquired_at':NOW.isoformat(),
        'candle_time':last['time'],'candle_end':last['end'],'candle_status':'OPEN',
        'price':price,'volume':last['volume'],'average_volume':300000.,'rvol':None,
        'partial_interval':True,'status_basis':'session_end','latest_price_origin':'Yahoo OHLC',
        'chart_history':rows,'ohlc':{k:last[k] for k in ('open','high','low','close')},
        'previous_closed':{**rows[-2],'rvol':2/3,'average_volume':300000.},
        'price_matrix':{'state':'CONFIRMED','anchor_price':1.5,'change_pct':(price/1.5-1)*100,
             'anchor_at':'2026-11-05T21:00:00Z','last_acquired_at':NOW.isoformat(),'last_price':price,
             'activity_tracking_version':'E05','activity_verified':True,'consecutive_reads':3,
             'read_status':'RECORDED','candidate_started_at':(NOW-timedelta(minutes=30)).isoformat()},
        'indicators':{'ma_fast':1.55,'last_macd_hist':.1,'rsi':60.,'plus_di':30.,'minus_di':10.}}


class SessionContextTests(unittest.TestCase):
    def test_whole_session_has_six_closed_hours_and_actual_short_tail(self):
        s=snapshot();before=copy.deepcopy(s);context=session.build(s)
        self.assertEqual(context['status'],'COMPLETE_TO_ASOF')
        self.assertEqual(context['closed_full_candles'],6)
        self.assertEqual(len(context['candles']),7)
        self.assertTrue(context['candles'][-1]['partial_interval'])
        self.assertEqual(context['summary']['observed_volume'],1221544.)
        self.assertEqual(context['summary']['session_open_price'],1.)
        self.assertEqual(s,before);self.assertIsNone(s['rvol'])

    def test_expected_missing_rvol_is_not_an_error_when_whole_day_is_verified(self):
        s=snapshot()
        self.assertTrue(shortened_activity_ready(s))
        self.assertEqual(material_issues(s),[])
        text=activity_summary(s)
        self.assertIn('skrócona świeca 30 min',text)
        self.assertIn('21 544 szt.',text)
        self.assertIn('całej sesji',text)
        self.assertNotIn('bieżąca dotąd:',text)

    def test_full_hours_still_require_actual_rvol_and_flag_cannot_forge_short_bar(self):
        s=snapshot();s['partial_interval']=False
        self.assertTrue(material_issues(s))
        s=snapshot();s['status_basis']='interval'
        self.assertFalse(shortened_activity_ready(s));self.assertTrue(material_issues(s))
        for value in (-1.,float('nan'),True):
            s=snapshot();s['rvol']=value
            self.assertFalse(shortened_activity_ready(s))
            self.assertTrue(material_issues(s))

    def test_missing_carried_and_conflicting_bars_are_not_filled(self):
        for kind in ('missing','carried','conflict'):
            s=snapshot()
            if kind=='missing':s['chart_history'].pop(2)
            elif kind=='carried':s['chart_history'][2]['price_origin']='carried_previous_close'
            else:s['chart_history'].append({**s['chart_history'][2],'volume':99.})
            self.assertEqual(session.build(s)['status'],'PARTIAL',kind)
            self.assertFalse(shortened_activity_ready(s),kind)
            self.assertTrue(material_issues(s),kind)

    def test_other_days_future_bars_and_duplicate_rows_never_inflate_volume(self):
        s=snapshot();base=session.build(s)
        s['chart_history']+=[dict(s['chart_history'][0]),
            {**s['chart_history'][0],'time':'2026-11-05T14:30:00Z','end':'2026-11-05T15:30:00Z'},
            {**s['chart_history'][0],'time':'2026-11-06T21:30:00Z','end':'2026-11-06T22:30:00Z'}]
        self.assertEqual(session.build(s),base)

    def test_regular_session_midday_cannot_be_claimed_as_shortened_tail(self):
        s=snapshot();s.update(acquired_at='2026-11-06T17:32:00Z',
            candle_time='2026-11-06T17:30:00Z',candle_end='2026-11-06T18:00:00Z')
        self.assertFalse(shortened_activity_ready(s))

    def test_stored_read_progress_is_not_summed_as_independent_candle_volume(self):
        s=snapshot()
        with tempfile.TemporaryDirectory() as folder:
            store=KI.Store(Path(folder)/'test.sqlite3')
            with store.transaction() as c:
                for at,volume,ticker in (('2026-11-06T20:31:00+00:00',10000.,'SVRA'),
                    (s['acquired_at'],21544.,'SVRA'),(s['acquired_at'],21544.,'SVRA'),
                    ('2026-11-06T20:40:00+00:00',99999.,'SVRA'),(s['acquired_at'],99999.,'OTHER')):
                    raw={**s,'ticker':ticker,'acquired_at':at,'volume':volume}
                    c.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                              (ticker,'1h',s['candle_time'],at,'OPEN',KI.encode_observation(raw)))
                carried={**s,'latest_price_origin':'carried_previous_close','volume':0.,'acquired_at':'2026-11-06T20:30:30+00:00'}
                c.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                          ('SVRA','1h',s['candle_time'],carried['acquired_at'],'OPEN',KI.encode_observation(carried)))
            context=session.gather(store,s)
        self.assertEqual(len(context['observations']),2)
        self.assertEqual([r['volume_in_candle'] for r in context['observations']],[10000.,21544.])
        self.assertEqual(context['summary']['observed_volume'],1221544.)
        self.assertEqual(context['excluded_observations'][0]['reason'],'CARRIED_PRICE')

    def test_final_ai_package_carries_the_whole_day_and_keeps_rvol_null(self):
        s=snapshot();ev={'kind':'CONFIRMED_OPPORTUNITY','snapshot':s,'autonomous_assessment_version':1,
            'company_review_batch':'batch','session_context':session.build(s)}
        ctx={'sources':[],'cutoff':s['acquired_at']};ctx['analysis_manifest']=KI.build_analysis_manifest(ev,ctx)
        decision=KI.automatic_ai_preflight(ev,ctx);ctx['ai_preflight']=decision
        self.assertTrue(decision['allowed'],decision['skip_reasons'])
        self.assertEqual(ctx['analysis_manifest']['local_review']['activity'],'SHORT_INTERVAL')
        request=KI.event_analysis_request(ev,ctx)
        body=KI.load_payload(request['messages'][1]['content'])['proved_event']
        self.assertEqual(len(body['analysis_manifest']['session_context']['candles']),7)
        self.assertIsNone(body['snapshot']['rvol'])
        self.assertIn('całej bieżącej sesji',request['messages'][0]['content'])

    def test_short_tail_reaches_new_job_only_with_full_day_evidence(self):
        import final_company_review as review
        s=snapshot()
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return NOW if tz else NOW.replace(tzinfo=None)
        with tempfile.TemporaryDirectory() as folder, patch.object(KI,'datetime',Clock):
            store=KI.Store(Path(folder)/'short.sqlite3')
            store.save_section('tickers',['SVRA'])
            store.save_section('settings',{'pipeline_enabled':True,'telegram_enabled':True,
                'price_threshold_pct':2.,'auto_scan_interval':15,review.SETTING:True})
            previous=copy.deepcopy(s);previous['acquired_at']=(NOW-timedelta(minutes=1)).isoformat();previous['volume']=10000.
            with store.transaction() as c:
                for snap in (previous,s):
                    c.execute('INSERT INTO observations(ticker,interval,candle_time,acquired_at,candle_status,payload) VALUES(?,?,?,?,?,?)',
                              ('SVRA','1h',snap['candle_time'],snap['acquired_at'],'OPEN',KI.encode_observation(snap)))
            KI.record_opportunity(store,s,'cycle',NOW)
            selected=KI.reserve_opportunities(store,'cycle',NOW)
            self.assertEqual(len(selected),1)
            with patch.object(KI,'fetch_opportunity_spread',return_value={}):batch=review.prepare(KI,store,'cycle',selected,NOW)
            with store.connection() as c:
                payload=KI.load_payload(c.execute('SELECT payload FROM company_review_batches WHERE id=?',(batch,)).fetchone()[0])
                self.assertEqual(len(payload['members']),1,payload)
                ev=KI.load_payload(c.execute('SELECT payload FROM events WHERE id=?',(payload['members'][0],)).fetchone()[0])
                self.assertEqual(len(ev['session_context']['candles']),7)
                self.assertEqual(len(ev['session_context']['observations']),2)
                self.assertIsNone(ev['snapshot']['rvol'])

    def test_final_narrative_must_cover_the_session_and_name_the_shortened_interval(self):
        from ai_assessment import validate_axes
        s=snapshot();manifest={'purpose':'FINAL_COMPANY_REVIEW','session_context':session.build(s),
                              'activity':{'status':'PARTIAL'},'trade_plan':{'status':'UNAVAILABLE'}}
        axes={'movement':'Wzrost ceny jest zgodny z momentum i położeniem względem średniej. To ocena bieżących wskazań, a nie dowód przyszłej kontynuacji kierunku.',
              'activity':'Przebieg sesji i wolumeny pełnych świec są dostępne do oceny. Skrócona świeca ma częściowy wolumen; godzinowy RVOL pozostaje niewyznaczony.',
              'risk':'Brak ofert ogranicza ocenę wykonania. Poziomy techniczne i zapisany przebieg rynku nie stanowią potwierdzenia płynności ani realizacji zlecenia.'}
        _,errors=validate_axes(axes,s,manifest)
        self.assertTrue(any('przebieg' in e for e in errors))
        axes['movement']='Przebieg sesji pokazuje wzrost ceny od otwarcia. Bieżące wskazania momentum są zgodne z ruchem, ale jego dalszy przebieg pozostaje nieustalony.'
        _,errors=validate_axes(axes,s,manifest)
        self.assertEqual(errors,[])


if __name__=='__main__':unittest.main()
