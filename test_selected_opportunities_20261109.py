"""Real SQLite final reviews and read-only mobile TOP 5; no live providers."""
import copy
from datetime import datetime, timedelta
from html.parser import HTMLParser
import unittest
from unittest.mock import patch

import KI
import selected_opportunities as top
import test_final_company_review_20261106 as fixtures

NOW=fixtures.NOW


class SelectedOpportunitiesTests(unittest.TestCase):
    def sample(self,count=3,attention='INFORM'):
        f=fixtures.FinalCompanyReviewTests();f.setUp();self.addCleanup(f.doCleanups)
        f.prepare(count,with_plan=True);f.finish_members(attention)
        KI.company_review.finalize(KI,f.store,NOW)
        return f

    def dump(self,store):
        with store.connection() as db:return list(db.iterdump())

    def read(self,f,**kwargs):
        with (patch.object(KI,'service_http',side_effect=AssertionError('No AI/Tavily/Telegram')),
              patch.object(KI,'fetch_market',side_effect=AssertionError('No Yahoo'))):
            return top.collect(KI,f.store,kwargs.pop('now',NOW+timedelta(minutes=2)),**kwargs)

    def clone_job(self,f,state='REVIEW_REQUIRED'):
        with f.store.transaction() as db:
            event=dict(db.execute('SELECT * FROM events WHERE ticker<>? ORDER BY created_at LIMIT 1',('KI',)).fetchone())
            job=dict(db.execute('SELECT * FROM analysis_jobs WHERE event_id=?',(event['id'],)).fetchone())
            ticker=event['ticker'];event['id']='newer_'+event['id']
            event['created_at']=(NOW+timedelta(minutes=1)).isoformat()
            job.update(event_id=event['id'],state=state,updated_at=event['created_at'])
            for name,row in (('events',event),('analysis_jobs',job)):
                db.execute('INSERT INTO '+name+' ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
        return ticker

    def test_cap_five_is_read_only_deterministic_and_does_not_create_new_work(self):
        f=self.sample(6);before=self.dump(f.store)
        view=self.read(f)
        self.assertEqual(len(view['cards']),5,view)
        self.assertEqual(len({x['ticker'] for x in view['cards']}),5)
        self.assertEqual(view,self.read(f))
        self.assertEqual(self.dump(f.store),before)
        for card in view['cards']:
            self.assertEqual(card['analysis']['final_review']['attention'],'INFORM')
            self.assertEqual(card['manifest']['local_review']['verdict'],'ALIGNED')

    def test_market_filters_and_no_forced_minimum(self):
        f=self.sample(3)
        self.assertEqual(len(self.read(f)['cards']),3)
        gpw=self.read(f,market='GPW')['cards'];usa=self.read(f,market='USA')['cards']
        self.assertTrue(gpw and usa)
        self.assertTrue(all(c['ticker'].endswith('.WA') for c in gpw))
        self.assertTrue(all(not c['ticker'].endswith('.WA') for c in usa))
        self.assertEqual(len(gpw)+len(usa),3)

    def test_expired_and_closed_session_reviews_are_not_recycled(self):
        f=self.sample(1)
        self.assertEqual(self.read(f,now=NOW+timedelta(minutes=16))['cards'],[])
        self.assertEqual(self.read(f,now=NOW+timedelta(days=1))['cards'],[])

    def test_newer_failed_pending_or_panel_only_review_hides_older_positive(self):
        for state in ('REVIEW_REQUIRED','FAILED','PENDING_AI','DONE'):
            f=self.sample(1);ticker=self.clone_job(f,state)
            view=self.read(f)
            self.assertEqual(view['cards'],[],(state,ticker,view))

    def test_current_reading_with_adverse_retrace_removes_old_positive(self):
        f=self.sample(1)
        with f.store.transaction() as db:
            row=db.execute('SELECT id,payload FROM observations ORDER BY id DESC LIMIT 1').fetchone()
            snap=KI.load_payload(row['payload'])
            snap['ohlc']['high']=snap['price']*1.05
            db.execute('UPDATE observations SET payload=? WHERE id=?',(KI.json_text(snap),row['id']))
        view=self.read(f)
        self.assertEqual(view['cards'],[])
        self.assertIn('Najnowszy odczyt nie podtrzymuje kwalifikacji',view['excluded'])

    def test_panel_only_invalid_identity_and_removed_ticker_never_fill_cards(self):
        f=self.sample(1,'PANEL_ONLY');self.assertEqual(self.read(f)['cards'],[])
        f=self.sample(1)
        with f.store.transaction() as db:
            row=db.execute('SELECT id,payload FROM events WHERE ticker<>?',('KI',)).fetchone()
            event=KI.load_payload(row['payload']);event['snapshot']['ticker']='OTHER'
            db.execute('UPDATE events SET payload=? WHERE id=?',(KI.json_text(event),row['id']))
        self.assertEqual(self.read(f)['cards'],[])
        f=self.sample(1);f.store.save_section('tickers',[])
        self.assertEqual(self.read(f)['cards'],[])

    def test_unfinalized_batch_does_not_present_a_review_as_selected(self):
        f=self.sample(1)
        with f.store.transaction() as db:db.execute("UPDATE company_review_batches SET state='OPEN'")
        self.assertEqual(self.read(f)['cards'],[])

    def test_frozen_report_price_is_not_replaced_by_another_market_snapshot(self):
        f=self.sample(1);view=self.read(f);card=view['cards'][0]
        before=copy.deepcopy(card)
        html=top.cards_html(KI,[card],NOW+timedelta(minutes=2))
        self.assertEqual(card,before)
        self.assertIn('Cena i analiza dotyczą odczytu',html)
        self.assertIn('Pełna analiza',html)
        self.assertIn('Wszystkie wskaźniki',html)
        self.assertIn('Przebieg zapisanej sesji',html)
        self.assertIn('Bid/ask',html)
        self.assertIn('Źródła i fakty',html)
        self.assertIn('Zapisane fundamenty',html)

    def test_mobile_cards_escape_content_and_have_native_accessible_details(self):
        f=self.sample(1);card=self.read(f)['cards'][0]
        card['analysis']['final_review']['explanation']='<script>alert(1)</script>'
        card['snapshot']['company_name']='<img src=x onerror=alert(1)>'
        card['analysis']['context']=[{'source_id':'S1','fact':'Źródłowy opis.'}]
        card['context']['sources']=[{'id':'S1','url':'javascript:alert(1)','title':'<svg onload=alert(1)>'}]
        html=top.cards_html(KI,[card],NOW)
        self.assertNotIn('<script>',html);self.assertNotIn('<img ',html);self.assertNotIn('<svg ',html)
        self.assertNotIn('href="javascript:',html)
        card['context']['sources'][0]['url']='https://[malformed'
        self.assertNotIn('href="https://[malformed',top.cards_html(KI,[card],NOW))
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('@media(max-width:900px)',html)
        self.assertIn('minmax(0,1fr)',html);self.assertIn('min-height:44px',html)
        class Parser(HTMLParser):
            def __init__(self):super().__init__();self.details=0;self.summaries=0
            def handle_starttag(self,tag,attrs):
                if tag=='details':self.details+=1
                if tag=='summary':self.summaries+=1
        parser=Parser();parser.feed(html)
        self.assertGreaterEqual(parser.details,2);self.assertEqual(parser.details,parser.summaries)

    def test_scenarios_are_conditional_and_expired_conditions_are_labelled(self):
        plan={'status':'CONDITIONAL','interval':'1h','valid_until':(NOW+timedelta(minutes=5)).isoformat(),
              'condition':{'operator':'BETWEEN','lower':.7951,'upper':.8611}}
        parts=top.scenario_text(plan,NOW)
        self.assertEqual([p[0] for p in parts],['W przedziale','Wyjście górą','Wyjście dołem'])
        self.assertIn('0,8611',parts[1][1]);self.assertIn('0,7951',parts[2][1])
        self.assertIn('Brak bieżącego scenariusza',top.scenario_text(plan,NOW+timedelta(minutes=6))[0][1])

    def test_streamlit_switches_market_and_refreshes_without_api_or_writes(self):
        from streamlit.testing.v1 import AppTest
        f=self.sample(3);before=self.dump(f.store)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return NOW+timedelta(minutes=2)
        script='import KI\nimport selected_opportunities as top\nfrom pathlib import Path\ntop.render(KI,KI.Store(Path('+repr(str(f.store.path))+')),False)'
        with patch.object(top,'datetime',Clock),patch.object(KI,'service_http',side_effect=AssertionError('No API')):
            app=AppTest.from_string(script).run(timeout=30)
            self.assertFalse(app.exception,list(app.exception))
            self.assertIn(top.VIEW,[x.value for x in app.subheader])
            self.assertTrue(any('ki-top5-card' in x.value for x in app.markdown))
            next(x for x in app.radio if x.label=='Rynek TOP 5').set_value('USA').run(timeout=30)
            self.assertFalse(app.exception,list(app.exception))
            next(x for x in app.button if x.label=='Odśwież wybrane okazje').click().run(timeout=30)
            self.assertFalse(app.exception,list(app.exception))
        self.assertEqual(self.dump(f.store),before)


if __name__=='__main__':unittest.main()
