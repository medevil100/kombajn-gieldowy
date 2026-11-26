"""One model and budget contract for every paid KI AI path; provider-free."""
import unittest
import sqlite3
from pathlib import Path

import KI
import ai_model_policy as policy
import company_narrative
import ki_assistant
import large_movement


class ModelPolicyTests(unittest.TestCase):
    def test_production_contract(self):
        self.assertEqual(policy.MODEL,'gpt-6-luna')
        self.assertEqual(policy.REASONING_EFFORT,'none')
        self.assertEqual(policy.FULL_MAX_TOKENS,6600)
        self.assertEqual(policy.MAX_AUTOMATIC_CALLS_DAY,48)
        self.assertEqual(policy.chat_parameters(),{
            'model':'gpt-6-luna','reasoning_effort':'none'})

    def test_shared_limits_and_prices(self):
        self.assertEqual(company_narrative.FULL_MAX_TOKENS,6600)
        self.assertEqual(large_movement.MAX_CALLS_DAY,48)
        self.assertEqual(ki_assistant.MODEL,'gpt-6-luna')
        self.assertEqual(ki_assistant.INPUT_MICRO,0.10)
        self.assertEqual(ki_assistant.OUTPUT_MICRO,0.50)

    def test_chat_and_deep_analysis_use_luna_without_provider_call(self):
        request=KI.gpt_chat_request('test',{},[])
        self.assertEqual(request['model'],'gpt-6-luna')
        self.assertEqual(request['reasoning_effort'],'none')
        config=KI.deep_analysis_config({},Path('.'))
        self.assertEqual(config['deep_think_llm'],'gpt-6-luna')
        self.assertEqual(config['quick_think_llm'],'gpt-6-luna')
        self.assertEqual(config['reasoning_effort'],'none')

    def test_automatic_limit_is_shared_and_manual_calls_are_excluded(self):
        c=sqlite3.connect(':memory:')
        try:
            c.executescript(large_movement.SCHEMA)
            c.execute("CREATE TABLE radar_ai_jobs(ticker TEXT,started_at TEXT,packet TEXT)")
            c.execute("INSERT INTO large_movement_jobs(id,ticker,cycle_id,state,created_at,started_at,packet) VALUES('l','AAA','c','DONE','2026-11-25','2026-11-25T01:00:00+00:00','{}')")
            c.execute("INSERT INTO radar_ai_jobs VALUES('AAA','2026-11-25T02:00:00+00:00','{}')")
            c.execute("INSERT INTO radar_ai_jobs VALUES('AAA','2026-11-25T03:00:00+00:00','{\"manual_requested\":1}')")
            self.assertEqual(large_movement.automatic_ai_usage(c,'2026-11-25T00:00:00+00:00'),2)
            self.assertEqual(large_movement.automatic_ai_usage(c,'2026-11-25T00:00:00+00:00','AAA'),2)
        finally:
            c.close()


if __name__=='__main__':
    unittest.main()
