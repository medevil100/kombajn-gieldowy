# KI repair notes — 2026-10-24

The saved application now reads hourly candles every fifteen minutes and stores daily OHLCV separately. The price matrix uses the previous completed session close, keeps that reference across restarts, and requires three accepted activity proofs. Missing references and stale/out-of-order reads cannot qualify an opportunity. The schema addition is compatible with the previous schema version; the migration helper only adds the daily table and checks existing table definitions and row counts.

AI analysis is sanitized on a deep copy. Numbers are bound to the selected indicator, source quotations must be literal and bounded, dependent conclusions are removed when a premise fails, and local quality diagnostics survive revalidation. Empty analyses require review and cannot produce pending publication messages. Provider responses remain available for audit.

Yahoo failures have persistent, instrument- and interval-specific retry schedules. Invalid daily rows are retained in diagnostics while valid sessions remain usable. Extending the provider's history range cannot replace a valid recent candle with an older tail. Closed-session fetches wait for the next standard opening.

Search uses the verified issuer name, with the instrument identifier and exact cutoff retained in metadata. Domain and date restrictions reach the Tavily SDK and remain enforced locally. Undated results are diagnostic-only. Search response IDs are distinguished from local reservation IDs. This intentionally supersedes the earlier requirement to place the full Yahoo ticker in query text; stored Yahoo instrument identifiers are unchanged.

Regular US sessions use America/New_York rather than a fixed Warsaw closing hour. Tests cover open/close boundaries and mismatched European/US daylight-saving transitions. A full holiday and early-close calendar is still outstanding. Worker liveness and historical provider diagnostics are displayed separately.

Validation for this working snapshot:

- Full application self-test: 203 passed.
- Streamlit panel tests: 24 passed.
- Additional E04/E05/matrix integration contracts: 31 passed.
- A separately authorized historical integration probe obtained a real OpenAI response, exercised sanitization and saved the result in an isolated SQLite database. One clearly marked Telegram test message received an API delivery acknowledgement.

The standard local test suites do not call paid services or send messages. Production databases, snapshots, credentials, live provider responses and delivery artifacts are excluded from this commit. The historical integration probe does not establish that a new automatic opportunity has completed the entire chain during an open market session.

Known limitations: seven older research-contract tests still reference the missing legacy automatic_search_plan interface. Those tests have not been weakened or masked. One historical REVIEW_REQUIRED job lacks enough original diagnostics to reconstruct its ValueError; it is not retried automatically. Unexpected future analysis errors now record a sanitized reason and processing stage.

KI.py already differed from Git HEAD before this repair session. This commit records its integrated, tested current version; unrelated changes in other files are left uncommitted. No push is included.
