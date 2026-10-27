"""Kontrakt offline wariantów REST/CLI, bez fikcyjnych danych rynkowych i mocków."""
import unittest
import KI
import tavily_cli_adapter as cli


class R1ConfigurationContract(unittest.TestCase):
    def test_search_is_only_backend_even_with_old_settings(self):
        for mode in (None, 'REST', 'CLI', 'INNY', 'RESEARCH'):
            self.assertEqual(KI.service_config({'tavily_mode': mode})['tavily_mode'], 'SEARCH')

    def test_switches_stay_strict(self):
        with self.assertRaises(ValueError):
            KI.service_config({'pipeline_enabled': 'true'})
        self.assertFalse(KI.service_config({})['telegram_enabled'])

    def test_only_mini_can_be_started(self):
        args=cli.research_start_arguments('MREO')
        self.assertEqual(args[:2], ['research', 'run'])
        self.assertEqual(args[args.index('--model')+1], 'mini')
        self.assertIn('--no-wait', args)
        with self.assertRaises(cli.CLITransportError):
            cli.start_research('MREO', '')

    def test_request_id_is_never_a_command_option(self):
        for value in ('', '--help', '../file', 'id name', '-id'):
            with self.assertRaises(cli.CLITransportError):
                cli.research_status_arguments(value)

    def test_old_transports_are_removed(self):
        for name in ('collect', '_search_arguments', 'scope_for_hit'):
            self.assertFalse(hasattr(cli, name))
        for name in ('tavily_cli_context', 'fetch_event_context', 'manual_search_plan', 'automatic_search_plan'):
            self.assertFalse(hasattr(KI, name))


class R1ResearchCLIContractTests(unittest.TestCase):
    """R1: kontrakt Research CLI, bez sieci, SQLite i platnych API."""

    def test_research_schema_describes_every_named_property(self):
        def check(node):
            for name,value in node.get('properties',{}).items():
                self.assertIsInstance(value.get('description'),str,name)
                self.assertTrue(value['description'].strip(),name)
                check(value)
            if isinstance(node.get('items'),dict):check(node['items'])
        check(cli.RESEARCH_OUTPUT_SCHEMA)

    def test_research_run_uses_mini_and_async(self):
        args=cli.research_start_arguments('MREO, kontekst emitenta')
        self.assertEqual(args[:2], ['research', 'run'])
        self.assertEqual(args[args.index('--model')+1], 'mini')
        self.assertIn('--no-wait', args)

    def test_research_rejects_empty_query(self):
        with self.assertRaises(cli.CLITransportError):
            cli.research_start_arguments('  ')

    def test_research_response_preserves_provider_fields(self):
        raw = {
            "request_id": "r1-contract-example",
            "status": "completed",
            "content": "Potwierdzony tekst odpowiedzi.",
            "sources": [
                {"url": "https://www.sec.gov/example"}
            ],
            "created_at": "2026-10-11T14:58:04+00:00",
            "response_time": 59.64
        }

        result = cli._normalize_research_response(raw)

        self.assertEqual(result["request_id"], raw["request_id"])
        self.assertEqual(result["status"], raw["status"])
        self.assertEqual(result["content"], raw["content"])
        self.assertEqual(result["sources"], raw["sources"])
        self.assertEqual(result["created_at"], raw["created_at"])
        self.assertEqual(result["raw_response"], raw)




class R1ResearchSQLiteContractTests(unittest.TestCase):
    """R1: rzeczywisty SQLite w RAM, bez sieci i plikow."""

    def setUp(self):
        import sqlite3
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(KI.SCHEMA)
        self.event_id = "R1-EVENT-001"
        self.query = "MREO: zweryfikuj kontekst potwierdzonego ruchu."
        self.cutoff = "2026-10-09T20:00:00+00:00"
        self.db.execute(
            "INSERT INTO events(id,ticker,interval,created_at,payload)"
            " VALUES(?,?,?,?,?)",
            (
                self.event_id,
                "MREO",
                "1h",
                self.cutoff,
                "{}"
            )
        )

    def tearDown(self):
        self.db.close()

    def test_reservation_is_persisted_before_api(self):
        self.assertTrue(
            KI.reserve_research(
                self.db, self.event_id, self.query, self.cutoff
            )
        )
        row = self.db.execute(
            "SELECT * FROM research_requests WHERE event_id=?",
            (self.event_id,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["state"], "RESERVED")
        self.assertEqual(row["query"], self.query)
        self.assertEqual(row["cutoff"], self.cutoff)
        self.assertIsNone(row["request_id"])

    def test_same_event_cannot_reserve_twice(self):
        self.assertTrue(
            KI.reserve_research(
                self.db, self.event_id, self.query, self.cutoff
            )
        )
        self.assertFalse(
            KI.reserve_research(
                self.db, self.event_id, self.query, self.cutoff
            )
        )
        count = self.db.execute(
            "SELECT COUNT(*) FROM research_requests WHERE event_id=?",
            (self.event_id,)
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_uncertain_request_cannot_be_restarted(self):
        self.assertTrue(
            KI.reserve_research(
                self.db, self.event_id, self.query, self.cutoff
            )
        )
        KI.mark_research_uncertain(
            self.db, self.event_id,
            "Nieznany wynik uruchomienia CLI."
        )
        row = self.db.execute(
            "SELECT state FROM research_requests WHERE event_id=?",
            (self.event_id,)
        ).fetchone()
        self.assertEqual(row["state"], "CALL_UNCERTAIN")
        self.assertFalse(
            KI.reserve_research(
                self.db, self.event_id, self.query, self.cutoff
            )
        )




class R1ResearchDurabilityContractTests(unittest.TestCase):
    """Rzeczywisty SQLite w RAM; bez API i plikow testowych."""

    def setUp(self):
        import sqlite3
        self.sqlite3 = sqlite3
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(KI.SCHEMA)
        self.event_id = "R1-PERSIST-001"
        self.cutoff = "2026-10-09T20:00:00+00:00"
        self.query = "MREO: sprawdz fakty dotyczace ruchu."
        self.db.execute(
            "INSERT INTO events(id,ticker,interval,created_at,payload)"
            " VALUES(?,?,?,?,?)",
            (self.event_id, "MREO", "1h", self.cutoff, "{}")
        )

    def tearDown(self):
        self.db.close()

    def restored_connection(self):
        """Odtworzenie obrazu SQLite do nowego polaczenia RAM."""
        restored = self.sqlite3.connect(":memory:")
        restored.row_factory = self.sqlite3.Row
        restored.execute("PRAGMA foreign_keys=ON")
        restored.deserialize(self.db.serialize())
        return restored

    def test_reserved_event_survives_database_restore(self):
        self.assertTrue(
            KI.reserve_research(
                self.db, self.event_id, self.query, self.cutoff
            )
        )
        restored = self.restored_connection()
        try:
            self.assertFalse(
                KI.reserve_research(
                    restored, self.event_id, self.query, self.cutoff
                )
            )
        finally:
            restored.close()

    def test_uncertain_event_survives_database_restore(self):
        self.assertTrue(
            KI.reserve_research(
                self.db, self.event_id, self.query, self.cutoff
            )
        )
        KI.mark_research_uncertain(
            self.db, self.event_id, "Nieznany wynik procesu."
        )
        restored = self.restored_connection()
        try:
            row = restored.execute(
                "SELECT state FROM research_requests WHERE event_id=?",
                (self.event_id,)
            ).fetchone()
            self.assertEqual(row["state"], "CALL_UNCERTAIN")
            self.assertFalse(
                KI.reserve_research(
                    restored, self.event_id, self.query, self.cutoff
                )
            )
        finally:
            restored.close()

    def test_request_id_and_completed_result_are_preserved(self):
        self.assertTrue(
            KI.reserve_research(
                self.db, self.event_id, self.query, self.cutoff
            )
        )

        raw = {
            "request_id": "r1-example-001",
            "status": "completed",
            "content": "Raport w jezyku polskim.",
            "sources": [{"url": "https://www.sec.gov/example"}],
            "created_at": "2026-10-11T14:58:04+00:00",
            "response_time": 59.64
        }

        KI.mark_research_submitted(
            self.db, self.event_id, raw["request_id"]
        )
        KI.complete_research(self.db, self.event_id, raw)

        restored = self.restored_connection()
        try:
            row = restored.execute(
                "SELECT * FROM research_requests WHERE event_id=?",
                (self.event_id,)
            ).fetchone()
            self.assertEqual(row["state"], "COMPLETED")
            self.assertEqual(row["request_id"], raw["request_id"])
            import json
            self.assertEqual(
                json.loads(row["raw_response"]), raw
            )
            self.assertFalse(
                KI.reserve_research(
                    restored, self.event_id, self.query, self.cutoff
                )
            )
        finally:
            restored.close()




class R1ResearchSafetyContractTests(unittest.TestCase):
    """Kontrakty bezpieczenstwa R1, tylko SQLite w RAM."""

    def setUp(self):
        import sqlite3
        self.sqlite3 = sqlite3
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(KI.SCHEMA)

        for event_id in ("R1-SAFE-001", "R1-SAFE-002"):
            self.db.execute(
                "INSERT INTO events(id,ticker,interval,created_at,payload)"
                " VALUES(?,?,?,?,?)",
                (
                    event_id, "MREO", "1h",
                    "2026-10-09T20:00:00+00:00", "{}"
                )
            )

    def tearDown(self):
        self.db.close()

    def test_repeated_event_cannot_change_research_identity(self):
        event = "R1-SAFE-001"
        cutoff = "2026-10-09T20:00:00+00:00"

        self.assertTrue(
            KI.reserve_research(self.db, event, "Zapytanie A", cutoff)
        )

        with self.assertRaises(ValueError):
            KI.reserve_research(
                self.db, event, "Zapytanie B", cutoff
            )

        with self.assertRaises(ValueError):
            KI.reserve_research(
                self.db, event, "Zapytanie A",
                "2026-10-10T20:00:00+00:00"
            )

        row = self.db.execute(
            "SELECT query,cutoff FROM research_requests"
            " WHERE event_id=?", (event,)
        ).fetchone()

        self.assertEqual(row["query"], "Zapytanie A")
        self.assertEqual(row["cutoff"], cutoff)

    def test_request_id_cannot_belong_to_two_events(self):
        cutoff = "2026-10-09T20:00:00+00:00"

        for event in ("R1-SAFE-001", "R1-SAFE-002"):
            self.assertTrue(
                KI.reserve_research(
                    self.db, event, "Kontekst MREO", cutoff
                )
            )

        KI.mark_research_submitted(
            self.db, "R1-SAFE-001", "research-unique-001"
        )

        with self.assertRaises(
            (ValueError, self.sqlite3.IntegrityError)
        ):
            KI.mark_research_submitted(
                self.db, "R1-SAFE-002", "research-unique-001"
            )

        row = self.db.execute(
            "SELECT state,request_id FROM research_requests"
            " WHERE event_id='R1-SAFE-002'"
        ).fetchone()

        self.assertEqual(row["state"], "RESERVED")
        self.assertIsNone(row["request_id"])

    def test_legacy_research_table_migration_preserves_record(self):
        self.db.execute("DROP TABLE research_requests")

        self.db.execute(
            "CREATE TABLE research_requests("
            "event_id TEXT PRIMARY KEY REFERENCES events(id),"
            "state TEXT NOT NULL,query TEXT NOT NULL,"
            "cutoff TEXT NOT NULL,request_id TEXT UNIQUE,"
            "last_error TEXT,created_at TEXT NOT NULL,"
            "updated_at TEXT NOT NULL)"
        )

        self.db.execute(
            "INSERT INTO research_requests"
            "(event_id,state,query,cutoff,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?)",
            (
                "R1-SAFE-001", "RESERVED", "Kontekst MREO",
                "2026-10-09T20:00:00+00:00",
                "2026-10-11T15:00:00+00:00",
                "2026-10-11T15:00:00+00:00"
            )
        )

        KI.ensure_research_schema(self.db)

        columns = {
            row["name"] for row in self.db.execute(
                "PRAGMA table_info(research_requests)"
            )
        }
        self.assertIn("raw_response", columns)

        record = self.db.execute(
            "SELECT * FROM research_requests"
            " WHERE event_id='R1-SAFE-001'"
        ).fetchone()

        self.assertEqual(record["state"], "RESERVED")
        self.assertEqual(record["query"], "Kontekst MREO")
        self.assertIsNone(record["raw_response"])
        self.assertFalse(
            KI.reserve_research(
                self.db, "R1-SAFE-001", "Kontekst MREO",
                "2026-10-09T20:00:00+00:00"
            )
        )




class R1ResearchStoreContractTests(unittest.TestCase):
    """Dwa polaczenia do SQLite RAM; bez plikow i bez API."""

    def setUp(self):
        import sqlite3
        import uuid
        self.sqlite3 = sqlite3
        self.uri = (
            "file:ki_r1_store_" + uuid.uuid4().hex +
            "?mode=memory&cache=shared"
        )
        self.a = sqlite3.connect(
            self.uri, uri=True, isolation_level=None,
            timeout=1
        )
        self.b = sqlite3.connect(
            self.uri, uri=True, isolation_level=None,
            timeout=1
        )
        for con in (self.a, self.b):
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA busy_timeout=1000")

        self.a.executescript(KI.SCHEMA)
        self.event_id = "R1-STORE-001"
        self.cutoff = "2026-10-09T20:00:00+00:00"
        self.query = "MREO: weryfikacja kontekstu ruchu."
        self.a.execute(
            "INSERT INTO events(id,ticker,interval,created_at,payload)"
            " VALUES(?,?,?,?,?)",
            (self.event_id, "MREO", "1h", self.cutoff, "{}")
        )

    def tearDown(self):
        self.b.close()
        self.a.close()

    def test_reservation_visible_to_second_connection_after_commit(self):
        self.a.execute("BEGIN IMMEDIATE")
        self.assertTrue(
            KI.reserve_research(
                self.a, self.event_id, self.query, self.cutoff
            )
        )
        self.a.execute("COMMIT")

        row = self.b.execute(
            "SELECT state,query,cutoff FROM research_requests"
            " WHERE event_id=?", (self.event_id,)
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["state"], "RESERVED")
        self.assertEqual(row["query"], self.query)

        self.assertFalse(
            KI.reserve_research(
                self.b, self.event_id, self.query, self.cutoff
            )
        )

    def test_concurrent_transaction_cannot_reserve_same_event(self):
        self.a.execute("BEGIN IMMEDIATE")
        try:
            self.assertTrue(
                KI.reserve_research(
                    self.a, self.event_id, self.query, self.cutoff
                )
            )

            with self.assertRaises(self.sqlite3.OperationalError):
                self.b.execute("BEGIN IMMEDIATE")
        finally:
            self.a.execute("COMMIT")

        self.b.execute("BEGIN IMMEDIATE")
        try:
            self.assertFalse(
                KI.reserve_research(
                    self.b, self.event_id, self.query, self.cutoff
                )
            )
        finally:
            self.b.execute("COMMIT")

        count = self.a.execute(
            "SELECT COUNT(*) FROM research_requests"
            " WHERE event_id=?", (self.event_id,)
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_store_has_research_reservation_transaction(self):
        self.assertTrue(
            hasattr(KI.Store, "reserve_research")
        )
        self.assertTrue(
            hasattr(KI.Store, "ensure_research_schema")
        )


class R1ResumeAndSourceContracts(unittest.TestCase):
    """Real Store/SQLite; completed records and pure contracts, no API replacements."""
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.temp=tempfile.TemporaryDirectory()
        self.store=KI.Store(Path(self.temp.name)/'r1.sqlite3')
        self.snapshot={'ticker':'MREO','company_name':'Mereo BioPharma Group',
                       'acquired_at':'2026-10-11T18:00:00+00:00'}
        self.event='r1-resume-event'
        with self.store.transaction() as c:
            c.execute('INSERT INTO events(id,ticker,interval,created_at,payload) VALUES(?,?,?,?,?)',
                      (self.event,'MREO','1h',self.snapshot['acquired_at'],KI.json_text({'snapshot':self.snapshot,'manual_analysis':True})))
            c.execute("INSERT INTO analysis_jobs(event_id,state,updated_at) VALUES(?,'PENDING_CONTEXT',?)",(self.event,KI.utc_now()))
        self.raw={'request_id':'r1-saved-id','status':'completed','content':'Unverified report',
                  'results':[{'url':'https://www.sec.gov/Archives/r1','title':'Mereo BioPharma Group: report',
                              'content':'Mereo BioPharma Group filed a report.',
                              'published_date':'2026-10-10T19:00:00Z'}]}

    def tearDown(self):
        self.temp.cleanup()

    def submitted(self):
        self.store.reserve_research(self.event,'ORIGINAL QUERY','2026-10-11T18:00:00+00:00')
        with self.store.transaction() as c:
            KI.mark_research_submitted(c,self.event,self.raw['request_id'])

    def test_completed_record_resumes_automatic_pipeline_without_key(self):
        self.submitted()
        with self.store.transaction() as c:KI.complete_research(c,self.event,KI.search_result_record(self.raw,'local'))
        self.assertTrue(KI.process_analysis_once(self.store,{},self.event))
        with self.store.connection() as c:
            row=c.execute('SELECT * FROM analysis_jobs WHERE event_id=?',(self.event,)).fetchone()
            self.assertEqual(row['state'],'PENDING_AI')
            import json
            context=json.loads(row['context'])
            self.assertEqual(context['request_id'],self.raw['request_id'])
            self.assertEqual(context['query'],'ORIGINAL QUERY')
            self.assertEqual(len(context['sources']),1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM research_requests').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)

    def test_submitted_record_keeps_original_identity(self):
        self.submitted()
        row=KI.load_event_research(self.store,self.event)
        self.assertEqual(row['query'],'ORIGINAL QUERY')
        self.assertEqual(row['request_id'],'r1-saved-id')
        KI.process_analysis_once(self.store,{},self.event)
        self.assertEqual(KI.load_event_research(self.store,self.event)['state'],'SUBMITTED')

    def test_reserved_record_requires_review_without_restart(self):
        self.store.reserve_research(self.event,'ORIGINAL QUERY',self.snapshot['acquired_at'])
        KI.process_analysis_once(self.store,{},self.event)
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT state FROM analysis_jobs').fetchone()[0],'REVIEW_REQUIRED')
        self.assertEqual(KI.load_event_research(self.store,self.event)['state'],'RESERVED')

    def test_completed_manual_record_is_reused_without_api_key(self):
        context={'ticker':'MREO','research':{'backend':'SEARCH','status':'DONE','query':'ORIGINAL QUERY','sources':[]}}
        KI.collect_manual_research(self.store,'unused',context,self.snapshot,'')
        self.assertEqual(context['research']['status'],'DONE')
        self.assertEqual(context['research']['query'],'ORIGINAL QUERY')

    def test_uncertain_manual_record_blocks_start_without_key(self):
        context={'research':{'status':'CALL_UNCERTAIN','query':'ORIGINAL QUERY'}}
        with self.assertRaises(KI.ServiceError):
            KI.collect_manual_research(self.store,'unused',context,self.snapshot,'')
        self.assertEqual(context['research']['status'],'CALL_UNCERTAIN')

    def test_metadata_does_not_become_source_text_or_publication_date(self):
        raw={**self.raw,'results':[{'url':'https://www.sec.gov/Archives/r1','title':'Mereo BioPharma Group'}]}
        result=KI.r1_research_sources(raw,self.snapshot['acquired_at'],self.snapshot)
        self.assertEqual(result['sources'],[])
        self.assertEqual(result['excluded'],1)
        self.assertNotIn('raw_response',result)
        self.assertEqual(result['raw_response_ref']['table'],'research_requests')

    def test_unsafe_future_undated_unrelated_sources_are_excluded(self):
        import copy
        good=copy.deepcopy(self.raw['results'][0])
        values=[good,{**good,'url':'https://127.0.0.1/a'},
                {**good,'url':'https://www.sec.gov/future','published_date':'2026-10-12T00:00:00Z'},
                {**good,'url':'https://www.sec.gov/undated','published_date':None},
                {**good,'url':'https://www.sec.gov/other','title':'Other company','content':'Other company report.'}]
        result=KI.r1_research_sources({**self.raw,'results':values},self.snapshot['acquired_at'],self.snapshot)
        self.assertEqual(len(result['sources']),1)
        self.assertEqual(result['excluded'],4)
        self.assertEqual(result['date_unverified_count'],1)

    def test_legacy_research_material_is_not_misread_as_search(self):
        raw={'request_id':'legacy','status':'completed','content':{'materials':self.raw['results']},'sources':self.raw['results']}
        with self.assertRaises(KI.ServiceError):
            KI.r1_research_sources(raw,self.snapshot['acquired_at'],self.snapshot)

    def test_raw_research_response_is_not_sent_twice_to_gpt(self):
        context={'ticker':'MREO','research':KI.r1_research_sources(self.raw,self.snapshot['acquired_at'],self.snapshot)}
        request=KI.gpt_chat_request('Explain',context,[])
        self.assertNotIn('raw_response',request['messages'][-1]['content'])
        self.assertNotIn('Unverified report',request['messages'][-1]['content'])

    def test_pending_status_schedules_read_without_new_reservation(self):
        self.submitted()
        KI.claim_analysis(self.store,self.event)
        KI.fail_analysis(self.store,self.event,KI.ResearchPending('Research still running',uncertain=True))
        with self.store.connection() as c:
            row=c.execute('SELECT state,next_attempt_at FROM analysis_jobs').fetchone()
            self.assertEqual(row['state'],'PENDING_CONTEXT')
            self.assertIsNotNone(row['next_attempt_at'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM research_requests').fetchone()[0],1)
        self.assertEqual(KI.load_event_research(self.store,self.event)['request_id'],'r1-saved-id')

    def test_restart_recovers_submitted_and_completed_without_new_id(self):
        self.submitted()
        KI.claim_analysis(self.store,self.event)
        KI.recover_service_jobs(self.store,'analysis')
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT state FROM analysis_jobs').fetchone()[0],'PENDING_CONTEXT')
        self.assertEqual(KI.load_event_research(self.store,self.event)['request_id'],'r1-saved-id')

    def test_manual_reservation_is_committed_and_cannot_be_repeated(self):
        import json
        context={'ticker':'MREO','research':{'status':'PENDING','sources':[]}}
        with self.store.transaction() as c:
            c.execute("INSERT INTO gpt_chat_turns(id,question,context,state,created_at) VALUES(?,?,?,'REQUESTED',?)",
                      ('r1-reserve','Question',KI.json_text(context),KI.utc_now()))
        reserved={'ticker':'MREO','research':{'status':'CALL_UNCERTAIN','query':'ORIGINAL QUERY'}}
        KI.reserve_manual_research(self.store,'r1-reserve',reserved)
        with self.store.connection() as c:
            saved=json.loads(c.execute('SELECT context FROM gpt_chat_turns WHERE id=?',('r1-reserve',)).fetchone()[0])
            self.assertEqual(saved['research']['status'],'CALL_UNCERTAIN')
        with self.assertRaises(KI.ServiceError):
            KI.reserve_manual_research(self.store,'r1-reserve',reserved)

    def test_pending_response_needs_no_sources(self):
        raw={'request_id':'r1-pending','status':'pending'}
        self.assertEqual(cli._normalize_research_response(raw)['status'],'pending')

    def test_status_requires_matching_id_and_known_status(self):
        for raw in ({'status':'completed','request_id':'other','sources':[]},
                    {'status':'INVENTED','request_id':'r1-saved-id'},
                    {'status':'completed','request_id':'r1-saved-id'}):
            with self.assertRaises(ValueError):
                cli._normalize_research_response(raw,'r1-saved-id')

    def test_submitted_legacy_research_never_starts_new_paid_search(self):
        self.submitted()
        KI.process_analysis_once(self.store,{},self.event)
        with self.store.connection() as c:
            row=c.execute('SELECT state,last_error FROM analysis_jobs').fetchone()
            self.assertEqual(row['state'],'REVIEW_REQUIRED')
            self.assertTrue(row['last_error'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM research_requests').fetchone()[0],1)


class R1CLIDiagnosticContracts(unittest.TestCase):
    """Pure process-result contracts; no subprocess or API replacements."""
    def test_start_diagnostics_are_excluded_from_gpt_input(self):
        context={'research':{'sources':[],'start_response':{'marker':'PRIVATE_START_RESPONSE'},
                             'start_error':'PRIVATE_START_ERROR'}}
        request=KI.gpt_chat_request('Question',context,[])
        text=KI.json_text(request)
        self.assertNotIn('PRIVATE_START_RESPONSE',text)
        self.assertNotIn('PRIVATE_START_ERROR',text)

    def test_successful_pending_process_result(self):
        result=cli.parse_cli_result(0,'{"request_id":"task-123","status":"pending"}','')
        self.assertEqual(result['request_id'],'task-123')

    def test_nonzero_process_exposes_redacted_error_and_task_id(self):
        with self.assertRaises(cli.CLITransportError) as raised:
            cli.parse_cli_result(1,'{"request_id":"task-123","status":"pending"}',
                                 'Unauthorized tvly-secret-key private-secret',('private-secret',))
        self.assertEqual(raised.exception.request_id,'task-123')
        self.assertIn('Unauthorized',str(raised.exception))
        self.assertNotIn('private-secret',str(raised.exception))
        self.assertNotIn('tvly-secret-key',str(raised.exception))

    def test_json_error_is_not_hidden(self):
        with self.assertRaises(cli.CLITransportError) as raised:
            cli.parse_cli_result(0,'{"error":"Invalid API key"}','')
        self.assertIn('Invalid API key',str(raised.exception))

    def test_invalid_json_keeps_traceback_without_credentials(self):
        with self.assertRaises(cli.CLITransportError) as raised:
            cli.parse_cli_result(1,'','TypeError: unexpected argument; Bearer abcsecret')
        self.assertIn('TypeError',str(raised.exception))
        self.assertNotIn('abcsecret',str(raised.exception))

    def test_invalid_id_is_not_used_for_resume(self):
        self.assertIsNone(cli.CLITransportError('failure',{'request_id':'--help'}).request_id)

    def test_diagnostic_is_bounded_and_removes_named_secrets(self):
        text=cli.sanitize_cli_diagnostic('api_key="abc" access_token=xyz '+('x'*4000))
        self.assertNotIn('abc',text);self.assertNotIn('xyz',text)
        self.assertLessEqual(len(text),3000)


class R1ManualStartDiagnosticSQLiteContracts(unittest.TestCase):
    def test_valid_id_survives_start_failure_without_new_call(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store=KI.Store(Path(directory)/'diagnostic.sqlite3')
            context={'research':{'status':'CALL_UNCERTAIN'}}
            with store.transaction() as con:
                con.execute("INSERT INTO gpt_chat_turns(id,question,state,context,created_at) VALUES(?,?,?,?,?)",
                            ('diagnostic-turn','Question','REQUESTED',KI.json_text(context),KI.utc_now()))
            KI.record_manual_start_failure(store,'diagnostic-turn',context,
                                           cli.CLITransportError('bad status',{'request_id':'saved-task'}))
            with store.connection() as con:
                saved=KI.json.loads(con.execute('SELECT context FROM gpt_chat_turns WHERE id=?',('diagnostic-turn',)).fetchone()[0])
            self.assertEqual(saved['research']['request_id'],'saved-task')
            self.assertEqual(saved['research']['status'],'SUBMITTED')
            self.assertEqual(saved['research']['start_error'],'bad status')

    def test_missing_id_keeps_uncertain_reservation(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store=KI.Store(Path(directory)/'diagnostic.sqlite3')
            context={'research':{'status':'CALL_UNCERTAIN'}}
            with store.transaction() as con:
                con.execute("INSERT INTO gpt_chat_turns(id,question,state,context,created_at) VALUES(?,?,?,?,?)",
                            ('diagnostic-turn','Question','REQUESTED',KI.json_text(context),KI.utc_now()))
            KI.record_manual_start_failure(store,'diagnostic-turn',context,cli.CLITransportError('CLI failed'))
            self.assertEqual(context['research']['status'],'CALL_UNCERTAIN')
            self.assertNotIn('request_id',context['research'])


class RVOLFullCandleReferenceContracts(unittest.TestCase):
    """Pure indicator contracts: shortened session bars must not erase the reference."""
    def rows(self,n=35):
        from datetime import datetime,timedelta,timezone
        start=datetime(2026,9,1,8,tzinfo=timezone.utc)
        return [{'time':(start+timedelta(hours=i)).isoformat(),'open':10.,'high':11.,
                 'low':9.,'close':10.,'volume':100.,'status':'CLOSED'} for i in range(n)]

    def test_shortened_previous_bar_is_skipped(self):
        rows=self.rows();rows[-5].update(partial_interval=True,volume=1.)
        rows[-1]['volume']=200.
        result=KI.market_indicators(rows)
        self.assertEqual(result['average_volume_reference'],100.)
        self.assertEqual(result['rvol'],2.)

    def test_reference_uses_latest_twenty_eligible_prior_bars(self):
        rows=self.rows()
        for index,row in enumerate(rows):row['volume']=float(index+1)
        rows[-3]['partial_interval']=True
        rows[-4]['status']='OPEN'
        rows[-1]['volume']=999.
        eligible=[r['volume'] for r in rows[:-1] if r['status']=='CLOSED' and not r.get('partial_interval')][-20:]
        expected=sum(eligible)/20
        result=KI.market_indicators(rows)
        self.assertEqual(result['average_volume_reference'],expected)
        self.assertEqual(result['rvol'],999./expected)

    def test_shortened_current_bar_keeps_reference_but_not_hourly_rvol(self):
        rows=self.rows();rows[-4]['partial_interval']=True
        rows[-1].update(partial_interval=True,volume=10.)
        result=KI.market_indicators(rows)
        self.assertEqual(result['average_volume_reference'],100.)
        self.assertIsNone(result['rvol'])

    def test_insufficient_eligible_bars_are_not_padded(self):
        rows=self.rows(21);rows[-3]['partial_interval']=True
        result=KI.market_indicators(rows)
        self.assertIsNone(result['average_volume_reference'])
        self.assertIsNone(result['rvol'])


class ADTXWatchlistRestoreContract(unittest.TestCase):
    def test_addition_preserves_other_tickers_and_is_idempotent(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store=KI.Store(Path(directory)/'watchlist.sqlite3')
            store.save_section('tickers',['STX.WA','MREO'])
            self.assertEqual(KI.add_observation_tickers(store,['ADTX']),1)
            self.assertEqual(KI.add_observation_tickers(store,['ADTX']),0)
            self.assertEqual(store.load_section('tickers',[]),['STX.WA','MREO','ADTX'])
            with store.connection() as con:
                self.assertEqual([r[0] for r in con.execute('SELECT ticker FROM watchlist ORDER BY position')],
                                 ['STX.WA','MREO','ADTX'])


class SearchMonthWindowContracts(unittest.TestCase):
    def snapshot(self,manual=False):
        return {'ticker':'MREO','company_name':'Mereo BioPharma Group',
                'acquired_at':'2026-10-11T18:00:00+00:00','_manual_research':manual}

    def raw(self,date):
        return {'request_id':'window-test','status':'completed','content':{},
                'results':[{'url':'https://www.sec.gov/Archives/window-test',
                            'title':'Mereo BioPharma Group report','content':'Mereo BioPharma Group filed a report.',
                            'published_date':date}]}

    def test_query_and_time_bounds_are_separate_for_both_modes(self):
        for manual in (False,True):
            s=self.snapshot(manual)
            self.assertEqual(KI.research_query(s,s['acquired_at']),'Mereo BioPharma Group')
            args=KI.event_search_arguments(s,s['acquired_at'])
            self.assertEqual(args['start_date'],'2026-09-11')
            self.assertEqual(args['end_date'],'2026-10-12')

    def test_exact_boundaries_are_accepted_in_both_modes(self):
        for manual in (False,True):
            snapshot=self.snapshot(manual)
            for date in ('2026-10-10T18:00:00Z','2026-10-11T18:00:00Z'):
                result=KI.r1_research_sources(self.raw(date),snapshot['acquired_at'],snapshot)
                self.assertEqual(len(result['sources']),1)

    def test_source_older_than_seven_days_is_background_in_month_window(self):
        s=self.snapshot()
        r=KI.r1_research_sources(self.raw('2026-09-24T18:54:00Z'),s['acquired_at'],s)
        self.assertEqual(r['sources'][0]['scope'],'background')

    def test_old_and_future_dates_are_not_used_as_background(self):
        for date in ('2024-10-10T20:00:00Z','2026-09-01T18:54:00Z','2026-10-11T18:00:01Z'):
            snapshot=self.snapshot(True)
            result=KI.r1_research_sources(self.raw(date),snapshot['acquired_at'],snapshot)
            self.assertEqual(result['sources'],[])

    def test_same_day_without_time_cannot_prove_publication_before_cutoff(self):
        s=self.snapshot(True)
        r=KI.r1_research_sources(self.raw('2026-10-11'),s['acquired_at'],s)
        self.assertEqual(r['sources'],[])
        self.assertEqual(r['date_unverified_count'],1)

    def test_empty_recent_excerpt_is_still_rejected(self):
        snapshot=self.snapshot(True);raw=self.raw('2026-10-11T12:00:00Z')
        raw['results'][0]['content']=''
        result=KI.r1_research_sources(raw,snapshot['acquired_at'],snapshot)
        self.assertEqual(result['sources'],[])
        self.assertEqual(result['excluded'],1)



class IdentityAndPartialRiskContracts(unittest.TestCase):
    def test_legal_suffix_variants(self):
        for suffix in ('Spólka Akcyjna','Spółka Akcyjna','Spolka Akcyjna','S.A.','SA'):
            self.assertEqual(KI.issuer_name('4Mobility '+suffix),'4Mobility')

    def result(self,title,content):
        return {'url':'https://example.org/report','title':title,'content':content,
                'published_date':'2026-10-11T12:00:00Z'}

    def snapshot(self):
        return {'ticker':'4MB.WA','company_name':'4Mobility Spólka Akcyjna',
                'acquired_at':'2026-10-11T18:00:00Z'}

    def test_named_title_with_substantive_report_is_accepted(self):
        result=self.result('4Mobility SA - Raport kwartalny','Przychody wzrosły względem poprzedniego okresu.')
        context=KI.normalize_tavily_context({'results':[result]},self.snapshot(),1,True,True)
        self.assertEqual(len(context['sources']),1)

    def test_unrelated_title_with_mere_mention_is_rejected(self):
        result=self.result('Rynek motoryzacyjny','Inne przedsiębiorstwo konkuruje z 4Mobility SA.')
        with self.assertRaises(ValueError):KI.issuer_source_match(result,self.snapshot(),True)

    def test_timestamp_only_text_is_rejected_even_with_named_title(self):
        result=self.result('4Mobility SA - Raport kwartalny','Aktualizacja: 11.10.2026 12:00 Publikacja: 11.10.2026 12:00')
        context=KI.normalize_tavily_context({'results':[result]},self.snapshot(),1,True,True)
        self.assertEqual(context['sources'],[])

    def test_partial_risk_retains_quote_uncertainty(self):
        risk=KI.opportunity_risk({'price':100.,'ohlc':{'high':101.},'spread':{'spread_pct':1.1}})
        self.assertEqual(risk['checked_criteria'],2)
        self.assertIn('Ocena częściowa',risk['label'])
        self.assertFalse(risk['complete'])
        self.assertIn('Potwierdzony czas aktualizacji bid/ask',risk['missing'])

    def test_no_metrics_is_not_low_risk(self):
        risk=KI.opportunity_risk({})
        self.assertEqual(risk['checked_criteria'],0)
        self.assertEqual(risk['label'],'Brak danych do oceny ryzyka')

    def test_elevated_risk_still_wins_over_missing_data(self):
        for snap in ({'spread':{'spread_pct':2.}}, {'price':98.,'ohlc':{'high':100.}}):
            risk=KI.opportunity_risk(snap)
            self.assertEqual(risk['label'],'Ryzyko podwyższone')
            self.assertTrue(risk['reasons'])

if __name__=='__main__':
    unittest.main()
