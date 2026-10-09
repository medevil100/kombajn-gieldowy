import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from KI import (
    Store,
    candle_state,
    claim_delivery,
    gpw_notification_session_open,
    load_price_matrix_rows,
    market_indicators,
    opportunity_local_rank,
    opportunity_message,
    opportunity_indicator_rows,
    opportunity_indicator_summary,
    opportunity_volume_average_label,
    record_price_matrix_read,
    two_candle_confirmation,
    json_text,
)


class GPWAlertIndicatorContractTests(unittest.TestCase):
    def test_gpw_alert_gate_uses_warsaw_time_and_leaves_other_markets_alone(self):
        before_close = datetime(2026, 10, 8, 14, 59, tzinfo=timezone.utc)
        at_close = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
        self.assertTrue(gpw_notification_session_open("TOS.WA", before_close))
        self.assertFalse(gpw_notification_session_open("TOS.WA", at_close))
        self.assertTrue(gpw_notification_session_open("MREO", datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)))

    def test_confirmed_matrix_cannot_notify_after_gpw_close_even_if_candle_is_open(self):
        now = datetime(2026, 10, 8, 15, 10, tzinfo=timezone.utc)  # 17:10 in Warsaw
        snapshot = {
            "ticker": "TOS.WA", "interval": "1h", "candle_time": "2026-10-08T15:00:00+00:00",
            "candle_end": "2026-10-08T16:00:00+00:00", "candle_status": "OPEN",
            "acquired_at": "2026-10-08T15:05:00+00:00", "price": 3.06, "volume": 100,
            "rvol": 2.0, "ohlc": {"open": 3.0, "high": 3.1, "low": 2.99, "close": 3.06},
            "indicators": {},
            "price_matrix": {"state": "CONFIRMED", "anchor_price": 2.96, "change_pct": 3.378,
                             "candidate_started_at": "2026-10-08T14:35:00+00:00"},
        }
        self.assertFalse(two_candle_confirmation(snapshot, now))

    def test_pending_telegram_alert_is_filtered_after_gpw_close_before_network(self):
        now = datetime(2026, 10, 8, 15, 10, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "matrix.sqlite3")
            store.save_section("tickers", ["TOS.WA"])
            snapshot = {
                "ticker": "TOS.WA", "interval": "1h", "candle_time": "2026-10-08T15:00:00+00:00",
                "candle_end": "2026-10-08T16:00:00+00:00", "candle_status": "OPEN",
                "acquired_at": "2026-10-08T15:05:00+00:00", "price": 3.06, "volume": 100,
                "rvol": 2.0, "ohlc": {"open": 3.0, "high": 3.1, "low": 2.99, "close": 3.06},
                "indicators": {},
                "price_matrix": {"state": "CONFIRMED", "anchor_price": 2.96, "change_pct": 3.378,
                                 "candidate_started_at": "2026-10-08T14:35:00+00:00"},
            }
            evidence = {"kind": "CONFIRMED_OPPORTUNITY", "snapshot": snapshot}
            with store.transaction() as connection:
                connection.execute('INSERT INTO events VALUES(?,?,?,?,?)',
                    ('event-1', 'TOS.WA', '1h', now.isoformat(), json_text(evidence)))
                connection.execute('INSERT INTO analysis_jobs(event_id,state,updated_at) VALUES(?,?,?)',
                    ('event-1', 'DONE', now.isoformat()))
                connection.execute('INSERT INTO outbox(id,event_id,kind,message,status,created_at) VALUES(?,?,?,?,?,?)',
                    ('event-1:analysis', 'event-1', 'ANALYSIS', 'alert', 'PENDING', now.isoformat()))
            self.assertIsNone(claim_delivery(store, now=now))
            with store.connection() as connection:
                row = connection.execute('SELECT status,last_error,attempts FROM outbox').fetchone()
            self.assertEqual(row['status'], 'FILTERED')
            self.assertIn('po 17:00', row['last_error'])
            self.assertEqual(row['attempts'], 0)

    def test_closed_session_reads_do_not_advance_gpws_confirmation_count(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "matrix.sqlite3")
            store.save_section("tickers", ["TOS.WA"])
            base = {"ticker": "TOS.WA", "price": 2.96, "volume": 100,
                    "candle_time": "2026-10-08T14:00:00+00:00",
                    "acquired_at": "2026-10-08T14:30:00+00:00"}
            self.assertEqual(record_price_matrix_read(store, base, 2.0, 15)["state"], "BASELINE_CREATED")
            after_close = {**base, "price": 3.06, "volume": 110,
                           "candle_time": "2026-10-08T15:00:00+00:00",
                           "acquired_at": "2026-10-08T15:01:00+00:00"}
            result = record_price_matrix_read(store, after_close, 2.0, 15)
            self.assertEqual(result["read_status"], "MARKET_CLOSED")
            self.assertEqual(result["consecutive_reads"], 0)
            self.assertEqual(result["last_price"], 2.96)

    def test_matrix_table_labels_gpw_alerts_as_held_after_close(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "matrix.sqlite3")
            store.save_section("tickers", ["TOS.WA"])
            start = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
            for count, price in enumerate((2.96, 3.06, 3.05)):
                record_price_matrix_read(store, {"ticker": "TOS.WA", "price": price,
                    "volume":100+15*count,"candle_time":start.isoformat(),
                    "acquired_at": (start + timedelta(minutes=15 * count)).isoformat()}, 2.0, 15)
            rows = load_price_matrix_rows(store, datetime(2026, 10, 8, 15, 10, tzinfo=timezone.utc))
            self.assertEqual(len(rows), 1)
            self.assertIn("Wstrzymane", rows[0]["Powiadomienia"])

    def test_partial_final_candle_is_marked_and_not_used_for_rvol(self):
        start = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
        session_end = datetime(2026, 10, 8, 15, 5, tzinfo=timezone.utc)
        state = candle_state(
            {"time": start.isoformat()}, "1h", datetime(2026, 10, 8, 16, 5, tzinfo=timezone.utc),
            {"currentTradingPeriod": {"regular": {"end": session_end.timestamp()}}},
        )
        self.assertTrue(state["partial_interval"])

        rows = []
        first = start - timedelta(hours=21)
        for index in range(22):
            moment = first + timedelta(hours=index)
            rows.append({"time": moment.isoformat(), "end": (moment + timedelta(hours=1)).isoformat(),
                         "open": 3.0, "high": 3.1, "low": 2.9, "close": 3.0,
                         "volume": 100.0, "status": "CLOSED", "partial_interval": False})
        rows[-1].update(volume=0.0, partial_interval=True)
        self.assertIsNone(market_indicators(rows)["rvol"])

    def test_volume_average_label_matches_snapshot_interval(self):
        self.assertIn("1h", opportunity_volume_average_label({"interval": "1h"}))
        self.assertIn("15m", opportunity_volume_average_label({"interval": "15m"}))

    def test_indicator_table_includes_existing_metrics_and_marks_missing_values(self):
        snapshot = {"currency": "PLN", "indicators": {"rsi": 44.2, "ma_fast": 3.01,
            "ma_slow": 2.98, "last_macd_hist": -0.01, "adx": 18.6, "plus_di": 35.5,
            "minus_di": 54.6, "stoch_k": 8.3, "stoch_d": 13.9, "last_upper_bb": 3.2,
            "bb_sma": 3.0, "last_lower_bb": 2.8, "atr": 0.02, "vwma": 3.0,
            "roc": 1.2, "obv": -16803, "rvol": None}}
        rows = {row["Wskaźnik"]: row["Wartość"] for row in opportunity_indicator_rows(snapshot)}
        self.assertEqual(rows["RSI"], "44,20")
        self.assertEqual(rows["RVOL"], "Brak danych")
        self.assertIn("MACD", rows)
        self.assertIn("BB środek · SMA 20", rows)
        self.assertIn("VWMA 20", rows)

    def test_compact_indicator_summary_is_suitable_for_alert_message(self):
        summary = opportunity_indicator_summary({"currency": "PLN", "indicators": {
            "rsi": 44.2, "ma_fast": 3.01, "ma_slow": 2.98, "last_macd_hist": -0.01,
            "adx": 18.6, "plus_di": 35.5, "minus_di": 54.6, "stoch_k": 8.3,
            "stoch_d": 13.9, "rvol": None}})
        self.assertIn("RSI", summary)
        self.assertIn("SMA 10", summary)
        self.assertIn("MACD", summary)
        self.assertIn("RVOL: Brak danych", summary)

    def test_opportunity_message_contains_indicator_values_and_real_candle_interval(self):
        now = datetime(2026, 10, 8, 13, 45, tzinfo=timezone.utc)
        snapshot = {"ticker": "AAA", "interval": "1h", "candle_time": "2026-10-08T13:00:00+00:00",
            "candle_end": "2026-10-08T14:00:00+00:00", "candle_status": "OPEN",
            "acquired_at": now.isoformat(), "price": 3.06, "volume": 100, "rvol": 1.2,
            "average_volume": 83.3, "currency": "PLN", "ohlc": {"open": 3.0, "high": 3.1, "low": 2.99},
            "previous_closed": {"open": 2.9, "close": 3.0, "rvol": 1.1},
            "price_matrix": {"state": "CONFIRMED", "anchor_price": 2.96, "anchor_at": "2026-10-08T12:00:00+00:00",
                             "change_pct": 3.378, "consecutive_reads": 3, "candidate_started_at": "2026-10-08T13:00:00+00:00"},
            "indicators": {"rsi": 44.2, "ma_fast": 3.01, "ma_slow": 2.98, "last_macd_hist": -0.01}}
        ranking = opportunity_local_rank(snapshot)
        evidence = {"snapshot": snapshot, "ranking": ranking}
        message = opportunity_message("event-1", evidence, {"sources": []},
                                      {"context": [], "risks": [], "technical": []})
        self.assertIn("RSI: 44,20", message)
        self.assertIn("SMA 30: 2,9800 PLN", message)
        self.assertIn("Świeca 1h:", message)


if __name__ == "__main__":
    unittest.main()
