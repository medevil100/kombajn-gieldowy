"""Regresje komunikatów GNPX/CLNN/GOSS/ORGO, reguły wspólne dla tickerów."""
import unittest
import KI
import test_alert_quality_20261026 as fixtures


class MessageSynthesisTests(unittest.TestCase):
    def sample(self):return fixtures.AlertQualityTests().sample()

    def summary(self):
        return 'Potwierdzony ruch ma mieszane wsparcie. Wolumen trwającej świecy nie rozstrzyga o aktywności całej godziny, a brak ofert ogranicza ocenę wykonania.'

    def test_new_schema_requires_separate_overall_assessment(self):
        ev,result=self.sample();ctx={'sources':[],'analysis_manifest':KI.build_analysis_manifest(ev,{'sources':[]})}
        self.assertIn('assessment',KI.analysis_schema(ev['snapshot'],ctx)['required'])
        self.assertTrue(KI.analysis_publication_issues(result,True))

    def test_single_indicator_is_not_an_overall_assessment_and_cleaning_is_stable(self):
        ev,result=self.sample();result['assessment']='Cena powyżej średniej wspiera wzrost.'
        clean=KI.validate_event_analysis(result,ev['snapshot'],{'sources':[]})
        self.assertEqual(clean['assessment'],'')
        self.assertTrue(KI.analysis_publication_issues(clean,True))
        self.assertEqual(KI.validate_event_analysis(clean,ev['snapshot'],{'sources':[]}),clean)
        self.assertTrue(result['assessment'])

    def test_open_partial_volume_does_not_claim_low_hourly_activity(self):
        for ticker in ('GOSS','CLNN','AAA.WA'):
            ev,result=self.sample();ev['snapshot']['ticker']=ticker;ev['snapshot']['rvol']=.7
            text=KI.opportunity_message('e',ev,{'sources':[]},result)
            self.assertIn('za wcześnie na ocenę aktywności całej godziny',text)
            self.assertNotIn('poniżej średniej',text)
            self.assertIn('nie można ocenić spreadu',text)
            self.assertNotIn('bez przekroczenia',text)

    def test_closed_volume_can_be_compared_to_full_hours(self):
        ev,result=self.sample();ev['snapshot'].update(candle_status='CLOSED',rvol=.7)
        text=KI.opportunity_message('e',ev,{'sources':[]},result)
        self.assertIn('wolumen zakończonej świecy poniżej średniej',text)

    def test_single_histogram_does_not_prove_trend_continuation(self):
        ev,result=self.sample();ev['snapshot']['indicators']['last_macd_hist']=-.1
        result['technical']=[{'metric':'last_macd_hist','interpretation':'Histogram MACD jest ujemny, co potwierdza kontynuację trendu spadkowego.'}]
        clean=KI.validate_event_analysis(result,ev['snapshot'],{'sources':[]})
        self.assertEqual(clean['technical'],[])

    def test_mixed_signals_and_missing_quotes_cannot_be_called_low_risk(self):
        ev,result=self.sample()
        ctx={'sources':[], 'analysis_manifest':{'version':2,'technical':{'assessment':'Wskazania mieszane'}}}
        for summary in ('Wzrost wspiera wolumen, ryzyko jest niskie.',
                        'Wzrost ma mieszane wsparcie wolumenu i niskie ryzyko.'):
            result['assessment']=summary
            self.assertEqual(KI.validate_event_analysis(result,ev['snapshot'],ctx)['assessment'],'')

    def test_telegram_uses_whole_assessment_not_first_technical_comment(self):
        ev,result=self.sample();result['assessment']=self.summary()
        ctx={'sources':[]};ctx['analysis_manifest']=KI.build_analysis_manifest(ev,ctx)
        ctx['analysis_manifest']['version']=2  # Compatibility with archived string assessments.
        clean=KI.validate_event_analysis(result,ev['snapshot'],ctx)
        self.assertFalse(KI.analysis_publication_issues(clean,True))
        text=KI.opportunity_message('e',ev,ctx,clean)
        self.assertIn('Wniosek AI: '+self.summary(),text)
        self.assertNotIn(result['technical'][0]['interpretation'],text)


if __name__=='__main__':unittest.main()
