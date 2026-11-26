import json
from pathlib import Path
import tempfile
import unittest

import KI


class ScannerCycleRecoveryTests(unittest.TestCase):
    def test_unfinished_cycle_is_closed_with_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            store=KI.Store(Path(directory)/'cycle.sqlite3')
            with store.transaction() as c:
                c.execute('INSERT INTO cycles VALUES(?,?,?,?,?)',
                          ('broken','2026-11-24T11:30:00+00:00',None,'RUNNING','{"mode":"MARKET"}'))
                c.execute('INSERT INTO cycles VALUES(?,?,?,?,?)',
                          ('complete','2026-11-24T11:00:00+00:00','2026-11-24T11:08:00+00:00','OK','{}'))
            closed=KI.close_unfinished_market_cycles(
                store,"KeyError: 'REFERENCE_RESEARCH_RESERVED'",'2026-11-24T11:38:00+00:00')
            self.assertEqual(closed,1)
            with store.connection() as c:
                broken=c.execute("SELECT * FROM cycles WHERE id='broken'").fetchone()
                complete=c.execute("SELECT * FROM cycles WHERE id='complete'").fetchone()
            self.assertEqual((broken['status'],broken['finished_at']),('ERROR','2026-11-24T11:38:00+00:00'))
            diagnostic=json.loads(broken['payload'])['interrupted']
            self.assertEqual(diagnostic['reason'],"KeyError: 'REFERENCE_RESEARCH_RESERVED'")
            self.assertEqual(complete['status'],'OK')


if __name__ == '__main__':
    unittest.main()
