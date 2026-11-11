"""Manual GPT number bindings, Python and provider-style JS regex; no API calls."""
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

import KI
from test_manual_numeric_contract import context, reply


class ManualUnicodeTests(unittest.TestCase):
    def test_actual_rejected_risk_is_preserved_and_rejected_until_bound(self):
        raw=reply('Opis danych.')
        raw['risks']=['Cofnięcie od maksimum bieżącej świecy ≥ ٢%.']
        before=copy.deepcopy(raw)
        with self.assertRaisesRegex(ValueError,r'risks\[0\].*٢'):
            KI.render_manual_research_reply(raw,context())
        self.assertEqual(raw,before)
        corrected=copy.deepcopy(raw)
        corrected['risks']=['Cofnięcie od maksimum bieżącej świecy ≥ {{threshold:retrace_risk_pct}}.']
        self.assertIn('Cofnięcie od maksimum bieżącej świecy ≥ 2%.',
                      KI.render_manual_research_reply(corrected,context()))
        self.assertEqual(raw,before)

    def test_python_schema_and_validator_reject_decimal_alphabets(self):
        c=context();pattern=KI.manual_research_schema(c)['$defs']['bound_text']['pattern']
        for digit in ('2','٢','۲','२','２','𝟚','𞥒'):
            text='Cofnięcie ≥ '+digit+'%.'
            with self.subTest(digit=digit):
                self.assertIsNone(re.fullmatch(pattern,text))
                with self.assertRaises(ValueError):KI.render_manual_research_reply(reply(text),c)
        for text in ('Żółć, cofnięcie ≥ {{threshold:retrace_risk_pct}}.',
                     'Zmiana {{metric:adverse_retrace_pct}}; SMA {{parameter:ma_fast_window}}.',
                     'Emitent {{identity:company_name}}.\nBrak potwierdzenia.'):
            self.assertIsNotNone(re.fullmatch(pattern,text))
            KI.render_manual_research_reply(reply(text),c)

    def test_javascript_schema_rejects_all_python_decimal_digits(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node.js unavailable; run provider-style regex check on Windows.')
        pattern=KI.manual_research_schema(context())['$defs']['bound_text']['pattern']
        digits=''.join(chr(code) for code in range(sys.maxunicode+1) if chr(code).isdecimal())
        script=r'''const fs=require('fs');const x=JSON.parse(fs.readFileSync(0,'utf8'));
          for(const flags of ['', 'u']) {
            const r=new RegExp(x.pattern,flags);
            for(const d of x.digits) if(r.test('Cofnięcie ≥ '+d+'%.')) throw Error('Unbound digit '+d);
            for(const t of x.valid) if(!r.test(t)) throw Error('Valid prose rejected');
          } console.log('ALL_DECIMAL_ALPHABETS_REJECTED');'''
        result=subprocess.run([node,'-e',script],input=json.dumps({'pattern':pattern,'digits':digits,
            'valid':['Żółć ≥ {{threshold:retrace_risk_pct}}.','Opis bez liczb.\nBrak danych.']}),
            text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('ALL_DECIMAL_ALPHABETS_REJECTED',result.stdout)

    def test_risk_reasons_are_bound_before_request_and_source_is_unchanged(self):
        for falling in (False,True):
            c=context();s=c['snapshot']
            s['price']=1.60;s['ohlc'].update(high=1.70,low=1.50)
            s['price_matrix']={'change_pct':-3. if falling else 3.}
            before=copy.deepcopy(c)
            request=KI.gpt_chat_request('Pełna ocena.',c,[])
            sent=json.loads(request['messages'][-1]['content'])['context']
            risk=sent['local_analysis']['risk']
            label='Odbicie od minimum' if falling else 'Cofnięcie od maksimum'
            self.assertTrue(any(label in item and '{{threshold:retrace_risk_pct}}' in item
                                for item in risk['reasons']))
            self.assertEqual(risk['pullback_pct'],'{{metric:adverse_retrace_pct}}')
            self.assertEqual(sent['numeric_constants']['threshold']['retrace_risk_pct']['value'],2.)
            measured=sent['numeric_catalog']['adverse_retrace_pct']
            self.assertEqual(measured['source'],'local_analysis.risk.pullback_pct')
            self.assertAlmostEqual(measured['value'],KI.opportunity_risk(s)['pullback_pct'])
            self.assertIn('{{threshold:retrace_risk_pct}}',request['messages'][0]['content'])
            self.assertEqual(c,before)

    def test_measurement_and_threshold_do_not_share_units_or_values(self):
        c=context();c['snapshot'].update(price=1.60,ohlc={'high':1.70,'low':1.50})
        rendered=KI.render_manual_research_reply(reply(
            'Cofnięcie {{metric:adverse_retrace_pct}}%; próg {{threshold:retrace_risk_pct}}%.'),c)
        self.assertIn('Cofnięcie 5,88 %; próg 2%.',rendered)
        self.assertNotIn('%%',rendered)
        for text in ('{{threshold:retrace_risk_pct}} USD.',
                     '{{metric:adverse_retrace_pct}} USD.','{{threshold:invented_retrace}}.'):
            with self.assertRaises(ValueError):KI.render_manual_research_reply(reply(text),c)
        c['snapshot']['ohlc']={}
        with self.assertRaises(ValueError):
            KI.render_manual_research_reply(reply('{{metric:adverse_retrace_pct}}.'),c)


if __name__=='__main__':unittest.main()
