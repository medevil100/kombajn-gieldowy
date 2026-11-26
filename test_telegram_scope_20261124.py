"""Central Telegram allow-list: TOP 5 growth, confirmed large cases, portfolio only."""
from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest

import KI


NOW=datetime(2026,11,24,15,0,tzinfo=timezone.utc)


class TelegramScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=KI.Store(Path(self.temp.name)/'scope.sqlite3')
        KI.portfolio_save(self.store,[
            {'ticker':'HELD.WA','direction':'long','sl':90.,'tp':130.},
            {'ticker':'HELDUS','direction':'long','sl':8.,'tp':14.},
        ])

    def item(self,kind,event_id):
        return {'id':event_id,'event_id':event_id,'kind':kind,'message':'test'}

    def test_unrelated_watchlist_messages_are_blocked(self):
        for kind in ('EARLY_MOVEMENT','ANALYSIS','EVIDENCE','ISSUER_NOTICE','MOVEMENT'):
            self.assertFalse(KI.telegram_scope_allowed(self.store,self.item(kind,'watch:OTHER.WA'),NOW))

    def test_individual_portfolio_alert_accepts_both_directions(self):
        self.assertTrue(KI.telegram_scope_allowed(
            self.store,self.item('PORTFOLIO_ALERT','portfolio:HELD.WA:sl:down'),NOW))
        self.assertTrue(KI.telegram_scope_allowed(
            self.store,self.item('PORTFOLIO_ALERT','portfolio:HELD.WA:tp:up'),NOW))
        self.assertFalse(KI.telegram_scope_allowed(
            self.store,self.item('PORTFOLIO_ALERT','portfolio:OTHER.WA:sl:down'),NOW))

    def test_portfolio_reports_require_at_least_one_position(self):
        self.assertTrue(KI.telegram_scope_allowed(
            self.store,self.item('PORTFOLIO_ALERT','daily_report:2026-11-24'),NOW))
        self.assertTrue(KI.telegram_scope_allowed(
            self.store,self.item('PORTFOLIO_ALERT','us_report:2026-11-24'),NOW))
        KI.portfolio_save(self.store,[])
        self.assertFalse(KI.telegram_scope_allowed(
            self.store,self.item('PORTFOLIO_ALERT','daily_report:2026-11-24'),NOW))


if __name__=='__main__':unittest.main()
