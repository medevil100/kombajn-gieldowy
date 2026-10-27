"""Pełny manifest przed AI, zgodne wnioski i krótki Telegram; bez sieci."""
import json
import unittest
import KI
import test_alert_quality_20261026 as fixtures


class FullPackageTests(unittest.TestCase):
    def sample(self):return fixtures.AlertQualityTests().sample()

    def test_manifest_has_all_local_assessments_and_all_indicator_values(self):
        ev,result=self.sample();ctx={'sources':[]}
        manifest=KI.build_analysis_manifest(ev,ctx)
        self.assertEqual(set(manifest),{'version','identity','detection','technical','activity','risk','quotes','trade_plan','comparison','sources','conclusion'})
        self.assertEqual(manifest['technical']['all_indicators'],ev['snapshot']['indicators'])
        self.assertEqual(manifest['comparison']['status'],'UNAVAILABLE')
        self.assertIn('okazji',manifest['conclusion'])
        ctx.update(analysis_manifest=manifest,ai_preflight=KI.automatic_ai_preflight(ev,ctx))
        package=json.loads(KI.event_analysis_request(ev,ctx)['messages'][-1]['content'])['proved_event']
        self.assertIn('analysis_manifest',package)
        self.assertEqual(package['analysis_manifest']['risk'],manifest['risk'])
        self.assertEqual(package['snapshot']['indicators'],manifest['technical']['all_indicators'])
        self.assertNotIn('all_indicators',package['analysis_manifest']['technical'])

    def test_telegram_is_movement_assessment_risk_not_indicator_dump(self):
        ev,result=self.sample()
        text=KI.opportunity_message('e',ev,{'sources':[]},result)
        self.assertIn('POTWIERDZONY SPADEK',text)
        self.assertIn('Ocena:',text)
        self.assertIn('Aktywność:',text)
        self.assertIn('Ryzyko:',text)
        self.assertNotIn('/100',text)
        self.assertNotIn('MACD hist.',text)
        self.assertNotIn('RVOL 2,00',text)
        self.assertLess(len(text),1200)

    def test_incorrect_rsi_labels_and_atr_paraphrase_cannot_survive(self):
        ev,result=self.sample()
        for metric,text in [('rsi','Wskaźnik pokazuje wykupienie.'),('rsi','Cena jest niedowartościowana.'),
                            ('atr','Wysoka wartość ATR wskazuje na zwiększoną zmienność.')]:
            clean=KI.validate_event_analysis({**result,'technical':[{'metric':metric,'interpretation':text}]},ev['snapshot'],{'sources':[]})
            self.assertEqual(clean['technical'],[])
            self.assertTrue(clean['quality_issues'])

    def test_full_verified_source_reaches_prompt_without_silent_cut(self):
        ev,result=self.sample();snap=ev['snapshot']
        snap.update(ticker='STX.WA',company_name='Stalexport Autostrady',company_website='https://stalexport-autostrady.pl')
        content='Stalexport Autostrady opublikował raport. '+('Dalsza treść raportu. '*150)+'KONIEC_PELNEGO_MATERIALU'
        context=KI.r1_research_sources({'results':[{'url':'https://stalexport-autostrady.pl/report','title':'Stalexport Autostrady raport','content':content,'published_date':'2026-10-12T12:00:00Z'}]},snap['acquired_at'],snap)
        self.assertEqual(context['sources'][0]['content'],content)
        context['analysis_manifest']=KI.build_analysis_manifest(ev,context)
        context['ai_preflight']=KI.automatic_ai_preflight(ev,context)
        self.assertIn('KONIEC_PELNEGO_MATERIALU',KI.event_analysis_request(ev,context)['messages'][-1]['content'])


if __name__=='__main__':unittest.main()
